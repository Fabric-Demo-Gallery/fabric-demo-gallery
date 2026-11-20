import type {
  AssessmentSummary,
  BoardOutcome,
  BoardReview,
  DemandRecord,
  HandoffReview,
  PlanningOutcome,
  PortfolioFit,
  PreCheckReport,
  PreCheckReview,
  ProjectPlanningHandoff,
  ResourceMatch,
  Roadmap,
  SeedData,
} from "./types";

const BASE = "";

export type StageEvent =
  | { type: "stage"; stage: "run_started"; title: string }
  | {
      type: "stage";
      stage: "intake" | "precheck" | "assessment" | "portfolio" | "resource" | "planning" | "approved";
    }
  | { type: "stage"; stage: "demand_record"; record: DemandRecord }
  | { type: "stage"; stage: "precheck_report"; report: PreCheckReport; record: DemandRecord }
  | { type: "stage"; stage: "precheck_updated"; report: PreCheckReport; record: DemandRecord }
  | { type: "stage"; stage: "assessment_summary"; summary: AssessmentSummary }
  | { type: "stage"; stage: "portfolio_fit"; portfolio_fit: PortfolioFit }
  | { type: "stage"; stage: "resource_match"; resource_match: ResourceMatch }
  | { type: "stage"; stage: "plan_draft"; draft: ProjectPlanningHandoff }
  | { type: "stage"; stage: "blocked" | "already_solved" | "rejected"; reason?: string | null }
  | { type: "stage"; stage: "handed_off"; handoff: ProjectPlanningHandoff }
  | {
      type: "awaiting";
      gate: string;
      request_id: string;
      request: PreCheckReview | BoardReview | HandoffReview;
      versions?: Record<string, number>;
    }
  | { type: "outcome"; outcome: PlanningOutcome }
  | { type: "error"; message: string };

export type PreCheckDecision =
  | { action: "proceed"; record?: DemandRecord }
  | { action: "provide_info"; provided_fields: Record<string, string>; record?: DemandRecord }
  | { action: "block"; reason?: string };

export type BoardDecision = { outcome: BoardOutcome; reason?: string; summary?: AssessmentSummary };

export type HandoffAdjustment =
  | { action: "accept"; draft?: ProjectPlanningHandoff }
  | { action: "adjust"; adjusted_summary?: string; notes?: string; draft?: ProjectPlanningHandoff };

export type Decision = PreCheckDecision | BoardDecision | HandoffAdjustment;

export interface ChatUpdate {
  step: string;
  artifact: unknown;
  version: number;
}

export interface ChatResponse {
  reply: string;
  action: "edit" | "answer";
  updates: ChatUpdate[];
}

export async function sendChat(
  run_id: string,
  message: string,
  viewing: string,
  language: string,
): Promise<ChatResponse> {
  const r = await fetch(`${BASE}/runs/${run_id}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message, viewing, language }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ChatResponse;
}

export async function fetchSeedData(): Promise<SeedData> {
  const r = await fetch(`${BASE}/api/seed-data`);
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as SeedData;
}

export async function fetchRoadmap(language: string, runId?: string | null): Promise<Roadmap> {
  const params = new URLSearchParams({ lang: language });
  if (runId) params.set("run_id", runId);
  const r = await fetch(`${BASE}/api/roadmap?${params.toString()}`);
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Roadmap;
}

export async function startRun(
  demand_id: string,
  language: string,
  raw_demand?: string,
): Promise<string> {
  const r = await fetch(`${BASE}/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ demand_id: raw_demand ? null : demand_id, raw_demand, language }),
  });
  if (!r.ok) throw new Error(await r.text());
  return ((await r.json()) as { run_id: string }).run_id;
}

export function openEventStream(
  run_id: string,
  onEvent: (event: StageEvent) => void,
  onEnd: () => void,
  onError: (err: unknown) => void,
): () => void {
  const source = new EventSource(`${BASE}/runs/${run_id}/events`);
  source.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data) as StageEvent);
    } catch (err) {
      onError(err);
    }
  };
  source.addEventListener("end", () => {
    source.close();
    onEnd();
  });
  source.onerror = (err) => {
    source.close();
    onError(err);
  };
  return () => source.close();
}

export async function respond(
  run_id: string,
  request_id: string,
  decision: Decision,
): Promise<void> {
  const r = await fetch(`${BASE}/runs/${run_id}/respond`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ request_id, decision }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export type ReviseStep =
  | "intake"
  | "precheck"
  | "assessment"
  | "portfolio"
  | "resource"
  | "plan";

export async function reviseStep<T>(
  run_id: string,
  step: ReviseStep,
  instruction: string,
  language: string,
): Promise<T> {
  const r = await fetch(`${BASE}/runs/${run_id}/revise`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ step, instruction, language }),
  });
  if (!r.ok) throw new Error(await r.text());
  return ((await r.json()) as { step: string; artifact: T }).artifact;
}
