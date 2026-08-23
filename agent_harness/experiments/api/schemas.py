"""Pydantic request/response models for the dashboard-facing API."""

from __future__ import annotations

from pydantic import BaseModel


class QueryRequest(BaseModel):
    goal: str
    session_id: str | None = None


class ToolCallRecord(BaseModel):
    tool: str
    output: str


class QueryResponse(BaseModel):
    session_id: str
    answer: str
    iterations: int
    tool_calls: list[ToolCallRecord]
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    trace_id: str | None = None
    sentry_trace_url: str | None = None


class ScenarioState(BaseModel):
    silent_truncation: bool
    infinite_tool_loop: bool
    mcp_schema_mismatch: bool
    context_inflation: bool


class ScenarioUpdate(BaseModel):
    silent_truncation: bool | None = None
    infinite_tool_loop: bool | None = None
    mcp_schema_mismatch: bool | None = None
    context_inflation: bool | None = None
