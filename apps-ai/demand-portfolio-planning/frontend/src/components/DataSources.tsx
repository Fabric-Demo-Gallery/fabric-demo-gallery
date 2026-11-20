import { useMemo } from "react";
import type { Person, PortfolioProject, SeedData } from "../types";
import { useT } from "../I18nProvider";
import type { Key } from "../i18n";

const LEVEL_RANK: Record<string, number> = {
  beginner: 1,
  intermediate: 2,
  advanced: 3,
  expert: 4,
};

function loadClass(pct: number): string {
  if (pct >= 85) return "load-high";
  if (pct >= 60) return "load-mid";
  return "load-low";
}

function AllocationBar({ pct }: { pct: number }) {
  return (
    <div className="alloc-bar" title={`${pct}%`}>
      <div className={`alloc-fill ${loadClass(pct)}`} style={{ width: `${Math.min(100, pct)}%` }} />
      <span className="alloc-pct">{pct}%</span>
    </div>
  );
}

function PersonCard({ person }: { person: Person }) {
  const t = useT();
  const skills = [...person.skills].sort(
    (a, b) => (LEVEL_RANK[b.level] ?? 0) - (LEVEL_RANK[a.level] ?? 0),
  );
  return (
    <div className="ds-person">
      <div className="ds-person-head">
        <span className="ds-person-name">{person.name}</span>
        <span className="ds-person-roles">{person.roles.join(" · ")}</span>
      </div>
      <div className="ds-person-alloc">
        <span className="ds-mini-label">{t("data.allocation")}</span>
        <AllocationBar pct={person.allocation_pct} />
      </div>
      <div className="ds-skills">
        {skills.map((s) => (
          <span key={s.skill} className={`ds-skill ds-skill-${s.level}`}>
            {s.skill}
            <span className="ds-skill-level">{t(`level.${s.level}` as Key)}</span>
          </span>
        ))}
      </div>
      {person.commitments.length > 0 && (
        <div className="ds-commitments">
          <span className="ds-mini-label">{t("data.commitments")}</span>
          <span className="ds-commitment-count">{person.commitments.length}</span>
        </div>
      )}
    </div>
  );
}

function statusKey(status: string): Key {
  return status === "in_progress" ? "status.in_progress" : "status.proposed";
}

function Bars({ value }: { value: number }) {
  return (
    <span className="ds-bars" aria-hidden="true">
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className={`ds-bar${n <= value ? " on" : ""}`} />
      ))}
    </span>
  );
}

function PortfolioTable({ portfolio }: { portfolio: PortfolioProject[] }) {
  const t = useT();
  const rows = useMemo(
    () =>
      [...portfolio].sort((a, b) => a.portfolio_area.localeCompare(b.portfolio_area)),
    [portfolio],
  );
  return (
    <table className="ds-table">
      <thead>
        <tr>
          <th>{t("data.project")}</th>
          <th>{t("data.area")}</th>
          <th>{t("data.status")}</th>
          <th>{t("data.value")}</th>
          <th>{t("data.effort")}</th>
          <th>{t("data.urgency")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.project_id}>
            <td>
              <div className="ds-proj-name">{p.name}</div>
              {p.roles.length > 0 && <div className="ds-proj-roles">{p.roles.join(" · ")}</div>}
            </td>
            <td>{p.portfolio_area}</td>
            <td>
              <span className={`ds-status ds-status-${p.status}`}>{t(statusKey(p.status))}</span>
            </td>
            <td><Bars value={p.value} /></td>
            <td><Bars value={p.effort} /></td>
            <td><Bars value={p.urgency} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DataSources({ seed }: { seed: SeedData }) {
  const t = useT();
  const pool = [...seed.resource_pool].sort((a, b) => b.allocation_pct - a.allocation_pct);
  return (
    <div className="ds">
      <h1 className="ds-heading">{t("data.heading")}</h1>
      <p className="ds-sub">{t("data.sub")}</p>

      <section className="ds-section">
        <div className="ds-section-head">
          <h2>{t("data.pool")}</h2>
          <span className="ds-count">{seed.resource_pool.length}</span>
        </div>
        <div className="ds-people">
          {pool.map((person) => (
            <PersonCard key={person.person_id} person={person} />
          ))}
        </div>
      </section>

      <section className="ds-section">
        <div className="ds-section-head">
          <h2>{t("data.portfolio")}</h2>
          <span className="ds-count">{seed.portfolio.length}</span>
        </div>
        <div className="card">
          <PortfolioTable portfolio={seed.portfolio} />
        </div>
      </section>
    </div>
  );
}
