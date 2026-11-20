"""The demand-portfolio-planning workflow.

A Microsoft Agent Framework workflow of small executors. LLM steps each sit in
their own superstep so live stage events stream to the UI. Three human gates use
``ctx.request_info`` to suspend the workflow until a person decides — no demand is
ever auto-approved or auto-rejected.

Act 1: intake -> pre-check -> 🚪 pre-check gate -> assessment -> 🚪 board gate
Act 2: portfolio fit -> resource match -> plan draft -> 🚪 handoff gate -> handoff
"""

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, Literal

from agent_framework import (
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
    response_handler,
)

from demand_portfolio_planning.models import (
    ApprovedDemand,
    AssessmentInput,
    AssessmentResult,
    AssessmentSummary,
    BoardDecision,
    BoardReview,
    DemandRecord,
    DemandResolved,
    HandoffAdjustment,
    HandoffReview,
    PlanDraft,
    PlanningOutcome,
    PortfolioFit,
    PortfolioResult,
    PreCheckDecision,
    PreCheckInput,
    PreCheckReport,
    PreCheckResult,
    PreCheckReview,
    ProjectPlanningHandoff,
    ResourceMatch,
    ResourceResult,
    SeedDemand,
    StartRequest,
    TrackedField,
)
from demand_portfolio_planning.prioritization import rank_backlog
from demand_portfolio_planning.sources import get_seed_demand
from demand_portfolio_planning.timeline import build_prince2_timeline

# Injected so tests can swap in fakes without touching Foundry.
DemandStructurer = Callable[[SeedDemand, str], Awaitable[DemandRecord]]
PreCheckEvaluator = Callable[[DemandRecord, str], Awaitable[PreCheckReport]]
AssessmentRunner = Callable[[DemandRecord, PreCheckReport, str], Awaitable[AssessmentSummary]]
PortfolioFitter = Callable[[DemandRecord, AssessmentSummary, str], Awaitable[PortfolioFit]]
ResourceMatcher = Callable[
    [DemandRecord, AssessmentSummary, PortfolioFit, str], Awaitable[ResourceMatch]
]
PlanDrafter = Callable[
    [DemandRecord, AssessmentSummary, PortfolioFit, ResourceMatch, str],
    Awaitable[ProjectPlanningHandoff],
]

PRECHECK_REQUEST_ID = "precheck_review"
BOARD_REQUEST_ID = "board_decision"
HANDOFF_REQUEST_ID = "handoff_review"

# Demand record TrackedField slots a human may fill or correct at the pre-check
# gate (sent as provided_fields). Covers every scalar field on the record so a
# direct edit on the Demand Record always flows back into the workflow.
_FILLABLE_FIELDS = {
    "demand_title",
    "business_requester",
    "process_owner",
    "business_demand",
    "pain_point",
    "portfolio_area",
    "enterprise_architecture_context",
    "workload_impact",
    "resource_needs",
    "timeline",
}


def _stage_event(executor_id: str, stage: str, **payload: Any) -> WorkflowEvent[dict[str, Any]]:
    return WorkflowEvent.emit(executor_id, {"stage": stage, **payload})


def _source_label(language: str) -> str:
    return "user input" if language == "en" else "Nutzereingabe"


class BootstrapExecutor(Executor):
    """Fast start executor: resolve the seeded demand and forward (no LLM)."""

    def __init__(self) -> None:
        super().__init__(id="bootstrap")

    @handler
    async def start(
        self, request: StartRequest, ctx: WorkflowContext[DemandResolved]
    ) -> None:
        demand = _resolve_demand(request)
        await ctx.add_event(_stage_event(self.id, "run_started", title=demand.title))
        await ctx.send_message(DemandResolved(language=request.language, demand=demand))


class IntakeExecutor(Executor):
    def __init__(self, *, structure_demand: DemandStructurer) -> None:
        super().__init__(id="intake")
        self._structure = structure_demand

    @handler
    async def run(
        self, message: DemandResolved, ctx: WorkflowContext[PreCheckInput]
    ) -> None:
        await ctx.add_event(_stage_event(self.id, "intake"))
        record = await self._structure(message.demand, message.language)
        await ctx.add_event(_stage_event(self.id, "demand_record", record=record.model_dump()))
        await ctx.send_message(PreCheckInput(language=message.language, record=record))


class PreCheckEvalExecutor(Executor):
    def __init__(self, *, evaluate_precheck: PreCheckEvaluator) -> None:
        super().__init__(id="precheck")
        self._evaluate = evaluate_precheck

    @handler
    async def run(
        self, message: PreCheckInput, ctx: WorkflowContext[PreCheckResult]
    ) -> None:
        await ctx.add_event(_stage_event(self.id, "precheck"))
        report = await self._evaluate(message.record, message.language)
        record = message.record.model_copy(deep=True)
        record.status = report.status
        await ctx.add_event(
            _stage_event(
                self.id,
                "precheck_report",
                report=report.model_dump(),
                record=record.model_dump(),
            )
        )
        await ctx.send_message(
            PreCheckResult(language=message.language, record=record, report=report)
        )


class PreCheckGateExecutor(Executor):
    """🚪 Pre-check gate: proceed, supply missing info, or block."""

    def __init__(self) -> None:
        super().__init__(id="precheck_gate")

    @handler
    async def request(
        self,
        message: PreCheckResult,
        ctx: WorkflowContext[PreCheckInput | AssessmentInput, PlanningOutcome],
    ) -> None:
        await ctx.request_info(
            PreCheckReview(
                language=message.language, record=message.record, report=message.report
            ),
            response_type=PreCheckDecision,
            request_id=PRECHECK_REQUEST_ID,
        )

    @response_handler
    async def on_decision(
        self,
        original_request: PreCheckReview,
        response: PreCheckDecision,
        ctx: WorkflowContext[PreCheckInput | AssessmentInput, PlanningOutcome],
    ) -> None:
        language = original_request.language
        # The UI may carry the latest edited DemandRecord (chat/inline edits);
        # that replacement is the source of truth so edits commit into the flow.
        record = (response.record or original_request.record).model_copy(deep=True)
        report = original_request.report.model_copy(deep=True)

        if response.action == "block":
            await ctx.add_event(_stage_event(self.id, "blocked", reason=response.reason))
            await ctx.yield_output(
                PlanningOutcome(status="blocked", reason=response.reason)
            )
            return

        if response.action == "provide_info":
            # Supplying info does not auto-advance: merge the human-provided
            # facts, then re-run the pre-check and return to this gate so the
            # reviewer can iterate. Only an explicit "proceed" moves forward.
            if response.provided_fields:
                _apply_provided_fields(record, response.provided_fields, language)
            await ctx.send_message(PreCheckInput(language=language, record=record))
            return

        await ctx.send_message(
            AssessmentInput(language=language, record=record, report=report)
        )


class AssessmentExecutor(Executor):
    def __init__(self, *, run_assessment: AssessmentRunner) -> None:
        super().__init__(id="assessment")
        self._assess = run_assessment

    @handler
    async def run(
        self, message: AssessmentInput, ctx: WorkflowContext[AssessmentResult]
    ) -> None:
        await ctx.add_event(_stage_event(self.id, "assessment"))
        summary = await self._assess(message.record, message.report, message.language)
        await ctx.add_event(
            _stage_event(self.id, "assessment_summary", summary=summary.model_dump())
        )
        await ctx.send_message(
            AssessmentResult(
                language=message.language,
                record=message.record,
                report=message.report,
                summary=summary,
            )
        )


class BoardGateExecutor(Executor):
    """🚪 Board gate: approve as project, already solved, or reject."""

    def __init__(self) -> None:
        super().__init__(id="board_gate")

    @handler
    async def request(
        self, message: AssessmentResult, ctx: WorkflowContext[ApprovedDemand, PlanningOutcome]
    ) -> None:
        await ctx.request_info(
            BoardReview(
                language=message.language, record=message.record, summary=message.summary
            ),
            response_type=BoardDecision,
            request_id=BOARD_REQUEST_ID,
        )

    @response_handler
    async def on_decision(
        self,
        original_request: BoardReview,
        response: BoardDecision,
        ctx: WorkflowContext[ApprovedDemand, PlanningOutcome],
    ) -> None:
        language = original_request.language
        if response.outcome == "approve_as_project":
            # Board mirrors Pre-Check: approving with an edited AssessmentSummary
            # makes that edited version generate all of Act 2.
            summary = response.summary or original_request.summary
            await ctx.add_event(_stage_event(self.id, "approved"))
            await ctx.send_message(
                ApprovedDemand(
                    language=language,
                    record=original_request.record,
                    summary=summary,
                )
            )
            return

        status: Literal["already_solved", "rejected"] = (
            "already_solved" if response.outcome == "already_solved" else "rejected"
        )
        await ctx.add_event(_stage_event(self.id, status, reason=response.reason))
        await ctx.yield_output(PlanningOutcome(status=status, reason=response.reason))


class PortfolioExecutor(Executor):
    def __init__(self, *, fit_portfolio: PortfolioFitter) -> None:
        super().__init__(id="portfolio")
        self._fit = fit_portfolio

    @handler
    async def run(
        self, message: ApprovedDemand, ctx: WorkflowContext[PortfolioResult]
    ) -> None:
        await ctx.add_event(_stage_event(self.id, "portfolio"))
        fit = await self._fit(message.record, message.summary, message.language)
        await ctx.add_event(_stage_event(self.id, "portfolio_fit", portfolio_fit=fit.model_dump()))
        await ctx.send_message(
            PortfolioResult(
                language=message.language,
                record=message.record,
                summary=message.summary,
                portfolio_fit=fit,
            )
        )


class ResourceExecutor(Executor):
    def __init__(self, *, match_resources: ResourceMatcher) -> None:
        super().__init__(id="resource")
        self._match = match_resources

    @handler
    async def run(
        self, message: PortfolioResult, ctx: WorkflowContext[ResourceResult]
    ) -> None:
        await ctx.add_event(_stage_event(self.id, "resource"))
        match = await self._match(
            message.record, message.summary, message.portfolio_fit, message.language
        )
        await ctx.add_event(
            _stage_event(self.id, "resource_match", resource_match=match.model_dump())
        )
        await ctx.send_message(
            ResourceResult(
                language=message.language,
                record=message.record,
                summary=message.summary,
                portfolio_fit=message.portfolio_fit,
                resource_match=match,
            )
        )


class PlanExecutor(Executor):
    """Generate the handoff draft, then inject the deterministic priority + timeline
    markers the LLM must not fabricate."""

    def __init__(self, *, draft_plan: PlanDrafter) -> None:
        super().__init__(id="plan")
        self._draft = draft_plan

    @handler
    async def run(
        self, message: ResourceResult, ctx: WorkflowContext[PlanDraft]
    ) -> None:
        await ctx.add_event(_stage_event(self.id, "planning"))
        handoff = await self._draft(
            message.record,
            message.summary,
            message.portfolio_fit,
            message.resource_match,
            message.language,
        )

        handoff.resource_allocation = message.resource_match

        title = message.record.demand_title.value or (
            "New demand" if message.language == "en" else "Neue Demand"
        )
        roles = [row.role_or_skill for row in message.resource_match.rows]
        handoff.priority = rank_backlog(
            new_demand_id="new-demand",
            new_demand_name=title,
            value=3,
            effort=3,
            urgency=3,
            roles=roles,
            language=message.language,
        )

        today = date.today().isoformat()
        # Inject a deterministic PRINCE2 stage timeline with concrete indicative
        # dates so the plan never shows "open"; keep any planner constraint notes.
        constraint_impact = handoff.timeline.resource_constraint_impact
        handoff.timeline = build_prince2_timeline(
            message.language, precheck=today, assessment=today
        )
        handoff.timeline.resource_constraint_impact = constraint_impact

        await ctx.add_event(_stage_event(self.id, "plan_draft", draft=handoff.model_dump()))
        await ctx.send_message(PlanDraft(language=message.language, draft=handoff))


class HandoffGateExecutor(Executor):
    """🚪 Handoff gate: accept the plan or adjust before handing off."""

    def __init__(self) -> None:
        super().__init__(id="handoff_gate")

    @handler
    async def request(
        self, message: PlanDraft, ctx: WorkflowContext[Any, PlanningOutcome]
    ) -> None:
        await ctx.request_info(
            HandoffReview(language=message.language, draft=message.draft),
            response_type=HandoffAdjustment,
            request_id=HANDOFF_REQUEST_ID,
        )

    @response_handler
    async def on_decision(
        self,
        original_request: HandoffReview,
        response: HandoffAdjustment,
        ctx: WorkflowContext[Any, PlanningOutcome],
    ) -> None:
        language = original_request.language
        # The UI may carry the latest edited handoff draft (chat edits).
        base = response.draft or original_request.draft
        handoff = base.model_copy(deep=True)
        if response.action == "adjust":
            if response.adjusted_summary:
                handoff.project_summary = response.adjusted_summary
            if response.notes:
                handoff.sources.append(f"{_source_label(language)}: {response.notes}")
        await ctx.add_event(_stage_event(self.id, "handed_off", handoff=handoff.model_dump()))
        await ctx.yield_output(PlanningOutcome(status="handed_off", handoff=handoff))


def _resolve_demand(request: StartRequest) -> SeedDemand:
    if request.demand_id:
        demand = get_seed_demand(request.demand_id)
        if demand is None:
            raise ValueError(f"unknown demand_id: {request.demand_id}")
        return demand
    if request.raw_demand:
        first_line = request.raw_demand.strip().splitlines()[0]
        title = first_line[:80] if first_line else "Custom demand"
        return SeedDemand(demand_id="custom", title=title, raw_demand=request.raw_demand)
    raise ValueError("StartRequest needs demand_id or raw_demand")


# Keywords used to retire an open question once the related field is supplied,
# so the Demand Record does not keep showing a question the human just answered.
_FIELD_QUESTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "portfolio_area": ("portfolio",),
    "process_owner": ("process owner", "prozessverantwort", "verantwortlich"),
    "timeline": ("timeline", "zeitrahmen", "zeitplan", "zeitlich"),
    "resource_needs": ("ressource", "resource"),
    "workload_impact": ("workload", "auslastung", "arbeitslast"),
    "enterprise_architecture_context": ("architektur", "architecture"),
    "business_requester": ("anforderer", "requester"),
    "pain_point": ("painpoint", "schmerzpunkt"),
}


def _apply_provided_fields(
    record: DemandRecord, provided: dict[str, str], language: str
) -> None:
    source = _source_label(language)
    answered: list[str] = []
    for field, value in provided.items():
        if field in _FILLABLE_FIELDS and value:
            setattr(record, field, TrackedField(value=value, kind="fact", source=source))
            answered.append(field)

    # Retire open questions that are clearly about a field the human just filled.
    keywords = tuple(kw for f in answered for kw in _FIELD_QUESTION_KEYWORDS.get(f, ()))
    if keywords:
        record.open_questions = [
            q for q in record.open_questions if not any(kw in q.value.lower() for kw in keywords)
        ]


def build_workflow(
    *,
    structure_demand: DemandStructurer,
    evaluate_precheck: PreCheckEvaluator,
    run_assessment: AssessmentRunner,
    fit_portfolio: PortfolioFitter,
    match_resources: ResourceMatcher,
    draft_plan: PlanDrafter,
) -> Workflow:
    bootstrap = BootstrapExecutor()
    intake = IntakeExecutor(structure_demand=structure_demand)
    precheck = PreCheckEvalExecutor(evaluate_precheck=evaluate_precheck)
    precheck_gate = PreCheckGateExecutor()
    assessment = AssessmentExecutor(run_assessment=run_assessment)
    board_gate = BoardGateExecutor()
    portfolio = PortfolioExecutor(fit_portfolio=fit_portfolio)
    resource = ResourceExecutor(match_resources=match_resources)
    plan = PlanExecutor(draft_plan=draft_plan)
    handoff_gate = HandoffGateExecutor()

    return (
        WorkflowBuilder(start_executor=bootstrap, name="demand_portfolio_planning")
        .add_edge(bootstrap, intake)
        .add_edge(intake, precheck)
        .add_edge(precheck, precheck_gate)
        .add_edge(precheck_gate, precheck)
        .add_edge(precheck_gate, assessment)
        .add_edge(assessment, board_gate)
        .add_edge(board_gate, portfolio)
        .add_edge(portfolio, resource)
        .add_edge(resource, plan)
        .add_edge(plan, handoff_gate)
        .build()
    )
