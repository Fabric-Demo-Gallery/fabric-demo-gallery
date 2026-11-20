import type { ActivityEntry } from "../App";
import { useT } from "../I18nProvider";

function StatusMark({ status }: { status: ActivityEntry["status"] }) {
  if (status === "running") return <span className="act-mark act-running" aria-hidden="true" />;
  if (status === "gate") return <span className="act-mark act-gate" aria-hidden="true">‖</span>;
  if (status === "outcome") return <span className="act-mark act-outcome" aria-hidden="true">✓</span>;
  return <span className="act-mark act-done" aria-hidden="true">✓</span>;
}

export function ActivityLog({ entries }: { entries: ActivityEntry[] }) {
  const t = useT();
  if (entries.length === 0) return null;
  return (
    <div className="activity">
      <div className="activity-title">{t("activity.title")}</div>
      <ul className="activity-list">
        {entries.map((e) => (
          <li key={e.id} className={`activity-row activity-${e.status}`}>
            <StatusMark status={e.status} />
            <span className="activity-label">{t(e.labelKey)}</span>
            <span className="activity-time">{e.time}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
