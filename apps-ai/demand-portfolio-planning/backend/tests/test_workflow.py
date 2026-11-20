import unittest

from agent_framework import WorkflowRunState

from demand_portfolio_planning.models import (
    AssessmentSummary,
    BoardDecision,
    Candidate,
    DemandRecord,
    HandoffAdjustment,
    PortfolioFit,
    PreCheckDecision,
    PreCheckReport,
    ProjectPlanningHandoff,
    ResourceMatch,
    ResourceRow,
    SeedDemand,
    StartRequest,
    TrackedField,
    TrackedItem,
    WorkPackage,
)
from demand_portfolio_planning.workflow import (
    BOARD_REQUEST_ID,
    HANDOFF_REQUEST_ID,
    PRECHECK_REQUEST_ID,
    build_workflow,
)


async def fake_structure(demand: SeedDemand, language: str) -> DemandRecord:
    return DemandRecord(
        demand_title=TrackedField(value=demand.title, kind="fact", source="Demand-Eingabe"),
        process_owner=TrackedField(
            value=demand.known_process_owner, kind="fact", source="Demand-Eingabe"
        ),
        business_demand=TrackedField(value=demand.raw_demand[:40], kind="fact"),
        portfolio_area=TrackedField(kind="unknown"),
        timeline=TrackedField(kind="unknown"),
        subject_matter_experts=[TrackedItem(value="HR Process Owner", kind="fact")],
        open_questions=[TrackedItem(value="Portfolio area?", kind="open_question")],
        sources=["Demand-Eingabe"],
    )


async def fake_precheck(record: DemandRecord, language: str) -> PreCheckReport:
    return PreCheckReport(
        status="more_info_needed",
        demand_summary="Local payroll system introduction.",
        missing_information=[TrackedItem(value="portfolio_area", kind="open_question")],
        required_smes=[TrackedItem(value="SAP FI expert", kind="assumption")],
    )


async def fake_assessment(
    record: DemandRecord, report: PreCheckReport, language: str
) -> AssessmentSummary:
    return AssessmentSummary(
        business_demand="Introduce a local payroll system.",
        confirmed_facts=[TrackedItem(value="Payroll is local", kind="fact")],
        assumptions=[TrackedItem(value="SAP FI integration likely", kind="assumption")],
        open_questions=[TrackedItem(value="Is SAP FI in scope?", kind="open_question")],
    )


async def fake_portfolio(
    record: DemandRecord, summary: AssessmentSummary, language: str
) -> PortfolioFit:
    return PortfolioFit(
        portfolio_area=TrackedField(value="HR & Payroll", kind="assumption"),
    )


async def fake_resources(
    record: DemandRecord,
    summary: AssessmentSummary,
    fit: PortfolioFit,
    language: str,
) -> ResourceMatch:
    return ResourceMatch(
        rows=[
            ResourceRow(
                role_or_skill="SAP FI Specialist",
                requested_contribution="Payment run integration",
                candidates=[
                    Candidate(
                        person_id="p-anders",
                        name="Alex Anders",
                        role="SAP FI Specialist",
                        fit_rationale="expert, but 90% allocated",
                        availability_pct=10,
                    )
                ],
                allocation_status="conflict",
            ),
            ResourceRow(
                role_or_skill="HR Systems Specialist",
                requested_contribution="SuccessFactors integration",
                allocation_status="proposed",
            ),
        ],
        workload_conflicts=[TrackedItem(value="SAP FI over-committed", kind="fact")],
    )


async def fake_plan(
    record: DemandRecord,
    summary: AssessmentSummary,
    fit: PortfolioFit,
    match: ResourceMatch,
    language: str,
) -> ProjectPlanningHandoff:
    return ProjectPlanningHandoff(
        project_summary="Introduce a local payroll system with HR/ERP integrations.",
        scope="Local payroll go-live for one country.",
        in_scope=[TrackedItem(value="Payroll configuration", kind="generated")],
        out_of_scope=[TrackedItem(value="Central payroll approach", kind="generated")],
        work_packages=[WorkPackage(title="Integration design")],
    )


class _Counting:
    """Wrap a fake callable and count invocations (memoization checks)."""

    def __init__(self, fn: object) -> None:
        self._fn = fn
        self.calls = 0

    async def __call__(self, *args: object) -> object:
        self.calls += 1
        return await self._fn(*args)  # type: ignore[operator]


def _build(**overrides: object) -> object:
    kwargs: dict[str, object] = {
        "structure_demand": fake_structure,
        "evaluate_precheck": fake_precheck,
        "run_assessment": fake_assessment,
        "fit_portfolio": fake_portfolio,
        "match_resources": fake_resources,
        "draft_plan": fake_plan,
    }
    kwargs.update(overrides)
    return build_workflow(**kwargs)  # type: ignore[arg-type]


def _start() -> StartRequest:
    return StartRequest(demand_id="payroll-local", language="de")


class WorkflowGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_pauses_at_precheck_gate(self) -> None:
        wf = _build()
        result = await wf.run(_start())  # type: ignore[attr-defined]
        self.assertEqual(result.get_final_state(), WorkflowRunState.IDLE_WITH_PENDING_REQUESTS)
        pending = result.get_request_info_events()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].request_id, PRECHECK_REQUEST_ID)
        self.assertIn("Payroll", pending[0].data.record.demand_title.value)
        self.assertEqual(pending[0].data.report.status, "more_info_needed")

    async def test_full_pipeline_hands_off(self) -> None:
        wf = _build()
        await wf.run(_start())  # type: ignore[attr-defined]
        await wf.run(responses={PRECHECK_REQUEST_ID: PreCheckDecision(action="proceed")})  # type: ignore[attr-defined]
        board = await wf.run(  # type: ignore[attr-defined]
            responses={BOARD_REQUEST_ID: BoardDecision(outcome="approve_as_project")}
        )
        self.assertEqual(board.get_final_state(), WorkflowRunState.IDLE_WITH_PENDING_REQUESTS)
        self.assertEqual(board.get_request_info_events()[0].request_id, HANDOFF_REQUEST_ID)

        final = await wf.run(  # type: ignore[attr-defined]
            responses={HANDOFF_REQUEST_ID: HandoffAdjustment(action="accept")}
        )
        self.assertEqual(final.get_final_state(), WorkflowRunState.IDLE)
        outcome = final.get_outputs()[0]
        self.assertEqual(outcome.status, "handed_off")
        handoff = outcome.handoff
        self.assertIsNotNone(handoff)
        # Deterministic priority injected, not fabricated by the LLM.
        self.assertGreaterEqual(handoff.priority.new_demand_rank, 1)
        self.assertLessEqual(handoff.priority.new_demand_rank, handoff.priority.total_items)
        self.assertTrue(handoff.priority.method)
        self.assertTrue(any(i.is_new_demand for i in handoff.priority.ranked))
        # Resource match injected verbatim.
        self.assertEqual(len(handoff.resource_allocation.rows), 2)
        # Timeline markers stamped for steps that actually ran.
        self.assertIsNotNone(handoff.timeline.precheck)
        self.assertIsNotNone(handoff.timeline.assessment)

    async def test_precheck_block_ends_run(self) -> None:
        wf = _build()
        await wf.run(_start())  # type: ignore[attr-defined]
        final = await wf.run(  # type: ignore[attr-defined]
            responses={
                PRECHECK_REQUEST_ID: PreCheckDecision(action="block", reason="Too vague")
            }
        )
        self.assertEqual(final.get_final_state(), WorkflowRunState.IDLE)
        outcome = final.get_outputs()[0]
        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(outcome.reason, "Too vague")
        self.assertIsNone(outcome.handoff)

    async def test_board_reject_ends_run(self) -> None:
        wf = _build()
        await wf.run(_start())  # type: ignore[attr-defined]
        await wf.run(responses={PRECHECK_REQUEST_ID: PreCheckDecision(action="proceed")})  # type: ignore[attr-defined]
        final = await wf.run(  # type: ignore[attr-defined]
            responses={
                BOARD_REQUEST_ID: BoardDecision(outcome="reject", reason="No budget")
            }
        )
        outcome = final.get_outputs()[0]
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.reason, "No budget")

    async def test_board_already_solved_ends_run(self) -> None:
        wf = _build()
        await wf.run(_start())  # type: ignore[attr-defined]
        await wf.run(responses={PRECHECK_REQUEST_ID: PreCheckDecision(action="proceed")})  # type: ignore[attr-defined]
        final = await wf.run(  # type: ignore[attr-defined]
            responses={BOARD_REQUEST_ID: BoardDecision(outcome="already_solved")}
        )
        self.assertEqual(final.get_outputs()[0].status, "already_solved")

    async def test_provide_info_reruns_precheck_and_returns_to_gate(self) -> None:
        class CapturingPrecheck:
            def __init__(self) -> None:
                self.records: list[DemandRecord] = []

            async def __call__(self, record: DemandRecord, language: str) -> PreCheckReport:
                self.records.append(record)
                return await fake_precheck(record, language)

        cp = CapturingPrecheck()
        wf = _build(evaluate_precheck=cp)
        await wf.run(_start())  # type: ignore[attr-defined]
        self.assertEqual(len(cp.records), 1)

        result = await wf.run(  # type: ignore[attr-defined]
            responses={
                PRECHECK_REQUEST_ID: PreCheckDecision(
                    action="provide_info",
                    provided_fields={"portfolio_area": "HR & Payroll"},
                )
            }
        )
        # Providing info re-runs the pre-check and re-suspends (it does not
        # auto-advance). The re-issued same-id request is not surfaced via
        # get_request_info_events(), so assert on state + the re-run instead.
        self.assertEqual(result.get_final_state(), WorkflowRunState.IDLE_WITH_PENDING_REQUESTS)
        self.assertEqual(len(cp.records), 2)
        # The merged human-provided fact reached the re-run.
        self.assertEqual(cp.records[1].portfolio_area.value, "HR & Payroll")
        self.assertEqual(cp.records[1].portfolio_area.kind, "fact")
        # The now-answered open question about the portfolio area is retired.
        self.assertFalse(
            any("portfolio" in q.value.lower() for q in cp.records[1].open_questions)
        )

        # An explicit proceed then advances to the board.
        final = await wf.run(  # type: ignore[attr-defined]
            responses={PRECHECK_REQUEST_ID: PreCheckDecision(action="proceed")}
        )
        self.assertEqual(final.get_request_info_events()[0].request_id, BOARD_REQUEST_ID)

    async def test_no_redundant_llm_calls_on_resume(self) -> None:
        intake = _Counting(fake_structure)
        precheck = _Counting(fake_precheck)
        wf = _build(structure_demand=intake, evaluate_precheck=precheck)
        await wf.run(_start())  # type: ignore[attr-defined]
        self.assertEqual(intake.calls, 1)
        self.assertEqual(precheck.calls, 1)
        await wf.run(responses={PRECHECK_REQUEST_ID: PreCheckDecision(action="proceed")})  # type: ignore[attr-defined]
        # Upstream LLM steps must not re-run when the gate resumes.
        self.assertEqual(intake.calls, 1)
        self.assertEqual(precheck.calls, 1)


if __name__ == "__main__":
    unittest.main()
