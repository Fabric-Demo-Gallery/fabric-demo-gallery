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
  MessageBar,
  MessageBarBody,
  Select,
  Spinner,
  Text,
} from "@fluentui/react-components";
import {
  CheckmarkCircleFilled,
  CircleRegular,
  CopyRegular,
  DeleteRegular,
  DismissCircleFilled,
  OpenRegular,
} from "@fluentui/react-icons";
import { useAuth } from "@/lib/AuthProvider";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { AGENT_PACKS, AGENT_PACK_PREREQUISITES, AGENT_PACK_RESOURCES } from "@/lib/agentPacks";
import { deleteAgentPackResources, deployAgentPack, fetchAgentPacks, fetchSubscriptions, getJob } from "@/lib/api";
import type { AzureSubscription, JobDetail } from "@/lib/api";
import { EvaluationsPanel, IncidentPanel, PlantBoardPanel, PresenterScript } from "./LiveDemo";
import type { TokenGetter } from "./LiveDemo";

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
  layout: { display: "grid", gridTemplateColumns: "minmax(0, 1fr) 360px", gap: "32px", alignItems: "start" },
  title: { fontSize: "28px", fontWeight: 700, color: "#e6edf3", margin: "0 0 8px 0" },
  lead: { color: "#8b949e", fontSize: "15px", lineHeight: 1.6, margin: "0 0 24px 0" },
  h2: { fontSize: "16px", fontWeight: 600, color: "#e6edf3", margin: "28px 0 10px 0" },
  list: { color: "#8b949e", fontSize: "14px", lineHeight: 1.7, margin: 0, paddingLeft: "20px" },
  card: { backgroundColor: "#161b22", border: "1px solid #30363d", borderRadius: "8px", padding: "18px 20px", marginBottom: "16px", scrollMarginTop: "110px" },
  cardTitle: { fontSize: "17px", fontWeight: 600, color: "#e6edf3", margin: "0 0 6px 0" },
  cardText: { color: "#8b949e", fontSize: "14px", lineHeight: 1.6, margin: "0 0 10px 0" },
  label: { display: "block", fontSize: "11px", fontWeight: 600, color: "#8b949e", textTransform: "uppercase" as const, letterSpacing: "0.5px", margin: "12px 0 6px 0" },
  prompt: { display: "flex", gap: "8px", alignItems: "flex-start", backgroundColor: "#0d1117", border: "1px solid #21262d", borderRadius: "6px", padding: "8px 10px", marginBottom: "6px", color: "#c9d1d9", fontSize: "13px", lineHeight: 1.5 },
  panel: { backgroundColor: "#161b22", border: "1px solid #30363d", borderRadius: "8px", padding: "20px", position: "sticky" as const, top: "100px" },
  fieldLabel: { display: "block", fontSize: "12px", fontWeight: 600, color: "#e6edf3", marginBottom: "6px" },
  field: { marginBottom: "14px" },
  badge: { display: "inline-block", fontSize: "11px", color: "#58a6ff", border: "1px solid #1f6feb", borderRadius: "10px", padding: "1px 8px", marginRight: "6px" },
  tool: { display: "inline-block", fontSize: "11px", color: "#3fb68b", border: "1px solid #238636", borderRadius: "10px", padding: "1px 8px", marginRight: "6px" },
};

function StepIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckmarkCircleFilled style={{ color: "#3fb68b" }} />;
  if (status === "failed") return <DismissCircleFilled style={{ color: "#f85149" }} />;
  if (status === "running") return <Spinner size="extra-tiny" />;
  return <CircleRegular style={{ color: "#484f58" }} />;
}

function CopyPrompt({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div style={s.prompt}>
      <span style={{ flexGrow: 1 }}>{text}</span>
      <Button
        appearance="subtle"
        size="small"
        icon={<CopyRegular />}
        aria-label="Copy question"
        title={copied ? "Copied" : "Copy"}
        onClick={() => {
          void navigator.clipboard?.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}
      />
    </div>
  );
}

export default function AgentPackClient({ packId }: { packId: string }) {
  const pack = AGENT_PACKS[packId];
  const searchParams = useSearchParams();
  const { account, initialized, login, getFabricToken, getManagementToken, getAgentToken } = useAuth();

  const [regions, setRegions] = useState<string[]>(Object.keys(REGION_NAMES));
  const [region, setRegion] = useState("swedencentral");
  const [subs, setSubs] = useState<AzureSubscription[]>([]);
  const [subsLoading, setSubsLoading] = useState(false);
  const [subsError, setSubsError] = useState("");
  const [subscription, setSubscription] = useState("");
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState("");
  const [jobId, setJobId] = useState<string | null>(searchParams.get("job_id"));
  const [job, setJob] = useState<JobDetail | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [boardKey, setBoardKey] = useState(0);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const getTokens = useCallback<TokenGetter>(
    async (opts) => {
      const token = await getFabricToken({ allowRedirect: false });
      const management = await getManagementToken({ allowRedirect: false });
      const agent = opts?.agent ? await getAgentToken({ allowRedirect: false }) : undefined;
      return { token, management, agent };
    },
    [getFabricToken, getManagementToken, getAgentToken]
  );
  const refreshBoard = useCallback(() => setBoardKey((k) => k + 1), []);

  useEffect(() => {
    fetchAgentPacks()
      .then((packs) => {
        const info = packs.find((p) => p.id === packId);
        if (info) {
          setRegions(info.regions);
          setRegion(info.defaultRegion);
        }
      })
      .catch(() => { /* keep the built-in region list */ });
  }, [packId]);

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

  // The job runs server-side; polling it lets the page resume after a reload
  // or when opened from Monitoring with ?job_id=.
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

  if (!pack) return null;

  const running = !!job && !TERMINAL.has(job.status);
  const az = job?.azure_resources;
  const portalUrl = az?.portalUrl || "";
  const canDeploy = !!account && !!subscription && !!region && !deploying && !running;
  const live = !!jobId && job?.status === "completed" && !deleted && !!az?.resourceGroup;
  const agentTitles = Object.fromEntries(pack.agents.map((a) => [a.id, a.title]));
  const agentLinks: Record<string, string> = {};
  try {
    const done = job?.steps.find((st) => st.name === "done");
    const detail = done?.detail ? (JSON.parse(done.detail) as { agents?: { id: string; portalUrl?: string }[] }) : null;
    for (const a of detail?.agents ?? []) if (a.portalUrl) agentLinks[a.id] = a.portalUrl;
  } catch { /* older deployments have no per-agent links */ }

  const handleDeploy = async () => {
    setDeploying(true);
    setError("");
    setDeleted(false);
    try {
      // Fresh, full-lifetime tokens; no redirect mid-deploy (it would unload the page).
      const token = await getFabricToken({ forceRefresh: true, allowRedirect: false });
      const management = await getManagementToken({ forceRefresh: true, allowRedirect: false });
      let agent = "";
      try {
        // May show a one-time consent popup for the Foundry Agent Service.
        agent = await getAgentToken({ forceRefresh: true, allowRedirect: false });
      } catch {
        setError(
          "Microsoft Foundry sign-in was cancelled or blocked. Allow the 'Foundry Agent Service' permission when prompted, or ask your administrator to approve it, then deploy again."
        );
        return;
      }
      const res = await deployAgentPack(token, { management, agent }, pack.id, { subscription_id: subscription, location: region });
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
      } catch { /* the backend reports the missing authorization */ }
      await deleteAgentPackResources(token, jobId, mgmt);
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
      <Breadcrumbs industrySlug={pack.industrySlug} pageName="AI Agents" />
      <div style={s.inner}>
        <div style={s.layout} className="fdg-agents-layout">
          <div>
            <div style={{ marginBottom: 10 }}>
              <span style={s.badge}>AI Agents</span>
              <span style={s.badge}>Microsoft Foundry</span>
              <span style={s.badge}>{pack.estimatedTime}</span>
            </div>
            <h1 style={s.title}>{pack.title}</h1>
            <p style={s.lead}>{pack.longDescription}</p>

            {live && jobId && pack.incident && az?.incidentWorkflow && (
              <>
                <IncidentPanel
                  pack={pack}
                  jobId={jobId}
                  getTokens={getTokens}
                  agentTitles={agentTitles}
                  onBoardChanged={refreshBoard}
                />
                <PlantBoardPanel jobId={jobId} getTokens={getTokens} refreshKey={boardKey} />
                <EvaluationsPanel jobId={jobId} getTokens={getTokens} tracingUrl={az.tracingUrl} workflowUrl={az.workflowUrl} />
              </>
            )}
            {!(live && az?.incidentWorkflow) && pack.incident && (
              <section style={s.card} aria-labelledby="incident-preview-title">
                <h2 id="incident-preview-title" style={s.cardTitle}>{pack.incident.title}</h2>
                <div style={{ marginBottom: 8 }}>
                  <span style={s.tool}>Multi-agent workflow</span>
                  <span style={s.tool}>Human approval</span>
                  <span style={s.tool}>Tracing + evaluations</span>
                </div>
                <p style={s.cardText}>{pack.incident.summary}</p>
                <ol style={s.list}>{pack.incident.flow.map((f) => <li key={f}>{f}</li>)}</ol>
                <Caption1 style={{ display: "block", color: "#8b949e", marginTop: 10 }}>
                  {live
                    ? "This deployment predates the incident workflow - deploy again to get it."
                    : "Deploy the agents to run it live from this page. The work orders and quality holds the agents create show up on a maintenance board here."}
                </Caption1>
              </section>
            )}
            <PresenterScript pack={pack} />

            {pack.agents.map((agent) => (
              <section key={agent.id} id={agent.id} style={s.card} aria-labelledby={`${agent.id}-title`}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
                  <h2 id={`${agent.id}-title`} style={s.cardTitle}>{agent.title}</h2>
                  {live && agentLinks[agent.id] && (
                    <Button size="small" appearance="subtle" icon={<OpenRegular />} as="a" href={agentLinks[agent.id]} target="_blank" rel="noopener noreferrer">
                      Chat in Foundry
                    </Button>
                  )}
                </div>
                <div style={{ marginBottom: 8 }}>
                  {agent.tools.map((t) => <span key={t} style={s.tool}>{t}</span>)}
                </div>
                <p style={s.cardText}>{agent.description}</p>
                <Caption1 style={{ display: "block", color: "#8b949e" }}>Grounded on: {agent.grounding}</Caption1>
                {agent.actions && (
                  <Caption1 style={{ display: "block", color: "#8b949e" }}>Actions: {agent.actions}</Caption1>
                )}
                <span style={s.label}>Try asking</span>
                {agent.prompts.map((p) => <CopyPrompt key={p} text={p} />)}
                {agent.samples && agent.samples.length > 0 && (
                  <>
                    <span style={s.label}>Sample images to attach in the playground</span>
                    <ul style={s.list}>
                      {agent.samples.map((f) => (
                        <li key={f.fileName}>
                          <a href={`/ai-agents/${pack.id}/${f.fileName}`} download style={{ color: "#58a6ff" }}>{f.label}</a>
                        </li>
                      ))}
                    </ul>
                    <Caption1 style={{ display: "block", color: "#8b949e", marginTop: 6 }}>
                      Photos of real parts work too - a phone picture is enough.
                    </Caption1>
                  </>
                )}
              </section>
            ))}

            <h2 style={s.h2}>What gets deployed</h2>
            <ul style={s.list}>{AGENT_PACK_RESOURCES.map((r) => <li key={r}>{r}</li>)}</ul>

            <h2 style={s.h2}>Before you deploy</h2>
            <ul style={s.list}>{AGENT_PACK_PREREQUISITES.map((p) => <li key={p}>{p}</li>)}</ul>
          </div>

          <aside style={s.panel} aria-label="Deploy">
            <Text weight="semibold" size={400} style={{ display: "block", color: "#e6edf3", marginBottom: 14 }}>
              Deploy all {pack.agents.length} agents
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
                  <label style={s.fieldLabel} htmlFor="agents-sub">Subscription</label>
                  {subsLoading ? (
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}><Spinner size="tiny" /><Caption1>Loading subscriptions…</Caption1></div>
                  ) : subs.length > 0 ? (
                    <Select id="agents-sub" value={subscription} onChange={(_, d) => setSubscription(d.value)} disabled={running}>
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
                  <label style={s.fieldLabel} htmlFor="agents-region">Region</label>
                  <Select id="agents-region" value={region} onChange={(_, d) => setRegion(d.value)} disabled={running}>
                    {regions.map((r) => <option key={r} value={r}>{REGION_NAMES[r] || r}</option>)}
                  </Select>
                </div>

                <Button appearance="primary" onClick={handleDeploy} disabled={!canDeploy} style={{ width: "100%" }}>
                  {deploying ? "Starting…" : running ? "Deploying…" : "Deploy"}
                </Button>
                <Caption1 style={{ display: "block", color: "#8b949e", marginTop: 8 }}>
                  Creates a new resource group. You may be asked once to allow the Foundry Agent Service permission.
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
                <Text weight="semibold" style={{ display: "block", color: "#e6edf3", marginBottom: 8, wordBreak: "break-all" }}>
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

                {job.status === "completed" && !deleted && (
                  <MessageBar intent="success" style={{ marginTop: 6 }}>
                    <MessageBarBody>
                      Your agents are ready. Run the incident on this page, or open an agent in Foundry and paste one of the questions.
                      {az?.foundryProject ? ` Project: ${az.foundryProject}.` : ""}
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
                  {job.status === "completed" && portalUrl && !deleted && (
                    <Button appearance="primary" icon={<OpenRegular />} as="a" href={portalUrl} target="_blank" rel="noopener noreferrer">
                      Open in Foundry
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
              This deletes the resource group <strong>“{az?.resourceGroup}”</strong> and everything in it: the Foundry
              account, the model, the agents, the workflows and the maintenance board. This can&apos;t be undone.
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
