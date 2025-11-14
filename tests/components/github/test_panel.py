"""Tests for the GitHub workflow panel websocket."""

from __future__ import annotations

import pytest

from homeassistant.components.github.const import (
    NO_WORKFLOW_ACTIVITY,
    WORKFLOW_RUNS_CACHE_SIZE,
    WORKFLOW_WEBSOCKET_TYPE,
)
from homeassistant.components.github.coordinator import GitHubWorkflowData
from homeassistant.core import HomeAssistant

from .common import TEST_REPOSITORY

from tests.common import MockConfigEntry
from tests.typing import WebSocketGenerator


@pytest.mark.usefixtures("init_integration")
async def test_workflow_runs_websocket(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Verify cached workflow data is returned over the websocket."""

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": WORKFLOW_WEBSOCKET_TYPE})
    response = await client.receive_json()

    assert response["success"]
    payload = response["result"]["repositories"]
    assert len(payload) == 1

    repository = payload[0]
    assert repository["repository"] == TEST_REPOSITORY
    assert repository["latest_status"] == "success"
    assert len(repository["recent_runs"]) == WORKFLOW_RUNS_CACHE_SIZE
    assert repository["recent_runs"][0]["title"] == "CI #101"


@pytest.mark.usefixtures("init_integration")
async def test_workflow_runs_websocket_filter(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Verify repository filters are respected."""

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": WORKFLOW_WEBSOCKET_TYPE, "repository": "octocat/unknown"}
    )
    response = await client.receive_json()

    assert response["success"]
    assert response["result"]["repositories"] == []


async def test_workflow_runs_websocket_handles_empty_data(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """Return a helpful message when no workflow runs are cached."""

    runtime = init_integration.runtime_data[TEST_REPOSITORY]
    runtime.workflow_coordinator.data = GitHubWorkflowData(total_count=0, runs=[])

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": WORKFLOW_WEBSOCKET_TYPE})
    response = await client.receive_json()

    assert response["success"]
    repositories = response["result"]["repositories"]
    assert len(repositories) == 1
    assert repositories[0]["status_message"] == NO_WORKFLOW_ACTIVITY
