"""Typed artifacts, provenance primitives, and workflow messages.

Every business fact the agent surfaces carries provenance: a ``kind`` that marks
it as a confirmed fact, an assumption, an open question, generated content, or
``unknown``. This is the data-level expression of the demo's trust contract:
the agent never invents facts and never silently merges conflicts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# --------------------------------------------------------------------------- #
# Provenance primitives
# --------------------------------------------------------------------------- #

Kind = Literal["fact", "assumption", "open_question", "generated", "unknown"]
"""How much trust an output position carries, and where it came from."""

_VALID_KINDS: frozenset[str] = frozenset(
    ("fact", "assumption", "open_question", "generated", "unknown")
)


def _coerce_kind(value: object) -> object:
    """LLMs occasionally bleed a neighbouring enum (e.g. a readiness "missing")
    into a provenance ``kind``. Default any unrecognized value to ``unknown`` so
    one stray token never breaks a whole artifact — the trust contract only ever
    weakens, never fabricates."""
    return value if value in _VALID_KINDS else "unknown"

PreCheckStatus = Literal["ready", "more_info_needed", "blocked"]
BoardOutcome = Literal["approve_as_project", "already_solved", "reject"]
AllocationStatus = Literal["unassigned", "proposed", "confirmed", "conflict"]

# PRINCE2 (Agile Foundation) readiness themes the pre-check verifies before a
# demand may go to the board. Mapped to the "Starting Up a Project" readiness:
# is there a viable, worthwhile project to bring to the board?
PrinceTheme = Literal[
    "business_case",   # Why  – business justification / expected benefit
    "organization",    # Who  – process owner (executive) and key roles/SMEs
    "scope_product",   # What – scope and the main product/outcome described
    "plans_timeline",  # When – an indicative timeframe / target exists
    "risk",            # Risk – major risks, dependencies and conflicts surfaced
    "resources",       # Resources – needs and feasibility considered
]
PRINCE_THEMES: tuple[PrinceTheme, ...] = (
    "business_case",
    "organization",
    "scope_product",
    "plans_timeline",
    "risk",
    "resources",
)
ReadinessLevel = Literal["covered", "partial", "missing"]


class ReadinessCriterion(BaseModel):
    """One PRINCE2 readiness check against the Demand Record."""

    theme: PrinceTheme
    question: str = ""
    status: ReadinessLevel = "missing"
    finding: str = ""
    evidence: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, value: object) -> object:
        # Default any unrecognized level to "missing" so a stray value can never
        # make a demand look board-ready.
        return value if value in ("covered", "partial", "missing") else "missing"


class TrackedField(BaseModel):
    """A single scalar slot with provenance. ``value=None`` + ``unknown`` means
    the agent could not source it and must not guess."""

    value: str | None = None
    kind: Kind = "unknown"
    source: str | None = None

    _coerce_kind = field_validator("kind", mode="before")(staticmethod(_coerce_kind))


class TrackedItem(BaseModel):
    """A list entry with its own provenance."""

    value: str
    kind: Kind = "fact"
    source: str | None = None

    _coerce_kind = field_validator("kind", mode="before")(staticmethod(_coerce_kind))


class Conflict(BaseModel):
    """Contradictory source information, surfaced rather than merged."""

    field: str
    description: str
    values: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Trust-contract enforcement
#
# Provenance is not left to the model's goodwill: these helpers make the
# invariants deterministic so an empty slot can never render as a fact and an
# open-questions list always carries the open_question kind. Artifacts apply
# them in a post-construction validator, so the contract holds no matter who
# builds the object (LLM JSON, gate merges, or tests).
# --------------------------------------------------------------------------- #

_CONTENTFUL_KINDS: tuple[Kind, ...] = ("fact", "assumption", "generated")


def _normalize_field(field: TrackedField) -> TrackedField:
    """A field with no value cannot assert content. Blank values collapse to
    ``None`` and a contentful kind (fact/assumption/generated) on an empty value
    is demoted to ``unknown`` — so an empty slot never claims to be a fact."""
    value = field.value if field.value and field.value.strip() else None
    kind = "unknown" if value is None and field.kind in _CONTENTFUL_KINDS else field.kind
    if value == field.value and kind == field.kind:
        return field
    return TrackedField(value=value, kind=kind, source=field.source)


def _as_open_questions(items: list[TrackedItem]) -> list[TrackedItem]:
    """Every entry in an open-questions list is, by definition, an open question."""
    return [
        item
        if item.kind == "open_question"
        else TrackedItem(value=item.value, kind="open_question", source=item.source)
        for item in items
    ]


# --------------------------------------------------------------------------- #
# Source-system data (deterministically seeded mock systems of record)
# --------------------------------------------------------------------------- #


class SkillRating(BaseModel):
    skill: str
    level: Literal["beginner", "intermediate", "advanced", "expert"]


class Person(BaseModel):
    person_id: str
    name: str
    roles: list[str] = Field(default_factory=list)
    skills: list[SkillRating] = Field(default_factory=list)
    allocation_pct: int = 0
    commitments: list[str] = Field(default_factory=list)


class PortfolioProject(BaseModel):
    project_id: str
    name: str
    portfolio_area: str
    status: str
    owner: str | None = None
    roles: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    value: int = 3
    effort: int = 3
    urgency: int = 3


class SeedDemand(BaseModel):
    demand_id: str
    title: str
    raw_demand: str
    known_process_owner: str | None = None


# --------------------------------------------------------------------------- #
# Artifacts
# --------------------------------------------------------------------------- #


class DemandRecord(BaseModel):
    demand_title: TrackedField = Field(default_factory=TrackedField)
    business_requester: TrackedField = Field(default_factory=TrackedField)
    process_owner: TrackedField = Field(default_factory=TrackedField)
    business_demand: TrackedField = Field(default_factory=TrackedField)
    pain_point: TrackedField = Field(default_factory=TrackedField)
    portfolio_area: TrackedField = Field(default_factory=TrackedField)
    enterprise_architecture_context: TrackedField = Field(default_factory=TrackedField)
    workload_impact: TrackedField = Field(default_factory=TrackedField)
    resource_needs: TrackedField = Field(default_factory=TrackedField)
    timeline: TrackedField = Field(default_factory=TrackedField)
    documents: list[TrackedItem] = Field(default_factory=list)
    notes: list[TrackedItem] = Field(default_factory=list)
    subject_matter_experts: list[TrackedItem] = Field(default_factory=list)
    open_questions: list[TrackedItem] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    status: PreCheckStatus | None = None

    @model_validator(mode="after")
    def _enforce_trust_contract(self) -> DemandRecord:
        self.demand_title = _normalize_field(self.demand_title)
        self.business_requester = _normalize_field(self.business_requester)
        self.process_owner = _normalize_field(self.process_owner)
        self.business_demand = _normalize_field(self.business_demand)
        self.pain_point = _normalize_field(self.pain_point)
        self.portfolio_area = _normalize_field(self.portfolio_area)
        self.enterprise_architecture_context = _normalize_field(
            self.enterprise_architecture_context
        )
        self.workload_impact = _normalize_field(self.workload_impact)
        self.resource_needs = _normalize_field(self.resource_needs)
        self.timeline = _normalize_field(self.timeline)
        self.open_questions = _as_open_questions(self.open_questions)
        return self


class PreCheckReport(BaseModel):
    status: PreCheckStatus = "more_info_needed"
    demand_summary: str = ""
    readiness: list[ReadinessCriterion] = Field(default_factory=list)
    missing_information: list[TrackedItem] = Field(default_factory=list)
    required_smes: list[TrackedItem] = Field(default_factory=list)
    portfolio_context: TrackedField = Field(default_factory=TrackedField)
    workload_resource_notes: list[TrackedItem] = Field(default_factory=list)
    timeline_notes: list[TrackedItem] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_status(self) -> PreCheckReport:
        """Make readiness deterministic: a demand is only ``ready`` for the board
        when every PRINCE2 theme is covered. An explicit ``blocked`` (hard
        dependency/conflict) is preserved; otherwise the checklist decides."""
        if self.readiness and self.status != "blocked":
            levels = {c.theme: c.status for c in self.readiness}
            all_covered = all(levels.get(theme) == "covered" for theme in PRINCE_THEMES)
            self.status = "ready" if all_covered else "more_info_needed"
        return self


class AssessmentSummary(BaseModel):
    business_demand: str = ""
    process_context: TrackedField = Field(default_factory=TrackedField)
    confirmed_facts: list[TrackedItem] = Field(default_factory=list)
    assumptions: list[TrackedItem] = Field(default_factory=list)
    open_questions: list[TrackedItem] = Field(default_factory=list)
    pain_points: list[TrackedItem] = Field(default_factory=list)
    portfolio_fit: TrackedField = Field(default_factory=TrackedField)
    enterprise_architecture_context: TrackedField = Field(default_factory=TrackedField)
    sme_input: list[TrackedItem] = Field(default_factory=list)
    resource_allocation: TrackedField = Field(default_factory=TrackedField)
    timeline: TrackedField = Field(default_factory=TrackedField)
    risks_blockers: list[TrackedItem] = Field(default_factory=list)
    decisions_needed: list[TrackedItem] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_trust_contract(self) -> AssessmentSummary:
        self.process_context = _normalize_field(self.process_context)
        self.portfolio_fit = _normalize_field(self.portfolio_fit)
        self.enterprise_architecture_context = _normalize_field(
            self.enterprise_architecture_context
        )
        self.resource_allocation = _normalize_field(self.resource_allocation)
        self.timeline = _normalize_field(self.timeline)
        self.open_questions = _as_open_questions(self.open_questions)
        return self


class RelatedProject(BaseModel):
    project_id: str
    name: str
    relationship: str
    note: str | None = None
    kind: Kind = "generated"


class PortfolioFit(BaseModel):
    portfolio_area: TrackedField = Field(default_factory=TrackedField)
    capability_area: TrackedField = Field(default_factory=TrackedField)
    related_projects: list[RelatedProject] = Field(default_factory=list)
    dependencies_overlaps: list[TrackedItem] = Field(default_factory=list)
    transparency_notes: list[TrackedItem] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    person_id: str
    name: str
    role: str
    skill_match: str = ""
    skill_level: str | None = None
    availability_pct: int | None = None
    current_commitments: list[str] = Field(default_factory=list)
    fit_rationale: str = ""
    kind: Kind = "assumption"


class ResourceRow(BaseModel):
    role_or_skill: str
    requested_contribution: str = ""
    candidates: list[Candidate] = Field(default_factory=list)
    owner: str | None = None
    allocation_status: AllocationStatus = "unassigned"
    open_question: str | None = None


class ResourceMatch(BaseModel):
    rows: list[ResourceRow] = Field(default_factory=list)
    constraints: list[TrackedItem] = Field(default_factory=list)
    workload_conflicts: list[TrackedItem] = Field(default_factory=list)
    unassigned_work: list[TrackedItem] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class Milestone(BaseModel):
    label: str
    date: str | None = None
    status: str | None = None
    kind: Kind = "generated"


class TimelineDraft(BaseModel):
    precheck: str | None = None
    assessment: str | None = None
    planned_project_start: str | None = None
    milestones: list[Milestone] = Field(default_factory=list)
    missing_dates: list[TrackedItem] = Field(default_factory=list)
    resource_constraint_impact: list[TrackedItem] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class PriorityRankedItem(BaseModel):
    rank: int
    item_id: str
    name: str
    score: float
    value: int
    effort: int
    urgency: int
    resource_contention: int
    rationale: str = ""
    is_new_demand: bool = False


class PrioritySuggestion(BaseModel):
    new_demand_rank: int = 0
    total_items: int = 0
    ranked: list[PriorityRankedItem] = Field(default_factory=list)
    method: str = ""
    sources: list[str] = Field(default_factory=list)


class RoadmapEntry(BaseModel):
    """One project positioned on the portfolio roadmap."""

    project_id: str
    name: str
    portfolio_area: str
    status: str  # in_progress | proposed | new_demand
    start: str  # ISO date
    end: str  # ISO date
    indicative: bool = False  # dates derived/planned, not sourced from a system
    priority_rank: int | None = None
    is_new_demand: bool = False


class Roadmap(BaseModel):
    """Deterministic portfolio roadmap: every project on one timeline, with the
    proposed backlog sequenced by the prioritization model and the new demand
    inserted at its rank."""

    today: str = ""
    months: list[str] = Field(default_factory=list)  # "YYYY-MM" grid columns
    entries: list[RoadmapEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class WorkPackage(BaseModel):
    title: str
    description: str | None = None
    kind: Kind = "generated"


class HandoffTask(BaseModel):
    title: str
    owner: str | None = None
    source: str | None = None
    due_date: str | None = None
    status: str = "open"
    kind: Kind = "generated"


class ProjectPlanningHandoff(BaseModel):
    project_summary: str = ""
    scope: str = ""
    in_scope: list[TrackedItem] = Field(default_factory=list)
    out_of_scope: list[TrackedItem] = Field(default_factory=list)
    work_packages: list[WorkPackage] = Field(default_factory=list)
    tasks: list[HandoffTask] = Field(default_factory=list)
    documents_needed: list[TrackedItem] = Field(default_factory=list)
    decisions_needed: list[TrackedItem] = Field(default_factory=list)
    sme_input_needed: list[TrackedItem] = Field(default_factory=list)
    resource_allocation: ResourceMatch = Field(default_factory=ResourceMatch)
    timeline: TimelineDraft = Field(default_factory=TimelineDraft)
    priority: PrioritySuggestion = Field(default_factory=PrioritySuggestion)
    risks_blockers: list[TrackedItem] = Field(default_factory=list)
    open_questions: list[TrackedItem] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_trust_contract(self) -> ProjectPlanningHandoff:
        self.open_questions = _as_open_questions(self.open_questions)
        return self


# --------------------------------------------------------------------------- #
# Workflow messages (one type per hop so routing is unambiguous)
# --------------------------------------------------------------------------- #


class StartRequest(BaseModel):
    demand_id: str | None = None
    raw_demand: str | None = None
    language: str = "de"


class DemandResolved(BaseModel):
    language: str
    demand: SeedDemand


class PreCheckInput(BaseModel):
    language: str
    record: DemandRecord


class PreCheckResult(BaseModel):
    language: str
    record: DemandRecord
    report: PreCheckReport


class AssessmentInput(BaseModel):
    language: str
    record: DemandRecord
    report: PreCheckReport


class AssessmentResult(BaseModel):
    language: str
    record: DemandRecord
    report: PreCheckReport
    summary: AssessmentSummary


class ApprovedDemand(BaseModel):
    language: str
    record: DemandRecord
    summary: AssessmentSummary


class PortfolioResult(BaseModel):
    language: str
    record: DemandRecord
    summary: AssessmentSummary
    portfolio_fit: PortfolioFit


class ResourceResult(BaseModel):
    language: str
    record: DemandRecord
    summary: AssessmentSummary
    portfolio_fit: PortfolioFit
    resource_match: ResourceMatch


class PlanDraft(BaseModel):
    language: str
    draft: ProjectPlanningHandoff


# --------------------------------------------------------------------------- #
# Human-in-the-loop gates
# --------------------------------------------------------------------------- #


class PreCheckReview(BaseModel):
    language: str = "de"
    record: DemandRecord
    report: PreCheckReport


class PreCheckDecision(BaseModel):
    action: Literal["proceed", "provide_info", "block"]
    provided_fields: dict[str, str] = Field(default_factory=dict)
    reason: str | None = None
    # Optional full replacement record carried from the UI (chat/inline edits),
    # so the workflow commits the latest edited DemandRecord version.
    record: DemandRecord | None = None


class BoardReview(BaseModel):
    language: str = "de"
    record: DemandRecord
    summary: AssessmentSummary


class BoardDecision(BaseModel):
    outcome: BoardOutcome
    reason: str | None = None
    # Optional edited AssessmentSummary carried from the UI. Approving with it
    # makes the Board mirror the Pre-Check: the edited assessment generates Act 2.
    summary: AssessmentSummary | None = None


class HandoffReview(BaseModel):
    language: str = "de"
    draft: ProjectPlanningHandoff


class HandoffAdjustment(BaseModel):
    action: Literal["accept", "adjust"]
    adjusted_summary: str | None = None
    notes: str | None = None
    # Optional edited handoff draft carried from the UI.
    draft: ProjectPlanningHandoff | None = None


class ChatRouterOutput(BaseModel):
    """How the floating assistant decided to act on a user message."""

    reply: str = ""
    action: Literal["edit", "answer"] = "answer"
    instruction: str | None = None


class PlanningOutcome(BaseModel):
    status: Literal["handed_off", "already_solved", "rejected", "blocked"]
    reason: str | None = None
    handoff: ProjectPlanningHandoff | None = None
