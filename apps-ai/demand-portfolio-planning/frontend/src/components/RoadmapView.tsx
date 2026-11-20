import type { Roadmap, RoadmapEntry } from "../types";
import { useI18n } from "../I18nProvider";

function monthStart(m: string): Date {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1);
}
function monthEnd(m: string): Date {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo, 0);
}
function parseISO(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T00:00:00`);
}

function monthLabel(m: string, lang: string): string {
  return monthStart(m).toLocaleDateString(lang === "en" ? "en-GB" : "de-DE", {
    month: "short",
    year: "2-digit",
  });
}

export function RoadmapView({
  roadmap,
  loading,
}: {
  roadmap: Roadmap | null;
  loading: boolean;
}) {
  const { t, lang } = useI18n();

  if (loading && !roadmap) {
    return (
      <section className="card">
        <h2 className="card-title">{t("roadmap.heading")}</h2>
        <div className="working">
          <span className="spinner" aria-hidden="true" />
        </div>
      </section>
    );
  }
  if (!roadmap || roadmap.months.length === 0 || roadmap.entries.length === 0) {
    return (
      <section className="card">
        <h2 className="card-title">{t("roadmap.heading")}</h2>
        <p className="muted">{t("roadmap.empty")}</p>
      </section>
    );
  }

  const months = roadmap.months;
  const gridStart = monthStart(months[0]).getTime();
  const gridEnd = monthEnd(months[months.length - 1]).getTime();
  const span = Math.max(1, gridEnd - gridStart);
  const pct = (iso: string) =>
    Math.min(100, Math.max(0, ((parseISO(iso).getTime() - gridStart) / span) * 100));
  const todayLeft = roadmap.today ? pct(roadmap.today) : null;

  const bar = (e: RoadmapEntry) => {
    const left = pct(e.start);
    const right = pct(e.end);
    return { left: `${left}%`, width: `${Math.max(2, right - left)}%` };
  };

  return (
    <section className="card roadmap-card">
      <h2 className="card-title">{t("roadmap.heading")}</h2>
      <p className="roadmap-sub">{t("roadmap.sub")}</p>

      <div className="gantt">
        <div className="gantt-row gantt-head">
          <div className="gantt-rowhead gantt-corner">{t("data.project")}</div>
          <div className="gantt-track gantt-track-head">
            {months.map((m) => (
              <div className="gantt-col" key={m}>
                {monthLabel(m, lang)}
              </div>
            ))}
            {todayLeft !== null && (
              <div className="gantt-today" style={{ left: `${todayLeft}%` }}>
                <span className="gantt-today-flag">{t("roadmap.today")}</span>
              </div>
            )}
          </div>
        </div>

        {roadmap.entries.map((e) => (
          <div
            className={`gantt-row${e.is_new_demand ? " gantt-row-new" : ""}`}
            key={`${e.project_id}-${e.start}`}
          >
            <div className="gantt-rowhead">
              <span className="gantt-name">
                {e.is_new_demand && <span className="gantt-star" aria-hidden="true">★</span>}
                {e.name}
              </span>
              <span className="gantt-area">
                {e.portfolio_area}
                {e.priority_rank ? ` · ${t("roadmap.rank", { rank: e.priority_rank })}` : ""}
              </span>
            </div>
            <div className="gantt-track">
              {months.map((m) => (
                <div className="gantt-cell" key={m} />
              ))}
              <div
                className={`gantt-bar bar-${e.status}${e.indicative ? " bar-indicative" : ""}`}
                style={bar(e)}
                title={`${e.name}`}
              />
              {todayLeft !== null && (
                <div className="gantt-todayline" style={{ left: `${todayLeft}%` }} />
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="roadmap-legend">
        <span className="rl-item">
          <span className="rl-swatch bar-in_progress" />
          {t("roadmap.legend.in_progress")}
        </span>
        <span className="rl-item">
          <span className="rl-swatch bar-proposed" />
          {t("roadmap.legend.proposed")}
        </span>
        <span className="rl-item">
          <span className="rl-swatch bar-new_demand" />
          {t("roadmap.legend.new_demand")}
        </span>
      </div>

      {roadmap.notes.length > 0 && (
        <ul className="roadmap-notes">
          {roadmap.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
