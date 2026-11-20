import type {
  AssessmentSummary,
  DemandRecord,
  PortfolioFit,
  PreCheckReport,
  ProjectPlanningHandoff,
  ResourceMatch,
} from "../types";
import type { StepId } from "./Stepper";
import { DemandRecordCard } from "./DemandRecordCard";
import { PreCheckPanel } from "./PreCheckPanel";
import { BoardGate } from "./Board";
import { PortfolioCard, PriorityList, ResourceTable, TimelineCard } from "./Resourcing";
import { HandoffGate } from "./Handoff";

const noop = () => {};

/** Read-only re-display of a previously produced stage, for demo replay. */
export function ReplayView({
  step,
  record,
  report,
  assessment,
  portfolioFit,
  resourceMatch,
  draft,
}: {
  step: StepId;
  record: DemandRecord | null;
  report: PreCheckReport | null;
  assessment: AssessmentSummary | null;
  portfolioFit: PortfolioFit | null;
  resourceMatch: ResourceMatch | null;
  draft: ProjectPlanningHandoff | null;
}) {
  const match = draft?.resource_allocation ?? resourceMatch;
  switch (step) {
    case "intake":
      return record ? <DemandRecordCard record={record} /> : null;
    case "precheck":
      return (
        <>
          {record && <DemandRecordCard record={record} />}
          {report && (
            <PreCheckPanel report={report} busy={false} onDecide={noop} readOnly />
          )}
        </>
      );
    case "board":
      return assessment ? (
        <BoardGate summary={assessment} busy={false} onDecide={noop} readOnly />
      ) : null;
    case "portfolio":
      return portfolioFit ? <PortfolioCard fit={portfolioFit} /> : null;
    case "resource":
      return match && match.rows.length > 0 ? <ResourceTable match={match} /> : null;
    case "plan":
      return draft ? (
        <>
          {match && match.rows.length > 0 && <ResourceTable match={match} />}
          <PriorityList priority={draft.priority} />
          <TimelineCard timeline={draft.timeline} />
        </>
      ) : null;
    case "handoff":
      return draft ? <HandoffGate draft={draft} busy={false} onDecide={noop} readOnly /> : null;
    default:
      return null;
  }
}
