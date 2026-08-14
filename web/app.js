const SCENARIO_LABELS = {
  silent_truncation: "Silent Truncation",
  infinite_tool_loop: "Infinite Tool Loop",
  mcp_schema_mismatch: "MCP Schema Mismatch",
  context_inflation: "Context Inflation",
};

class HarnessDashboard {
  constructor() {
    this.scenariosEl = document.getElementById("scenarios");
    this.formEl = document.getElementById("query-form");
    this.goalEl = document.getElementById("goal");
    this.runBtn = document.getElementById("run-btn");
    this.answerEl = document.getElementById("answer");
    this.toolCallsEl = document.getElementById("tool-calls");
    this.telemetryBar = document.getElementById("telemetry-bar");

    this.formEl.addEventListener("submit", (e) => this.onSubmit(e));
  }

  async init() {
    const state = await fetch("/api/scenarios").then((r) => r.json());
    this.renderScenarios(state);
  }

  renderScenarios(state) {
    this.scenariosEl.innerHTML = "";
    for (const [key, label] of Object.entries(SCENARIO_LABELS)) {
      const row = document.createElement("label");
      row.className = "toggle-row";
      row.innerHTML = `
        <input type="checkbox" data-flag="${key}" ${state[key] ? "checked" : ""} />
        <span>${label}</span>
      `;
      row.querySelector("input").addEventListener("change", (e) => this.onToggle(key, e.target.checked));
      this.scenariosEl.appendChild(row);
    }
  }

  async onToggle(flag, value) {
    const state = await fetch("/api/scenarios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [flag]: value }),
    }).then((r) => r.json());
    this.renderScenarios(state);
  }

  async onSubmit(event) {
    event.preventDefault();
    const goal = this.goalEl.value.trim();
    if (!goal) return;

    this.runBtn.disabled = true;
    this.runBtn.textContent = "Running…";
    this.answerEl.textContent = "Running…";
    this.toolCallsEl.innerHTML = "";

    try {
      const result = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      }).then((r) => r.json());
      this.renderResult(result);
    } catch (err) {
      this.answerEl.textContent = `Request failed: ${err}`;
    } finally {
      this.runBtn.disabled = false;
      this.runBtn.textContent = "Run";
    }
  }

  renderResult(result) {
    this.answerEl.textContent = result.answer ?? "(no answer)";

    this.toolCallsEl.innerHTML = "";
    for (const call of result.tool_calls || []) {
      const li = document.createElement("li");
      li.innerHTML = `<strong>${call.tool}</strong><pre>${call.output}</pre>`;
      this.toolCallsEl.appendChild(li);
    }

    document.getElementById("tel-latency").textContent = `latency: ${Math.round(result.latency_ms)}ms`;
    document.getElementById("tel-tokens").textContent =
      `tokens: ${result.prompt_tokens} in / ${result.completion_tokens} out`;
    document.getElementById("tel-iterations").textContent = `iterations: ${result.iterations}`;

    const traceLink = document.getElementById("tel-trace");
    if (result.sentry_trace_url) {
      traceLink.href = result.sentry_trace_url;
      traceLink.classList.remove("hidden");
    } else {
      traceLink.classList.add("hidden");
    }
    this.telemetryBar.classList.remove("hidden");
  }
}

document.addEventListener("DOMContentLoaded", () => new HarnessDashboard().init());
