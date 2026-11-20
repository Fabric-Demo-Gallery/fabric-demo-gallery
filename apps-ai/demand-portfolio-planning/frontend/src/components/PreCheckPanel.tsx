import { useState } from "react";
import type { PreCheckReport, PrinceTheme, ReadinessLevel } from "../types";
import type { PreCheckDecision } from "../api";
import type { Key } from "../i18n";
import { useT } from "../I18nProvider";
import { ItemList } from "./fields";

const STATUS_KEY: Record<PreCheckReport["status"], Key> = {
  ready: "precheck.status.ready",
  more_info_needed: "precheck.status.more_info_needed",
  blocked: "precheck.status.blocked",
};

const THEME_KEY: Record<PrinceTheme, Key> = {
  business_case: "prince.business_case",
  organization: "prince.organization",
  scope_product: "prince.scope_product",
  plans_timeline: "prince.plans_timeline",
  risk: "prince.risk",
  resources: "prince.resources",
};

const READY_KEY: Record<ReadinessLevel, Key> = {
  covered: "ready.covered",
  partial: "ready.partial",
  missing: "ready.missing",
};

export function PreCheckPanel({
  report,
  busy,
  onDecide,
  readOnly = false,
}: {
  report: PreCheckReport;
  busy: boolean;
  onDecide: (d: PreCheckDecision) => void;
  readOnly?: boolean;
}) {
  const t = useT();
  const [blocking, setBlocking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const ready = report.status === "ready";

  const onProceed = () => {
    if (ready) onDecide({ action: "proceed" });
    else setConfirming(true);
  };

  return (
    <section className="card gate-card">
      <h2 className="card-title">{t("precheck.heading")}</h2>
      <div className={`status-chip status-${report.status}`}>{t(STATUS_KEY[report.status])}</div>

      {report.readiness.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("precheck.readiness")}</h3>
          <p className="precheck-sub">{t("precheck.readinessSub")}</p>
          <ul className="readiness-list">
            {report.readiness.map((c) => (
              <li key={c.theme} className={`readiness-row rd-${c.status}`}>
                <span className={`rd-dot rd-dot-${c.status}`} aria-hidden="true" />
                <span className="rd-body">
                  <span className="rd-head">
                    <span className="rd-theme">{t(THEME_KEY[c.theme])}</span>
                    <span className={`rd-pill rd-pill-${c.status}`}>{t(READY_KEY[c.status])}</span>
                  </span>
                  {c.finding && <span className="rd-finding">{c.finding}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.required_smes.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("precheck.smes")}</h3>
          <ItemList items={report.required_smes} />
        </div>
      )}

      {!readOnly && (
        <p className={`precheck-hint${ready ? " precheck-ready" : ""}`}>
          {ready ? t("precheck.readyHint") : t("precheck.notReady")}
        </p>
      )}
      {!readOnly && !ready && !confirming && (
        <p className="precheck-hint">{t("precheck.editHint")}</p>
      )}

      {confirming && !readOnly && (
        <div className="gate-warn">{t("precheck.confirmProceed")}</div>
      )}
      {blocking && !readOnly && (
        <div className="gate-form">
          <label className="form-field">
            <span>{t("precheck.blockReason")}</span>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
          </label>
        </div>
      )}

      {!readOnly && (
        <div className="gate-actions">
          {confirming ? (
            <>
              <button
                className="btn btn-primary"
                disabled={busy}
                onClick={() => onDecide({ action: "proceed" })}
              >
                {t("precheck.proceedAnyway")}
              </button>
              <button className="btn" disabled={busy} onClick={() => setConfirming(false)}>
                {t("precheck.cancel")}
              </button>
            </>
          ) : !blocking ? (
            <>
              <button className="btn btn-primary" disabled={busy} onClick={onProceed}>
                {t("precheck.proceed")}
              </button>
              <button className="btn btn-danger" disabled={busy} onClick={() => setBlocking(true)}>
                {t("precheck.block")}
              </button>
            </>
          ) : (
            <>
              <button
                className="btn btn-danger"
                disabled={busy}
                onClick={() => onDecide({ action: "block", reason: reason.trim() || undefined })}
              >
                {t("precheck.block")}
              </button>
              <button className="btn" disabled={busy} onClick={() => setBlocking(false)}>
                {t("precheck.cancel")}
              </button>
            </>
          )}
        </div>
      )}
    </section>
  );
}
