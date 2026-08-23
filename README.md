# sentry-agent-harness

A **product**, not a one-off demo: reusable Sentry AI-agent instrumentation, in Python and
TypeScript, for getting **Sentry AI Monitoring** and **Seer Root Cause Analysis** working against
a real agentic coding tool. Two integrations ship today; the instrumentation itself isn't tied to
either.

Every codebase in this repo follows the same split, in folders named exactly this:

- **`product/`** — the general, reusable instrumentation. Sentry init, span/breadcrumb helpers,
  provider plumbing. Would still make sense with every scenario/bug-toggle concept deleted.
- **`experiments/`** — the scenario lab: a deliberately toggleable bug deck built *on top of* the
  product code, used to demonstrate what Sentry/Seer actually surfaces when an agent misbehaves.

| | `agent_harness/` (Python) | `cline/` (TypeScript) |
|---|---|---|
| What it is | A small agent we wrote from scratch: LangGraph loop, FastMCP tools, FastAPI dashboard | A real fork of [Cline](https://github.com/cline/cline), the open-source AI coding CLI, instrumented in place |
| Why it exists | Fast to run, fully self-contained, good for iterating on the failure-mode ideas themselves | The stronger demo: real agent code, real MCP protocol traffic, a genuine "confidently wrong agent" story instead of a toy one |
| `product/` | `config.py`, `telemetry/`, `llm/` — Settings, Sentry init/span helpers, multi-provider LLM factory | `instrumentation/product/` — `telemetry.ts` (Sentry init + the event→span-tree builder), `event-utils.ts` |
| `experiments/` | `scenarios/`, `tools/`, `mcp/`, `agent/`, `api/`, `cli.py` — the bug toggle deck and the demo app driving it | `instrumentation/experiments/scenarios.ts` — the same four scenarios, injected via Cline's own hooks |

Both expose the same four toggleable failure modes — silent tool-output truncation, infinite
tool-call loop, MCP schema-mismatch, context/token inflation — so the same Sentry/Seer story can
be told against either one, and either `product/` layer could be lifted into a different agent
entirely without dragging the scenario code along.

---

## Part 1 — Python harness (`agent_harness/`)

```
agent_harness/
  product/                # general — reusable regardless of which agent/demo uses it
    config.py              Settings (env-driven)
    telemetry/              Sentry init + span/breadcrumb helpers
    llm/                     LLMProviderFactory (anthropic | openai | ollama | together)
  experiments/             # the scenario-lab demo app, built on top of product/
    scenarios/               FailureEngine — the bug toggle deck
    tools/                    read_file_contents / query_database / execute_bash
    mcp/                      FastMCP server + LangChain-facing MCP client
    agent/                    SystemPromptRegistry + AgentHarness (LangGraph state machine)
    api/                      FastAPI app, /api/query, /api/scenarios
    cli.py                    run / repl / serve
web/                      static dashboard (no build step)
```

### Setup

```bash
uv sync
cp .env.example .env
# edit .env: set SENTRY_DSN, LLM_PROVIDER, and that provider's API key
```

### Run

```bash
# web dashboard (query box, scenario toggles, telemetry bar)
uv run agent-harness serve
# -> http://localhost:8000

# one-shot CLI query
uv run agent-harness run "Look up Ada Lovelace's orders in the database"

# interactive REPL
uv run agent-harness repl

# toggle a scenario for a single CLI run
uv run agent-harness run "read agent_harness/product/config.py" --silent-truncation
```

### Scenario deck

| Flag | Effect |
|---|---|
| `silent_truncation` | Tool output over `TRUNCATION_LIMIT_CHARS` is silently cut, no exception — the LLM answers from partial context. |
| `infinite_tool_loop` | Disables the "empty tool result → stop" boundary; the agent keeps retrying until `MAX_ITERATIONS`. |
| `mcp_schema_mismatch` | Corrupts an outgoing MCP tool argument's type, tripping FastMCP's schema validation into an unhandled `ValidationError`. |
| `context_inflation` | Skips normal conversation trimming so raw tool output accumulates every turn instead of being bounded. |

### MCP transport

Defaults to `stdio` (the harness spawns `python -m agent_harness.experiments.mcp.server` per
query). For a cross-process trace, set `MCP_TRANSPORT=sse` in `.env`, run the server standalone
(`uv run python -m agent_harness.experiments.mcp.server`), and point `MCP_SSE_URL` at it.

Its MCP server (`agent_harness/experiments/mcp/server.py`) is also reused as the MCP target for
the Cline harness below — one seeded SQLite database, one set of tools, two different agents
driving them.

---

## Part 2 — Cline harness (`cline/`)

A local, unmodified-elsewhere clone of `cline/cline` with Sentry wired in through its own public
extension seams:

```
apps/cli/src/instrumentation/
  product/
    telemetry.ts        initSentryInstrumentation() + createTelemetryHooks() — the Sentry
                         span-tree builder (run -> turn -> llm_call / tool.<name>) + breadcrumbs,
                         no scenario awareness
    event-utils.ts        runKey/turnKey/firstToolResultPart/extractMcpText — generic
                         AgentRuntimeEvent helpers shared by both layers
  experiments/
    scenarios.ts          ScenarioFlags, readScenarioFlagsFromEnv, createScenarioHooks — the same
                         four failure modes, injected via beforeModel/beforeTool/afterTool
  index.ts                 createSentryHooks() = mergeAgentHooks([telemetry, scenarios])
```

Composed into the three existing call sites: `apps/cli/src/index.ts` (init),
`apps/cli/src/runtime/run-agent.ts` and `apps/cli/src/runtime/interactive/session-runtime.ts`
(hooks merged alongside Cline's own via `mergeAgentHooks`).

### Setup

Requires `bun` 1.3.13 and `node` 22 (both pinned in `cline/.tool-versions`; `asdf install` picks
them up if you use asdf).

```bash
cd cline
bun install
bun --conditions=development run build:sdk   # build the SDK workspace packages once
```

### Model access

Cline resolves which provider/model to use, in order: an explicit `-P <id> -m <model>` flag on
the current run, then whatever provider was last used (persisted to
`~/.cline/data/settings/providers.json`), then `cline` (Cline's own hosted account proxy) as the
final fallback.

Register a provider once with `cline auth`:

```bash
# local, no key needed
bun --conditions=development apps/cli/src/index.ts auth ollama -m llama3.1:8b

# any hosted provider
bun --conditions=development apps/cli/src/index.ts auth anthropic -k sk-ant-... -m claude-sonnet-5
bun --conditions=development apps/cli/src/index.ts auth openai -k sk-... -m gpt-5
```

Passing `-P`/`-m` directly on a `cline` run (as in the examples throughout this section) also
persists that provider as the new default for next time — a separate `auth` step isn't strictly
required for Ollama.

#### Which local model to use

All four scenarios below hinge on the model actually invoking tool calls correctly, which rules
out most small local models. Of the models we tested against:

| Model | Verdict |
|---|---|
| `llama3.1:8b` | **Use this.** Reliable structured tool calls across all four scenarios. Slow — often 90–300s on a cold load, and Cline's own Ollama timeout is a hard 300s ceiling, so an occasional cold-start run will time out and just needs a retry. |
| `qwen2.5-coder:1.5b` / `qwen2.5:1.5b` | Fast, but unreliable — caught hallucinating a full file's contents instead of calling the read tool at all. Fine for a non-tool sanity check only. |
| `gemma2:2b`, `phi3.5` | Not verified against these scenarios; both have weak/inconsistent native function-calling support through Ollama generally. |

#### Best scenario for a live local demo

Ranked by "compelling story ÷ wall-clock time" — local inference, not scenario logic, is the
bottleneck:

1. **`CLINE_SENTRY_MCP_SCHEMA_MISMATCH=1`** — best pick. Fast (Cline's own "max consecutive
   mistakes" safety net aborts after ~3 identical failures, so it's done in a handful of short
   tool-call round-trips) and the most visually dramatic: a real `ValidationError`, the model
   repeatedly retrying the same broken call, then a hard abort.
2. **`CLINE_SENTRY_SILENT_TRUNCATION=1`** — best "wrong answer" story. Only 2 iterations, and the
   sharpest payoff: the model confidently invents content that was never in the truncated file.
3. `CLINE_SENTRY_INFINITE_TOOL_LOOP=1` — narratively great (8 iterations vs. 2 baseline, ~4.4x
   token usage) but each iteration is a full local LLM round-trip, so live it can run 10–20+
   minutes. Better pre-recorded or run against a faster/hosted model.
4. `CLINE_SENTRY_CONTEXT_INFLATION=1` — weakest alone; it's breadcrumb-only observability with no
   distinct failure behavior to watch happen. Pair it with one of the others.

#### Example use case: investigate a billing discrepancy

The strongest demo isn't "call this tool" — it's a real support ticket that happens to need every
Cline feature to resolve, so each scenario surfaces as something that plausibly *actually
happened* mid-investigation rather than a flag flip. The fixtures for this live in
[`demo-billing-app/`](./demo-billing-app) and the `invoices` table seeded by
`agent_harness/experiments/tools/database.py`.

**The ticket** (give this to Cline verbatim as the prompt):

> A customer (grace@example.com) says her July invoice — she thinks the ID is `INV-1034` — is
> higher than expected. Look into the `sentry-harness` database and the billing app under
> `demo-billing-app/`, figure out what's wrong, and explain the root cause.

**What actually happens, and why:**

1. Cline queries `invoices` for `INV-1034` — a typo in the ticket for the real ID `INV-1043` — and
   gets an empty result. With `CLINE_SENTRY_INFINITE_TOOL_LOOP=1` this is exactly where the
   `beforeModel` nudge fires, forcing reformulation instead of giving up.
2. Querying by `grace@example.com` instead finds two real invoices: `INV-1002` (June, `$192.50`,
   correct) and `INV-1043` (July, `$195.00`) — the same customer, same discount, different period.
3. Reading `demo-billing-app/billing_engine.py` shows the actual calculation code; reading
   `demo-billing-app/PRICING.md` shows the *documented* contract — they disagree on whether tax
   applies before or after the discount.
4. Reading `demo-billing-app/audit.log` (4,258 chars) should reveal the smoking gun — a
   `billing-engine version=2.0.0` deploy on `2026-07-01` whose changelog directly admits the
   change. With `CLINE_SENTRY_SILENT_TRUNCATION=1`, that entry sits at character 2,311 — past the
   2,000-char cutoff — so Cline never sees it and has to guess at timing instead of citing the
   deploy that caused it.
5. Root cause, if nothing was truncated: the July 1 deploy switched tax calculation to the
   pre-discount subtotal, contradicting `PRICING.md`'s "discounts apply before tax" contract —
   `(subtotal - discount) * (1 + tax)` (correct, `$192.50`) vs. `subtotal * (1 + tax) - discount`
   (what the code now does, `$195.00`).

`CLINE_SENTRY_MCP_SCHEMA_MISMATCH=1` fits naturally too — run it while Cline is issuing any of the
`query_database` calls above (e.g. limiting results while scanning invoices) to show a tool
contract breaking mid-investigation rather than on the first call.

### Point it at an MCP server

Any MCP server works, but the natural pairing is the Python harness's own server, since it
already has plain-text tool outputs and a genuinely typed (`limit: int`) argument for the
schema-mismatch scenario to corrupt:

```bash
bun --conditions=development apps/cli/src/index.ts mcp add sentry-harness \
  --transport stdio --yes -- \
  uv run --directory /path/to/sentry-agent-harness python -m agent_harness.experiments.mcp.server
```

(Registers it in `~/.cline/data/settings/cline_mcp_settings.json`; run once.)

### Run

```bash
# one-shot query against a local Ollama model
bun --conditions=development apps/cli/src/index.ts -P ollama -m llama3.1:8b --auto-approve true \
  "Call sentry-harness__query_database to find Ada Lovelace's plan."

# interactive TUI
bun --conditions=development apps/cli/src/index.ts -P ollama -m llama3.1:8b -i
```

Small local models (e.g. `qwen2.5-coder:1.5b`) are much faster to iterate with but unreliable at
actually invoking tools; `llama3.1:8b` is the model the scenarios below were verified against.
The very first call to any given model is slow (Ollama loading it from disk into memory, often
1–3 minutes) — that's normal, not a hang.

### Scenario deck

Same four failure modes, toggled via env vars instead of a dashboard:

| Env var | Effect |
|---|---|
| `CLINE_SENTRY_SILENT_TRUNCATION=1` | Truncates MCP tool output over 2000 chars in the `afterTool` hook, no error — the model answers from partial content. |
| `CLINE_SENTRY_INFINITE_TOOL_LOOP=1` | On an empty tool result, the `beforeModel` hook injects a "try a different query" nudge instead of letting the run end. |
| `CLINE_SENTRY_MCP_SCHEMA_MISMATCH=1` | The `beforeTool` hook corrupts a non-string MCP argument's type before it's sent, tripping the server's real schema validation. |
| `CLINE_SENTRY_CONTEXT_INFLATION=1` | Breadcrumbs request/message size on every model call so growth across turns is visible in Sentry. |

```bash
CLINE_SENTRY_MCP_SCHEMA_MISMATCH=1 bun --conditions=development apps/cli/src/index.ts \
  -P ollama -m llama3.1:8b --auto-approve true \
  "Call sentry-harness__query_database with query 'SELECT * FROM users' and limit 5."
```

Verified behavior (against `llama3.1:8b` + the Python harness's MCP server):

- **Baseline**: 2 iterations, clean tool call, correct answer.
- **Silent truncation**: a 865,287-char file truncated to 2,000 before reaching the model, which
  then fabricated plausible-but-invented content — the "confidently wrong agent" failure mode on
  a real tool call.
- **Infinite tool loop**: 2 iterations → 8 iterations, 6 genuine reformulation attempts, ~4.4x the
  token usage.
- **MCP schema mismatch**: a real FastMCP `ValidationError`, the model retrying the same broken
  call repeatedly, and Cline's own "max consecutive mistakes" safety net aborting the run — a
  cascading failure, not just a single bad call.

### Sentry

Set `SENTRY_DSN` (and optionally `SENTRY_ENVIRONMENT`) before running; unset, every `Sentry.*` call
in `instrumentation/product/telemetry.ts` and `instrumentation/experiments/scenarios.ts` is a safe
no-op, which is how the scenarios above were verified (by observing CLI/model behavior directly,
not yet against a live Sentry project).

```bash
export SENTRY_DSN="https://...@sentry.io/..."
```

Span tree per run: `agent.run` → `agent.turn <n>` → `agent.llm_call` / `tool.<name>`, with
prompt/completion token counts attached to the LLM span and breadcrumbs on every
`AgentRuntimeEvent` plus each scenario's corruption/truncation/nudge point.
