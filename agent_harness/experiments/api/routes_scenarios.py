"""GET/POST /api/scenarios — read and flip the failure-mode toggle deck at runtime."""

from __future__ import annotations

from fastapi import APIRouter, Request

from agent_harness.experiments.api.schemas import ScenarioState, ScenarioUpdate

router = APIRouter()


@router.get("/api/scenarios", response_model=ScenarioState)
async def get_scenarios(request: Request) -> ScenarioState:
    return ScenarioState(**request.app.state.failure_engine.as_dict())


@router.post("/api/scenarios", response_model=ScenarioState)
async def update_scenarios(payload: ScenarioUpdate, request: Request) -> ScenarioState:
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    request.app.state.failure_engine.update(**changes)
    return ScenarioState(**request.app.state.failure_engine.as_dict())
