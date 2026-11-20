"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Button,
  Caption1,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  Input,
  MessageBar,
  MessageBarBody,
  Radio,
  RadioGroup,
  Select,
  Spinner,
  Text,
} from "@fluentui/react-components";
import {
  CheckmarkCircleFilled,
  CircleRegular,
  DeleteRegular,
  DismissCircleFilled,
  OpenRegular,
} from "@fluentui/react-icons";
import { useAuth } from "@/lib/AuthProvider";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { APPS, APP_PREREQUISITES, APP_RESOURCES } from "@/lib/appsCatalog";
import {
  deleteAppResources,
  deployApp,
  fetchAppsCatalog,
  fetchClientIp,
  fetchSubscriptions,
  getJob,
} from "@/lib/api";
import type { AzureSubscription, JobDetail } from "@/lib/api";

const FALLBACK_REGIONS = ["swedencentral", "germanywestcentral", "westeurope", "francecentral", "uksouth", "eastus", "eastus2", "westus3"];
const REGION_NAMES: Record<string, string> = {
  swedencentral: "Sweden Central",
  germanywestcentral: "Germany West Central",
  westeurope: "West Europe",
  francecentral: "France Central",
  uksouth: "UK South",
  eastus: "East US",
  eastus2: "East US 2",
  westus3: "West US 3",
};
const TERMINAL = new Set(["completed", "failed", "cancelled"]);

const s = {
  page: { minHeight: "100vh", backgroundColor: "#0d1117" },
  inner: { maxWidth: "1100px", margin: "0 auto", padding: "32px 40px 48px 40px" },
  layout: { display: "grid", gridTemplateColumns: "minmax(0, 1fr) 380px", gap: "32px", alignItems: "start" },
  title: { fontSize: "28px", fontWeight: 700, color: "#e6edf3", margin: "0 0 8px 0" },
  lead: { color: "#8b949e", fontSize: "15px", lineHeight: 1.6, margin: "0 0 24px 0" },
  h2: { fontSize: "16px", fontWeight: 600, color: "#e6edf3", margin: "28px 0 10px 0" },
  text: { color: "#8b949e", fontSize: "14px", lineHeight: 1.6 },
  list: { color: "#8b949e", fontSize: "14px", lineHeight: 1.7, margin: 0, paddingLeft: "20px" },
  panel: { backgroundColor: "#161b22", border: "1px solid #30363d", borderRadius: "8px", padding: "20px", position: "sticky" as const, top: "100px" },
  label: { display: "block", fontSize: "12px", fontWeight: 600, color: "#e6edf3", marginBottom: "6px" },
  field: { marginBottom: "14px" },
  badge: { display: "inline-block", fontSize: "11px", color: "#58a6ff", border: "1px solid #1f6feb", borderRadius: "10px", padding: "1px 8px", marginRight: "6px" },
};

function StepIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckmarkCircleFilled style={{ color: "#3fb68b" }} />;
  if (status === "failed") return <DismissCircleFilled style={{ color: "#f85149" }} />;
  if (status === "running") return <Spinner size="extra-tiny" />;
  return <CircleRegular style={{ color: "#484f58" }} />;
}

function appUrlOf(job: JobDetail | null): string {
  if (!job) return "";
  if (job.azure_resources?.appUrl) return job.azure_resources.appUrl;
  const done = job.steps.find((st) => st.name === "done" && st.status === "completed");
  try {
    return done?.detail ? (JSON.parse(done.detail).appUrl as string) || "" : "";
  } catch {
    return "";
  }
}

export default function AppDetailClient({ id }: { id: string }) {
  const app = APPS[id];
  const searchParams = useSearchParams();
  const { account, initialized, login, getFabricToken, getManagementToken } = useAuth();

  const [regions, setRegions] = useState<string[]>(FALLBACK_REGIONS);
  const [region, setRegion] = useState("swedencentral");
  const [subs, setSubs] = useState<AzureSubscription[]>([]);
  const [subsLoading, setSubsLoading] = useState(false);
  const [subsError, setSubsError] = useState("");
  const [subscription, setSubscription] = useState("");
  const [access, setAccess] = useState<"ip" | "public">("ip");
  const [ipText, setIpText] = useState("");
  const [detectedIp, setDetectedIp] = useState<string | null>(null);
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState("");
  const [jobId, setJobId] = useState<string | null>(searchParams.get("job_id"));
  const [job, setJob] = useState<JobDetail | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetchAppsCatalog()
      .then((c) => {
        setRegions(c.regions);
        setRegion(c.defaultRegion);
      })
      .catch(() => { /* keep fallback regions */ });
    fetchClientIp().then((ip) => {
      setDetectedIp(ip);
      if (ip) setIpText((current) => current || ip);
    });
  }, []);

  const loadSubscriptions = useCallback(async () => {
    setSubsLoading(true);
    setSubsError("");
    try {
      const mgmt = await getManagementToken({ allowRedirect: false });
      const list = await fetchSubscriptions(mgmt);
      setSubs(list);
      // No default: billable resources should land in a subscription the user picked.
      if (list.length === 1) setSubscription(list[0].id);
    } catch (e) {
      setSubsError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubsLoading(false);
    }
  }, [getManagementToken]);

  useEffect(() => {
    if (account) void loadSubscriptions();
  }, [account, loadSubscriptions]);

  // Poll the job while it runs. The job lives server-side, so leaving and
  // returning (or opening it from Monitoring via ?job_id=) resumes progress.
  useEffect(() => {
    if (!jobId || !account) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const token = await getFabricToken({ allowRedirect: false });
        const detail = await getJob(token, jobId);
        if (cancelled) return;
        setJob(detail);
        if (TERMINAL.has(detail.status)) return;
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
      pollRef.current = setTimeout(tick, 4000);
    };
    void tick();
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [jobId, account, getFabricToken]);

  if (!app) return null;

  const ranges = ipText.split(/[\s,;]+/).map((r) => r.trim()).filter(Boolean);
  const canDeploy = !!account && !!subscription && !!region && (access === "public" || ranges.length > 0) && !deploying;
  const running = !!job && !TERMINAL.has(job.status);
  const appUrl = appUrlOf(job);
  const az = job?.azure_resources;
  const portalUrl = az?.subscriptionId && az?.resourceGroup
    ? `https://portal.azure.com/#resource/subscriptions/${az.subscriptionId}/resourceGroups/${az.resourceGroup}/overview`
    : "";

  const handleDeploy = async () => {
    setDeploying(true);
    setError("");
    setDeleted(false);
    try {
      // Fresh, full-lifetime tokens; no redirect mid-deploy (it would unload the page).
      const token = await getFabricToken({ forceRefresh: true, allowRedirect: false });
      const mgmt = await getManagementToken({ forceRefresh: true, allowRedirect: false });
      const res = await deployApp(token, mgmt, app.id, {
        subscription_id: subscription,
        location: region,
        public_access: access === "public",
        allowed_ip_ranges: access === "public" ? [] : ranges,
      });
      setJob(null);
      setJobId(res.job_id);
      window.history.replaceState(null, "", `?job_id=${res.job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeploying(false);
    }
  };

  const handleDelete = async () => {
    if (!jobId) return;
    setConfirmDelete(false);
    setDeleting(true);
    setError("");
    try {
      const token = await getFabricToken({ allowRedirect: false });
      let mgmt: string | undefined;
      try {
        mgmt = (await getManagementToken({ allowRedirect: false })) || undefined;
      } catch { /* backend reports the missing authorization */ }
      await deleteAppResources(token, jobId, mgmt);
      setDeleted(true);
      setJob(await getJob(token, jobId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div style={s.page}>
      <Breadcrumbs industrySlug={app.industrySlug} pageName={app.title} />
      <div style={s.inner}>
        <div style={s.layout} className="fdg-app-layout">
          <div>
            <div style={{ marginBottom: 10 }}>
              <span style={s.badge}>Apps &amp; AI</span>
              <span style={s.badge}>Azure subscription</span>
              <span style={s.badge}>{app.estimatedTime}</span>
            </div>
            <h1 style={s.title}>{app.title}</h1>
            <p style={s.lead}>{app.longDescription}</p>

            <h2 style={s.h2}>Why it matters</h2>
            <p style={s.text}>{app.businessValue}</p>

            <h2 style={s.h2}>Talking points</h2>
            <ul style={s.list}>{app.talkingPoints.map((t) => <li key={t}>{t}</li>)}</ul>

            <h2 style={s.h2}>Demo flow</h2>
            <ol style={s.list}>
              {app.demoFlow.map((f) => (
                <li key={f.step}><strong style={{ color: "#e6edf3" }}>{f.step}.</strong> {f.detail}</li>
              ))}
            </ol>

            {app.samples && app.samples.length > 0 && (
              <>
                <h2 style={s.h2}>Sample files</h2>
                <ul style={s.list}>
                  {app.samples.map((f) => (
                    <li key={f.fileName}>
                      <a href={`/apps-ai/${app.id}/${f.fileName}`} download style={{ color: "#58a6ff" }}>{f.label}</a>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <h2 style={s.h2}>Architecture</h2>
            <ul style={s.list}>{app.architecture.map((a) => <li key={a}>{a}</li>)}</ul>

            <h2 style={s.h2}>What gets deployed</h2>
            <ul style={s.list}>{APP_RESOURCES.map((r) => <li key={r}>{r}</li>)}</ul>

            <h2 style={s.h2}>Before you deploy</h2>
            <ul style={s.list}>{APP_PREREQUISITES.map((p) => <li key={p}>{p}</li>)}</ul>
            <p style={{ ...s.text, marginTop: 10 }}>Language: {app.language}</p>
            <p style={s.text}>
              Source:{" "}
              <a
                href={`https://github.com/Fabric-Demo-Gallery/fabric-demo-gallery/tree/main/${app.sourcePath}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "#58a6ff" }}
              >
                {app.sourcePath}
              </a>
            </p>
          </div>

          <aside style={s.panel} aria-label="Deploy">
            <Text weight="semibold" size={400} style={{ display: "block", color: "#e6edf3", marginBottom: 14 }}>
              Deploy to Azure
            </Text>

            {!initialized ? (
              <Spinner size="small" />
            ) : !account ? (
              <>
                <Caption1 style={{ display: "block", color: "#8b949e", marginBottom: 12 }}>
                  Sign in with the account that has access to your Azure subscription.
                </Caption1>
                <Button appearance="primary" onClick={login}>Sign in with Microsoft</Button>
              </>
            ) : (
              <>
                <div style={s.field}>
                  <label style={s.label} htmlFor="app-sub">Subscription</label>
                  {subsLoading ? (
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}><Spinner size="tiny" /><Caption1>Loading subscriptions…</Caption1></div>
                  ) : subs.length > 0 ? (
                    <Select id="app-sub" value={subscription} onChange={(_, d) => setSubscription(d.value)} disabled={running}>
                      <option value="">Select…</option>
                      {subs.map((sub) => <option key={sub.id} value={sub.id}>{sub.displayName}</option>)}
                    </Select>
                  ) : (
                    <>
                      <MessageBar intent="error" style={{ marginBottom: 8 }}>
                        <MessageBarBody>{subsError || "No Azure subscriptions were returned - usually Azure consent wasn't granted."}</MessageBarBody>
                      </MessageBar>
                      <Button size="small" appearance="subtle" onClick={() => void loadSubscriptions()}>Retry Azure sign-in</Button>
                    </>
                  )}
                </div>

                <div style={s.field}>
                  <label style={s.label} htmlFor="app-region">Region</label>
                  <Select id="app-region" value={region} onChange={(_, d) => setRegion(d.value)} disabled={running}>
                    {regions.map((r) => <option key={r} value={r}>{REGION_NAMES[r] || r}</option>)}
                  </Select>
                </div>

                <div style={s.field}>
                  <label style={s.label} id="app-access">Who can open the app</label>
                  <RadioGroup aria-labelledby="app-access" value={access} onChange={(_, d) => setAccess(d.value as "ip" | "public")} disabled={running}>
                    <Radio value="ip" label="Only these IP addresses (recommended)" />
                    <Radio value="public" label="Anyone with the link" />
                  </RadioGroup>
                  {access === "ip" ? (
                    <>
                      <Input
                        value={ipText}
                        onChange={(_, d) => setIpText(d.value)}
                        placeholder="e.g. 203.0.113.10 or 203.0.113.0/24"
                        style={{ width: "100%", marginTop: 6 }}
                        disabled={running}
                        aria-label="Allowed public IPv4 addresses or ranges"
                      />
                      <Caption1 style={{ display: "block", color: "#8b949e", marginTop: 4 }}>
                        {detectedIp
                          ? `Pre-filled with your current public IP (${detectedIp}). Separate several entries with commas. You can change the list later under the frontend Container App's Ingress settings.`
                          : "Enter the public IPv4 address you'll present from. Separate several entries with commas."}
                      </Caption1>
                    </>
                  ) : (
                    <MessageBar intent="warning" style={{ marginTop: 6 }}>
                      <MessageBarBody>
                        The app has no sign-in. Anyone who has the URL can use it and consume your model quota.
                      </MessageBarBody>
                    </MessageBar>
                  )}
                </div>

                <Button appearance="primary" onClick={handleDeploy} disabled={!canDeploy || running} style={{ width: "100%" }}>
                  {deploying ? "Starting…" : running ? "Deploying…" : "Deploy"}
                </Button>
                <Caption1 style={{ display: "block", color: "#8b949e", marginTop: 8 }}>
                  Creates billable resources in a new resource group. Delete it when you are done.
                </Caption1>
              </>
            )}

            {error && (
              <MessageBar intent="error" style={{ marginTop: 12 }}>
                <MessageBarBody>{error}</MessageBarBody>
              </MessageBar>
            )}

            {job && (
              <div style={{ marginTop: 18, borderTop: "1px solid #21262d", paddingTop: 14 }}>
                <Text weight="semibold" style={{ display: "block", color: "#e6edf3", marginBottom: 8 }}>
                  {job.workspace_name}
                </Text>
                <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {job.steps.filter((st) => st.name !== "done").map((st) => (
                    <li key={st.name} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 8 }}>
                      <span style={{ marginTop: 2 }}><StepIcon status={st.status} /></span>
                      <span>
                        <Caption1 style={{ display: "block", color: "#e6edf3" }}>{st.description}</Caption1>
                        {st.detail && st.status !== "pending" && (
                          <Caption1 style={{ display: "block", color: st.status === "failed" ? "#f85149" : "#8b949e", wordBreak: "break-word" }}>
                            {st.detail}
                          </Caption1>
                        )}
                      </span>
                    </li>
                  ))}
                </ol>

                {job.status === "completed" && appUrl && !deleted && (
                  <MessageBar intent="success" style={{ marginTop: 6 }}>
                    <MessageBarBody>
                      Your app is ready. If the page is blank at first, give the containers a minute to warm up. If it shows &quot;RBAC: access denied&quot;, your network reaches Azure from a different public IP than the one allowed - add that IP under the frontend Container App&apos;s Ingress settings in the Azure portal.
                    </MessageBarBody>
                  </MessageBar>
                )}
                {(job.status === "failed" || job.status === "cancelled") && job.error && (
                  <MessageBar intent="error" style={{ marginTop: 6 }}>
                    <MessageBarBody>{job.error}</MessageBarBody>
                  </MessageBar>
                )}
                {deleted && (
                  <MessageBar intent="info" style={{ marginTop: 6 }}>
                    <MessageBarBody>The resource group is being deleted. Azure finishes this in the background.</MessageBarBody>
                  </MessageBar>
                )}

                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                  {job.status === "completed" && appUrl && !deleted && (
                    <Button appearance="primary" icon={<OpenRegular />} as="a" href={appUrl} target="_blank" rel="noopener noreferrer">
                      Open app
                    </Button>
                  )}
                  {portalUrl && !deleted && (
                    <Button appearance="subtle" icon={<OpenRegular />} as="a" href={portalUrl} target="_blank" rel="noopener noreferrer">
                      Azure portal
                    </Button>
                  )}
                  {TERMINAL.has(job.status) && az?.resourceGroup && !deleted && (
                    <Button appearance="subtle" icon={<DeleteRegular />} onClick={() => setConfirmDelete(true)} disabled={deleting}>
                      {deleting ? "Deleting…" : "Delete resources"}
                    </Button>
                  )}
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>

      <Dialog open={confirmDelete} onOpenChange={(_, d) => { if (!d.open) setConfirmDelete(false); }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Delete resources?</DialogTitle>
            <DialogContent>
              This deletes the resource group <strong>“{az?.resourceGroup}”</strong> and everything in it: the app,
              the Foundry account, and its model deployment. This can&apos;t be undone.
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setConfirmDelete(false)}>Keep it</Button>
              <Button appearance="primary" onClick={handleDelete}>Delete</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  );
}
