"""In-process run registry that owns workflow lifecycles across multiple human
gates. Generalizes the single-approval pattern: each ``/respond`` resumes the
workflow, which then either suspends at the next gate or completes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Workflow, WorkflowEvent, WorkflowRunState
from pydantic import BaseModel

from demand_portfolio_planning.agents import (
    draft_plan,
    edit_demand_record,
    evaluate_precheck,
    fit_portfolio,
    get_assessment_agent,
    get_assistant_agent,
    get_planner_agent,
    get_portfolio_agent,
    get_precheck_agent,
    get_record_editor_agent,
    get_resource_agent,
    match_resources,
    route_chat,
    run_assessment,
)
from demand_portfolio_planning.models import (
    AssessmentSummary,
    DemandRecord,
    PlanningOutcome,
    PortfolioFit,
    PreCheckReport,
    ResourceMatch,
    StartRequest,
)

logger = logging.getLogger(__name__)

END_SENTINEL = "__end__"
REVISION_STEPS = frozenset({"intake", "precheck", "assessment", "portfolio", "resource", "plan"})

# The single editable artifact behind each open gate (lock-on-commit model).
_GATE_EDITABLE_STEP = {
    "precheck_review": "intake",  # DemandRecord
    "board_decision": "assessment",  # AssessmentSummary
    "handoff_review": "plan",  # ProjectPlanningHandoff
}
_STEP_TO_ARTIFACT = {
    "intake": "DemandRecord",
    "precheck": "PreCheckReport",
    "assessment": "AssessmentSummary",
    "portfolio": "PortfolioFit",
    "resource": "ResourceMatch",
    "plan": "ProjectPlanningHandoff",
}


@dataclass
class RunHandle:
    run_id: str
    workflow: Workflow
    events: asyncio.Queue[dict[str, Any] | str] = field(
        default_factory=lambda: asyncio.Queue(maxsize=0)
    )
    pending: dict[str, BaseModel] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, int] = field(default_factory=dict)
    chat_history: list[dict[str, str]] = field(default_factory=list)
    final_state: str | None = None
    outcome: PlanningOutcome | None = None


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunHandle] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    def get(self, run_id: str) -> RunHandle | None:
        return self._runs.get(run_id)

    async def start(self, *, workflow_factory: Any, message: StartRequest) -> RunHandle:
        async with self._lock:
            run_id = uuid.uuid4().hex[:12]
            handle = RunHandle(run_id=run_id, workflow=workflow_factory())
            self._runs[run_id] = handle
            self._tasks[run_id] = asyncio.create_task(self._drive(handle, message=message))
            return handle

    async def respond(self, handle: RunHandle, *, responses: Mapping[str, BaseModel]) -> None:
        handle.events = asyncio.Queue(maxsize=0)
        handle.pending.clear()
        self._tasks[handle.run_id] = asyncio.create_task(
            self._drive(handle, responses=responses)
        )

    async def _drive(
        self,
        handle: RunHandle,
        *,
        message: StartRequest | None = None,
        responses: Mapping[str, BaseModel] | None = None,
    ) -> None:
        run = (
            handle.workflow.run(message=message, stream=True)
            if message is not None
            else handle.workflow.run(responses=responses, stream=True)
        )
        try:
            async for event in run:
                payload = serialize_event(event)
                if payload is not None:
                    _capture_artifact(handle, payload)
                    await handle.events.put(payload)
                if event.type == "request_info":
                    handle.pending[event.request_id] = event.data

            result = await run.get_final_response()
            state = result.get_final_state()
            handle.final_state = state.value if hasattr(state, "value") else str(state)
            outputs = result.get_outputs()
            if outputs and isinstance(outputs[0], PlanningOutcome):
                handle.outcome = outputs[0]

            # Authoritative pending-request lookup. Streamed request_info events
            # are not re-emitted when a gate re-issues the same request_id (e.g.
            # the pre-check iteration loop), so we read the runner context, which
            # always reflects the current pending request and its latest data.
            pending = await _pending_requests(handle.workflow)
            if pending:
                handle.pending = pending

            if state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS and handle.pending:
                req_id, req = next(iter(handle.pending.items()))
                await handle.events.put(
                    {
                        "type": "awaiting",
                        "gate": req_id,
                        "request_id": req_id,
                        "request": req.model_dump(),
                        "versions": dict(handle.versions),
                    }
                )
            elif handle.outcome is not None:
                await handle.events.put(
                    {"type": "outcome", "outcome": handle.outcome.model_dump()}
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Workflow run failed: %s", exc)
            await handle.events.put({"type": "error", "message": str(exc)})
        finally:
            await handle.events.put(END_SENTINEL)

    async def stream(self, handle: RunHandle) -> AsyncIterator[dict[str, Any]]:
        queue = handle.events
        while True:
            item = await queue.get()
            if item == END_SENTINEL:
                return
            assert isinstance(item, dict)
            yield item

    async def revise(
        self,
        handle: RunHandle,
        *,
        step: str,
        instruction: str,
        language: str,
    ) -> dict[str, Any]:
        artifacts = handle.artifacts
        revised: BaseModel
        if step == "intake":
            record = DemandRecord(**_required_artifact(artifacts, "intake", step))
            # Patch the existing record in place — never re-derive from scratch,
            # which would drop every field the instruction did not mention.
            revised = await edit_demand_record(
                get_record_editor_agent(), record, instruction, language
            )
        elif step == "precheck":
            record = DemandRecord(**_required_artifact(artifacts, "intake", step))
            revised = await evaluate_precheck(
                get_precheck_agent(), record, language, instruction=instruction
            )
        elif step == "assessment":
            precheck = _required_artifact(artifacts, "precheck", step)
            report = PreCheckReport(**_required_nested_artifact(precheck, "report", step))
            record_data = precheck.get("record")
            record = DemandRecord(
                **(
                    record_data
                    if isinstance(record_data, dict)
                    else _required_artifact(artifacts, "intake", step)
                )
            )
            revised = await run_assessment(
                get_assessment_agent(), record, report, language, instruction=instruction
            )
        elif step == "portfolio":
            record = DemandRecord(**_required_artifact(artifacts, "intake", step))
            summary = AssessmentSummary(**_required_artifact(artifacts, "assessment", step))
            revised = await fit_portfolio(
                get_portfolio_agent(), record, summary, language, instruction=instruction
            )
        elif step == "resource":
            record = DemandRecord(**_required_artifact(artifacts, "intake", step))
            summary = AssessmentSummary(**_required_artifact(artifacts, "assessment", step))
            portfolio_fit = PortfolioFit(**_required_artifact(artifacts, "portfolio", step))
            revised = await match_resources(
                get_resource_agent(),
                record,
                summary,
                portfolio_fit,
                language,
                instruction=instruction,
            )
        elif step == "plan":
            record = DemandRecord(**_required_artifact(artifacts, "intake", step))
            summary = AssessmentSummary(**_required_artifact(artifacts, "assessment", step))
            portfolio_fit = PortfolioFit(**_required_artifact(artifacts, "portfolio", step))
            resource_match = ResourceMatch(**_required_artifact(artifacts, "resource", step))
            # The workflow injects deterministic priority/timeline after draft_plan;
            # a single-step revision returns only the agent's draft.
            revised = await draft_plan(
                get_planner_agent(),
                record,
                summary,
                portfolio_fit,
                resource_match,
                language,
                instruction=instruction,
            )
        else:
            raise ValueError(f"unknown revision step: {step}")

        artifact = revised.model_dump()
        handle.artifacts[step] = artifact
        handle.versions[step] = handle.versions.get(step, 1) + 1
        return {"step": step, "artifact": artifact, "version": handle.versions[step]}

    async def chat(
        self,
        handle: RunHandle,
        *,
        message: str,
        viewing: str,
        language: str,
    ) -> dict[str, Any]:
        """One conversational turn: the assistant either edits the currently
        editable artifact (and re-derives its dependents) or answers/explains."""
        editable = _editable_step(handle)
        snapshot = _artifact_snapshot(handle, editable)
        editable_payload: dict[str, Any] | None = None
        if editable is not None:
            editable_payload = {
                "name": _STEP_TO_ARTIFACT[editable],
                "step": editable,
                "data": handle.artifacts.get(editable),
            }
        context: dict[str, Any] = {
            "viewing": viewing,
            "editable": editable_payload,
            "artifacts": snapshot,
            "history": handle.chat_history[-12:],
            "message": message,
            "response_language": "English" if language == "en" else "German",
        }
        handle.chat_history.append({"role": "user", "content": message})
        decision = await route_chat(get_assistant_agent(), context)

        updates: list[dict[str, Any]] = []
        if decision.action == "edit" and editable is not None and decision.instruction:
            updates = await self._apply_chat_edit(handle, editable, decision.instruction, language)

        handle.chat_history.append({"role": "assistant", "content": decision.reply})
        return {"reply": decision.reply, "action": decision.action, "updates": updates}

    async def _apply_chat_edit(
        self, handle: RunHandle, step: str, instruction: str, language: str
    ) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        prev_plan = handle.artifacts.get("plan") if step == "plan" else None
        result = await self.revise(handle, step=step, instruction=instruction, language=language)

        if step == "plan" and isinstance(prev_plan, dict):
            # Preserve the deterministic priority/timeline/resource_allocation the
            # planner agent must not fabricate.
            draft = dict(result["artifact"])
            for key in ("priority", "timeline", "resource_allocation"):
                if key in prev_plan:
                    draft[key] = prev_plan[key]
            handle.artifacts["plan"] = draft
            result = {"step": "plan", "artifact": draft, "version": handle.versions["plan"]}
        updates.append(result)

        if step == "intake":
            # The DemandRecord changed -> re-derive a fresh PreCheckReport version.
            record = DemandRecord(**handle.artifacts["intake"])
            report = await evaluate_precheck(get_precheck_agent(), record, language)
            rec = handle.artifacts["intake"]
            handle.artifacts["precheck"] = {"report": report.model_dump(), "record": rec}
            handle.versions["precheck"] = handle.versions.get("precheck", 1) + 1
            updates.append(
                {
                    "step": "precheck",
                    "artifact": report.model_dump(),
                    "version": handle.versions["precheck"],
                }
            )
        return updates

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
            with contextlib.suppress(Exception):
                await task


def serialize_event(event: WorkflowEvent[Any]) -> dict[str, Any] | None:
    if event.type == "data":
        data = event.data
        if isinstance(data, dict) and "stage" in data:
            return {"type": "stage", **data}
    return None


async def _pending_requests(workflow: Workflow) -> dict[str, BaseModel]:
    """Read the current pending human-gate requests from the runner context.

    This is the reliable source after a resume: when a gate re-issues the same
    request_id (the pre-check iteration loop), the framework does not re-emit a
    streamed ``request_info`` event, but the runner context still tracks it.
    """
    ctx = getattr(workflow, "_runner_context", None)
    getter = getattr(ctx, "get_pending_request_info_events", None)
    if getter is None:
        return {}
    events = await getter()
    pending: dict[str, BaseModel] = {}
    for req_id, event in events.items():
        data = getattr(event, "data", None)
        if isinstance(data, BaseModel):
            pending[req_id] = data
    return pending


def _bump(handle: RunHandle, step: str) -> None:
    handle.versions[step] = handle.versions.get(step, 0) + 1


def _capture_artifact(handle: RunHandle, payload: dict[str, Any]) -> None:
    stage = payload.get("stage")
    if stage == "demand_record" and isinstance(payload.get("record"), dict):
        handle.artifacts["intake"] = payload["record"]
        _bump(handle, "intake")
    elif stage in ("precheck_report", "precheck_updated"):
        report = payload.get("report")
        record = payload.get("record")
        if isinstance(report, dict) and isinstance(record, dict):
            handle.artifacts["precheck"] = {"report": report, "record": record}
            handle.artifacts["intake"] = record
            _bump(handle, "precheck")
            if stage == "precheck_updated":
                _bump(handle, "intake")
    elif stage == "assessment_summary" and isinstance(payload.get("summary"), dict):
        handle.artifacts["assessment"] = payload["summary"]
        _bump(handle, "assessment")
    elif stage == "portfolio_fit" and isinstance(payload.get("portfolio_fit"), dict):
        handle.artifacts["portfolio"] = payload["portfolio_fit"]
        _bump(handle, "portfolio")
    elif stage == "resource_match" and isinstance(payload.get("resource_match"), dict):
        handle.artifacts["resource"] = payload["resource_match"]
        _bump(handle, "resource")
    elif stage == "plan_draft" and isinstance(payload.get("draft"), dict):
        handle.artifacts["plan"] = payload["draft"]
        _bump(handle, "plan")


def _editable_step(handle: RunHandle) -> str | None:
    """The one artifact editable right now, from the currently open gate."""
    for request_id in handle.pending:
        step = _GATE_EDITABLE_STEP.get(request_id)
        if step is not None:
            return step
    return None


def _lock_state(step: str, present: bool, editable: str | None, pending: set[str]) -> str:
    if not present:
        return "not_produced"
    if step == editable:
        return "editable"
    if step == "precheck" and "precheck_review" in pending:
        return "derived"  # recomputed from the DemandRecord; not edited directly
    if step in ("portfolio", "resource"):
        return "locked_on_creation"
    return "locked"


def _artifact_snapshot(handle: RunHandle, editable: str | None) -> list[dict[str, Any]]:
    pending = set(handle.pending.keys())
    snapshot: list[dict[str, Any]] = []
    for step in ("intake", "precheck", "assessment", "portfolio", "resource", "plan"):
        present = step in handle.artifacts
        snapshot.append(
            {
                "artifact": _STEP_TO_ARTIFACT[step],
                "step": step,
                "lock_state": _lock_state(step, present, editable, pending),
                "version": handle.versions.get(step, 1 if present else 0),
            }
        )
    if "plan" in handle.artifacts:
        snapshot.append(
            {
                "artifact": "PrioritySuggestion",
                "step": "priority",
                "lock_state": "deterministic",
                "version": 1,
            }
        )
    return snapshot


def _required_artifact(
    artifacts: dict[str, Any],
    key: str,
    step: str,
) -> dict[str, Any]:
    artifact = artifacts.get(key)
    if not isinstance(artifact, dict):
        raise ValueError(f"cannot revise {step}: missing required '{key}' artifact")
    return artifact


def _required_nested_artifact(
    artifact: dict[str, Any],
    key: str,
    step: str,
) -> dict[str, Any]:
    value = artifact.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"cannot revise {step}: missing required '{key}' artifact")
    return value
