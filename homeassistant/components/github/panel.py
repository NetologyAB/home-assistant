"""Frontend helpers for GitHub workflow activity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .const import (
    DATA_FRONTEND,
    DATA_FRONTEND_PANEL_REGISTERED,
    DATA_FRONTEND_STATIC_REGISTERED,
    DATA_FRONTEND_WS_REGISTERED,
    DOMAIN,
    LOGGER,
    NO_WORKFLOW_ACTIVITY,
    WORKFLOW_PANEL_FRONTEND_URL_PATH,
    WORKFLOW_PANEL_MODULE_FILENAME,
    WORKFLOW_PANEL_SIDEBAR_ICON,
    WORKFLOW_PANEL_SIDEBAR_TITLE,
    WORKFLOW_PANEL_STATIC_URL,
    WORKFLOW_WEBSOCKET_TYPE,
)
from .coordinator import GitHubRepositoryRuntimeData, GitHubWorkflowUpdateCoordinator


_ASSET_PATH = Path(__file__).parent / "www"


def _workflow_state(latest_run: dict[str, str] | None) -> str:
    """Return the status string for a workflow run."""

    if not latest_run:
        return NO_WORKFLOW_ACTIVITY

    conclusion = latest_run.get("conclusion")
    if conclusion and conclusion != "unknown":
        return conclusion

    status = latest_run.get("status")
    return status or NO_WORKFLOW_ACTIVITY


@callback
def _copy_runs(coordinator: GitHubWorkflowUpdateCoordinator) -> list[dict[str, str]]:
    """Return a shallow copy of cached runs for serialization."""

    if not coordinator.data:
        return []

    return [dict(run) for run in coordinator.data.runs]


@callback
def _serialize_repository_payload(
    repository: str,
    runtime_data: GitHubRepositoryRuntimeData,
) -> dict[str, Any]:
    """Serialize workflow information for a repository."""

    workflow_coordinator = runtime_data.workflow_coordinator
    runs = _copy_runs(workflow_coordinator)
    latest_run = runs[0] if runs else None
    workflow_data = workflow_coordinator.data
    display_name = (
        runtime_data.repository_coordinator.data.get("full_name")
        if runtime_data.repository_coordinator.data
        else repository
    )

    payload: dict[str, Any] = {
        "repository": repository,
        "display_name": display_name or repository,
        "actions_url": f"https://github.com/{repository}/actions",
        "latest_status": _workflow_state(latest_run),
        "recent_runs": runs,
        "total_runs": workflow_data.total_count if workflow_data else 0,
    }

    if latest_run:
        payload["latest_run"] = latest_run
        payload["latest_run_url"] = latest_run.get("url")
        payload["latest_updated_at"] = latest_run.get("updated_at")
    else:
        payload["status_message"] = NO_WORKFLOW_ACTIVITY

    return payload


@callback
def _gather_workflow_payload(
    hass: HomeAssistant,
    repository_filter: str | None,
) -> list[dict[str, Any]]:
    """Collect workflow payloads for the websocket response."""

    repositories: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime_data: dict[str, GitHubRepositoryRuntimeData] | None = getattr(
            entry, "runtime_data", None
        )
        if not runtime_data:
            continue

        for repository, data in runtime_data.items():
            if repository_filter and repository_filter != repository:
                continue
            repositories.append(_serialize_repository_payload(repository, data))

    return repositories


@websocket_api.websocket_command(
    {
        vol.Required("type"): WORKFLOW_WEBSOCKET_TYPE,
        vol.Optional("repository"): cv.string,
    }
)
@callback
def websocket_get_workflow_runs(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Return cached workflow run activity for the UI panel."""

    repository_filter = msg.get("repository")
    connection.send_result(
        msg["id"],
        {
            "repositories": _gather_workflow_payload(
                hass,
                repository_filter,
            )
        },
    )


async def async_register_workflow_panel(hass: HomeAssistant) -> None:
    """Register the static assets, panel, and websocket command."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    frontend_data = domain_data.setdefault(DATA_FRONTEND, {})

    if not frontend_data.get(DATA_FRONTEND_WS_REGISTERED):
        websocket_api.async_register_command(hass, websocket_get_workflow_runs)
        frontend_data[DATA_FRONTEND_WS_REGISTERED] = True

    assets_ready = frontend_data.get(DATA_FRONTEND_STATIC_REGISTERED, False)
    if not assets_ready:
        if not _ASSET_PATH.exists():
            LOGGER.warning("GitHub panel assets directory missing: %s", _ASSET_PATH)
        else:
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        WORKFLOW_PANEL_STATIC_URL,
                        str(_ASSET_PATH),
                        cache_headers=False,
                    )
                ]
            )
            frontend_data[DATA_FRONTEND_STATIC_REGISTERED] = True
            assets_ready = True

    if assets_ready and not frontend_data.get(DATA_FRONTEND_PANEL_REGISTERED):
        await panel_custom.async_register_panel(
            hass=hass,
            frontend_url_path=WORKFLOW_PANEL_FRONTEND_URL_PATH,
            webcomponent_name="github-workflow-panel",
            sidebar_title=WORKFLOW_PANEL_SIDEBAR_TITLE,
            sidebar_icon=WORKFLOW_PANEL_SIDEBAR_ICON,
            module_url=f"{WORKFLOW_PANEL_STATIC_URL}/{WORKFLOW_PANEL_MODULE_FILENAME}",
            config_panel_domain=DOMAIN,
        )
        frontend_data[DATA_FRONTEND_PANEL_REGISTERED] = True
