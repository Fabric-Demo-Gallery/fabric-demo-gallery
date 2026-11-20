import contextlib
import unittest
from contextlib import AbstractContextManager
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

from agent_framework import Workflow

from demand_portfolio_planning.models import (
    AssessmentSummary,
    ChatRouterOutput,
    DemandRecord,
    PreCheckReport,
    TrackedField,
)
from demand_portfolio_planning.runs import RunHandle, RunRegistry


def _handle() -> RunHandle:
    return RunHandle(run_id="run-1", workflow=cast(Workflow, object()))


def _record() -> DemandRecord:
    return DemandRecord(
        demand_title=TrackedField(value="Payroll rollout", kind="fact"),
        business_demand=TrackedField(value="Introduce payroll locally", kind="fact"),
    )


def _patch(name: str, value: object) -> AbstractContextManager[Any]:
    return patch(f"demand_portfolio_planning.runs.{name}", new=value)


class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_answer_action_does_not_edit(self) -> None:
        registry = RunRegistry()
        handle = _handle()
        handle.artifacts["assessment"] = AssessmentSummary().model_dump()
        handle.pending["board_decision"] = Mock()  # board gate open

        routed = ChatRouterOutput(reply="The assessment locked at the Board.", action="answer")
        with contextlib.ExitStack() as stack:
            stack.enter_context(_patch("get_assistant_agent", Mock(return_value=Mock())))
            stack.enter_context(_patch("route_chat", AsyncMock(return_value=routed)))
            result = await registry.chat(
                handle, message="why can't I change the demand?", viewing="board", language="en"
            )

        self.assertEqual(result["action"], "answer")
        self.assertEqual(result["updates"], [])
        self.assertEqual(len(handle.chat_history), 2)

    async def test_edit_action_revises_editable_artifact(self) -> None:
        registry = RunRegistry()
        handle = _handle()
        handle.artifacts["intake"] = _record().model_dump()
        handle.artifacts["precheck"] = {
            "report": PreCheckReport().model_dump(),
            "record": _record().model_dump(),
        }
        handle.artifacts["assessment"] = AssessmentSummary().model_dump()
        handle.pending["board_decision"] = Mock()  # editable step = assessment

        routed = ChatRouterOutput(reply="Done.", action="edit", instruction="Sharpen the risks")
        revised = AssessmentSummary(business_demand="sharpened")
        with contextlib.ExitStack() as stack:
            stack.enter_context(_patch("get_assistant_agent", Mock(return_value=Mock())))
            stack.enter_context(_patch("route_chat", AsyncMock(return_value=routed)))
            stack.enter_context(_patch("get_assessment_agent", Mock(return_value=Mock())))
            ra = stack.enter_context(_patch("run_assessment", AsyncMock(return_value=revised)))
            result = await registry.chat(
                handle, message="sharpen the risks", viewing="board", language="en"
            )

        ra.assert_awaited_once()
        self.assertEqual(result["action"], "edit")
        self.assertEqual(len(result["updates"]), 1)
        self.assertEqual(result["updates"][0]["step"], "assessment")
        self.assertEqual(handle.artifacts["assessment"], revised.model_dump())

    async def test_edit_record_patches_and_rederives_precheck(self) -> None:
        registry = RunRegistry()
        handle = _handle()
        handle.artifacts["intake"] = _record().model_dump()
        handle.pending["precheck_review"] = Mock()  # editable step = intake

        routed = ChatRouterOutput(reply="Marked in scope.", action="edit", instruction="x")
        # The editor patches the record: it keeps the original fields and adds one.
        patched = _record()
        patched.portfolio_area = TrackedField(
            value="Finance & ERP", kind="fact", source="user input"
        )
        new_report = PreCheckReport(status="ready", demand_summary="ok")
        with contextlib.ExitStack() as stack:
            stack.enter_context(_patch("get_assistant_agent", Mock(return_value=Mock())))
            stack.enter_context(_patch("route_chat", AsyncMock(return_value=routed)))
            stack.enter_context(_patch("get_record_editor_agent", Mock(return_value=Mock())))
            ed_mock = AsyncMock(return_value=patched)
            ed = stack.enter_context(_patch("edit_demand_record", ed_mock))
            stack.enter_context(_patch("get_precheck_agent", Mock(return_value=Mock())))
            ep_mock = AsyncMock(return_value=new_report)
            ep = stack.enter_context(_patch("evaluate_precheck", ep_mock))
            result = await registry.chat(
                handle, message="mark SAP-FI in scope", viewing="precheck", language="en"
            )

        # The editor must receive the FULL current record (a patch, not a re-derive).
        ed.assert_awaited_once()
        passed_record = cast(DemandRecord, ed.await_args.args[1])
        self.assertEqual(passed_record.demand_title.value, "Payroll rollout")
        ep.assert_awaited_once()
        steps = [u["step"] for u in result["updates"]]
        self.assertIn("intake", steps)
        self.assertIn("precheck", steps)  # report re-derived as a new version
        # Untouched fields survive the edit; the changed field is applied.
        self.assertEqual(handle.artifacts["intake"]["demand_title"]["value"], "Payroll rollout")
        self.assertEqual(handle.artifacts["intake"]["portfolio_area"]["value"], "Finance & ERP")
        self.assertEqual(handle.artifacts["precheck"]["report"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
