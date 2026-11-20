import type {
  PortfolioFit,
  PrioritySuggestion,
  ResourceMatch,
  TimelineDraft,
} from "../types";
import type { Key } from "../i18n";
import { useI18n, useT } from "../I18nProvider";
import { KindDot } from "./Provenance";
import { ItemList } from "./fields";

const ALLOC_KEY: Record<string, Key> = {
  unassigned: "alloc.unassigned",
  proposed: "alloc.proposed",
  confirmed: "alloc.confirmed",
  conflict: "alloc.conflict",
};

const LEVEL_KEY: Record<string, Key> = {
  beginner: "level.beginner",
  intermediate: "level.intermediate",
  advanced: "level.advanced",
  expert: "level.expert",
};

function levelLabel(level: string, t: (k: Key) => string): string {
  const key = LEVEL_KEY[level.toLowerCase().trim()];
  return key ? t(key) : level;
}

function fmtDate(iso: string | null | undefined, lang: string): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang === "en" ? "en-GB" : "de-DE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function ResourceTable({ match }: { match: ResourceMatch }) {
  const t = useT();
  return (
    <section className="card">
      <h2 className="card-title">{t("resource.heading")}</h2>
      <div className="role-cards">
        {match.rows.map((row, i) => (
          <div className="role-card" key={i}>
            <div className="role-head">
              <div className="role-id">
                <span className="role-name">{row.role_or_skill}</span>
                {row.requested_contribution && (
                  <span className="role-sub">{row.requested_contribution}</span>
                )}
              </div>
              <span className={`alloc-chip alloc-${row.allocation_status}`}>
                {t(ALLOC_KEY[row.allocation_status])}
              </span>
            </div>

            {row.candidates.length === 0 ? (
              <p className="muted role-none">{t("resource.none")}</p>
            ) : (
              <ul className="cand-list">
                {row.candidates.map((c) => (
                  <li className="cand-row" key={c.person_id} title={c.fit_rationale}>
                    <KindDot kind={c.kind} />
                    <span className="cand-name">{c.name}</span>
                    {c.skill_level && (
                      <span className="cand-level">{levelLabel(c.skill_level, t)}</span>
                    )}
                    <span className="cand-avail">
                      {c.availability_pct === null ? (
                        <span className="muted">{t("none")}</span>
                      ) : (
                        <>
                          <span className="avail-bar">
                            <span
                              className={`avail-fill${c.availability_pct < 25 ? " avail-low" : ""}`}
                              style={{ width: `${Math.max(4, c.availability_pct)}%` }}
                            />
                          </span>
                          <span className="avail-pct">{c.availability_pct}%</span>
                        </>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {row.open_question && <p className="role-oq">{row.open_question}</p>}
          </div>
        ))}
      </div>

      {match.workload_conflicts.length > 0 && (
        <div className="card-block">
          <h3 className="block-title conflict-title">{t("resource.conflicts")}</h3>
          <ItemList items={match.workload_conflicts} />
        </div>
      )}
      {match.unassigned_work.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("resource.unassignedWork")}</h3>
          <ItemList items={match.unassigned_work} />
        </div>
      )}
    </section>
  );
}

export function PriorityList({ priority }: { priority: PrioritySuggestion }) {
  const t = useT();
  return (
    <section className="card priority-card">
      <h2 className="card-title">{t("priority.heading")}</h2>
      <p className="priority-note">
        {t("priority.newDemand", {
          rank: priority.new_demand_rank,
          total: priority.total_items,
        })}
      </p>
      <ol className="priority-list">
        {priority.ranked.map((item) => (
          <li
            key={item.item_id}
            className={`priority-row${item.is_new_demand ? " priority-new" : ""}`}
          >
            <span className="priority-rank">{item.rank}</span>
            <span className="priority-body">
              <span className="priority-name">{item.name}</span>
              <span className="priority-meta">{item.rationale}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="priority-method">
        <strong>{t("priority.method")}:</strong> {priority.method}
      </p>
    </section>
  );
}

export function TimelineCard({ timeline }: { timeline: TimelineDraft }) {
  const { t, lang } = useI18n();
  return (
    <section className="card">
      <h2 className="card-title">{t("timeline.heading")}</h2>
      {timeline.planned_project_start && (
        <div className="tl-head">
          <span>
            {t("timeline.plannedStart")}:{" "}
            <strong>{fmtDate(timeline.planned_project_start, lang)}</strong>
          </span>
        </div>
      )}
      <ul className="tl-list">
        {timeline.milestones.map((m, i) => (
          <li key={i} className="tl-row">
            <span className="tl-dot" aria-hidden="true" />
            <span className="tl-label">{m.label}</span>
            <span className="tl-date">
              {m.date ? fmtDate(m.date, lang) : <span className="muted">{t("timeline.open")}</span>}
            </span>
          </li>
        ))}
      </ul>
      <p className="tl-note">{t("timeline.indicativeNote")}</p>
    </section>
  );
}

export function PortfolioCard({ fit }: { fit: PortfolioFit }) {
  const t = useT();
  return (
    <section className="card">
      <h2 className="card-title">{t("portfolio.heading")}</h2>
      {fit.related_projects.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("portfolio.related")}</h3>
          <ul className="related-list">
            {fit.related_projects.map((p) => (
              <li key={p.project_id} className="related-row">
                <span className={`rel-chip rel-${p.relationship}`}>{p.relationship}</span>
                <span>{p.name}</span>
                {p.note && <span className="muted"> — {p.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {fit.transparency_notes.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("portfolio.transparency")}</h3>
          <ItemList items={fit.transparency_notes} />
        </div>
      )}
    </section>
  );
}
