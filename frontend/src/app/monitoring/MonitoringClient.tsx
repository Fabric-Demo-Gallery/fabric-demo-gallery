"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import NextLink from "next/link";
import { useAuth } from "@/lib/AuthProvider";
import { getJobs, deleteJobWorkspace } from "@/lib/api";
import type { JobSummary } from "@/lib/api";
import {
  Button,
  Badge,
  Caption1,
  Spinner,
  Text,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  CheckmarkCircleFilled,
  DismissCircleFilled,
  OpenRegular,
  ArrowLeftRegular,
  DeleteRegular,
  EyeRegular,
} from "@fluentui/react-icons";

const DEMO_TITLES: Record<string, string> = {
  "manufacturing-qc": "Quality Control Analytics",
  "retail-sales": "Sales & Inventory Analytics",
  "energy-grid": "Smart Grid Monitoring",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

const useStyles = makeStyles({
  page: {
    maxWidth: "1200px",
    marginLeft: "auto",
    marginRight: "auto",
    paddingLeft: "40px",
    paddingRight: "40px",
    paddingTop: "32px",
    paddingBottom: "48px",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: "24px",
  },
  title: {
    fontSize: "20px",
    fontWeight: 600,
    color: "#e6edf3",
  },
  backLink: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    color: "#8b949e",
    textDecoration: "none",
    fontSize: "13px",
    ":hover": { color: "#e6edf3" },
  },
  table: {
    width: "100%",
    borderCollapse: "collapse" as const,
  },
  th: {
    textAlign: "left" as const,
    padding: "10px 12px",
    fontSize: "11px",
    fontWeight: 600,
    color: "#484f58",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    borderBottom: "1px solid #21262d",
  },
  td: {
    padding: "12px 12px",
    borderBottom: "1px solid #161b22",
    fontSize: "13px",
    color: "#e6edf3",
    verticalAlign: "middle" as const,
  },
  row: {
    ":hover": {
      backgroundColor: "#161b22",
    },
  },
  progressBar: {
    width: "100%",
    height: "4px",
    backgroundColor: "#21262d",
    borderRadius: "2px",
    overflow: "hidden",
    marginTop: "4px",
  },
  progressFill: {
    height: "100%",
    borderRadius: "2px",
    transitionProperty: "width",
    transitionDuration: "0.3s",
  },
  actions: {
    display: "flex",
    gap: "6px",
  },
  empty: {
    textAlign: "center" as const,
    padding: "64px 0",
    color: "#484f58",
  },
  signIn: {
    textAlign: "center" as const,
    padding: "80px 0",
    color: "#8b949e",
  },
});

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "running":
      return (
        <Badge appearance="tint" color="informative" size="small">
          <Spinner size="extra-tiny" style={{ marginRight: 4 }} /> Running
        </Badge>
      );
    case "completed":
      return (
        <Badge appearance="tint" color="success" size="small">
          <CheckmarkCircleFilled fontSize={12} style={{ marginRight: 4, color: tokens.colorPaletteGreenForeground1 }} />
          Completed
        </Badge>
      );
    case "failed":
      return (
        <Badge appearance="tint" color="danger" size="small">
          <DismissCircleFilled fontSize={12} style={{ marginRight: 4, color: tokens.colorPaletteRedForeground1 }} />
          Failed
        </Badge>
      );
    case "pending":
      return (
        <Badge appearance="tint" color="warning" size="small">
          Pending
        </Badge>
      );
    default:
      return <Badge appearance="tint" size="small">{status}</Badge>;
  }
}

export default function MonitoringClient() {
  const { account, login, getFabricToken, initialized } = useAuth();
  const router = useRouter();
  const styles = useStyles();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingJob, setDeletingJob] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const token = await getFabricToken();
      const data = await getJobs(token);
      setJobs(data);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [getFabricToken]);

  useEffect(() => {
    if (!account) {
      setLoading(false);
      return;
    }
    fetchJobs();
  }, [account, fetchJobs]);

  // Auto-refresh while any job is active
  useEffect(() => {
    const hasActive = jobs.some((j) => j.status === "running" || j.status === "pending");
    if (!hasActive || !account) return;
    const interval = setInterval(fetchJobs, 10000);
    return () => clearInterval(interval);
  }, [jobs, account, fetchJobs]);

  const handleDelete = async (job: JobSummary) => {
    if (!confirm("Delete the workspace and all its items?")) return;
    setDeletingJob(job.job_id);
    try {
      const token = await getFabricToken();
      await deleteJobWorkspace(token, job.job_id);
      await fetchJobs();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeletingJob(null);
    }
  };

  if (!initialized) {
    return (
      <div className={styles.page}>
        <div style={{ textAlign: "center", padding: "80px 0" }}>
          <Spinner size="medium" />
        </div>
      </div>
    );
  }

  if (!account) {
    return (
      <div className={styles.page}>
        <div className={styles.signIn}>
          <Text size={400} style={{ display: "block", marginBottom: 16, color: "#e6edf3" }}>
            Sign in to view your deployments
          </Text>
          <Button appearance="primary" onClick={login}>
            Sign in with Microsoft
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <NextLink href="/" className={styles.backLink}>
            <ArrowLeftRegular fontSize={12} /> Gallery
          </NextLink>
          <span className={styles.title}>Deployment Monitoring</span>
        </div>
        <Button
          appearance="subtle"
          size="small"
          onClick={fetchJobs}
          disabled={loading}
        >
          Refresh
        </Button>
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: "64px 0" }}>
          <Spinner size="medium" label="Loading deployments..." />
        </div>
      )}

      {!loading && error && (
        <div style={{ color: "#f85149", textAlign: "center", padding: "32px 0" }}>
          {error}
        </div>
      )}

      {!loading && !error && jobs.length === 0 && (
        <div className={styles.empty}>
          <Text size={300} style={{ display: "block", marginBottom: 8 }}>
            No deployments yet
          </Text>
          <Caption1>Deploy a demo from the gallery to see it here.</Caption1>
        </div>
      )}

      {!loading && !error && jobs.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>Demo</th>
              <th className={styles.th}>Workspace</th>
              <th className={styles.th}>Started</th>
              <th className={styles.th}>Status</th>
              <th className={styles.th}>Progress</th>
              <th className={styles.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => {
              const pct =
                job.step_summary.total > 0
                  ? Math.round(
                      (job.step_summary.completed / job.step_summary.total) * 100
                    )
                  : 0;
              const barColor =
                job.status === "failed"
                  ? "#f85149"
                  : job.status === "completed"
                  ? "#3fb68b"
                  : "#58a6ff";
              return (
                <tr key={job.job_id} className={styles.row}>
                  <td className={styles.td}>
                    <Text weight="medium" size={300}>
                      {DEMO_TITLES[job.demo_id] || job.demo_id}
                    </Text>
                  </td>
                  <td className={styles.td}>
                    <Caption1>{job.workspace_name}</Caption1>
                  </td>
                  <td className={styles.td}>
                    <Caption1>{timeAgo(job.created_at)}</Caption1>
                  </td>
                  <td className={styles.td}>
                    <StatusBadge status={job.status} />
                  </td>
                  <td className={styles.td} style={{ minWidth: 120 }}>
                    <Caption1>
                      {job.step_summary.completed}/{job.step_summary.total} steps
                    </Caption1>
                    <div className={styles.progressBar}>
                      <div
                        className={styles.progressFill}
                        style={{
                          width: `${pct}%`,
                          backgroundColor: barColor,
                        }}
                      />
                    </div>
                  </td>
                  <td className={styles.td}>
                    <div className={styles.actions}>
                      {(job.status === "running" || job.status === "pending") && (
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<EyeRegular />}
                          onClick={() =>
                            router.push(`/demos/${job.demo_id}?job_id=${job.job_id}`)
                          }
                        >
                          View
                        </Button>
                      )}
                      {job.status === "completed" && job.workspace_id && (
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<OpenRegular />}
                          as="a"
                          href={`https://app.fabric.microsoft.com/groups/${job.workspace_id}`}
                          target="_blank"
                        >
                          Open
                        </Button>
                      )}
                      {(job.status === "failed" || job.status === "completed") &&
                        job.workspace_id && (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<DeleteRegular />}
                            onClick={() => handleDelete(job)}
                            disabled={deletingJob === job.job_id}
                          >
                            {deletingJob === job.job_id ? "..." : "Delete"}
                          </Button>
                        )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
