"""POST /api/query — runs one agent turn end-to-end and returns telemetry alongside the answer."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from agent_harness.experiments.agent.graph import AgentHarness
from agent_harness.experiments.api.schemas import QueryRequest, QueryResponse, ToolCallRecord
from agent_harness.product.llm.provider_factory import LLMProviderFactory
from agent_harness.experiments.mcp.client import MCPToolProvider
from agent_harness.product.telemetry.spans import current_trace_id

router = APIRouter()


@router.post("/api/query", response_model=QueryResponse)
async def run_query(payload: QueryRequest, request: Request) -> QueryResponse:
    settings = request.app.state.settings
    failure_engine = request.app.state.failure_engine
    session_id = payload.session_id or str(uuid.uuid4())

    tools = await MCPToolProvider(settings, failure_engine).get_tools()
    llm = LLMProviderFactory.create(settings)
    harness = AgentHarness(llm=llm, tools=tools, settings=settings, failure_engine=failure_engine)

    result = await harness.run(goal=payload.goal, session_id=session_id)

    trace_id = current_trace_id()
    sentry_trace_url = None
    if trace_id and settings.sentry_org and settings.sentry_project:
        sentry_trace_url = f"https://{settings.sentry_org}.sentry.io/explore/traces/trace/{trace_id}/"

    return QueryResponse(
        session_id=session_id,
        answer=result.answer,
        iterations=result.iterations,
        tool_calls=[ToolCallRecord(tool=c["tool"], output=c["output"]) for c in result.tool_calls],
        latency_ms=result.latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        trace_id=trace_id,
        sentry_trace_url=sentry_trace_url,
    )
