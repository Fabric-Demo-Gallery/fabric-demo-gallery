import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "./I18nProvider";
import type { Key, Lang } from "./i18n";
import {
  fetchRoadmap,
  fetchSeedData,
  openEventStream,
  respond,
  startRun,
  type BoardDecision,
  type ChatUpdate,
  type Decision,
  type HandoffAdjustment,
  type PreCheckDecision,
  type StageEvent,
} from "./api";
import type {
  AssessmentSummary,
  DemandRecord,
  PlanningOutcome,
  PortfolioFit,
  PreCheckReport,
  ProjectPlanningHandoff,
  ResourceMatch,
  Roadmap,
  SeedData,
} from "./types";
import { Stepper, type StepId } from "./components/Stepper";
import { StartScreen } from "./components/StartScreen";
import { DataSources } from "./components/DataSources";
import { DemandRecordCard } from "./components/DemandRecordCard";
import { PreCheckPanel } from "./components/PreCheckPanel";
import { BoardGate } from "./components/Board";
import {
  PortfolioCard,
  PriorityList,
  ResourceTable,
  TimelineCard,
} from "./components/Resourcing";
import { HandoffGate } from "./components/Handoff";
import { FloatingChat } from "./components/FloatingChat";
import { ActivityLog } from "./components/ActivityLog";
import { ReplayView } from "./components/ReplayView";
import { RoadmapView } from "./components/RoadmapView";
import { Legend } from "./components/Provenance";

type Gate = "precheck" | "board" | "handoff" | null;
type Nav = "flow" | "data" | "roadmap";

export type ActivityStatus = "running" | "done" | "gate" | "outcome";
export interface ActivityEntry {
  id: number;
  labelKey: Key;
  status: ActivityStatus;
  time: string;
}

const ACT1: StepId[] = ["intake", "precheck", "board"];

const STAGE_ACTIVITY: Partial<Record<string, Key>> = {
  intake: "step.intake",
  precheck: "step.precheck",
  assessment: "step.assessment",
  portfolio: "step.portfolio",
  resource: "step.resource",
  planning: "step.plan",
};

function fieldPatch(value: string, lang: Lang) {
  return {
    value: value || null,
    kind: value ? "fact" : "unknown",
    source: lang === "en" ? "user input" : "Nutzereingabe",
  };
}

function withField(rec: DemandRecord, name: string, value: string, lang: Lang): DemandRecord {
  const next = { ...rec } as unknown as Record<string, unknown>;
  next[name] = fieldPatch(value, lang);
  return next as unknown as DemandRecord;
}

export default function App() {
  const { lang, setLang, t } = useI18n();
  const [seed, setSeed] = useState<SeedData | null>(null);
  const [view, setView] = useState<"start" | "run">("start");
  const [nav, setNav] = useState<Nav>("flow");
  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rechecking, setRechecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [step, setStep] = useState<StepId>("intake");
  const [viewStep, setViewStep] = useState<StepId | null>(null);
  const [working, setWorking] = useState<Key | null>(null);
  const [gate, setGate] = useState<Gate>(null);

  const [record, setRecord] = useState<DemandRecord | null>(null);
  const [report, setReport] = useState<PreCheckReport | null>(null);
  const [assessment, setAssessment] = useState<AssessmentSummary | null>(null);
  const [portfolioFit, setPortfolioFit] = useState<PortfolioFit | null>(null);
  const [resourceMatch, setResourceMatch] = useState<ResourceMatch | null>(null);
  const [draft, setDraft] = useState<ProjectPlanningHandoff | null>(null);
  const [outcome, setOutcome] = useState<PlanningOutcome | null>(null);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [versions, setVersions] = useState<Record<string, number>>({});
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [roadmapLoading, setRoadmapLoading] = useState(false);

  const closeRef = useRef<(() => void) | null>(null);
  const activityIdRef = useRef(0);
  // Refs that let the SSE handler (a stable callback) read live values and
  // coalesce rapid pencil edits without locking the form between round-trips.
  const recordRef = useRef<DemandRecord | null>(null);
  const langRef = useRef<Lang>(lang);
  const editQueueRef = useRef<Record<string, string>>({});
  const editFlightRef = useRef(false);
  const flushRef = useRef<() => void>(() => {});

  useEffect(() => {
    recordRef.current = record;
  }, [record]);
  useEffect(() => {
    langRef.current = lang;
  }, [lang]);

  useEffect(() => {
    fetchSeedData().then(setSeed).catch((e) => setError(String(e)));
    return () => closeRef.current?.();
  }, []);

  useEffect(() => {
    if (nav !== "roadmap") return;
    let cancelled = false;
    setRoadmapLoading(true);
    fetchRoadmap(lang, runId)
      .then((r) => {
        if (!cancelled) setRoadmap(r);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setRoadmapLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nav, lang, runId, draft]);

  const handleEvent = useCallback((ev: StageEvent) => {
    const logActivity = (labelKey: Key, status: ActivityStatus) => {
      setActivity((prev) => {
        const marked = prev.map((e) => (e.status === "running" ? { ...e, status: "done" as const } : e));
        return [
          ...marked,
          {
            id: (activityIdRef.current += 1),
            labelKey,
            status,
            time: new Date().toLocaleTimeString(),
          },
        ];
      });
    };

    if (ev.type === "error") {
      setError(ev.message);
      return;
    }
    if (ev.type === "outcome") {
      logActivity(`outcome.${ev.outcome.status}` as Key, "outcome");
      setOutcome(ev.outcome);
      setGate(null);
      setWorking(null);
      setBusy(false);
      return;
    }
    if (ev.type === "awaiting") {
      setBusy(false);
      setWorking(null);
      if (ev.versions) setVersions(ev.versions);
      if (ev.gate === "precheck_review" && "report" in ev.request) {
        logActivity("step.precheck", "gate");
        // A pre-check re-run finished: unlock the form and reconcile the record
        // with any edits the user queued while it was in flight.
        editFlightRef.current = false;
        setRechecking(false);
        let rec = ev.request.record;
        const pending = editQueueRef.current;
        for (const [name, value] of Object.entries(pending)) {
          rec = withField(rec, name, value, langRef.current);
        }
        recordRef.current = rec;
        setRecord(rec);
        setReport(ev.request.report);
        setStep("precheck");
        setGate("precheck");
        flushRef.current();
      } else if (ev.gate === "board_decision" && "summary" in ev.request) {
        logActivity("step.board", "gate");
        setRecord(ev.request.record);
        setAssessment(ev.request.summary);
        setStep("board");
        setGate("board");
      } else if (ev.gate === "handoff_review" && "draft" in ev.request) {
        logActivity("step.handoff", "gate");
        setDraft(ev.request.draft);
        setStep("handoff");
        setGate("handoff");
      }
      return;
    }
    // stage events
    const activityLabel = STAGE_ACTIVITY[ev.stage];
    if (activityLabel) logActivity(activityLabel, "running");
    switch (ev.stage) {
      case "run_started":
      case "intake":
        setStep("intake");
        setWorking("working.intake");
        break;
      case "demand_record":
        setRecord(ev.record);
        setStep("intake");
        break;
      case "precheck":
        setStep("precheck");
        setWorking("working.precheck");
        break;
      case "precheck_report":
      case "precheck_updated":
        setRecord(ev.record);
        setReport(ev.report);
        break;
      case "assessment":
        setStep("board");
        setWorking("working.assessment");
        break;
      case "assessment_summary":
        setAssessment(ev.summary);
        break;
      case "approved":
        setStep("portfolio");
        break;
      case "portfolio":
        setStep("portfolio");
        setWorking("working.portfolio");
        break;
      case "portfolio_fit":
        setPortfolioFit(ev.portfolio_fit);
        break;
      case "resource":
        setStep("resource");
        setWorking("working.resource");
        break;
      case "resource_match":
        setResourceMatch(ev.resource_match);
        break;
      case "planning":
        setStep("plan");
        setWorking("working.planning");
        break;
      case "plan_draft":
        setDraft(ev.draft);
        break;
      default:
        break;
    }
  }, []);

  const attach = useCallback(
    (id: string) => {
      closeRef.current?.();
      closeRef.current = openEventStream(
        id,
        handleEvent,
        () => {},
        (e) => setError(String(e)),
      );
    },
    [handleEvent],
  );

  const onStart = useCallback(
    async ({ demandId, rawDemand }: { demandId?: string; rawDemand?: string }) => {
      setStarting(true);
      setError(null);
      setRecord(null);
      setReport(null);
      setAssessment(null);
      setPortfolioFit(null);
      setResourceMatch(null);
      setDraft(null);
      setOutcome(null);
      setGate(null);
      setActivity([]);
      setVersions({});
      setViewStep(null);
      setStep("intake");
      setWorking("working.intake");
      editQueueRef.current = {};
      editFlightRef.current = false;
      setRechecking(false);
      try {
        const id = await startRun(demandId ?? "", lang, rawDemand);
        setRunId(id);
        setView("run");
        attach(id);
      } catch (e) {
        setError(String(e));
      } finally {
        setStarting(false);
      }
    },
    [attach, lang],
  );

  const decide = useCallback(
    async (decision: Decision) => {
      if (!runId || !gate) return;
      const requestId =
        gate === "precheck" ? "precheck_review" : gate === "board" ? "board_decision" : "handoff_review";
      // Carry the latest edited artifact so chat/inline edits commit into the flow.
      let payload: Decision = decision;
      if (gate === "precheck" && record && "action" in decision && decision.action !== "block") {
        payload = { ...decision, record } as Decision;
      } else if (gate === "board" && assessment && "outcome" in decision) {
        payload = { ...decision, summary: assessment } as Decision;
      } else if (gate === "handoff" && draft && "action" in decision) {
        payload = { ...decision, draft } as Decision;
      }
      // Leaving the gate: drop any queued field edits so no stale provide_info
      // fires against a run that has already advanced.
      editQueueRef.current = {};
      editFlightRef.current = false;
      setRechecking(false);
      setBusy(true);
      setGate(null);
      try {
        await respond(runId, requestId, payload);
        attach(runId);
      } catch (e) {
        setError(String(e));
        setBusy(false);
      }
    },
    [runId, gate, attach, record, assessment, draft],
  );

  const applyChatUpdates = useCallback((updates: ChatUpdate[]) => {
    for (const u of updates) {
      switch (u.step) {
        case "intake":
          setRecord(u.artifact as DemandRecord);
          break;
        case "precheck":
          setReport(u.artifact as PreCheckReport);
          break;
        case "assessment":
          setAssessment(u.artifact as AssessmentSummary);
          break;
        case "portfolio":
          setPortfolioFit(u.artifact as PortfolioFit);
          break;
        case "resource":
          setResourceMatch(u.artifact as ResourceMatch);
          break;
        case "plan":
          setDraft(u.artifact as ProjectPlanningHandoff);
          break;
        default:
          break;
      }
      setVersions((v) => ({ ...v, [u.step]: u.version }));
    }
  }, []);

  const reset = useCallback(() => {
    closeRef.current?.();
    setView("start");
    setRunId(null);
    setOutcome(null);
    setError(null);
  }, []);

  // Send queued pencil edits as one provide_info; keep only a single request in
  // flight so the workflow is never resumed twice at once.
  const flushEdits = useCallback(() => {
    if (editFlightRef.current || !runId) return;
    const fields = editQueueRef.current;
    const names = Object.keys(fields);
    if (names.length === 0) return;
    editQueueRef.current = {};
    editFlightRef.current = true;
    setRechecking(true);
    setWorking("working.precheck");
    respond(runId, "precheck_review", {
      action: "provide_info",
      provided_fields: fields,
      record: recordRef.current ?? undefined,
    })
      .then(() => attach(runId))
      .catch((e) => {
        editFlightRef.current = false;
        setRechecking(false);
        setError(String(e));
      });
  }, [runId, attach]);

  useEffect(() => {
    flushRef.current = flushEdits;
  }, [flushEdits]);

  const provideField = useCallback(
    (name: string, value: string) => {
      if (!runId) return;
      // Optimistic local update so the record reflects the edit instantly.
      const base = recordRef.current;
      if (base) {
        const next = withField(base, name, value, langRef.current);
        recordRef.current = next;
        setRecord(next);
      }
      // Empty values only clear locally; never push a blank to the backend.
      if (!value) return;
      editQueueRef.current[name] = value;
      flushEdits();
    },
    [runId, flushEdits],
  );

  const visitable = new Set<StepId>();
  if (record) visitable.add("intake");
  if (report) visitable.add("precheck");
  if (assessment) visitable.add("board");
  if (portfolioFit) visitable.add("portfolio");
  if (resourceMatch || draft?.resource_allocation?.rows.length) visitable.add("resource");
  if (draft) {
    visitable.add("plan");
    visitable.add("handoff");
  }
  const replayStep = viewStep && viewStep !== step ? viewStep : null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-title">{t("app.title")}</span>
          <span className="brand-kicker">{t("app.kicker")}</span>
        </div>
        <nav className="topnav" aria-label="sections">
          <button className={nav === "flow" ? "on" : ""} onClick={() => setNav("flow")}>
            {t("nav.flow")}
          </button>
          <button className={nav === "roadmap" ? "on" : ""} onClick={() => setNav("roadmap")}>
            {t("nav.roadmap")}
          </button>
          <button className={nav === "data" ? "on" : ""} onClick={() => setNav("data")}>
            {t("nav.data")}
          </button>
        </nav>
        <div className="lang-toggle" role="group" aria-label="language">
          <button className={lang === "de" ? "on" : ""} onClick={() => setLang("de")}>
            DE
          </button>
          <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>
            EN
          </button>
        </div>
      </header>

      {error && (
        <div className="banner banner-error">
          <strong>{t("error.title")}:</strong> {error}
        </div>
      )}

      {nav === "data" && seed && <DataSources seed={seed} />}

      {nav === "roadmap" && <RoadmapView roadmap={roadmap} loading={roadmapLoading} />}

      {nav === "flow" && view === "start" && seed && (
        <StartScreen
          demands={seed.demands}
          portfolioCount={seed.portfolio.length}
          poolCount={seed.resource_pool.length}
          starting={starting}
          onStart={onStart}
        />
      )}

      {nav === "flow" && view === "run" && (
        <div className="run">
          <div className="run-rail">
            <Stepper
              current={viewStep ?? step}
              visitable={visitable}
              onSelect={(s) => setViewStep(s === step ? null : s)}
            />
            <ActivityLog entries={activity} />
          </div>
          <main className="run-main">
            {replayStep ? (
              <>
                <div className="replay-banner">
                  <span>{t("replay.viewing")}</span>
                  <button type="button" className="btn btn-sm" onClick={() => setViewStep(null)}>
                    {t("replay.back")}
                  </button>
                </div>
                <ReplayView
                  step={replayStep}
                  record={record}
                  report={report}
                  assessment={assessment}
                  portfolioFit={portfolioFit}
                  resourceMatch={resourceMatch}
                  draft={draft}
                />
              </>
            ) : outcome ? (
              <OutcomeView outcome={outcome} onReset={reset} />
            ) : ACT1.includes(step) ? (
              <Act1
                gate={gate}
                busy={busy}
                rechecking={rechecking}
                working={working}
                record={record}
                report={report}
                assessment={assessment}
                onDecide={decide}
                onEditField={provideField}
                versions={versions}
              />
            ) : (
              <Act2
                gate={gate}
                busy={busy}
                working={working}
                portfolioFit={portfolioFit}
                resourceMatch={resourceMatch}
                draft={draft}
                onDecide={decide}
                versions={versions}
              />
            )}
            <Legend />
          </main>
          {runId && <FloatingChat runId={runId} viewing={step} onUpdates={applyChatUpdates} />}
        </div>
      )}
    </div>
  );
}

function Working({ label }: { label: Key | null }) {
  const { t } = useI18n();
  if (!label) return null;
  return (
    <div className="working">
      <span className="spinner" aria-hidden="true" />
      {t(label)}
    </div>
  );
}

function Act1({
  gate,
  busy,
  rechecking,
  working,
  record,
  report,
  assessment,
  onDecide,
  onEditField,
  versions,
}: {
  gate: Gate;
  busy: boolean;
  rechecking: boolean;
  working: Key | null;
  record: DemandRecord | null;
  report: PreCheckReport | null;
  assessment: AssessmentSummary | null;
  onDecide: (d: Decision) => void;
  onEditField: (field: string, value: string) => void;
  versions: Record<string, number>;
}) {
  if (gate === "board" && assessment) {
    return (
      <BoardGate
        summary={assessment}
        busy={busy}
        onDecide={(d: BoardDecision) => onDecide(d)}
        version={versions.assessment}
      />
    );
  }
  return (
    <>
      {record && (
        <DemandRecordCard
          record={record}
          onEditField={gate === "precheck" ? onEditField : undefined}
          rechecking={rechecking}
          version={versions.intake}
        />
      )}
      {gate === "precheck" && report && record && (
        <PreCheckPanel
          report={report}
          busy={busy || rechecking}
          onDecide={(d: PreCheckDecision) => onDecide(d)}
        />
      )}
      {!gate && <Working label={working} />}
    </>
  );
}

function Act2({
  gate,
  busy,
  working,
  portfolioFit,
  resourceMatch,
  draft,
  onDecide,
  versions,
}: {
  gate: Gate;
  busy: boolean;
  working: Key | null;
  portfolioFit: PortfolioFit | null;
  resourceMatch: ResourceMatch | null;
  draft: ProjectPlanningHandoff | null;
  onDecide: (d: Decision) => void;
  versions: Record<string, number>;
}) {
  const match = draft?.resource_allocation ?? resourceMatch;
  return (
    <>
      {portfolioFit && <PortfolioCard fit={portfolioFit} />}
      {match && match.rows.length > 0 && <ResourceTable match={match} />}
      {draft && <PriorityList priority={draft.priority} />}
      {draft && <TimelineCard timeline={draft.timeline} />}
      {!gate && <Working label={working} />}
      {gate === "handoff" && draft && (
        <HandoffGate
          draft={draft}
          busy={busy}
          onDecide={(d: HandoffAdjustment) => onDecide(d)}
          version={versions.plan}
        />
      )}
    </>
  );
}

function OutcomeView({ outcome, onReset }: { outcome: PlanningOutcome; onReset: () => void }) {
  const { t } = useI18n();
  const key = `outcome.${outcome.status}` as Key;
  return (
    <div className={`outcome outcome-${outcome.status}`}>
      <div className="outcome-icon" aria-hidden="true">
        {outcome.status === "handed_off" ? "✓" : outcome.status === "blocked" ? "■" : "✕"}
      </div>
      <h2>{t(key)}</h2>
      {outcome.reason && (
        <p>
          <strong>{t("outcome.reason")}:</strong> {outcome.reason}
        </p>
      )}
      {outcome.handoff && <p className="outcome-summary">{outcome.handoff.project_summary}</p>}
      <button className="btn btn-primary" onClick={onReset}>
        {t("outcome.reset")}
      </button>
    </div>
  );
}
