"""Custom data update coordinator for the GitHub integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    FALLBACK_UPDATE_INTERVAL,
    LOGGER,
    REFRESH_EVENT_TYPES,
    WORKFLOW_RUNS_UPDATE_INTERVAL,
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
class GitHubRepositoryRuntimeData:
    """Container for repository level coordinators."""

    repository_coordinator: GitHubDataUpdateCoordinator
    workflow_coordinator: "GitHubWorkflowRunsDataUpdateCoordinator"


type GithubConfigEntry = ConfigEntry[dict[str, GitHubRepositoryRuntimeData]]


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


WORKFLOW_RUNS_LIMIT = 5


class GitHubWorkflowRunsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator responsible for GitHub workflow runs."""

    config_entry: GithubConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        config_entry: GithubConfigEntry,
        session: ClientSession,
        token: str,
        repository: str,
    ) -> None:
        """Initialize the workflow runs coordinator."""
        self._session = session
        self._token = token
        self.repository = repository

        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=f"{repository} workflow runs",
            update_interval=WORKFLOW_RUNS_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch workflow run information."""
        owner, repository = self.repository.split("/")
        url = f"https://api.github.com/repos/{owner}/{repository}/actions/runs"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        params = {"per_page": WORKFLOW_RUNS_LIMIT}

        try:
            async with self._session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                payload: dict[str, Any] = await response.json()
        except (asyncio.TimeoutError, ClientError) as exception:
            raise UpdateFailed(exception) from exception

        runs = []
        for run in payload.get("workflow_runs", [])[:WORKFLOW_RUNS_LIMIT]:
            runs.append(
                {
                    "id": run.get("id"),
                    "name": run.get("name"),
                    "display_title": run.get("display_title"),
                    "branch": run.get("head_branch"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "html_url": run.get("html_url"),
                    "event": run.get("event"),
                    "run_number": run.get("run_number"),
                    "run_attempt": run.get("run_attempt"),
                }
            )

        return {
            "total_count": payload.get("total_count", 0),
            "workflow_runs": runs,
        }
