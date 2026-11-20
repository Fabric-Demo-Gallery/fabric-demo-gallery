import { useState } from "react";
import type { ProjectPlanningHandoff } from "../types";
import type { HandoffAdjustment } from "../api";
import { useT } from "../I18nProvider";
import { ItemList } from "./fields";

export function HandoffGate({
  draft,
  busy,
  onDecide,
  readOnly = false,
  version,
}: {
  draft: ProjectPlanningHandoff;
  busy: boolean;
  onDecide: (d: HandoffAdjustment) => void;
  readOnly?: boolean;
  version?: number;
}) {
  const t = useT();
  const [adjust, setAdjust] = useState(false);
  const [summary, setSummary] = useState(draft.project_summary);
  const [notes, setNotes] = useState("");

  return (
    <section className="card handoff-card">
      <h2 className="card-title">
        {t("handoff.heading")}
        {version && version > 1 ? <span className="ver-badge">v{version}</span> : null}
      </h2>

      <div className="card-block">
        <h3 className="block-title">{t("handoff.summary")}</h3>
        <p>{draft.project_summary}</p>
      </div>
      {draft.scope && (
        <div className="card-block">
          <h3 className="block-title">{t("handoff.scope")}</h3>
          <p>{draft.scope}</p>
        </div>
      )}

      <div className="handoff-grid">
        {draft.in_scope.length > 0 && (
          <div className="card-block">
            <h3 className="block-title">{t("handoff.inScope")}</h3>
            <ItemList items={draft.in_scope} />
          </div>
        )}
        {draft.out_of_scope.length > 0 && (
          <div className="card-block">
            <h3 className="block-title">{t("handoff.outScope")}</h3>
            <ItemList items={draft.out_of_scope} />
          </div>
        )}
      </div>

      {draft.work_packages.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("handoff.workPackages")}</h3>
          <ul className="wp-list">
            {draft.work_packages.map((w, i) => (
              <li key={i}>
                <strong>{w.title}</strong>
                {w.description && <span className="muted"> — {w.description}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {draft.tasks.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("handoff.tasks")}</h3>
          <ul className="task-list">
            {draft.tasks.map((task, i) => (
              <li key={i} className="task-row">
                <span className="task-title">{task.title}</span>
                {task.owner && <span className="task-owner">{task.owner}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="handoff-grid">
        {draft.decisions_needed.length > 0 && (
          <div className="card-block">
            <h3 className="block-title">{t("handoff.decisions")}</h3>
            <ItemList items={draft.decisions_needed} />
          </div>
        )}
        {draft.risks_blockers.length > 0 && (
          <div className="card-block">
            <h3 className="block-title">{t("handoff.risks")}</h3>
            <ItemList items={draft.risks_blockers} />
          </div>
        )}
      </div>

      {adjust && !readOnly && (
        <div className="gate-form">
          <label className="form-field">
            <span>{t("handoff.adjustSummary")}</span>
            <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={2} />
          </label>
          <label className="form-field">
            <span>{t("handoff.notes")}</span>
            <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      )}

      {!readOnly && (
        <div className="gate-actions">
          {!adjust ? (
            <>
              <button className="btn btn-primary" disabled={busy} onClick={() => onDecide({ action: "accept" })}>
                {t("handoff.accept")}
              </button>
              <button className="btn" disabled={busy} onClick={() => setAdjust(true)}>
                {t("handoff.adjust")}
              </button>
            </>
          ) : (
            <>
              <button
                className="btn btn-primary"
                disabled={busy}
                onClick={() =>
                  onDecide({
                    action: "adjust",
                    adjusted_summary: summary.trim() || undefined,
                    notes: notes.trim() || undefined,
                  })
                }
              >
                {t("handoff.accept")}
              </button>
              <button className="btn" disabled={busy} onClick={() => setAdjust(false)}>
                {t("precheck.cancel")}
              </button>
            </>
          )}
        </div>
      )}
    </section>
  );
}
