"""The GitHub integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from aiogithubapi import GitHubAPI

from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import (
    SERVER_SOFTWARE,
    async_get_clientsession,
)
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_REPOSITORIES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_WORKFLOW_UPDATE_INTERVAL,
    DEFAULT_WORKFLOW_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    LOGGER,
    MINIMUM_WORKFLOW_UPDATE_INTERVAL_MINUTES,
)
from .coordinator import (
    GithubConfigEntry,
    GitHubDataUpdateCoordinator,
    GitHubRepositoryRuntimeData,
    GitHubWorkflowUpdateCoordinator,
)
from .panel import async_register_workflow_panel

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the GitHub integration."""
    await async_register_workflow_panel(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GithubConfigEntry) -> bool:
    """Set up GitHub from a config entry."""
    session = async_get_clientsession(hass)
    client = GitHubAPI(
        token=entry.data[CONF_ACCESS_TOKEN],
        session=session,
        client_name=SERVER_SOFTWARE,
    )

    repositories: list[str] = entry.options[CONF_REPOSITORIES]
    update_interval_minutes = entry.options.get(
        CONF_UPDATE_INTERVAL, DEFAULT_WORKFLOW_UPDATE_INTERVAL_MINUTES
    )
    update_interval_minutes = max(
        update_interval_minutes, MINIMUM_WORKFLOW_UPDATE_INTERVAL_MINUTES
    )
    update_interval = (
        DEFAULT_WORKFLOW_UPDATE_INTERVAL
        if update_interval_minutes == DEFAULT_WORKFLOW_UPDATE_INTERVAL_MINUTES
        else timedelta(minutes=update_interval_minutes)
    )

    entry.runtime_data = {}
    for repository in repositories:
        coordinator = GitHubDataUpdateCoordinator(
            hass=hass,
            config_entry=entry,
            client=client,
            repository=repository,
        )

        workflow_coordinator = GitHubWorkflowUpdateCoordinator(
            hass=hass,
            config_entry=entry,
            repository=repository,
            session=session,
            token=entry.data[CONF_ACCESS_TOKEN],
            update_interval=update_interval,
        )

        await asyncio.gather(
            coordinator.async_config_entry_first_refresh(),
            workflow_coordinator.async_config_entry_first_refresh(),
        )

        if not entry.pref_disable_polling:
            await coordinator.subscribe()

        entry.runtime_data[repository] = GitHubRepositoryRuntimeData(
            repository_coordinator=coordinator,
            workflow_coordinator=workflow_coordinator,
        )

    async_cleanup_device_registry(hass=hass, entry=entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


@callback
def async_cleanup_device_registry(
    hass: HomeAssistant,
    entry: GithubConfigEntry,
) -> None:
    """Remove entries form device registry if we no longer track the repository."""
    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(
        registry=device_registry,
        config_entry_id=entry.entry_id,
    )
    for device in devices:
        for item in device.identifiers:
            if item[0] == DOMAIN and item[1] not in entry.options[CONF_REPOSITORIES]:
                LOGGER.debug(
                    (
                        "Unlinking device %s for untracked repository %s from config"
                        " entry %s"
                    ),
                    device.id,
                    item[1],
                    entry.entry_id,
                )
                device_registry.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
                )
                break


async def async_unload_entry(hass: HomeAssistant, entry: GithubConfigEntry) -> bool:
    """Unload a config entry."""
    repositories = entry.runtime_data
    for runtime_data in repositories.values():
        runtime_data.repository_coordinator.unsubscribe()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
