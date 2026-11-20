"""FastAPI app: start a run, stream stage events over SSE, respond to gates, and
serve the seeded source-system data the UI renders alongside the agent output."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from demand_portfolio_planning.agents import (
    draft_plan,
    evaluate_precheck,
    fit_portfolio,
    get_assessment_agent,
    get_intake_agent,
    get_planner_agent,
    get_portfolio_agent,
    get_precheck_agent,
    get_resource_agent,
    match_resources,
    run_assessment,
    structure_demand,
)
from demand_portfolio_planning.models import (
    BoardDecision,
    HandoffAdjustment,
    PreCheckDecision,
    StartRequest,
)
from demand_portfolio_planning.observability import setup_observability
from demand_portfolio_planning.roadmap import build_roadmap
from demand_portfolio_planning.runs import REVISION_STEPS, RunHandle, RunRegistry
from demand_portfolio_planning.settings import get_settings
from demand_portfolio_planning.sources import (
    get_portfolio,
    get_resource_pool,
    get_seed_demands,
    get_skill_matrix,
)
from demand_portfolio_planning.workflow import (
    BOARD_REQUEST_ID,
    HANDOFF_REQUEST_ID,
    PRECHECK_REQUEST_ID,
    build_workflow,
)

logger = logging.getLogger(__name__)

_DECISION_MODELS: dict[str, type[BaseModel]] = {
    PRECHECK_REQUEST_ID: PreCheckDecision,
    BOARD_REQUEST_ID: BoardDecision,
    HANDOFF_REQUEST_ID: HandoffAdjustment,
}


def _workflow_factory() -> Any:
    return build_workflow(
        structure_demand=lambda demand, lang: structure_demand(
            get_intake_agent(), demand, lang
        ),
        evaluate_precheck=lambda record, lang: evaluate_precheck(
            get_precheck_agent(), record, lang
        ),
        run_assessment=lambda record, report, lang: run_assessment(
            get_assessment_agent(), record, report, lang
        ),
        fit_portfolio=lambda record, summary, lang: fit_portfolio(
            get_portfolio_agent(), record, summary, lang
        ),
        match_resources=lambda record, summary, fit, lang: match_resources(
            get_resource_agent(), record, summary, fit, lang
        ),
        draft_plan=lambda record, summary, fit, match, lang: draft_plan(
            get_planner_agent(), record, summary, fit, match, lang
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_observability()
    app.state.registry = RunRegistry()
    try:
        yield
    finally:
        await app.state.registry.shutdown()


app = FastAPI(title="Demand-Portfolio-Planning Agent Demo", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartRunBody(BaseModel):
    demand_id: str | None = "payroll-local"
    raw_demand: str | None = None
    language: str = "de"


class RespondBody(BaseModel):
    request_id: str
    decision: dict[str, Any]


class ChatBody(BaseModel):
    message: str
    viewing: str = ""
    language: str = "de"


class ReviseBody(BaseModel):
    step: str
    instruction: str
    language: str = "de"


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/demands")
async def list_demands() -> list[dict[str, str | None]]:
    return [
        {"demand_id": d.demand_id, "title": d.title, "known_process_owner": d.known_process_owner}
        for d in get_seed_demands()
    ]


@app.get("/api/seed-data")
async def seed_data() -> dict[str, Any]:
    return {
        "portfolio": [p.model_dump() for p in get_portfolio()],
        "resource_pool": [p.model_dump() for p in get_resource_pool()],
        "skill_matrix": get_skill_matrix(),
        "demands": [d.model_dump() for d in get_seed_demands()],
    }


def _roadmap_inputs(handle: RunHandle) -> dict[str, Any]:
    """Pull the new-demand scheduling inputs from a run's captured artifacts so
    the roadmap can place it against the existing portfolio."""
    arts = handle.artifacts
    intake = arts.get("intake") or {}
    title = (intake.get("demand_title") or {}).get("value")
    if not title:
        return {}
    area = (intake.get("portfolio_area") or {}).get("value")
    if not area:
        area = ((arts.get("portfolio") or {}).get("portfolio_area") or {}).get("value")
    resource = arts.get("resource") or {}
    roles = [
        row.get("role_or_skill")
        for row in resource.get("rows", [])
        if row.get("role_or_skill")
    ]
    planned_start = ((arts.get("plan") or {}).get("timeline") or {}).get("planned_project_start")
    return {
        "new_demand_id": "new-demand",
        "new_demand_name": title,
        "new_demand_area": area,
        "new_demand_roles": roles,
        "planned_start": planned_start,
    }


@app.get("/api/roadmap")
async def roadmap(run_id: str | None = None, lang: str = "de") -> dict[str, Any]:
    """Portfolio roadmap. With a run_id whose demand is structured, the new
    demand is ranked against the backlog and placed on the timeline."""
    inputs: dict[str, Any] = {}
    if run_id:
        handle = app.state.registry.get(run_id)
        if handle is not None:
            inputs = _roadmap_inputs(handle)
    return build_roadmap(language=lang, **inputs).model_dump()


@app.post("/runs")
async def create_run(body: StartRunBody) -> dict[str, str]:
    handle = await app.state.registry.start(
        workflow_factory=_workflow_factory,
        message=StartRequest(
            demand_id=body.demand_id, raw_demand=body.raw_demand, language=body.language
        ),
    )
    return {"run_id": handle.run_id}


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    handle = app.state.registry.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run not found")

    async def gen() -> AsyncIterator[bytes]:
        async for item in app.state.registry.stream(handle):
            payload = json.dumps(item, default=str, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode()
        yield b"event: end\ndata: {}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/runs/{run_id}/respond")
async def respond(run_id: str, body: RespondBody) -> dict[str, str]:
    handle = app.state.registry.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run not found")
    model = _DECISION_MODELS.get(body.request_id)
    if model is None:
        raise HTTPException(status_code=400, detail="unknown request_id")
    if body.request_id not in handle.pending:
        raise HTTPException(status_code=409, detail="no pending request for this run")
    decision = model.model_validate(body.decision)
    await app.state.registry.respond(handle, responses={body.request_id: decision})
    return {"status": "resumed"}


@app.post("/runs/{run_id}/revise")
async def revise(run_id: str, body: ReviseBody) -> dict[str, Any]:
    registry: RunRegistry = app.state.registry
    handle = registry.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run not found")
    if body.step not in REVISION_STEPS:
        raise HTTPException(status_code=400, detail="unknown revision step")
    try:
        return await registry.revise(
            handle, step=body.step, instruction=body.instruction, language=body.language
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/runs/{run_id}/chat")
async def chat(run_id: str, body: ChatBody) -> dict[str, Any]:
    registry: RunRegistry = app.state.registry
    handle = registry.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        return await registry.chat(
            handle, message=body.message, viewing=body.viewing, language=body.language
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
