"""argparse CLI — a scriptable path to the same AgentHarness/FailureEngine the API uses."""

from __future__ import annotations

import argparse
import asyncio

from agent_harness.experiments.agent.graph import AgentHarness
from agent_harness.product.config import Settings, get_settings
from agent_harness.product.llm.provider_factory import LLMProviderFactory
from agent_harness.experiments.mcp.client import MCPToolProvider
from agent_harness.experiments.scenarios.failure_engine import FailureEngine
from agent_harness.product.telemetry.sentry_init import init_sentry
from agent_harness.product.telemetry.spans import current_trace_id

_SCENARIO_FLAGS = ("silent-truncation", "infinite-tool-loop", "mcp-schema-mismatch", "context-inflation")


async def _build_harness(failure_engine: FailureEngine, settings: Settings) -> AgentHarness:
    tools = await MCPToolProvider(settings, failure_engine).get_tools()
    llm = LLMProviderFactory.create(settings)
    return AgentHarness(llm=llm, tools=tools, settings=settings, failure_engine=failure_engine)


async def _run_once(goal: str, failure_engine: FailureEngine, settings: Settings) -> None:
    harness = await _build_harness(failure_engine, settings)
    result = await harness.run(goal=goal, session_id="cli")
    print(f"\n{result.answer}\n")
    print(
        f"[iterations={result.iterations} latency_ms={result.latency_ms:.0f} "
        f"prompt_tokens={result.prompt_tokens} completion_tokens={result.completion_tokens} "
        f"trace_id={current_trace_id()}]"
    )


async def _repl(failure_engine: FailureEngine, settings: Settings) -> None:
    print("sentry-agent-harness REPL — type a goal, or 'exit'.")
    while True:
        goal = input("> ").strip()
        if goal in ("exit", "quit"):
            break
        if goal:
            await _run_once(goal, failure_engine, settings)


def _add_scenario_flags(parser: argparse.ArgumentParser) -> None:
    for flag in _SCENARIO_FLAGS:
        dest = flag.replace("-", "_")
        parser.add_argument(f"--{flag}", dest=dest, action="store_true", default=None)
        parser.add_argument(f"--no-{flag}", dest=dest, action="store_false", default=None)


def _apply_scenario_flags(failure_engine: FailureEngine, args: argparse.Namespace) -> None:
    changes = {flag.replace("-", "_"): getattr(args, flag.replace("-", "_")) for flag in _SCENARIO_FLAGS}
    changes = {k: v for k, v in changes.items() if v is not None}
    if changes:
        failure_engine.update(**changes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run one goal and print the result")
    run_p.add_argument("goal")
    _add_scenario_flags(run_p)

    repl_p = sub.add_parser("repl", help="Interactive multi-turn loop")
    _add_scenario_flags(repl_p)

    serve_p = sub.add_parser("serve", help="Launch the FastAPI dashboard server")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.add_argument("--reload", action="store_true")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()

    if args.command == "serve":
        import uvicorn

        uvicorn.run("agent_harness.experiments.api.app:app", host=args.host, port=args.port, reload=args.reload)
        return

    init_sentry(settings)
    failure_engine = FailureEngine(settings)
    _apply_scenario_flags(failure_engine, args)

    if args.command == "run":
        asyncio.run(_run_once(args.goal, failure_engine, settings))
    elif args.command == "repl":
        asyncio.run(_repl(failure_engine, settings))


if __name__ == "__main__":
    main()
