"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthProvider";
import { getJobs, deleteJobWorkspace, cancelJob } from "@/lib/api";
import type { JobSummary } from "@/lib/api";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { explainError } from "@/lib/errorHelp";
import { TagBadge } from "@/lib/TagBadge";
import {
  Button,
  Caption1,
  Spinner,
  Text,
  makeStyles,
  Dialog,
  DialogSurface,
  DialogBody,
  DialogTitle,
  DialogContent,
  DialogActions,
  MessageBar,
  MessageBarBody,
} from "@fluentui/react-components";
import {
  CheckmarkCircleFilled,
  DismissCircleFilled,
  OpenRegular,
  DeleteRegular,
  EyeRegular,
  DismissRegular,
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
        <TagBadge label="Running" color="#4493f8">
          <Spinner size="extra-tiny" />
        </TagBadge>
      );
    case "completed":
      return (
        <TagBadge label="Completed" color="#3fb68b">
          <CheckmarkCircleFilled fontSize={12} />
        </TagBadge>
      );
    case "failed":
      return (
        <TagBadge label="Failed" color="#f85149">
          <DismissCircleFilled fontSize={12} />
        </TagBadge>
      );
    case "pending":
      return <TagBadge label="Pending" color="#d29922" />;
    case "cancelled":
      return <TagBadge label="Cancelled" />;
    default:
      return <TagBadge label={status} />;
  }
}

export default function MonitoringClient() {
  const { account, login, getFabricToken, getManagementToken, initialized } = useAuth();
  const router = useRouter();
  const styles = useStyles();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingJob, setDeletingJob] = useState<string | null>(null);
  const [cancellingJob, setCancellingJob] = useState<string | null>(null);
  // Fluent dialogs replace the native confirm()/alert() — styled, focus-trapped,
  // and they say WHICH workspace is affected.
  const [confirmAction, setConfirmAction] = useState<{ kind: "delete" | "cancel"; job: JobSummary } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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
    setDeletingJob(job.job_id);
    setActionError(null);
    try {
      const token = await getFabricToken();
      // Best-effort management token so the backend can also delete Azure
      // resources the deploy provisioned (SQL server, Foundry, AI Search).
      let mgmt: string | undefined;
      try {
        mgmt = (await getManagementToken()) || undefined;
      } catch { /* non-fatal — workspace still gets deleted */ }
      await deleteJobWorkspace(token, job.job_id, mgmt);
      await fetchJobs();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeletingJob(null);
    }
  };

  // Cancel a stuck running/pending job so it stops showing as active. Does not
  // delete any workspace that may have been partially created.
  const handleCancel = async (job: JobSummary) => {
    setCancellingJob(job.job_id);
    setActionError(null);
    try {
      const token = await getFabricToken();
      await cancelJob(token, job.job_id);
      await fetchJobs();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Cancel failed");
    } finally {
      setCancellingJob(null);
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
    <>
      <Breadcrumbs pageName="Deployment Monitoring" />
      <div className={styles.page}>
        <div className={styles.header}>
        <h1 className={styles.title} style={{ margin: 0 }}>Deployment Monitoring</h1>
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

      {!loading && error && (() => {
        const friendly = explainError(error);
        return (
          <div role="alert" style={{ color: "#f85149", textAlign: "center", padding: "32px 0" }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{friendly.title}</div>
            <Caption1 style={{ color: "#8b949e" }}>{friendly.guidance}</Caption1>
          </div>
        );
      })()}

      {!loading && !error && actionError && (
        <MessageBar intent="error" style={{ marginBottom: 12 }}>
          <MessageBarBody>{actionError}</MessageBarBody>
        </MessageBar>
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
          <caption style={{ position: "absolute", width: 1, height: 1, padding: 0, margin: -1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap", border: 0 }}>
            Your Fabric deployments
          </caption>
          <thead>
            <tr>
              <th scope="col" className={styles.th}>Demo</th>
              <th scope="col" className={styles.th}>Workspace</th>
              <th scope="col" className={styles.th}>Started</th>
              <th scope="col" className={styles.th}>Status</th>
              <th scope="col" className={styles.th}>Progress</th>
              <th scope="col" className={styles.th}>Actions</th>
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
                    <div
                      className={styles.progressBar}
                      role="progressbar"
                      aria-valuenow={pct}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${job.step_summary.completed} of ${job.step_summary.total} steps complete`}
                    >
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
                      <Button
                        appearance="subtle"
                        size="small"
                        icon={<EyeRegular />}
                        onClick={() =>
                          router.push(
                            `/demos/${job.demo_id}?job_id=${job.job_id}${
                              job.scenario_id
                                ? `&mode=custom&scenario=${job.scenario_id}`
                                : ""
                            }`
                          )
                        }
                      >
                        View
                      </Button>
                      {(job.status === "running" || job.status === "pending") && (
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<DismissRegular />}
                          onClick={() => setConfirmAction({ kind: "cancel", job })}
                          disabled={cancellingJob === job.job_id}
                        >
                          {cancellingJob === job.job_id ? "..." : "Cancel"}
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
                            onClick={() => setConfirmAction({ kind: "delete", job })}
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

      {/* Confirmation dialog — replaces the native confirm() so it's styled,
          focus-trapped, and names the workspace it affects. */}
      <Dialog open={confirmAction !== null} onOpenChange={(_, d) => { if (!d.open) setConfirmAction(null); }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>
              {confirmAction?.kind === "delete" ? "Delete workspace?" : "Cancel deployment?"}
            </DialogTitle>
            <DialogContent>
              {confirmAction?.kind === "delete"
                ? <>This permanently deletes the workspace <strong>“{confirmAction.job.workspace_name}”</strong> and every item in it. This can&apos;t be undone.</>
                : <>The deployment of <strong>“{confirmAction?.job.workspace_name}”</strong> will be marked cancelled. Anything already created is kept.</>}
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setConfirmAction(null)}>
                Keep it
              </Button>
              <Button
                appearance="primary"
                onClick={async () => {
                  const a = confirmAction;
                  setConfirmAction(null);
                  if (!a) return;
                  if (a.kind === "delete") await handleDelete(a.job);
                  else await handleCancel(a.job);
                }}
              >
                {confirmAction?.kind === "delete" ? "Delete" : "Cancel deployment"}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </>
  );
}
