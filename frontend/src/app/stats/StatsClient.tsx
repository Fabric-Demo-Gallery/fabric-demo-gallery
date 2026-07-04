"use client";

import { useEffect, useState } from "react";
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
} from "@fluentui/react-icons";

const REFRESH_MS = 60_000;

function demoTitle(id: string): string {
  return DEMOS[id]?.title ?? id;
}

function formatDuration(s: number | null): string {
  if (s === null) return "—";
  if (s < 90) return `${Math.round(s)}s`;
  return `${(s / 60).toFixed(1)} min`;
}

/** Last N days ending today, as YYYY-MM-DD (UTC) — keeps the chart gap-free. */
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
          Live deployment activity across the gallery. Counts are anonymous — no names or emails are stored.
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
                <div className={styles.cardLabel}><PeopleRegular fontSize={14} aria-hidden />Unique users</div>
                <div className={styles.cardValue}>{stats.distinct_users}</div>
                <div className={styles.cardSub}>anonymised</div>
              </div>
              <div className={styles.card}>
                <div className={styles.cardLabel}><CheckmarkCircleRegular fontSize={14} aria-hidden />Success rate</div>
                <div className={styles.cardValue}>
                  {stats.success_rate === null ? "—" : `${Math.round(stats.success_rate * 100)}%`}
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
                  No deployments recorded yet — stats appear here as soon as someone deploys a demo.
                </div>
              </div>
            ) : (
              <>
                <div className={styles.sectionTitle}>Deployments — last 30 days</div>
                <div className={styles.panel}>
                  <div className={styles.chart} role="img" aria-label="Deployments per day, last 30 days">
                    {days.map((d) => {
                      const n = stats.per_day[d] ?? 0;
                      return (
                        <div key={d} className={styles.chartCol} title={`${d}: ${n} deployment${n === 1 ? "" : "s"}`}>
                          <div
                            className={styles.chartBar}
                            style={{
                              height: `${(n / perDayMax) * 100}%`,
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
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
