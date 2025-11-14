"""Custom data update coordinator for the GitHub integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus
from typing import Any

from aiohttp import ClientError, ClientSession
from aiogithubapi import (
    GitHubAPI,
    GitHubConnectionException,
    GitHubEventModel,
    GitHubException,
    GitHubRatelimitException,
    GitHubResponseModel,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import SERVER_SOFTWARE
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    FALLBACK_UPDATE_INTERVAL,
    LOGGER,
    NO_WORKFLOW_ACTIVITY,
    REFRESH_EVENT_TYPES,
    WORKFLOW_RUNS_CACHE_SIZE,
)

GRAPHQL_REPOSITORY_QUERY = """
query ($owner: String!, $repository: String!) {
  rateLimit {
    cost
    remaining
  }
  repository(owner: $owner, name: $repository) {
    default_branch_ref: defaultBranchRef {
      commit: target {
        ... on Commit {
          message: messageHeadline
          url
          sha: oid
        }
      }
    }
    stargazers_count: stargazerCount
    forks_count: forkCount
    full_name: nameWithOwner
    id: databaseId
    watchers(first: 1) {
      total: totalCount
    }
    discussion: discussions(
      first: 1
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      total: totalCount
      discussions: nodes {
        title
        url
        number
      }
    }
    issue: issues(
      first: 1
      states: OPEN
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      total: totalCount
      issues: nodes {
        title
        url
        number
      }
    }
    pull_request: pullRequests(
      first: 1
      states: OPEN
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      total: totalCount
      pull_requests: nodes {
        title
        url
        number
      }
    }
    release: latestRelease {
      name
      url
      tag: tagName
    }
    refs(
      first: 1
      refPrefix: "refs/tags/"
      orderBy: {field: TAG_COMMIT_DATE, direction: DESC}
    ) {
      tags: nodes {
        name
        target {
          url: commitUrl
        }
      }
    }
  }
}
"""

@dataclass(slots=True)
class GitHubWorkflowData:
    """Coordinator data for workflow runs."""

    total_count: int
    runs: list[dict[str, str]]


@dataclass(slots=True)
class GitHubRepositoryRuntimeData:
    """Runtime data for a tracked repository."""

    repository_coordinator: "GitHubDataUpdateCoordinator"
    workflow_coordinator: "GitHubWorkflowUpdateCoordinator"


type GithubConfigEntry = ConfigEntry[dict[str, GitHubRepositoryRuntimeData]]


def _normalize_field(value: Any, *, lowercase: bool = False) -> str:
    """Normalize text values for workflow runs."""

    if value in (None, ""):
        return "unknown"

    text = str(value)
    return text.lower() if lowercase else text


def _format_workflow_run(run: dict[str, Any]) -> dict[str, str]:
    """Format a workflow run for the coordinator cache."""

    return {
        "id": _normalize_field(run.get("id")),
        "title": _normalize_field(run.get("display_title") or run.get("name")),
        "name": _normalize_field(run.get("name")),
        "status": _normalize_field(run.get("status"), lowercase=True),
        "conclusion": _normalize_field(run.get("conclusion"), lowercase=True),
        "url": run.get("html_url") or "unknown",
        "event": _normalize_field(run.get("event")),
        "updated_at": _normalize_field(run.get("updated_at")),
        "head_branch": _normalize_field(run.get("head_branch")),
        "run_number": _normalize_field(run.get("run_number")),
        "workflow_id": _normalize_field(run.get("workflow_id")),
    }


class GitHubDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for the GitHub integration."""

    config_entry: GithubConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GithubConfigEntry,
        client: GitHubAPI,
        repository: str,
    ) -> None:
        """Initialize GitHub data update coordinator base class."""
        self.repository = repository
        self._client = client
        self._last_response: GitHubResponseModel[dict[str, Any]] | None = None
        self._subscription_id: str | None = None
        self.data = {}

        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=repository,
            update_interval=FALLBACK_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> GitHubResponseModel[dict[str, Any]]:
        """Update data."""
        owner, repository = self.repository.split("/")
        try:
            response = await self._client.graphql(
                query=GRAPHQL_REPOSITORY_QUERY,
                variables={"owner": owner, "repository": repository},
            )
        except (GitHubConnectionException, GitHubRatelimitException) as exception:
            # These are expected and we dont log anything extra
            raise UpdateFailed(exception) from exception
        except GitHubException as exception:
            # These are unexpected and we log the trace to help with troubleshooting
            LOGGER.exception(exception)
            raise UpdateFailed(exception) from exception

        self._last_response = response
        return response.data["data"]["repository"]

    async def _handle_event(self, event: GitHubEventModel) -> None:
        """Handle an event."""
        if event.type in REFRESH_EVENT_TYPES:
            await self.async_request_refresh()

    @staticmethod
    async def _handle_error(error: GitHubException) -> None:
        """Handle an error."""
        LOGGER.error("An error occurred while processing new events - %s", error)

    async def subscribe(self) -> None:
        """Subscribe to repository events."""
        self._subscription_id = await self._client.repos.events.subscribe(
            self.repository,
            event_callback=self._handle_event,
            error_callback=self._handle_error,
        )
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.unsubscribe)

    def unsubscribe(self, *args: Any) -> None:
        """Unsubscribe to repository events."""
        self._client.repos.events.unsubscribe(subscription_id=self._subscription_id)


class GitHubWorkflowUpdateCoordinator(DataUpdateCoordinator[GitHubWorkflowData]):
    """Coordinator responsible for polling workflow runs."""

    config_entry: GithubConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        config_entry: GithubConfigEntry,
        repository: str,
        session: ClientSession,
        token: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize the workflow run coordinator."""

        self.repository = repository
        self._session = session
        self._token = token
        self._etag: str | None = None
        self._last_successful: GitHubWorkflowData | None = None
        self._url = f"https://api.github.com/repos/{repository}/actions/runs"

        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=f"{repository} workflow runs",
            update_interval=update_interval,
        )

    def _build_headers(self, include_etag: bool) -> dict[str, str]:
        """Return default headers for API calls."""

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": SERVER_SOFTWARE,
        }
        if include_etag and self._etag:
            headers["If-None-Match"] = self._etag
        return headers

    async def _async_update_data(self) -> GitHubWorkflowData:
        """Poll the GitHub Actions API for workflow runs."""

        params = {"per_page": WORKFLOW_RUNS_CACHE_SIZE, "page": 1}
        runs: list[dict[str, Any]] = []
        total_count = 0

        while len(runs) < WORKFLOW_RUNS_CACHE_SIZE:
            headers = self._build_headers(include_etag=params["page"] == 1)
            try:
                response = await self._session.get(
                    self._url,
                    headers=headers,
                    params=params,
                )
            except (ClientError, asyncio.TimeoutError) as exception:
                raise UpdateFailed(exception) from exception

            async with response:
                if response.status == HTTPStatus.NOT_MODIFIED:
                    if self.data is not None:
                        return self.data
                    if self._last_successful is not None:
                        return self._last_successful
                    return GitHubWorkflowData(total_count=0, runs=[])

                if response.status != HTTPStatus.OK:
                    text = await response.text()
                    raise UpdateFailed(
                        f"Error fetching workflow runs ({response.status}): {text}"
                    )

                payload = await response.json()
                page_runs = payload.get("workflow_runs") or []
                total_count = payload.get("total_count") or total_count

                if params["page"] == 1:
                    self._etag = response.headers.get("ETag") or response.headers.get(
                        "Etag"
                    )

                runs.extend(page_runs)
                if len(runs) >= WORKFLOW_RUNS_CACHE_SIZE or len(page_runs) < params["per_page"]:
                    break

                params["page"] += 1

        normalized_runs = [_format_workflow_run(run) for run in runs[:WORKFLOW_RUNS_CACHE_SIZE]]
        data = GitHubWorkflowData(
            total_count=total_count or len(normalized_runs),
            runs=normalized_runs,
        )
        self._last_successful = data
        return data
