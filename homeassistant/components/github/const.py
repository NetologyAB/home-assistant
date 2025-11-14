"""Constants for the GitHub integration."""

from __future__ import annotations

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "github"

CLIENT_ID = "1440cafcc86e3ea5d6a2"

DEFAULT_REPOSITORIES = ["home-assistant/core", "esphome/esphome"]
FALLBACK_UPDATE_INTERVAL = timedelta(hours=1, minutes=30)

CONF_REPOSITORIES = "repositories"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_WORKFLOW_UPDATE_INTERVAL_MINUTES = 15
MINIMUM_WORKFLOW_UPDATE_INTERVAL_MINUTES = 5

DEFAULT_WORKFLOW_UPDATE_INTERVAL = timedelta(
    minutes=DEFAULT_WORKFLOW_UPDATE_INTERVAL_MINUTES
)
MINIMUM_WORKFLOW_UPDATE_INTERVAL = timedelta(
    minutes=MINIMUM_WORKFLOW_UPDATE_INTERVAL_MINUTES
)

WORKFLOW_RUNS_CACHE_SIZE = 5
NO_WORKFLOW_ACTIVITY = "No Workflow Activity"

WORKFLOW_PANEL_FRONTEND_URL_PATH = "github-workflows"
WORKFLOW_PANEL_MODULE_FILENAME = "github-workflows-panel.js"
WORKFLOW_PANEL_STATIC_URL = "/github-workflows-static"
WORKFLOW_WEBSOCKET_TYPE = f"{DOMAIN}/workflow_runs"

DATA_FRONTEND = "frontend"
DATA_FRONTEND_PANEL_REGISTERED = "panel_registered"
DATA_FRONTEND_STATIC_REGISTERED = "static_registered"
DATA_FRONTEND_WS_REGISTERED = "websocket_registered"


REFRESH_EVENT_TYPES = (
    "CreateEvent",
    "ForkEvent",
    "IssuesEvent",
    "PullRequestEvent",
    "PushEvent",
    "ReleaseEvent",
    "WatchEvent",
)
