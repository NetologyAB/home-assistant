"""Test GitHub sensor."""

import json

import pytest

from homeassistant.components.github.const import (
    DOMAIN,
    FALLBACK_UPDATE_INTERVAL,
    NO_WORKFLOW_ACTIVITY,
    WORKFLOW_RUNS_CACHE_SIZE,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .common import TEST_REPOSITORY

from tests.common import MockConfigEntry, async_fire_time_changed, async_load_fixture
from tests.test_util.aiohttp import AiohttpClientMocker

TEST_SENSOR_ENTITY = "sensor.octocat_hello_world_latest_release"
WORKFLOW_SUMMARY_SENSOR = "sensor.octocat_hello_world_workflow_summary"
WORKFLOW_ACTIVITY_SENSOR = "sensor.octocat_hello_world_workflow_activity"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_sensor_updates_with_empty_release_array(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test the sensor updates by default GitHub sensors."""
    state = hass.states.get(TEST_SENSOR_ENTITY)
    assert state.state == "v1.0.0"

    response_json = json.loads(await async_load_fixture(hass, "graphql.json", DOMAIN))
    response_json["data"]["repository"]["release"] = None
    headers = json.loads(await async_load_fixture(hass, "base_headers.json", DOMAIN))

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"https://api.github.com/repos/{TEST_REPOSITORY}/events",
        json=[],
        headers=headers,
    )
    aioclient_mock.post(
        "https://api.github.com/graphql",
        json=response_json,
        headers=headers,
    )

    async_fire_time_changed(hass, dt_util.utcnow() + FALLBACK_UPDATE_INTERVAL)
    await hass.async_block_till_done()

    new_state = hass.states.get(TEST_SENSOR_ENTITY)
    assert new_state.state == "unavailable"


async def test_workflow_sensors_state_and_attributes(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Ensure workflow sensors expose cached run metadata."""

    summary = hass.states.get(WORKFLOW_SUMMARY_SENSOR)
    assert summary.state == "12"
    assert summary.attributes["success_runs"] == 2
    assert summary.attributes["failure_runs"] == 1
    assert len(summary.attributes["recent_runs"]) == WORKFLOW_RUNS_CACHE_SIZE

    activity = hass.states.get(WORKFLOW_ACTIVITY_SENSOR)
    assert activity.state == "success"
    assert activity.attributes["head_branch"] == "main"
    assert activity.attributes["latest_run_title"] == "CI #101"


async def test_workflow_sensors_reuse_etag(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Ensure workflow coordinator reuses cached data via ETag."""

    runtime = init_integration.runtime_data[TEST_REPOSITORY]
    coordinator = runtime.workflow_coordinator
    etag_headers = json.loads(await async_load_fixture(hass, "base_headers.json", DOMAIN))

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"https://api.github.com/repos/{TEST_REPOSITORY}/actions/runs",
        params={"per_page": WORKFLOW_RUNS_CACHE_SIZE, "page": 1},
        status=304,
        headers=etag_headers,
    )

    await coordinator.async_request_refresh()
    assert (
        aioclient_mock.mock_calls[-1][3]["If-None-Match"]
        == etag_headers["Etag"]
    )

    activity = hass.states.get(WORKFLOW_ACTIVITY_SENSOR)
    assert activity.state == "success"


async def test_workflow_sensors_pagination(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Ensure at least five runs are cached via pagination."""

    runtime = init_integration.runtime_data[TEST_REPOSITORY]
    coordinator = runtime.workflow_coordinator
    workflow_runs = json.loads(
        await async_load_fixture(hass, "workflow_runs.json", DOMAIN)
    )
    page_one = {
        "total_count": 6,
        "workflow_runs": workflow_runs["workflow_runs"][:3],
    }
    page_two = {
        "total_count": 6,
        "workflow_runs": workflow_runs["workflow_runs"][3:5]
        + [workflow_runs["workflow_runs"][1]],
    }

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"https://api.github.com/repos/{TEST_REPOSITORY}/actions/runs",
        params={"per_page": WORKFLOW_RUNS_CACHE_SIZE, "page": 1},
        json=page_one,
        headers={"Etag": "W/\"etag\""},
    )
    aioclient_mock.get(
        f"https://api.github.com/repos/{TEST_REPOSITORY}/actions/runs",
        params={"per_page": WORKFLOW_RUNS_CACHE_SIZE, "page": 2},
        json=page_two,
        headers={"Etag": "W/\"etag2\""},
    )

    await coordinator.async_request_refresh()
    assert len(coordinator.data.runs) == WORKFLOW_RUNS_CACHE_SIZE
    assert aioclient_mock.call_count == 2


async def test_workflow_sensors_handle_null_fields(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Ensure null workflow fields are surfaced as unknown."""

    runtime = init_integration.runtime_data[TEST_REPOSITORY]
    coordinator = runtime.workflow_coordinator
    null_payload = {
        "total_count": 1,
        "workflow_runs": [
            {
                "id": None,
                "name": None,
                "display_title": None,
                "status": None,
                "conclusion": None,
                "html_url": None,
                "event": None,
                "updated_at": None,
                "head_branch": None,
                "run_number": None,
            }
        ],
    }

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"https://api.github.com/repos/{TEST_REPOSITORY}/actions/runs",
        params={"per_page": WORKFLOW_RUNS_CACHE_SIZE, "page": 1},
        json=null_payload,
        headers={"Etag": "W/\"etag3\""},
    )

    await coordinator.async_request_refresh()
    activity = hass.states.get(WORKFLOW_ACTIVITY_SENSOR)
    assert activity.state == "unknown"
    assert activity.attributes["latest_run_title"] == "unknown"
    summary = hass.states.get(WORKFLOW_SUMMARY_SENSOR)
    assert summary.attributes["recent_runs"][0]["title"] == "unknown"


async def test_workflow_sensors_no_activity_message(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Show message when there are no workflow runs."""

    runtime = init_integration.runtime_data[TEST_REPOSITORY]
    coordinator = runtime.workflow_coordinator

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"https://api.github.com/repos/{TEST_REPOSITORY}/actions/runs",
        params={"per_page": WORKFLOW_RUNS_CACHE_SIZE, "page": 1},
        json={"total_count": 0, "workflow_runs": []},
        headers={"Etag": "W/\"etag4\""},
    )

    await coordinator.async_request_refresh()
    summary = hass.states.get(WORKFLOW_SUMMARY_SENSOR)
    assert summary.attributes["status_message"] == NO_WORKFLOW_ACTIVITY
    activity = hass.states.get(WORKFLOW_ACTIVITY_SENSOR)
    assert activity.state == NO_WORKFLOW_ACTIVITY
