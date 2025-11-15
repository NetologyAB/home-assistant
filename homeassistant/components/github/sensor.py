"""Sensor platform for the GitHub integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NO_WORKFLOW_ACTIVITY
from .coordinator import (
    GithubConfigEntry,
    GitHubDataUpdateCoordinator,
    GitHubRepositoryRuntimeData,
    GitHubWorkflowUpdateCoordinator,
)


@dataclass(frozen=True, kw_only=True)
class GitHubSensorEntityDescription(SensorEntityDescription):
    """Describes GitHub issue sensor entity."""

    value_fn: Callable[[dict[str, Any]], StateType]

    attr_fn: Callable[[dict[str, Any]], Mapping[str, Any] | None] = lambda data: None
    avabl_fn: Callable[[dict[str, Any]], bool] = lambda data: True


def _build_device_info(repository: str, name: str | None) -> DeviceInfo:
    """Return standard device info for a repository."""

    return DeviceInfo(
        identifiers={(DOMAIN, repository)},
        name=name or repository,
        manufacturer="GitHub",
        configuration_url=f"https://github.com/{repository}",
        entry_type=DeviceEntryType.SERVICE,
    )


SENSOR_DESCRIPTIONS: tuple[GitHubSensorEntityDescription, ...] = (
    GitHubSensorEntityDescription(
        key="discussions_count",
        translation_key="discussions_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["discussion"]["total"],
    ),
    GitHubSensorEntityDescription(
        key="stargazers_count",
        translation_key="stargazers_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["stargazers_count"],
    ),
    GitHubSensorEntityDescription(
        key="subscribers_count",
        translation_key="subscribers_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["watchers"]["total"],
    ),
    GitHubSensorEntityDescription(
        key="forks_count",
        translation_key="forks_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["forks_count"],
    ),
    GitHubSensorEntityDescription(
        key="issues_count",
        translation_key="issues_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["issue"]["total"],
    ),
    GitHubSensorEntityDescription(
        key="pulls_count",
        translation_key="pulls_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["pull_request"]["total"],
    ),
    GitHubSensorEntityDescription(
        key="latest_commit",
        translation_key="latest_commit",
        value_fn=lambda data: data["default_branch_ref"]["commit"]["message"][:255],
        attr_fn=lambda data: {
            "sha": data["default_branch_ref"]["commit"]["sha"],
            "url": data["default_branch_ref"]["commit"]["url"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_discussion",
        translation_key="latest_discussion",
        avabl_fn=lambda data: data["discussion"]["discussions"],
        value_fn=lambda data: data["discussion"]["discussions"][0]["title"][:255],
        attr_fn=lambda data: {
            "url": data["discussion"]["discussions"][0]["url"],
            "number": data["discussion"]["discussions"][0]["number"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_release",
        translation_key="latest_release",
        avabl_fn=lambda data: data["release"] is not None,
        value_fn=lambda data: data["release"]["name"][:255],
        attr_fn=lambda data: {
            "url": data["release"]["url"],
            "tag": data["release"]["tag"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_issue",
        translation_key="latest_issue",
        avabl_fn=lambda data: data["issue"]["issues"],
        value_fn=lambda data: data["issue"]["issues"][0]["title"][:255],
        attr_fn=lambda data: {
            "url": data["issue"]["issues"][0]["url"],
            "number": data["issue"]["issues"][0]["number"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_pull_request",
        translation_key="latest_pull_request",
        avabl_fn=lambda data: data["pull_request"]["pull_requests"],
        value_fn=lambda data: data["pull_request"]["pull_requests"][0]["title"][:255],
        attr_fn=lambda data: {
            "url": data["pull_request"]["pull_requests"][0]["url"],
            "number": data["pull_request"]["pull_requests"][0]["number"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_tag",
        translation_key="latest_tag",
        avabl_fn=lambda data: data["refs"]["tags"],
        value_fn=lambda data: data["refs"]["tags"][0]["name"][:255],
        attr_fn=lambda data: {
            "url": data["refs"]["tags"][0]["target"]["url"],
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GithubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up GitHub sensor based on a config entry."""
    repositories: dict[str, GitHubRepositoryRuntimeData] = entry.runtime_data
    entities: list[SensorEntity] = [
        GitHubSensorEntity(runtime.repository_coordinator, description)
        for description in SENSOR_DESCRIPTIONS
        for runtime in repositories.values()
    ]

    for runtime in repositories.values():
        repository_name = runtime.repository_coordinator.data.get("full_name")
        entities.extend(
            (
                GitHubWorkflowSummarySensor(
                    runtime.workflow_coordinator, repository_name
                ),
                GitHubWorkflowActivitySensor(
                    runtime.workflow_coordinator, repository_name
                ),
            )
        )

    async_add_entities(entities)


class GitHubSensorEntity(CoordinatorEntity[GitHubDataUpdateCoordinator], SensorEntity):
    """Defines a GitHub sensor entity."""

    _attr_attribution = "Data provided by the GitHub API"
    _attr_has_entity_name = True

    entity_description: GitHubSensorEntityDescription

    def __init__(
        self,
        coordinator: GitHubDataUpdateCoordinator,
        entity_description: GitHubSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)

        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.data.get('id')}_{entity_description.key}"

        self._attr_device_info = _build_device_info(
            coordinator.repository,
            coordinator.data.get("full_name"),
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.avabl_fn(self.coordinator.data)
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the extra state attributes."""
        return self.entity_description.attr_fn(self.coordinator.data)


class GitHubWorkflowSensorEntity(
    CoordinatorEntity[GitHubWorkflowUpdateCoordinator], SensorEntity
):
    """Shared behavior for workflow sensors."""

    _attr_attribution = "Data provided by the GitHub API"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GitHubWorkflowUpdateCoordinator,
        repository_name: str | None,
    ) -> None:
        """Initialize workflow sensor base."""
        super().__init__(coordinator)
        self._repository = coordinator.repository
        self._repository_name = repository_name or coordinator.repository
        self._actions_url = f"https://github.com/{self._repository}/actions"
        self._attr_device_info = _build_device_info(
            coordinator.repository,
            repository_name,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available and self.coordinator.data is not None

    def _latest_run(self) -> dict[str, str] | None:
        """Return the latest cached workflow run."""
        if self.coordinator.data and self.coordinator.data.runs:
            return self.coordinator.data.runs[0]
        return None

    def _recent_runs(self) -> list[dict[str, str]]:
        """Return cached workflow runs."""
        return self.coordinator.data.runs if self.coordinator.data else []

    def _recent_runs_payload(self) -> list[dict[str, str]]:
        """Return workflow run data formatted for attributes."""
        return [
            {
                "title": run["title"],
                "status": run["status"],
                "conclusion": run["conclusion"],
                "url": run["url"],
                "event": run["event"],
                "head_branch": run["head_branch"],
                "updated_at": run["updated_at"],
            }
            for run in self._recent_runs()
        ]

    @property
    def configuration_url(self) -> str | None:
        """Return a configuration URL that points to the workflow run."""
        latest = self._latest_run()
        if latest and latest.get("url") and latest["url"] != "unknown":
            return latest["url"]
        return self._actions_url


class GitHubWorkflowSummarySensor(GitHubWorkflowSensorEntity):
    """Summarize workflow run activity."""

    _attr_translation_key = "workflow_summary"

    def __init__(
        self,
        coordinator: GitHubWorkflowUpdateCoordinator,
        repository_name: str | None,
    ) -> None:
        """Initialize the workflow summary sensor."""
        super().__init__(coordinator, repository_name)
        self._attr_unique_id = f"{coordinator.repository}_workflow_summary"

    @property
    def native_value(self) -> StateType:
        """Return the total workflow run count."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.total_count

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return metadata about recent workflow activity."""
        latest = self._latest_run()
        runs = self._recent_runs()
        attrs: dict[str, Any] = {
            "success_runs": sum(
                1 for run in runs if run["conclusion"] == "success"
            ),
            "failure_runs": sum(
                1 for run in runs if run["conclusion"] == "failure"
            ),
            "recent_runs": self._recent_runs_payload(),
        }

        if latest:
            attrs.update(
                latest_run_title=latest["title"],
                latest_run_status=latest["status"],
                latest_run_conclusion=latest["conclusion"],
                latest_run_url=latest["url"],
            )
        else:
            attrs["status_message"] = NO_WORKFLOW_ACTIVITY

        if not runs:
            attrs.setdefault("status_message", NO_WORKFLOW_ACTIVITY)

        return attrs


class GitHubWorkflowActivitySensor(GitHubWorkflowSensorEntity):
    """Represent the latest workflow run state."""

    _attr_translation_key = "workflow_activity"

    def __init__(
        self,
        coordinator: GitHubWorkflowUpdateCoordinator,
        repository_name: str | None,
    ) -> None:
        """Initialize the workflow activity sensor."""
        super().__init__(coordinator, repository_name)
        self._attr_unique_id = f"{coordinator.repository}_workflow_activity"

    def _activity_state(self) -> str:
        """Return the textual representation of the workflow state."""
        latest = self._latest_run()
        if not latest:
            return NO_WORKFLOW_ACTIVITY
        if latest["conclusion"] != "unknown":
            return latest["conclusion"]
        return latest["status"]

    @property
    def native_value(self) -> StateType:
        """Return the status of the most recent workflow run."""
        return self._activity_state()

    @property
    def icon(self) -> str:
        """Return a dynamic icon based on workflow status."""
        state = self._activity_state()
        if state == "success":
            return "mdi:check-circle"
        if state in {"failure", "cancelled", "timed_out"}:
            return "mdi:close-circle"
        if state in {"in_progress", "queued", "requested"}:
            return "mdi:progress-clock"
        return "mdi:source-branch"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the extra state attributes."""
        latest = self._latest_run()
        attrs: dict[str, Any] = {
            "recent_runs": self._recent_runs_payload(),
        }

        if latest:
            attrs.update(
                latest_run_title=latest["title"],
                latest_run_status=latest["status"],
                latest_run_conclusion=latest["conclusion"],
                latest_run_url=latest["url"],
                event=latest["event"],
                head_branch=latest["head_branch"],
                updated_at=latest["updated_at"],
            )
        else:
            attrs["status_message"] = NO_WORKFLOW_ACTIVITY

        return attrs
