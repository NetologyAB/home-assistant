const STATUS_LABELS = {
  success: "Success",
  failure: "Failure",
  cancelled: "Cancelled",
  timed_out: "Timed out",
  in_progress: "In progress",
  queued: "Queued",
  requested: "Requested",
};

const STATUS_ICONS = {
  success: "mdi:check-circle",
  failure: "mdi:close-circle",
  cancelled: "mdi:close-circle",
  timed_out: "mdi:close-circle",
  in_progress: "mdi:progress-clock",
  queued: "mdi:progress-clock",
  requested: "mdi:progress-clock",
};

const EMPTY_MESSAGE = "No Workflow Activity";

const TEMPLATE = document.createElement("template");
TEMPLATE.innerHTML = `
  <style>
    :host {
      display: block;
      color: var(--primary-text-color);
      padding: 16px;
      box-sizing: border-box;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 1.5rem;
    }

    p.description {
      margin: 0 0 16px;
      color: var(--secondary-text-color);
    }

    button.refresh {
      border: none;
      border-radius: var(--control-border-radius, 8px);
      padding: 6px 14px;
      background-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
      font: inherit;
      cursor: pointer;
      margin-bottom: 16px;
    }

    button.refresh:hover {
      filter: brightness(1.05);
    }

    .repo-grid {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }

    article.repo-card {
      background: var(--card-background-color, #fff);
      border-radius: var(--ha-card-border-radius, 12px);
      box-shadow: var(
        --ha-card-box-shadow,
        0 2px 4px 0 rgba(0, 0, 0, 0.16)
      );
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .repo-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
    }

    .repo-header h2 {
      margin: 0;
      font-size: 1.1rem;
    }

    .repo-header a {
      font-size: 0.9rem;
      color: var(--primary-color);
      text-decoration: none;
    }

    .repo-header a:hover {
      text-decoration: underline;
    }

    details.status {
      border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      border-radius: 12px;
      padding: 0 12px;
    }

    details.status summary {
      list-style: none;
      display: flex;
      gap: 8px;
      align-items: center;
      cursor: pointer;
      padding: 12px 0;
    }

    details.status summary::-webkit-details-marker {
      display: none;
    }

    .status-label {
      display: inline-flex;
      gap: 6px;
      align-items: center;
      background: var(--chip-background-color, rgba(0, 0, 0, 0.05));
      padding: 4px 10px;
      border-radius: 999px;
      font-weight: 600;
      text-transform: capitalize;
    }

    .status-label ha-icon {
      --mdc-icon-size: 20px;
      color: currentColor;
    }

    .status-label.success {
      color: var(--success-color, #0f9d58);
    }

    .status-label.failure,
    .status-label.cancelled,
    .status-label.timed_out {
      color: var(--error-color);
    }

    .status-label.in_progress,
    .status-label.queued,
    .status-label.requested {
      color: var(--warning-color, #f57c00);
    }

    .runs {
      padding-bottom: 12px;
    }

    .runs p.empty {
      margin: 0 0 8px;
      color: var(--secondary-text-color);
    }

    details.run {
      border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      padding: 8px 0;
    }

    details.run summary {
      list-style: none;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      cursor: pointer;
    }

    details.run summary::-webkit-details-marker {
      display: none;
    }

    .run-title {
      font-weight: 600;
    }

    .run-status {
      text-transform: capitalize;
      font-size: 0.85rem;
      color: var(--secondary-text-color);
    }

    .run-body {
      margin-top: 6px;
      display: grid;
      gap: 4px;
      font-size: 0.9rem;
    }

    .run-body span {
      color: var(--secondary-text-color);
    }

    .run-body a {
      color: var(--primary-color);
      text-decoration: none;
    }

    .run-body a:hover {
      text-decoration: underline;
    }
  </style>
  <h1>Workflow Activity</h1>
  <p class="description">
    View the latest GitHub Actions runs that Home Assistant has cached. These
    results reuse the sensor data so opening this panel never triggers an API
    call.
  </p>
  <button class="refresh" type="button">Refresh data</button>
  <div class="repo-grid" id="repoGrid"></div>
`;

function statusLabel(status) {
  return STATUS_LABELS[status] || status || EMPTY_MESSAGE;
}

function statusIcon(status) {
  return STATUS_ICONS[status] || "mdi:source-branch";
}

function runState(run) {
  if (!run) {
    return "unknown";
  }
  if (run.conclusion && run.conclusion !== "unknown") {
    return run.conclusion;
  }
  return run.status || "unknown";
}

function formatDate(text) {
  if (!text || text === "unknown") {
    return "Unknown";
  }
  const value = new Date(text);
  if (Number.isNaN(value.getTime())) {
    return text;
  }
  return value.toLocaleString();
}

function buildRun(repo, run) {
  const details = document.createElement("details");
  details.className = "run";

  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.className = "run-title";
  title.textContent = run.title;
  summary.appendChild(title);

  const state = runState(run);
  const stateLabel = document.createElement("span");
  stateLabel.className = "run-status";
  stateLabel.textContent = statusLabel(state);
  summary.appendChild(stateLabel);

  details.appendChild(summary);

  const body = document.createElement("div");
  body.className = "run-body";

  const branch = document.createElement("span");
  branch.textContent = `Branch: ${run.head_branch}`;
  body.appendChild(branch);

  const event = document.createElement("span");
  event.textContent = `Event: ${run.event}`;
  body.appendChild(event);

  const updated = document.createElement("span");
  updated.textContent = `Updated: ${formatDate(run.updated_at)}`;
  body.appendChild(updated);

  const link = document.createElement("a");
  link.href = run.url && run.url !== "unknown" ? run.url : repo.actions_url;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = "Open on GitHub";
  body.appendChild(link);

  details.appendChild(body);
  return details;
}

function buildRepoCard(repo) {
  const card = document.createElement("article");
  card.className = "repo-card";

  const header = document.createElement("div");
  header.className = "repo-header";

  const title = document.createElement("h2");
  title.textContent = repo.display_name || repo.repository;
  header.appendChild(title);

  const actionsLink = document.createElement("a");
  actionsLink.href = repo.actions_url;
  actionsLink.target = "_blank";
  actionsLink.rel = "noreferrer";
  actionsLink.textContent = "Open workflow";
  header.appendChild(actionsLink);

  card.appendChild(header);

  const details = document.createElement("details");
  details.className = "status";

  const summary = document.createElement("summary");
  const label = document.createElement("span");
  const status = repo.latest_status || "unknown";
  label.className = `status-label ${status}`;

  const icon = document.createElement("ha-icon");
  icon.setAttribute("icon", statusIcon(status));
  label.appendChild(icon);

  const labelText = document.createElement("span");
  labelText.textContent = statusLabel(status);
  label.appendChild(labelText);

  summary.appendChild(label);

  const summaryHint = document.createElement("span");
  summaryHint.textContent = "Tap to view latest runs";
  summary.appendChild(summaryHint);

  details.appendChild(summary);

  const runsContainer = document.createElement("div");
  runsContainer.className = "runs";

  if (!repo.recent_runs || repo.recent_runs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = repo.status_message || EMPTY_MESSAGE;
    runsContainer.appendChild(empty);
  } else {
    repo.recent_runs.slice(0, 5).forEach((run) => {
      runsContainer.appendChild(buildRun(repo, run));
    });
  }

  details.appendChild(runsContainer);
  card.appendChild(details);
  return card;
}

class GitHubWorkflowPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.appendChild(TEMPLATE.content.cloneNode(true));
    this._refreshButton = this.shadowRoot.querySelector("button.refresh");
    this._grid = this.shadowRoot.getElementById("repoGrid");
    this._refreshButton?.addEventListener("click", () => this._fetchRuns());
  }

  set hass(value) {
    this._hass = value;
    if (!this._hasLoaded && value) {
      this._hasLoaded = true;
      this._fetchRuns();
    }
  }

  async _fetchRuns() {
    if (!this._hass || this._loading) {
      return;
    }
    this._loading = true;
    this._render();
    try {
      const result = await this._hass.callWS({ type: "github/workflow_runs" });
      this._repositories = result?.repositories || [];
      this._error = undefined;
    } catch (err) {
      this._error = err;
    }
    this._loading = false;
    this._render();
  }

  _render() {
    if (!this._grid) {
      return;
    }
    this._grid.innerHTML = "";

    if (this._loading) {
      const loading = document.createElement("p");
      loading.className = "description";
      loading.textContent = "Loading workflow runs…";
      this._grid.appendChild(loading);
      return;
    }

    if (this._error) {
      const error = document.createElement("p");
      error.className = "description";
      error.textContent = `Unable to load workflow runs: ${String(this._error)}`;
      this._grid.appendChild(error);
      return;
    }

    if (!this._repositories || this._repositories.length === 0) {
      const empty = document.createElement("p");
      empty.className = "description";
      empty.textContent = EMPTY_MESSAGE;
      this._grid.appendChild(empty);
      return;
    }

    this._repositories.forEach((repo) => {
      this._grid.appendChild(buildRepoCard(repo));
    });
  }
}

if (!customElements.get("github-workflow-panel")) {
  customElements.define("github-workflow-panel", GitHubWorkflowPanel);
}
