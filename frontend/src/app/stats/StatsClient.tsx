"use client";

import { useEffect, useState, Fragment } from "react";
import { fetchStats } from "@/lib/api";
import type { UsageStats } from "@/lib/api";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { DEMOS } from "@/lib/demoCatalog";
import { Spinner, makeStyles } from "@fluentui/react-components";
import {
  RocketRegular,
  PeopleRegular,
  CheckmarkCircleRegular,
  TimerRegular,
  ArrowClockwiseRegular,
  EyeRegular,
} from "@fluentui/react-icons";

const REFRESH_MS = 60_000;

function demoTitle(id: string): string {
  return DEMOS[id]?.title ?? id;
}

function scenarioLabel(id: string): string {
  if (id === "standard") return "Standard";
  return id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const EVENT_LABEL: Record<string, { label: string; color: string }> = {
  deploy_started: { label: "Started", color: "#58a6ff" },
  deploy_completed: { label: "Completed", color: "#3fb950" },
  deploy_failed: { label: "Failed", color: "#f85149" },
  deploy_cancelled: { label: "Cancelled", color: "#8b949e" },
};

// Fault-domain classifier for failed deploys: distinguishes failures the USER
// must resolve (input conflicts, tenant settings, consent, quota - not product
// bugs) from app/platform failures. Patterns mirror errorHelp.ts's non-retryable
// user-environment cases. Unknown errors default to app-side so real problems
// are never hidden behind a "user error" label.
const USER_FAULT_PATTERNS = [
  "already exists", "choose a different name", "invalid character", // input
  "feature is not available", // tenant can't create Fabric items
  "lacks a service principal", "aadsts", "consent", "conditional access", // tenant auth
  "sufficient scopes", // stale consent - re-sign-in fixes
  "quota", "not registered", "disallowed by policy", "public network", // subscription
  "paused", "no active fabric capacity", // capacity state
  "unauthorized", "sign-in expired", // session
];
function classifyFault(error?: string): "user" | "app" {
  if (!error) return "app";
  const m = error.toLowerCase();
  return USER_FAULT_PATTERNS.some((p) => m.includes(p)) ? "user" : "app";
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatDuration(s: number | null): string {
  if (s === null) return "-";
  if (s < 90) return `${Math.round(s)}s`;
  return `${(s / 60).toFixed(1)} min`;
}

/** Last N days ending today, as YYYY-MM-DD (UTC) - keeps the chart gap-free. */
function lastDays(n: number): string[] {
  const out: string[] = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - i));
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

const useStyles = makeStyles({
  page: {
    maxWidth: "1080px",
    marginLeft: "auto",
    marginRight: "auto",
    paddingLeft: "40px",
    paddingRight: "40px",
    paddingTop: "32px",
    paddingBottom: "64px",
    "@media (max-width: 640px)": {
      paddingLeft: "20px",
      paddingRight: "20px",
    },
  },
  header: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    flexWrap: "wrap" as const,
    gap: "8px",
    marginBottom: "8px",
  },
  title: { fontSize: "20px", fontWeight: 600, color: "#e6edf3", margin: 0 },
  subtitle: { fontSize: "13px", color: "#8b949e", marginBottom: "28px" },
  refreshed: { fontSize: "12px", color: "#484f58", display: "inline-flex", alignItems: "center", gap: "5px" },
  cardGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))",
    gap: "16px",
    marginBottom: "32px",
  },
  card: {
    backgroundColor: "#161b22",
    border: "1px solid #21262d",
    borderRadius: "10px",
    padding: "18px 20px",
  },
  cardLabel: {
    fontSize: "11px",
    fontWeight: 600,
    color: "#8b949e",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    display: "flex",
    alignItems: "center",
    gap: "6px",
    marginBottom: "10px",
  },
  cardValue: { fontSize: "30px", fontWeight: 700, color: "#e6edf3", lineHeight: 1 },
  cardSub: { fontSize: "12px", color: "#484f58", marginTop: "8px" },
  sectionTitle: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#e6edf3",
    marginTop: "36px",
    marginBottom: "14px",
  },
  panel: {
    backgroundColor: "#161b22",
    border: "1px solid #21262d",
    borderRadius: "10px",
    padding: "20px",
  },
  // ── Per-day column chart ──
  chart: {
    display: "flex",
    alignItems: "flex-end",
    gap: "3px",
    height: "140px",
  },
  chartCol: {
    flexGrow: 1,
    flexBasis: 0,
    minWidth: 0,
    display: "flex",
    flexDirection: "column" as const,
    justifyContent: "flex-end",
    height: "100%",
  },
  chartBar: {
    width: "100%",
    borderRadius: "3px 3px 0 0",
    backgroundColor: "#1f6feb",
    minHeight: "2px",
    transitionProperty: "height",
    transitionDuration: "0.3s",
    ":hover": { backgroundColor: "#388bfd" },
  },
  // Count label sitting on top of each day's bar.
  chartValue: {
    fontSize: "10px",
    lineHeight: "12px",
    color: "#8b949e",
    textAlign: "center" as const,
    marginBottom: "3px",
    whiteSpace: "nowrap" as const,
    fontVariantNumeric: "tabular-nums",
  },
  chartAxis: {
    display: "flex",
    justifyContent: "space-between",
    marginTop: "8px",
    fontSize: "11px",
    color: "#484f58",
  },
  // ── Horizontal bar leaderboard ──
  barRow: {
    display: "grid",
    gridTemplateColumns: "minmax(140px, 260px) 1fr 48px",
    alignItems: "center",
    gap: "12px",
    paddingTop: "7px",
    paddingBottom: "7px",
  },
  barLabel: {
    fontSize: "13px",
    color: "#e6edf3",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
  barTrack: {
    height: "10px",
    backgroundColor: "#21262d",
    borderRadius: "5px",
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    borderRadius: "5px",
    background: "linear-gradient(90deg, #1f6feb, #388bfd)",
    transitionProperty: "width",
    transitionDuration: "0.3s",
  },
  barCount: { fontSize: "13px", fontWeight: 600, color: "#8b949e", textAlign: "right" as const },
  // ── Outcomes strip ──
  outcomeStrip: {
    display: "flex",
    height: "12px",
    borderRadius: "6px",
    overflow: "hidden",
    marginBottom: "12px",
  },
  legend: { display: "flex", flexWrap: "wrap" as const, gap: "16px", fontSize: "12px", color: "#8b949e" },
  legendDot: { display: "inline-block", width: "9px", height: "9px", borderRadius: "50%", marginRight: "6px" },
  // ── Detail tables ──
  table: { width: "100%", borderCollapse: "collapse" as const },
  th: {
    textAlign: "left" as const,
    padding: "8px 10px",
    fontSize: "11px",
    fontWeight: 600,
    color: "#484f58",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    borderBottom: "1px solid #21262d",
    whiteSpace: "nowrap" as const,
  },
  td: {
    padding: "9px 10px",
    borderBottom: "1px solid #161b22",
    fontSize: "13px",
    color: "#e6edf3",
    verticalAlign: "middle" as const,
  },
  tdMuted: { color: "#8b949e" },
  num: { textAlign: "right" as const, fontVariantNumeric: "tabular-nums" },
  tableWrap: { overflowX: "auto" as const },
  // ── Small hour/weekday charts ──
  miniChartsRow: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))",
    gap: "16px",
  },
  percRow: { display: "flex", flexWrap: "wrap" as const, gap: "24px" },
  percItem: { textAlign: "center" as const },
  percLabel: { fontSize: "11px", fontWeight: 600, color: "#484f58", textTransform: "uppercase" as const, letterSpacing: "0.5px" },
  percValue: { fontSize: "18px", fontWeight: 700, color: "#e6edf3", marginTop: "4px" },
  empty: { textAlign: "center" as const, padding: "48px 0", color: "#484f58", fontSize: "13px" },
  error: { textAlign: "center" as const, padding: "48px 0", color: "#f85149", fontSize: "13px" },
  loading: { display: "flex", justifyContent: "center", padding: "96px 0" },
});

const OUTCOME_COLORS: Record<string, { color: string; label: string }> = {
  completed: { color: "#238636", label: "Completed" },
  failed: { color: "#da3633", label: "Failed" },
  cancelled: { color: "#6e7681", label: "Cancelled" },
};

export default function StatsClient() {
  const styles = useStyles();
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchStats();
        if (!cancelled) {
          setStats(s);
          setError(null);
          setRefreshedAt(new Date());
        }
      } catch {
        if (!cancelled && !stats) setError("Couldn't load usage stats. Try refreshing the page.");
      }
    };
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const days = lastDays(30);
  const perDayMax = stats ? Math.max(1, ...days.map((d) => stats.per_day[d] ?? 0)) : 1;
  const demoEntries = stats ? Object.entries(stats.by_demo) : [];
  const demoMax = Math.max(1, ...demoEntries.map(([, n]) => n));
  const outcomeEntries = stats
    ? Object.entries(stats.outcomes).filter(([k]) => k in OUTCOME_COLORS)
    : [];
  const outcomeTotal = outcomeEntries.reduce((a, [, n]) => a + n, 0);

  return (
    <>
      <Breadcrumbs pageName="Usage" />
      <div className={styles.page}>
        <div className={styles.header}>
          <h1 className={styles.title}>Usage dashboard</h1>
          {refreshedAt && (
            <span className={styles.refreshed}>
              <ArrowClockwiseRegular fontSize={12} aria-hidden />
              Updated {refreshedAt.toLocaleTimeString()} · auto-refreshes every minute
            </span>
          )}
        </div>
        <div className={styles.subtitle}>
          Live deployment activity across the gallery. This page shows aggregates only - no individual names appear here.
        </div>

        {error && <div className={styles.error}>{error}</div>}
        {!error && !stats && (
          <div className={styles.loading}>
            <Spinner label="Loading usage stats…" />
          </div>
        )}

        {stats && (
          <>
            <div className={styles.cardGrid}>
              <div className={styles.card}>
                <div className={styles.cardLabel}><RocketRegular fontSize={14} aria-hidden />Deployments</div>
                <div className={styles.cardValue}>{stats.total_deployments}</div>
                <div className={styles.cardSub}>all time</div>
              </div>
              <div className={styles.card}>
                <div className={styles.cardLabel}><EyeRegular fontSize={14} aria-hidden />Demo views</div>
                <div className={styles.cardValue}>{stats.total_views ?? "-"}</div>
                <div className={styles.cardSub}>demo pages opened</div>
              </div>
              <div className={styles.card}>
                <div className={styles.cardLabel}><PeopleRegular fontSize={14} aria-hidden />Unique users</div>
                <div className={styles.cardValue}>{stats.distinct_users}</div>
                <div className={styles.cardSub}>all time</div>
              </div>
              <div className={styles.card}>
                <div className={styles.cardLabel}><PeopleRegular fontSize={14} aria-hidden />Active users</div>
                <div className={styles.cardValue}>{stats.distinct_users_7d ?? "-"}</div>
                <div className={styles.cardSub}>last 7 days · {stats.distinct_users_30d ?? "-"} in 30 days</div>
              </div>
              <div className={styles.card}>
                <div className={styles.cardLabel}><CheckmarkCircleRegular fontSize={14} aria-hidden />Success rate</div>
                <div className={styles.cardValue}>
                  {stats.success_rate === null ? "-" : `${Math.round(stats.success_rate * 100)}%`}
                </div>
                <div className={styles.cardSub}>of finished deployments</div>
              </div>
              <div className={styles.card}>
                <div className={styles.cardLabel}><TimerRegular fontSize={14} aria-hidden />Median duration</div>
                <div className={styles.cardValue}>{formatDuration(stats.median_duration_s)}</div>
                <div className={styles.cardSub}>start to finish</div>
              </div>
            </div>

            {stats.total_deployments === 0 ? (
              <div className={styles.panel}>
                <div className={styles.empty}>
                  No deployments recorded yet - stats appear here as soon as someone deploys a demo.
                </div>
              </div>
            ) : (
              <>
                <div className={styles.sectionTitle}>Deployments - last 30 days</div>
                <div className={styles.panel}>
                  <div className={styles.chart} role="img" aria-label="Deployments per day, last 30 days">
                    {days.map((d) => {
                      const n = stats.per_day[d] ?? 0;
                      return (
                        <div key={d} className={styles.chartCol} title={`${d}: ${n} deployment${n === 1 ? "" : "s"}`}>
                          {n > 0 && <div className={styles.chartValue}>{n}</div>}
                          <div
                            className={styles.chartBar}
                            style={{
                              // 85% cap leaves room for the count label above
                              // the tallest bar inside the fixed-height chart.
                              height: `${(n / perDayMax) * 85}%`,
                              backgroundColor: n === 0 ? "#21262d" : undefined,
                            }}
                          />
                        </div>
                      );
                    })}
                  </div>
                  <div className={styles.chartAxis}>
                    <span>{days[0]}</span>
                    <span>{days[days.length - 1]}</span>
                  </div>
                </div>

                <div className={styles.sectionTitle}>Most deployed demos</div>
                <div className={styles.panel}>
                  {demoEntries.map(([id, n]) => (
                    <div key={id} className={styles.barRow}>
                      <span className={styles.barLabel} title={demoTitle(id)}>{demoTitle(id)}</span>
                      <div className={styles.barTrack}>
                        <div className={styles.barFill} style={{ width: `${(n / demoMax) * 100}%` }} />
                      </div>
                      <span className={styles.barCount}>{n}</span>
                    </div>
                  ))}
                </div>

                {/* ── Most viewed demos (anonymous page views) ── */}
                {stats.views_by_demo && Object.keys(stats.views_by_demo).length > 0 && (
                  <>
                    <div className={styles.sectionTitle}>Most viewed demos</div>
                    <div className={styles.panel}>
                      {Object.entries(stats.views_by_demo).map(([id, n]) => {
                        const viewMax = Math.max(1, ...Object.values(stats.views_by_demo ?? {}));
                        return (
                          <div key={id} className={styles.barRow}>
                            <span className={styles.barLabel} title={demoTitle(id)}>{demoTitle(id)}</span>
                            <div className={styles.barTrack}>
                              <div className={styles.barFill} style={{ width: `${(n / viewMax) * 100}%`, background: "linear-gradient(90deg, #8957e5, #a371f7)" }} />
                            </div>
                            <span className={styles.barCount}>{n}</span>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}

                {outcomeTotal > 0 && (
                  <>
                    <div className={styles.sectionTitle}>Outcomes</div>
                    <div className={styles.panel}>
                      <div className={styles.outcomeStrip} role="img" aria-label="Deployment outcomes">
                        {outcomeEntries.map(([k, n]) => (
                          <div
                            key={k}
                            title={`${OUTCOME_COLORS[k].label}: ${n}`}
                            style={{
                              width: `${(n / outcomeTotal) * 100}%`,
                              backgroundColor: OUTCOME_COLORS[k].color,
                            }}
                          />
                        ))}
                      </div>
                      <div className={styles.legend}>
                        {outcomeEntries.map(([k, n]) => (
                          <span key={k}>
                            <span className={styles.legendDot} style={{ backgroundColor: OUTCOME_COLORS[k].color }} />
                            {OUTCOME_COLORS[k].label}: <strong style={{ color: "#e6edf3" }}>{n}</strong>
                          </span>
                        ))}
                      </div>
                    </div>
                  </>
                )}

                {/* ── Per-demo outcome detail ── */}
                {stats.demo_detail && Object.keys(stats.demo_detail).length > 0 && (
                  <>
                    <div className={styles.sectionTitle}>Per-demo details</div>
                    <div className={styles.panel}>
                      <div className={styles.tableWrap}>
                        <table className={styles.table}>
                          <thead>
                            <tr>
                              <th className={styles.th}>Demo</th>
                              <th className={`${styles.th} ${styles.num}`}>Deployments</th>
                              <th className={`${styles.th} ${styles.num}`}>Completed</th>
                              <th className={`${styles.th} ${styles.num}`}>Failed</th>
                              <th className={`${styles.th} ${styles.num}`}>Success</th>
                              <th className={`${styles.th} ${styles.num}`}>Median</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(stats.demo_detail).map(([id, d]) => (
                              <tr key={id}>
                                <td className={styles.td}>{demoTitle(id)}</td>
                                <td className={`${styles.td} ${styles.num}`}>{d.started}</td>
                                <td className={`${styles.td} ${styles.num}`} style={{ color: "#3fb950" }}>{d.completed}</td>
                                <td className={`${styles.td} ${styles.num}`} style={{ color: d.failed ? "#f85149" : undefined }}>{d.failed}</td>
                                <td className={`${styles.td} ${styles.num}`}>{d.success_rate === null ? "-" : `${Math.round(d.success_rate * 100)}%`}</td>
                                <td className={`${styles.td} ${styles.num} ${styles.tdMuted}`}>{formatDuration(d.median_duration_s)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}

                {/* ── Per-scenario outcome detail ── */}
                {stats.scenario_detail && Object.keys(stats.scenario_detail).length > 0 && (
                  <>
                    <div className={styles.sectionTitle}>Per-scenario details</div>
                    <div className={styles.panel}>
                      <div className={styles.tableWrap}>
                        <table className={styles.table}>
                          <thead>
                            <tr>
                              <th className={styles.th}>Scenario</th>
                              <th className={`${styles.th} ${styles.num}`}>Deployments</th>
                              <th className={`${styles.th} ${styles.num}`}>Completed</th>
                              <th className={`${styles.th} ${styles.num}`}>Failed</th>
                              <th className={`${styles.th} ${styles.num}`}>Success</th>
                              <th className={`${styles.th} ${styles.num}`}>Median</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(stats.scenario_detail).map(([id, d]) => (
                              <tr key={id}>
                                <td className={styles.td}>{scenarioLabel(id)}</td>
                                <td className={`${styles.td} ${styles.num}`}>{d.started}</td>
                                <td className={`${styles.td} ${styles.num}`} style={{ color: "#3fb950" }}>{d.completed}</td>
                                <td className={`${styles.td} ${styles.num}`} style={{ color: d.failed ? "#f85149" : undefined }}>{d.failed}</td>
                                <td className={`${styles.td} ${styles.num}`}>{d.success_rate === null ? "-" : `${Math.round(d.success_rate * 100)}%`}</td>
                                <td className={`${styles.td} ${styles.num} ${styles.tdMuted}`}>{formatDuration(d.median_duration_s)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}

                {/* ── Duration percentiles ── */}
                {stats.duration_percentiles_s && stats.duration_percentiles_s.median !== null && (
                  <>
                    <div className={styles.sectionTitle}>Deployment duration</div>
                    <div className={styles.panel}>
                      <div className={styles.percRow}>
                        {(["min", "p25", "median", "p75", "p90", "max"] as const).map((k) => (
                          <div key={k} className={styles.percItem}>
                            <div className={styles.percLabel}>{k}</div>
                            <div className={styles.percValue}>{formatDuration(stats.duration_percentiles_s?.[k] ?? null)}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}

                {/* ── Activity patterns ── */}
                {(stats.by_hour_utc || stats.by_weekday) && (
                  <>
                    <div className={styles.sectionTitle}>Activity patterns</div>
                    <div className={styles.miniChartsRow}>
                      {stats.by_hour_utc && (
                        <div className={styles.panel}>
                          <div className={styles.percLabel} style={{ marginBottom: 10 }}>By hour (UTC)</div>
                          <div className={styles.chart} style={{ height: 80 }} role="img" aria-label="Deployments by hour of day (UTC)">
                            {Array.from({ length: 24 }, (_, h) => {
                              const n = stats.by_hour_utc?.[String(h)] ?? 0;
                              const max = Math.max(1, ...Object.values(stats.by_hour_utc ?? {}));
                              return (
                                <div key={h} className={styles.chartCol} title={`${String(h).padStart(2, "0")}:00 UTC - ${n}`}>
                                  <div className={styles.chartBar} style={{ height: `${(n / max) * 100}%`, backgroundColor: n === 0 ? "#21262d" : undefined }} />
                                </div>
                              );
                            })}
                          </div>
                          <div className={styles.chartAxis}><span>00</span><span>12</span><span>23</span></div>
                        </div>
                      )}
                      {stats.by_weekday && (
                        <div className={styles.panel}>
                          <div className={styles.percLabel} style={{ marginBottom: 10 }}>By weekday</div>
                          <div className={styles.chart} style={{ height: 80 }} role="img" aria-label="Deployments by weekday">
                            {WEEKDAYS.map((label, d) => {
                              const n = stats.by_weekday?.[String(d)] ?? 0;
                              const max = Math.max(1, ...Object.values(stats.by_weekday ?? {}));
                              return (
                                <div key={d} className={styles.chartCol} title={`${label} - ${n}`}>
                                  <div className={styles.chartBar} style={{ height: `${(n / max) * 100}%`, backgroundColor: n === 0 ? "#21262d" : undefined }} />
                                </div>
                              );
                            })}
                          </div>
                          <div className={styles.chartAxis}><span>Mon</span><span>Sun</span></div>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {/* ── Recent activity (no identities - truncated hash only) ── */}
                {stats.recent && stats.recent.length > 0 && (
                  <>
                    <div className={styles.sectionTitle}>Recent activity</div>
                    <div className={styles.panel}>
                      <div className={styles.tableWrap}>
                        <table className={styles.table}>
                          <thead>
                            <tr>
                              <th className={styles.th}>When</th>
                              <th className={styles.th}>Event</th>
                              <th className={styles.th}>Demo</th>
                              <th className={styles.th}>Scenario</th>
                              <th className={`${styles.th} ${styles.num}`}>Duration</th>
                              <th className={styles.th}>User</th>
                            </tr>
                          </thead>
                          <tbody>
                            {stats.recent.map((e, i) => {
                              // User-side failures (name conflicts, tenant/consent/quota
                              // issues) aren't product failures - amber + explicit label
                              // so they read differently from app/platform failures.
                              // The server classifies from the FULL error text (which the
                              // public API omits); client classification is only a
                              // fallback for older API responses.
                              const fault = e.event === "deploy_failed" ? (e.fault ?? classifyFault(e.error)) : null;
                              const ev =
                                fault === "user"
                                  ? { label: "Failed · user side", color: "#d29922" }
                                  : fault === "app"
                                  ? { label: "Failed · app side", color: "#f85149" }
                                  : EVENT_LABEL[e.event] ?? { label: e.event, color: "#8b949e" };
                              // When a failure message follows, drop this row's bottom
                              // border so the message reads as part of the same entry.
                              const joined = e.error ? { borderBottom: "none" } : undefined;
                              return (
                                <Fragment key={i}>
                                  <tr>
                                    <td className={`${styles.td} ${styles.tdMuted}`} style={joined} title={e.ts}>{timeAgo(e.ts)}</td>
                                    <td className={styles.td} style={joined}>
                                      <span className={styles.legendDot} style={{ backgroundColor: ev.color }} />
                                      {ev.label}
                                    </td>
                                    <td className={styles.td} style={joined}>{demoTitle(e.demo_id)}</td>
                                    <td className={`${styles.td} ${styles.tdMuted}`} style={joined}>{scenarioLabel(e.scenario_id)}</td>
                                    <td className={`${styles.td} ${styles.num} ${styles.tdMuted}`} style={joined}>{e.duration_s !== undefined ? formatDuration(e.duration_s) : "-"}</td>
                                    <td className={`${styles.td} ${styles.tdMuted}`} style={{ fontFamily: "Consolas, monospace", fontSize: 12, ...joined }}>#{e.user}</td>
                                  </tr>
                                  {e.error && (
                                    <tr>
                                      <td colSpan={6} style={{ padding: "0 10px 10px 26px", borderBottom: "1px solid #161b22", color: fault === "user" ? "rgba(210,153,34,0.9)" : "rgba(248,81,73,0.85)", fontSize: 12, lineHeight: 1.45 }}>
                                        {e.failed_step && (
                                          <span style={{ fontFamily: "Consolas, monospace", color: "#8b949e" }}>{e.failed_step} · </span>
                                        )}
                                        {e.error}
                                      </td>
                                    </tr>
                                  )}
                                </Fragment>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
