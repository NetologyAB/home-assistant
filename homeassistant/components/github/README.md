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
