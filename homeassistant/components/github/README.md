# GitHub Integration Enhancements

The GitHub integration now exposes recent GitHub Actions workflow activity for
tracked repositories. Two new sensors are available for each repository:

- **Workflow Summary** – Reports the total number of recorded workflow runs and
  exposes attributes for the latest run plus counts of successful and failed
  runs. The attributes also cache the five most recent workflow runs so the
  information can be viewed immediately in the UI.
- **Workflow Activity** – Shows the status or conclusion of the most recent
  workflow run and provides a dynamic icon (success, failure, or in-progress) so
  that activity can be seen at a glance. Its attributes also include the cached
  recent runs, each with a link to the GitHub UI.

## Update Interval Option

The options flow now includes **Workflow update interval (minutes)**. The
interval defaults to 15 minutes (minimum 5 minutes). Adjust this value if you
need faster or slower polling of the GitHub Actions API.

These additions reuse the existing OAuth token configured for the GitHub
integration and cache responses with ETag support to minimize API calls.

## Workflow Activity card

The GitHub integration page now exposes an **Activity** card alongside the
existing Service info, Automations, Scenes, Scripts, Sensors, and Diagnostics
cards. The card is available to Home Assistant admins and opens a focused
GitHub Workflows view that uses the cached workflow data from the two sensors so
opening it never triggers an additional API request. For every tracked
repository you will see:

- A status label (success, failure, or in-progress) that can be clicked to
  reveal the latest five workflow runs.
- Each run expands to show the event type, branch, last updated timestamp, and a
  button that opens the run directly on GitHub.
- A friendly "No Workflow Activity" message if a repository does not yet have
  any cached workflow history.

Use the **Refresh data** button in the panel if you want to request the latest
cached results from Home Assistant without waiting for the next polling cycle.

> This is a dedicated Workflow Activity card that only appears inside the
> GitHub integration. It does not modify or extend the default Activity UI
> shown for other integrations.
