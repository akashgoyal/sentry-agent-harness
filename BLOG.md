---
title: I Gave My AI Coding Agent Amnesia, Then Watched Sentry Diagnose It
published: false
tags: ai, sentry, observability, agents
cover_image:
---

<!--
  HOW TO USE THIS DRAFT
  - Every [SCREENSHOT N: ...] marker maps to a step in the action checklist we worked through.
    Replace it with an actual image embed once you've captured it: ![caption](path-or-url)
  - Anything in <!-- --> is a note to you, not part of the post. Delete these before publishing.
  - Every number in this draft is a real, verified result from actually running this against
    llama3.1:8b with a live Sentry DSN wired in — don't round them off, the specificity (and the
    variance between runs) is what makes this credible.
  - Fill in the repo URL and PR link(s) before publishing (search for TODO).
-->

*This is a submission for [DEV's Summer Bug Smash: Clear the Lineup](https://dev.to/bugsmash)
powered by [Sentry](https://sentry.io/).*

## Project Overview

`sentry-agent-harness` instruments AI coding agents with **Sentry AI Monitoring**, two different
ways: a fork of [Cline](https://github.com/cline/cline) instrumented entirely through its own
public hook system (no patches to Cline's internals), and a from-scratch Python/LangGraph agent
for fast iteration. Both expose the same four toggleable agent failure modes — silent tool-output
truncation, an infinite tool-call retry loop, an MCP schema mismatch, and unbounded context growth
— so the same Sentry story can be told against either one. <!-- TODO: repo URL -->

To actually exercise it, I didn't hand Cline a synthetic prompt — I gave it a real support ticket:

> A customer (grace@example.com) says her July invoice — she thinks the ID is `INV-1034` — is
> higher than expected. Look into the database and the billing app, figure out what's wrong, and
> explain the root cause.

Behind that ticket is a tiny billing service (a `users`/`orders`/`invoices` SQLite database over
MCP, a `billing_engine.py` with the real calculation logic, a `PRICING.md` with the *documented*
pricing contract, and an `audit.log` of deploy events) carrying a genuine, seeded bug: a deploy on
`2026-07-01` silently switched whether tax is computed before or after a discount, so invoice
`INV-1043` came out **$195.00** instead of the correct **$192.50**. The ticket's invoice ID even
has a typo, so step one is already a dead end.

Everything ran against **`llama3.1:8b` through Ollama — entirely local, no API key, no hosted
inference bill.** That matters twice over: anyone can reproduce this for free, and a small local
model is noisier than a frontier hosted one, which is honestly closer to real production agent
traffic than a cherry-picked demo would be — exactly the kind of variance you need observability
for, not the case where everything already works.

Worth separating out clearly from the four scenarios below: some of that noise was just the model
being an 8B model, nothing to do with any bug I injected. It occasionally hallucinated a
plausible-looking tool call as plain text instead of issuing a real one, and routinely sent
integer arguments as quoted strings (`"limit": "5"` instead of `5`) — usually harmless, since the
MCP server coerced it, but a good reminder that "the agent looks like it's working" and "the agent
is reliably doing what you asked" aren't the same claim. None of the four failures in this post are
that — each one below reproduces identically regardless of model size, because each one is an
infrastructure/hook-level bug, not a reasoning failure. A bigger model wouldn't have avoided any of
them: silent truncation cuts data *before* it reaches the model, and the other three are hook-level
overrides that happen regardless of what the model does.

[SCREENSHOT 1: the trace waterfall for a clean run — agent.run → agent.turn → tool spans, token
counts visible. Sentry recognized the span ops (gen_ai.invoke_agent, gen_ai.chat,
gen_ai.execute_tool) as its own AI Agent Monitoring format — a dedicated "Agent Activity" tab
appears next to the raw waterfall.]

## Bug Fix or Performance Improvement

There were two layers of bugs here, and honestly the second one ended up being the more
interesting story.

**Layer 1 — the bug I seeded on purpose.** The billing discrepancy above, investigated live by
Cline while I watched Sentry. Four distinct failure modes surfaced during that investigation (full
detail in "My Improvements" below): a silently truncated log file that made the agent confidently
cite the wrong deploy, a retry loop that burned 3x the tokens on a typo'd invoice ID, and a
schema-mismatch that produced a real, cascading `ValidationError`.

**Layer 2 — the bugs I found by accident.** Building this wasn't "write the instrumentation once,
watch it work." Actually running it against a live Sentry project surfaced **five real bugs in my
own instrumentation code**, none of which `tsc` or a unit test would have caught, all of which I
only noticed because I went looking in the Sentry UI and found something missing or wrong:

1. **Events dropped at process exit.** My first version called `Sentry.flush()` fire-and-forget.
   Cline's CLI calls `process.exit()` moments after a run finishes, which routinely won the race
   against the network flush — exceptions were being generated and silently never delivered.
2. **The error flag that's never true.** FastMCP catches its own schema validation errors and
   returns them as normal-looking text content, not a protocol-level error — so gating my capture
   logic on `result.isError` meant it never fired for the exact scenario it existed to catch.
3. **Seer caught a bug in my bug report.** My exception message did `String(result.output)` on a
   response object, coercing it to the literal text `"[object Object]"`. I asked Seer for the root
   cause of my own captured exception, and it correctly diagnosed *my* bug instead of the scenario
   I'd built — exact line number, reproduction steps, all of it.
4. **The fix that silently didn't apply.** My first version of silent truncation returned a
   modified tool result from an `afterTool` hook. The hook fired, computed the right truncated
   value, returned it — and the *next* model call still saw the full, untruncated content anyway.
5. **Breadcrumbs need a body to travel in.** Sentry breadcrumbs only ship attached to an event.
   Three of my four scenarios are deliberately silent (no exception), so their breadcrumbs were
   being recorded locally and then never sent anywhere — invisible until I noticed nothing showed
   up where I expected an issue.

All five are fixed in the code linked below.

## Code

<!-- TODO: link the PR(s) — the instrumentation lives in cline/apps/cli/src/instrumentation/
     (product/telemetry.ts, experiments/scenarios.ts, index.ts), and the billing-app fixtures
     that make the investigation real are in demo-billing-app/ + agent_harness's invoices table. -->

All four scenarios are just environment variables, off by default — clone the repo and flip
whichever one you want to see for yourself, no code changes needed:

```bash
CLINE_SENTRY_SILENT_TRUNCATION=1     # cuts tool output over 2,000 chars before the model sees it
CLINE_SENTRY_INFINITE_TOOL_LOOP=1    # forces a retry instead of stopping on an empty result
CLINE_SENTRY_MCP_SCHEMA_MISMATCH=1   # corrupts an outgoing MCP argument's type
CLINE_SENTRY_CONTEXT_INFLATION=1     # skips message-history trimming
```

## My Improvements

**No patches to Cline's internals.** `AgentRuntime` — the actual agent loop — already exposes a
public hook system (`beforeModel`, `beforeTool`, `afterTool`, `onEvent`) plus a subscribable event
stream. The whole integration is one new module split into two files by responsibility: a
`telemetry.ts` that turns Cline's own events into a Sentry span tree and knows nothing about the
scenarios below, and a `scenarios.ts` that injects the four failure modes purely through the same
public hooks. Three call sites, merged in via `mergeAgentHooks`.

**Failure #1 — the confidently wrong agent.** The `audit.log` file is 4,258 characters. Buried at
character **2,311** — well past a naive truncation point — is the one line that actually explains
the bug: a `billing-engine version=2.0.0` deploy whose changelog admits the tax-calculation change
outright. I added a middleware bug on purpose: silently cut any tool output over 2,000 characters
before it reaches the model, no exception raised. With it active, the agent confidently blamed a
real but *unrelated* `api-gateway` release from three weeks earlier — sha and all — because that's
what was still inside its 2,000-char window. Nothing crashed. A green checkmark looks identical
whether the agent got lucky or got it right.

[SCREENSHOT 2: the "Silent truncation" warning issue — originalLength 4258 → limit 2000 — next to
the run's answer citing the wrong deploy]

**Failure #2 — the loop that won't take no for an answer.** Normally an empty query result is
where the agent should say "I don't have that" and stop. I added a hook that, on an empty result,
injects a "try a different query" nudge instead of letting the run end. Baseline: **2 iterations**.
With the nudge active, runs stretched to **3–6 iterations** depending on how many reformulations
the model attempted, and prompt token usage peaked at **116,901** in one run — over **3x** the
baseline's ~36,000 for the exact same question.

[SCREENSHOT 3: the bloated trace next to the baseline trace — span count and token usage side by
side]

**Failure #3 — the one with a real stack trace.** I corrupted an outgoing MCP tool argument's type
right before it left the client — a `limit` parameter that should be an integer went out as the
string `"not-a-valid-type"`. What happened next wasn't scripted: the tool rejected it with a
genuine schema `ValidationError` from the server's own pydantic validation. The agent retried the
*exact same broken call* — nothing about the corruption changes between attempts — until Cline's
own "max consecutive mistakes" safety net aborted the run. A cascading failure, not a single bad
call.

[SCREENSHOT 4: the Issue detail page — the ValidationError, with the corrupted-argument breadcrumb
right before it]

**Why hooks instead of a fork-and-edit.** Every failure mode above is injected through
`beforeModel`/`beforeTool`/`onEvent` — the same seams Cline itself uses for its own hook-event
dispatch, tool approval, and context compaction. That meant zero merge conflicts with Cline's own
logic (confirmed by testing that its native hook-event output kept working unchanged throughout),
and it's the reason the one genuinely subtle bug (#4 in the list above) was fixable by moving logic
between two *equally legitimate* hooks rather than needing a deeper architectural change.

## Best Use of Sentry

This project leans on several distinct Sentry AI Monitoring capabilities, each mapped to a
specific problem in agent debugging that a plain log file handles badly:

- **Distributed Tracing / Agent Tracing** — `AgentRuntime`'s event stream (`run-started`,
  `turn-started`, `tool-started`, ...) is turned into a real nested span tree: `agent.run` →
  `agent.turn <n>` → `agent.llm_call` / `tool.<name>`, with prompt/completion token counts attached
  to each LLM span via `gen_ai.usage.*` attributes. Because the span `op` values follow Sentry's
  `gen_ai.*` semantic conventions (`gen_ai.invoke_agent`, `gen_ai.chat`, `gen_ai.execute_tool`),
  Sentry's own UI recognized this as agent monitoring automatically — a dedicated **Agent
  Activity** view came for free, not something I had to build a custom dashboard to get.
- **Error Monitoring** — the schema-mismatch scenario produces a real `Sentry.captureException`
  with full breadcrumb context (which argument got corrupted, on which tool, right before the
  server's validation error). The two other "silent" scenarios (truncation, infinite loop) don't
  throw by design, so I added explicit `Sentry.captureMessage(..., "warning")` calls at the exact
  moment each one fires — turning invisible failures into findable issues, with the issue's event
  count doubling as "how many times did this actually happen in one run."
- **Seer** — asked to explain the schema-mismatch issue, and its root cause analysis was accurate
  down to the specific line and the specific reason (`String()` coercing an object to
  `"[object Object]"`) — which is how I found and fixed bug #3 in the list above. Seer diagnosed a
  real bug in my own code, not the synthetic scenario I thought I was showing it.
- **Breadcrumbs** — every `AgentRuntimeEvent` (run/turn/tool lifecycle, model requests) leaves a
  breadcrumb, plus a scenario-specific one at each failure point (`scenario.silent_truncation`,
  `scenario.infinite_tool_loop`, `scenario.mcp_schema_mismatch`). These are what actually let me
  (and Seer) reconstruct *why* a run went wrong, not just *that* it did.

[SCREENSHOT 5: Seer's root cause analysis on the schema-mismatch issue]

[SCREENSHOT 6: clean trace vs. broken trace, side by side, for whichever scenario hit hardest]

<!-- Best Use of Google AI section removed — this project runs entirely against Ollama (local
     Llama models); no Google AI products are used. -->
