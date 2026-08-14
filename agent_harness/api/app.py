"""FastAPI app factory: wires settings, Sentry, the failure engine, and the dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent_harness.api.routes_agent import router as agent_router
from agent_harness.api.routes_scenarios import router as scenarios_router
from agent_harness.config import get_settings
from agent_harness.scenarios.failure_engine import FailureEngine
from agent_harness.telemetry.sentry_init import init_sentry

_WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


def create_app() -> FastAPI:
    settings = get_settings()
    init_sentry(settings)

    app = FastAPI(title="sentry-agent-harness")
    app.state.settings = settings
    app.state.failure_engine = FailureEngine(settings)

    app.include_router(agent_router)
    app.include_router(scenarios_router)
    app.mount("/static", StaticFiles(directory=_WEB_DIR), name="static")

    @app.get("/")
    async def dashboard() -> FileResponse:
        return FileResponse(_WEB_DIR / "index.html")

    return app


app = create_app()
