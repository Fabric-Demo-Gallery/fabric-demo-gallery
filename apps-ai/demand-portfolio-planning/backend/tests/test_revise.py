import unittest
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

from agent_framework import Workflow

from demand_portfolio_planning.models import (
    AssessmentSummary,
    DemandRecord,
    PortfolioFit,
    TrackedField,
)
from demand_portfolio_planning.runs import RunHandle, RunRegistry


def _handle() -> RunHandle:
    return RunHandle(run_id="run-1", workflow=cast(Workflow, object()))


def _record() -> DemandRecord:
    return DemandRecord(
        demand_title=TrackedField(value="Payroll rollout", kind="fact"),
        business_demand=TrackedField(value="Introduce payroll locally", kind="fact"),
        process_owner=TrackedField(value="HR", kind="fact"),
    )


def _summary() -> AssessmentSummary:
    return AssessmentSummary(business_demand="Introduce payroll locally")


class ReviseTests(unittest.IsolatedAsyncioTestCase):
    async def test_portfolio_revision_uses_reconstructed_inputs_and_instruction(self) -> None:
        registry = RunRegistry()
        handle = _handle()
        handle.artifacts["intake"] = _record().model_dump()
        handle.artifacts["assessment"] = _summary().model_dump()
        revised = PortfolioFit(portfolio_area=TrackedField(value="HR & Payroll", kind="generated"))
        agent = Mock()

        with (
            patch("demand_portfolio_planning.runs.get_portfolio_agent", return_value=agent),
            patch(
                "demand_portfolio_planning.runs.fit_portfolio",
                new=AsyncMock(return_value=revised),
            ) as fit,
        ):
            result = await registry.revise(
                handle,
                step="portfolio",
                instruction="Emphasize payroll dependencies",
                language="en",
            )

        fit.assert_awaited_once()
        await_args = fit.await_args
        self.assertIsNotNone(await_args)
        assert await_args is not None
        args = await_args.args
        kwargs = await_args.kwargs
        self.assertIs(args[0], agent)
        self.assertIsInstance(args[1], DemandRecord)
        self.assertEqual(args[1].demand_title.value, "Payroll rollout")
        self.assertIsInstance(args[2], AssessmentSummary)
        self.assertEqual(args[3], "en")
        self.assertEqual(kwargs["instruction"], "Emphasize payroll dependencies")
        self.assertEqual(result["step"], "portfolio")
        self.assertEqual(result["artifact"], revised.model_dump())
        self.assertEqual(handle.artifacts["portfolio"], revised.model_dump())

    async def test_missing_inputs_raise_value_error(self) -> None:
        registry = RunRegistry()
        handle = _handle()
        handle.artifacts["intake"] = _record().model_dump()

        with self.assertRaisesRegex(ValueError, "assessment"):
            await registry.revise(
                handle,
                step="portfolio",
                instruction="Revise",
                language="de",
            )


    async def test_intake_revision_patches_existing_record(self) -> None:
        registry = RunRegistry()
        handle = _handle()
        handle.artifacts["intake"] = _record().model_dump()
        # The editor returns the full record with one field changed; untouched
        # fields must be preserved (no full re-derive from scratch).
        patched = _record()
        patched.portfolio_area = TrackedField(
            value="HR & Payroll", kind="fact", source="user input"
        )
        agent = Mock()

        with (
            patch("demand_portfolio_planning.runs.get_record_editor_agent", return_value=agent),
            patch(
                "demand_portfolio_planning.runs.edit_demand_record",
                new=AsyncMock(return_value=patched),
            ) as ed,
        ):
            result = await registry.revise(
                handle,
                step="intake",
                instruction="set portfolio area to HR & Payroll",
                language="en",
            )

        ed.assert_awaited_once()
        await_args = ed.await_args
        assert await_args is not None
        args = await_args.args
        self.assertIs(args[0], agent)
        self.assertIsInstance(args[1], DemandRecord)
        self.assertEqual(args[1].demand_title.value, "Payroll rollout")
        self.assertEqual(args[2], "set portfolio area to HR & Payroll")
        self.assertEqual(args[3], "en")
        self.assertEqual(result["step"], "intake")
        self.assertEqual(handle.artifacts["intake"]["portfolio_area"]["value"], "HR & Payroll")
        self.assertEqual(handle.artifacts["intake"]["demand_title"]["value"], "Payroll rollout")


if __name__ == "__main__":
    unittest.main()
