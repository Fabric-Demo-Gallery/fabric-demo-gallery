// Mirrors the backend Pydantic artifacts (demand_portfolio_planning.models).

export type Kind = "fact" | "assumption" | "open_question" | "generated" | "unknown";
export type PreCheckStatus = "ready" | "more_info_needed" | "blocked";
export type BoardOutcome = "approve_as_project" | "already_solved" | "reject";
export type AllocationStatus = "unassigned" | "proposed" | "confirmed" | "conflict";

export interface TrackedField {
  value: string | null;
  kind: Kind;
  source: string | null;
}

export interface TrackedItem {
  value: string;
  kind: Kind;
  source: string | null;
}

export interface Conflict {
  field: string;
  description: string;
  values: string[];
  sources: string[];
}

export interface DemandRecord {
  demand_title: TrackedField;
  business_requester: TrackedField;
  process_owner: TrackedField;
  business_demand: TrackedField;
  pain_point: TrackedField;
  portfolio_area: TrackedField;
  enterprise_architecture_context: TrackedField;
  workload_impact: TrackedField;
  resource_needs: TrackedField;
  timeline: TrackedField;
  documents: TrackedItem[];
  notes: TrackedItem[];
  subject_matter_experts: TrackedItem[];
  open_questions: TrackedItem[];
  conflicts: Conflict[];
  sources: string[];
  status: PreCheckStatus | null;
}

export interface PreCheckReport {
  status: PreCheckStatus;
  demand_summary: string;
  readiness: ReadinessCriterion[];
  missing_information: TrackedItem[];
  required_smes: TrackedItem[];
  portfolio_context: TrackedField;
  workload_resource_notes: TrackedItem[];
  timeline_notes: TrackedItem[];
  rationale: string[];
  sources: string[];
}

export type PrinceTheme =
  | "business_case"
  | "organization"
  | "scope_product"
  | "plans_timeline"
  | "risk"
  | "resources";
export type ReadinessLevel = "covered" | "partial" | "missing";

export interface ReadinessCriterion {
  theme: PrinceTheme;
  question: string;
  status: ReadinessLevel;
  finding: string;
  evidence: string[];
}

export interface AssessmentSummary {
  business_demand: string;
  process_context: TrackedField;
  confirmed_facts: TrackedItem[];
  assumptions: TrackedItem[];
  open_questions: TrackedItem[];
  pain_points: TrackedItem[];
  portfolio_fit: TrackedField;
  enterprise_architecture_context: TrackedField;
  sme_input: TrackedItem[];
  resource_allocation: TrackedField;
  timeline: TrackedField;
  risks_blockers: TrackedItem[];
  decisions_needed: TrackedItem[];
  conflicts: Conflict[];
  sources: string[];
}

export interface RelatedProject {
  project_id: string;
  name: string;
  relationship: string;
  note: string | null;
  kind: Kind;
}

export interface PortfolioFit {
  portfolio_area: TrackedField;
  capability_area: TrackedField;
  related_projects: RelatedProject[];
  dependencies_overlaps: TrackedItem[];
  transparency_notes: TrackedItem[];
  conflicts: Conflict[];
  sources: string[];
}

export interface Candidate {
  person_id: string;
  name: string;
  role: string;
  skill_match: string;
  skill_level: string | null;
  availability_pct: number | null;
  current_commitments: string[];
  fit_rationale: string;
  kind: Kind;
}

export interface ResourceRow {
  role_or_skill: string;
  requested_contribution: string;
  candidates: Candidate[];
  owner: string | null;
  allocation_status: AllocationStatus;
  open_question: string | null;
}

export interface ResourceMatch {
  rows: ResourceRow[];
  constraints: TrackedItem[];
  workload_conflicts: TrackedItem[];
  unassigned_work: TrackedItem[];
  sources: string[];
}

export interface Milestone {
  label: string;
  date: string | null;
  status: string | null;
  kind: Kind;
}

export interface TimelineDraft {
  precheck: string | null;
  assessment: string | null;
  planned_project_start: string | null;
  milestones: Milestone[];
  missing_dates: TrackedItem[];
  resource_constraint_impact: TrackedItem[];
  sources: string[];
}

export interface PriorityRankedItem {
  rank: number;
  item_id: string;
  name: string;
  score: number;
  value: number;
  effort: number;
  urgency: number;
  resource_contention: number;
  rationale: string;
  is_new_demand: boolean;
}

export interface PrioritySuggestion {
  new_demand_rank: number;
  total_items: number;
  ranked: PriorityRankedItem[];
  method: string;
  sources: string[];
}

export interface WorkPackage {
  title: string;
  description: string | null;
  kind: Kind;
}

export interface HandoffTask {
  title: string;
  owner: string | null;
  source: string | null;
  due_date: string | null;
  status: string;
  kind: Kind;
}

export interface ProjectPlanningHandoff {
  project_summary: string;
  scope: string;
  in_scope: TrackedItem[];
  out_of_scope: TrackedItem[];
  work_packages: WorkPackage[];
  tasks: HandoffTask[];
  documents_needed: TrackedItem[];
  decisions_needed: TrackedItem[];
  sme_input_needed: TrackedItem[];
  resource_allocation: ResourceMatch;
  timeline: TimelineDraft;
  priority: PrioritySuggestion;
  risks_blockers: TrackedItem[];
  open_questions: TrackedItem[];
  conflicts: Conflict[];
  sources: string[];
}

export interface PlanningOutcome {
  status: "handed_off" | "already_solved" | "rejected" | "blocked";
  reason: string | null;
  handoff: ProjectPlanningHandoff | null;
}

// Gate request payloads (data carried on `awaiting` events).
export interface PreCheckReview {
  language: string;
  record: DemandRecord;
  report: PreCheckReport;
}

export interface BoardReview {
  language: string;
  record: DemandRecord;
  summary: AssessmentSummary;
}

export interface HandoffReview {
  language: string;
  draft: ProjectPlanningHandoff;
}

// Seed source-system data for the context panels.
export interface SkillRating {
  skill: string;
  level: string;
}

export interface Person {
  person_id: string;
  name: string;
  roles: string[];
  skills: SkillRating[];
  allocation_pct: number;
  commitments: string[];
}

export interface PortfolioProject {
  project_id: string;
  name: string;
  portfolio_area: string;
  status: string;
  owner: string | null;
  roles: string[];
  start: string | null;
  end: string | null;
  value: number;
  effort: number;
  urgency: number;
}

export interface SeedDemand {
  demand_id: string;
  title: string;
  raw_demand: string;
  known_process_owner: string | null;
}

export interface SeedData {
  portfolio: PortfolioProject[];
  resource_pool: Person[];
  skill_matrix: Record<string, { person_id: string; name: string; level: string }[]>;
  demands: SeedDemand[];
}

export interface RoadmapEntry {
  project_id: string;
  name: string;
  portfolio_area: string;
  status: string; // in_progress | proposed | new_demand
  start: string;
  end: string;
  indicative: boolean;
  priority_rank: number | null;
  is_new_demand: boolean;
}

export interface Roadmap {
  today: string;
  months: string[]; // "YYYY-MM"
  entries: RoadmapEntry[];
  notes: string[];
  sources: string[];
}
