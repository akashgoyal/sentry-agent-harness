# sentry-agent-harness

A small, modular agent harness built to demo **Sentry AI Monitoring** and **Seer Root Cause
Analysis**: a real LangGraph agent loop, real FastMCP tools, full Sentry span/breadcrumb
instrumentation, and a live-toggleable "bug deck" of deterministic failure modes.

## Layout

```
agent_harness/
  config.py            Settings (env-driven)
  telemetry/            Sentry init + span/breadcrumb helpers
  scenarios/            FailureEngine — the bug toggle deck
  tools/                 read_file_contents / query_database / execute_bash
  mcp/                   FastMCP server + LangChain-facing MCP client
  llm/                    LLMProviderFactory (anthropic | openai | ollama | together)
  agent/                  SystemPromptRegistry + AgentHarness (LangGraph state machine)
  api/                    FastAPI app, /api/query, /api/scenarios
  cli.py                  run / repl / serve
web/                      static dashboard (no build step)
```

## Setup

```bash
uv sync
cp .env.example .env
# edit .env: set SENTRY_DSN, LLM_PROVIDER, and that provider's API key
```

## Run

```bash
# web dashboard (query box, scenario toggles, telemetry bar)
uv run agent-harness serve
# -> http://localhost:8000

# one-shot CLI query
uv run agent-harness run "Look up Ada Lovelace's orders in the database"

# interactive REPL
uv run agent-harness repl

# toggle a scenario for a single CLI run
uv run agent-harness run "read agent_harness/config.py" --silent-truncation
```

## Scenario deck

Toggle these from the dashboard (or CLI flags) to trigger deterministic, demoable bugs and
watch them show up in Sentry / Seer:

| Flag | Effect |
|---|---|
| `silent_truncation` | Tool output over `TRUNCATION_LIMIT_CHARS` is silently cut, no exception — the LLM answers from partial context. |
| `infinite_tool_loop` | Disables the "empty tool result → stop" boundary; the agent keeps retrying until `MAX_ITERATIONS`. |
| `mcp_schema_mismatch` | Corrupts an outgoing MCP tool argument's type, tripping FastMCP's schema validation into an unhandled `ValidationError`. |
| `context_inflation` | Skips normal conversation trimming so raw tool output accumulates every turn instead of being bounded. |

## MCP transport

Defaults to `stdio` (the harness spawns `python -m agent_harness.mcp.server` per query). For a
cross-process trace, set `MCP_TRANSPORT=sse` in `.env`, run the server standalone
(`uv run python -m agent_harness.mcp.server`), and point `MCP_SSE_URL` at it.
