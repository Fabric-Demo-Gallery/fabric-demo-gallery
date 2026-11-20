import { useState } from "react";
import type { AssessmentSummary, TrackedItem } from "../types";
import type { BoardDecision } from "../api";
import { useT } from "../I18nProvider";
import { ItemList } from "./fields";

function Column({
  title,
  kind,
  icon,
  items,
}: {
  title: string;
  kind: "fact" | "assumption" | "open_question";
  icon: string;
  items: TrackedItem[];
}) {
  return (
    <div className="gate-col">
      <div className={`col-head col-head-${kind}`}>
        <span className="col-icon">{icon}</span>
        {title}
      </div>
      <div className="col-items">
        {items.map((it, i) => (
          <div key={i} className={`col-item col-item-${kind}`}>
            <span className="col-item-icon">{icon}</span>
            <span>{it.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function BoardGate({
  summary,
  busy,
  onDecide,
  readOnly = false,
  version,
}: {
  summary: AssessmentSummary;
  busy: boolean;
  onDecide: (d: BoardDecision) => void;
  readOnly?: boolean;
  version?: number;
}) {
  const t = useT();
  const [reason, setReason] = useState("");

  return (
    <section className="card board-card">
      <h2 className="card-title">
        {t("assessment.heading")}
        {version && version > 1 ? <span className="ver-badge">v{version}</span> : null}
      </h2>
      {summary.business_demand && <p className="board-lead">{summary.business_demand}</p>}

      <div className="gate-cols">
        <Column title={t("assessment.facts")} kind="fact" icon="✓" items={summary.confirmed_facts} />
        <Column
          title={t("assessment.assumptions")}
          kind="assumption"
          icon="?"
          items={summary.assumptions}
        />
        <Column
          title={t("assessment.open")}
          kind="open_question"
          icon="i"
          items={summary.open_questions}
        />
      </div>

      {(summary.risks_blockers.length > 0 || summary.decisions_needed.length > 0) && (
        <div className="board-extra">
          {summary.risks_blockers.length > 0 && (
            <div className="card-block">
              <h3 className="block-title">{t("assessment.risks")}</h3>
              <ItemList items={summary.risks_blockers} />
            </div>
          )}
          {summary.decisions_needed.length > 0 && (
            <div className="card-block">
              <h3 className="block-title">{t("assessment.decisions")}</h3>
              <ItemList items={summary.decisions_needed} />
            </div>
          )}
        </div>
      )}

      {!readOnly && (
        <>
          <div className="gate-form">
            <label className="form-field">
              <span>{t("board.reason")}</span>
              <input type="text" value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          </div>

          <div className="gate-actions board-actions">
            <button
              className="btn btn-primary"
              disabled={busy}
              onClick={() => onDecide({ outcome: "approve_as_project", reason: reason.trim() || undefined })}
            >
              {t("board.approve")} <span aria-hidden="true">→</span>
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => onDecide({ outcome: "already_solved", reason: reason.trim() || undefined })}
            >
              {t("board.solved")}
            </button>
            <button
              className="btn btn-danger"
              disabled={busy}
              onClick={() => onDecide({ outcome: "reject", reason: reason.trim() || undefined })}
            >
              {t("board.reject")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
