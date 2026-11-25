"use client";

// Live demo for a deployed agent pack: the multi-agent incident workflow with
// its approval step, the plant maintenance board the agents write to, the
// agents' evaluation scores, and links to tracing and the workflow designer.

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Button,
  Caption1,
  MessageBar,
  MessageBarBody,
  Spinner,
  Text,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowClockwiseRegular,
  CheckmarkCircleFilled,
  CheckmarkRegular,
  CircleRegular,
  DismissCircleFilled,
  DismissRegular,
  OpenRegular,
  PauseCircleRegular,
  PlayRegular,
  SubtractCircleRegular,
} from "@fluentui/react-icons";
import type { AgentPack } from "@/lib/agentPacks";
import {
  decideIncident,
  getEvaluations,
  getIncident,
  getPlantBoard,
  rerunEvaluations,
  startIncident,
} from "@/lib/api";
import type { EvaluationResult, IncidentStatus, PackTokens, PlantBoard } from "@/lib/api";

export type TokenGetter = (opts?: { agent?: boolean }) => Promise<PackTokens>;

const MAX_PHOTO_BYTES = 4 * 1024 * 1024;
const ACTIVE_RUN = new Set(["Running", "Waiting", "Paused"]);

const s = {
  card: { backgroundColor: "#161b22", border: "1px solid #30363d", borderRadius: "8px", padding: "18px 20px", marginBottom: "16px" },
  cardTitle: { fontSize: "17px", fontWeight: 600, color: "#e6edf3", margin: "0 0 6px 0" },
  text: { color: "#8b949e", fontSize: "14px", lineHeight: 1.6, margin: "0 0 10px 0" },
  label: { display: "block", fontSize: "11px", fontWeight: 600, color: "#8b949e", textTransform: "uppercase" as const, letterSpacing: "0.5px", margin: "12px 0 6px 0" },
  list: { color: "#8b949e", fontSize: "14px", lineHeight: 1.7, margin: 0, paddingLeft: "20px" },
  step: { borderTop: "1px solid #21262d", padding: "10px 0" },
  output: { backgroundColor: "#0d1117", border: "1px solid #21262d", borderRadius: "6px", padding: "10px 14px", marginTop: "8px", color: "#c9d1d9", fontSize: "13px", lineHeight: 1.55, overflowX: "auto" as const },
  approval: { backgroundColor: "#1c2128", border: "1px solid #d29922", borderRadius: "8px", padding: "14px 16px", margin: "10px 0" },
  table: { width: "100%", borderCollapse: "collapse" as const, fontSize: "13px", color: "#c9d1d9" },
  th: { textAlign: "left" as const, color: "#8b949e", fontWeight: 600, padding: "6px 8px", borderBottom: "1px solid #30363d" },
  td: { padding: "6px 8px", borderBottom: "1px solid #21262d", verticalAlign: "top" as const },
  photo: (selected: boolean) => ({
    border: `2px solid ${selected ? "#58a6ff" : "#30363d"}`,
    borderRadius: "6px",
    padding: 0,
    background: "none",
    cursor: "pointer",
    width: "140px",
    textAlign: "center" as const,
    color: "#8b949e",
    fontSize: "12px",
  }),
  link: { color: "#58a6ff" },
};

export function Markdown({ text }: { text: string }) {
  return (
    <div className="fdg-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckmarkCircleFilled style={{ color: "#3fb68b" }} />;
  if (status === "failed") return <DismissCircleFilled style={{ color: "#f85149" }} />;
  if (status === "running") return <Spinner size="extra-tiny" />;
  if (status === "waiting") return <PauseCircleRegular style={{ color: "#d29922" }} />;
  if (status === "skipped") return <SubtractCircleRegular style={{ color: "#484f58" }} />;
  return <CircleRegular style={{ color: "#484f58" }} />;
}

async function photoDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Couldn't read the photo"));
    reader.readAsDataURL(blob);
  });
}

// ── Incident workflow ──────────────────────────────────────────────────────

export function IncidentPanel({
  pack,
  jobId,
  getTokens,
  agentTitles,
  onBoardChanged,
}: {
  pack: AgentPack;
  jobId: string;
  getTokens: TokenGetter;
  agentTitles: Record<string, string>;
  onBoardChanged: () => void;
}) {
  const scenario = pack.incident!;
  const storageKey = `fdg-incident-${jobId}`;
  const [photo, setPhoto] = useState<string>(scenario.photos[0]?.fileName ?? "");
  const [upload, setUpload] = useState<{ name: string; dataUrl: string } | null>(null);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [status, setStatus] = useState<IncidentStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setIncidentId(sessionStorage.getItem(storageKey));
  }, [storageKey]);

  useEffect(() => {
    if (!incidentId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await getIncident(await getTokens(), jobId, incidentId);
        if (cancelled) return;
        setStatus(next);
        setError("");
        if (!ACTIVE_RUN.has(next.status)) {
          onBoardChanged();
          return;
        }
      } catch (e) {
        if (cancelled) return;
        setError(errorText(e));
      }
      pollRef.current = setTimeout(tick, 4000);
    };
    void tick();
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [incidentId, jobId, getTokens, onBoardChanged]);

  const running = !!incidentId && (!status || ACTIVE_RUN.has(status.status));

  const handleStart = async () => {
    setStarting(true);
    setError("");
    try {
      let dataUrl = "";
      if (photo === "upload") {
        dataUrl = upload?.dataUrl ?? "";
      } else if (photo) {
        const res = await fetch(`/ai-agents/${pack.id}/${photo}`);
        if (!res.ok) throw new Error("Couldn't load the sample photo");
        dataUrl = await photoDataUrl(await res.blob());
      }
      const { incidentId: id } = await startIncident(await getTokens(), jobId, {
        line: scenario.line,
        shift: scenario.shift,
        date: scenario.date,
        photo: dataUrl,
      });
      sessionStorage.setItem(storageKey, id);
      setStatus(null);
      setComment("");
      setIncidentId(id);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setStarting(false);
    }
  };

  const handleDecision = async (decision: "approved" | "rejected") => {
    if (!incidentId) return;
    setDeciding(true);
    setError("");
    try {
      await decideIncident(await getTokens(), jobId, incidentId, { decision, comment });
      setStatus((prev) => (prev ? { ...prev, awaitingApproval: false } : prev));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setDeciding(false);
    }
  };

  const handleUpload = async (file: File | undefined) => {
    if (!file) return;
    if (!["image/png", "image/jpeg"].includes(file.type)) {
      setError("Use a PNG or JPEG photo.");
      return;
    }
    if (file.size > MAX_PHOTO_BYTES) {
      setError("The photo must be under 4 MB.");
      return;
    }
    setUpload({ name: file.name, dataUrl: await photoDataUrl(file) });
    setPhoto("upload");
    setError("");
  };

  const elapsed = status?.startedAt
    ? Math.round(((status.endedAt ? Date.parse(status.endedAt) : Date.now()) - Date.parse(status.startedAt)) / 1000)
    : 0;

  return (
    <section style={s.card} aria-labelledby="incident-title">
      <h2 id="incident-title" style={s.cardTitle}>{scenario.title}</h2>
      <p style={s.text}>{scenario.summary}</p>

      <span style={s.label}>Part photo sent with the incident</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        {scenario.photos.map((p) => (
          <button
            key={p.fileName}
            type="button"
            style={s.photo(photo === p.fileName)}
            onClick={() => setPhoto(p.fileName)}
            aria-pressed={photo === p.fileName}
            disabled={running}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`/ai-agents/${pack.id}/${p.fileName}`} alt={p.label} style={{ width: "100%", borderRadius: "4px 4px 0 0", display: "block" }} />
            <span style={{ display: "block", padding: "4px" }}>{p.label}</span>
          </button>
        ))}
        <label style={{ ...s.photo(photo === "upload"), padding: "8px", display: "block", opacity: running ? 0.5 : 1 }}>
          <input
            type="file"
            accept="image/png,image/jpeg"
            style={{ display: "none" }}
            disabled={running}
            onChange={(e) => void handleUpload(e.target.files?.[0])}
          />
          {upload ? `Your photo: ${upload.name}` : "Upload your own photo"}
        </label>
        <button type="button" style={{ ...s.photo(photo === ""), padding: "8px" }} onClick={() => setPhoto("")} disabled={running}>
          No photo
        </button>
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14 }}>
        <Button
          appearance="primary"
          icon={<PlayRegular />}
          onClick={handleStart}
          disabled={starting || running || (photo === "upload" && !upload)}
        >
          {starting ? "Starting…" : incidentId && !running ? "Start a new incident" : "Start incident"}
        </Button>
        {status && (
          <Caption1 style={{ color: "#8b949e" }}>
            Incident {status.incidentId.slice(-8)} · {status.status} · {elapsed}s
          </Caption1>
        )}
      </div>

      {error && (
        <MessageBar intent="error" style={{ marginTop: 12 }}>
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}

      {!incidentId && (
        <>
          <span style={s.label}>What happens</span>
          <ol style={s.list}>{scenario.flow.map((f) => <li key={f}>{f}</li>)}</ol>
        </>
      )}

      {incidentId && !status && !error && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
          <Spinner size="tiny" /><Caption1>Starting the workflow…</Caption1>
        </div>
      )}

      {status && (
        <ol style={{ listStyle: "none", padding: 0, margin: "14px 0 0 0" }} aria-label="Incident steps">
          {status.steps.map((step) => (
            <li key={step.id} style={s.step}>
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <span style={{ marginTop: 2 }}><StatusIcon status={step.status} /></span>
                <div style={{ flexGrow: 1, minWidth: 0 }}>
                  <Text weight="semibold" style={{ color: "#e6edf3" }}>{step.title}</Text>
                  <Caption1 style={{ display: "block", color: "#8b949e" }}>
                    {step.agent === "supervisor" ? "You, as the maintenance supervisor" : agentTitles[step.agent] ?? step.agent}
                    {step.status === "skipped" ? " · skipped" : ""}
                  </Caption1>
                  {step.error && <Caption1 style={{ display: "block", color: "#f85149" }}>{step.error}</Caption1>}

                  {step.id === "approval" && step.status === "waiting" && status.awaitingApproval && status.draft && (
                    <div style={s.approval} role="group" aria-label="Approve the work order">
                      <Text weight="semibold" style={{ display: "block", color: "#e6edf3", marginBottom: 6 }}>
                        Proposed work order · {status.draft.priority} · {status.draft.machine_id}
                      </Text>
                      <Text style={{ display: "block", color: "#e6edf3", marginBottom: 6 }}>{status.draft.title}</Text>
                      <div style={s.output}><Markdown text={status.draft.description} /></div>
                      <Textarea
                        value={comment}
                        onChange={(_, d) => setComment(d.value)}
                        placeholder="Comment (optional)"
                        aria-label="Comment"
                        maxLength={500}
                        style={{ width: "100%", marginTop: 10 }}
                      />
                      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                        <Button appearance="primary" icon={<CheckmarkRegular />} onClick={() => void handleDecision("approved")} disabled={deciding}>
                          Approve
                        </Button>
                        <Button icon={<DismissRegular />} onClick={() => void handleDecision("rejected")} disabled={deciding}>
                          Reject
                        </Button>
                      </div>
                    </div>
                  )}
                  {step.id === "approval" && step.status === "completed" && step.data && (
                    <Caption1 style={{ display: "block", color: "#8b949e" }}>
                      {String(step.data.status ?? "")} by {String(step.data.decided_by ?? "")}
                      {step.data.comment ? `: ${String(step.data.comment)}` : ""}
                    </Caption1>
                  )}

                  {step.status === "completed" && step.output && (
                    <details open={step.id === "handover"} style={{ marginTop: 6 }}>
                      <summary style={{ cursor: "pointer", color: "#58a6ff", fontSize: "13px" }}>
                        {step.id === "handover" ? "Shift handover" : "Agent answer"}
                      </summary>
                      <div style={s.output}><Markdown text={step.output} /></div>
                    </details>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}

      {status?.status === "Succeeded" && (
        <MessageBar intent="success" style={{ marginTop: 10 }}>
          <MessageBarBody>Incident handled in {elapsed} seconds. Check the maintenance board for the holds and the work order.</MessageBarBody>
        </MessageBar>
      )}
      {status && !ACTIVE_RUN.has(status.status) && status.status !== "Succeeded" && (
        <MessageBar intent="error" style={{ marginTop: 10 }}>
          <MessageBarBody>The workflow ended with status {status.status}. Open it in the Azure portal to see the failed step.</MessageBarBody>
        </MessageBar>
      )}
    </section>
  );
}

// ── Plant maintenance board ────────────────────────────────────────────────

export function PlantBoardPanel({ jobId, getTokens, refreshKey }: { jobId: string; getTokens: TokenGetter; refreshKey: number }) {
  const [board, setBoard] = useState<PlantBoard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setBoard(await getPlantBoard(await getTokens(), jobId));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [jobId, getTokens]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <section style={s.card} aria-labelledby="board-title">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 id="board-title" style={s.cardTitle}>Plant maintenance system</h2>
        <Button appearance="subtle" size="small" icon={<ArrowClockwiseRegular />} onClick={() => void load()} disabled={loading}>
          Refresh
        </Button>
      </div>
      <p style={s.text}>
        Work orders and quality holds the agents created through their OpenAPI tool - from the incident workflow or from your chats in Foundry.
      </p>
      {error && (
        <MessageBar intent="warning"><MessageBarBody>{error}</MessageBarBody></MessageBar>
      )}
      {loading && !board && <Spinner size="tiny" />}
      {board && (
        <>
          <span style={s.label}>Work orders ({board.workOrders.length})</span>
          {board.workOrders.length === 0 ? (
            <Caption1 style={{ color: "#8b949e" }}>None yet.</Caption1>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={s.table}>
                <thead><tr><th style={s.th}>ID</th><th style={s.th}>Priority</th><th style={s.th}>Machine</th><th style={s.th}>Title</th><th style={s.th}>Status</th><th style={s.th}>By</th></tr></thead>
                <tbody>
                  {board.workOrders.map((w) => (
                    <tr key={w.id}>
                      <td style={{ ...s.td, whiteSpace: "nowrap" }}>{w.id}</td>
                      <td style={s.td}>{w.priority}</td>
                      <td style={s.td}>{w.machine_id}</td>
                      <td style={s.td}>
                        <details>
                          <summary style={{ cursor: "pointer" }}>{w.title}</summary>
                          <div style={s.output}><Markdown text={w.description} /></div>
                        </details>
                      </td>
                      <td style={s.td}>{w.status}</td>
                      <td style={s.td}>{w.requested_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <span style={s.label}>Quality holds ({board.qualityHolds.length})</span>
          {board.qualityHolds.length === 0 ? (
            <Caption1 style={{ color: "#8b949e" }}>None yet.</Caption1>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={s.table}>
                <thead><tr><th style={s.th}>ID</th><th style={s.th}>Batch</th><th style={s.th}>Machine</th><th style={s.th}>Reason</th><th style={s.th}>Status</th></tr></thead>
                <tbody>
                  {board.qualityHolds.map((h) => (
                    <tr key={h.id}>
                      <td style={{ ...s.td, whiteSpace: "nowrap" }}>{h.id}</td>
                      <td style={s.td}>{h.batch_id}</td>
                      <td style={s.td}>{h.machine_id}</td>
                      <td style={s.td}>{h.reason}</td>
                      <td style={s.td}>{h.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

// ── Evaluations, tracing and links ─────────────────────────────────────────

export function EvaluationsPanel({
  jobId,
  getTokens,
  tracingUrl,
  workflowUrl,
}: {
  jobId: string;
  getTokens: TokenGetter;
  tracingUrl?: string;
  workflowUrl?: string;
}) {
  const [results, setResults] = useState<EvaluationResult[] | null>(null);
  const [error, setError] = useState("");
  const [rerunning, setRerunning] = useState(false);
  const [round, setRound] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await getEvaluations(await getTokens({ agent: true }), jobId);
        if (cancelled) return;
        setResults(next);
        setError("");
        if (next.every((r) => ["completed", "failed", "canceled"].includes(r.status))) return;
      } catch (e) {
        if (cancelled) return;
        setError(errorText(e));
        return;
      }
      timer.current = setTimeout(tick, 20000);
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [jobId, getTokens, round]);

  const handleRerun = async () => {
    setRerunning(true);
    setError("");
    try {
      await rerunEvaluations(await getTokens({ agent: true }), jobId);
      setResults(null);
      setRound((r) => r + 1);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRerunning(false);
    }
  };

  const criteria = Array.from(new Set((results ?? []).flatMap((r) => r.criteria.map((c) => c.name))));

  return (
    <section style={s.card} aria-labelledby="evals-title">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 id="evals-title" style={s.cardTitle}>Evaluations and tracing</h2>
        {results && results.length > 0 && (
          <Button appearance="subtle" size="small" icon={<ArrowClockwiseRegular />} onClick={() => void handleRerun()} disabled={rerunning}>
            {rerunning ? "Starting…" : "Run again"}
          </Button>
        )}
      </div>
      <p style={s.text}>
        Foundry runs each agent on a small test set and a judge model scores the answers (task adherence pass/fail, the others 1-5, higher is better). Every agent and tool call is also traced in Application Insights.
      </p>
      {error && <MessageBar intent="warning"><MessageBarBody>{error}</MessageBarBody></MessageBar>}
      {!results && !error && <Spinner size="tiny" />}
      {results && results.length === 0 && (
        <>
          <Button appearance="primary" icon={<PlayRegular />} onClick={() => void handleRerun()} disabled={rerunning}>
            {rerunning ? "Starting…" : "Run evaluations"}
          </Button>
          <Caption1 style={{ display: "block", color: "#8b949e", marginTop: 6 }}>
            Takes about 5 minutes and uses the same model as the agents - start it before the demo, not during the incident.
          </Caption1>
        </>
      )}
      {results && results.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={s.th}>Agent</th>
                {criteria.map((c) => <th key={c} style={s.th}>{c}</th>)}
                <th style={s.th}>Report</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.agent}>
                  <td style={s.td}>{r.title}<Caption1 style={{ display: "block", color: "#8b949e" }}>{r.queries} test questions</Caption1></td>
                  {r.status === "completed" ? (
                    criteria.map((c) => {
                      const v = r.criteria.find((x) => x.name === c);
                      return (
                        <td key={c} style={s.td}>
                          {!v || v.average === null
                            ? "–"
                            : v.scale === 1
                              ? `${Math.round(v.average * 100)}% pass`
                              : `${v.average.toFixed(1)} / ${v.scale}`}
                          {v && v.scored > 0 && <Caption1 style={{ display: "block", color: "#8b949e" }}>{v.passed}/{v.scored} passed</Caption1>}
                        </td>
                      );
                    })
                  ) : (
                    <td style={s.td} colSpan={Math.max(criteria.length, 1)}>
                      {r.error ? (
                        <Caption1 style={{ color: "#f85149" }}>{r.error}</Caption1>
                      ) : (
                        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><Spinner size="extra-tiny" /><Caption1>{r.status || "queued"}…</Caption1></span>
                      )}
                    </td>
                  )}
                  <td style={s.td}>
                    {r.reportUrl ? <a href={r.reportUrl} target="_blank" rel="noopener noreferrer" style={s.link}>Open</a> : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
        {tracingUrl && (
          <Button size="small" icon={<OpenRegular />} as="a" href={tracingUrl} target="_blank" rel="noopener noreferrer">
            Tracing in Application Insights
          </Button>
        )}
        {workflowUrl && (
          <Button size="small" icon={<OpenRegular />} as="a" href={workflowUrl} target="_blank" rel="noopener noreferrer">
            Incident workflow in Azure
          </Button>
        )}
      </div>
      <Caption1 style={{ display: "block", color: "#8b949e", marginTop: 8 }}>
        In Foundry, each agent&apos;s Traces tab shows its conversations step by step, including tool calls.
      </Caption1>
    </section>
  );
}

// ── Presenter script ───────────────────────────────────────────────────────

export function PresenterScript({ pack }: { pack: AgentPack }) {
  if (!pack.presenterScript?.length) return null;
  const total = pack.presenterScript.reduce((sum, step) => sum + step.minutes, 0);
  return (
    <details style={s.card}>
      <summary style={{ cursor: "pointer", color: "#e6edf3", fontWeight: 600, fontSize: "15px" }}>
        Presenter script ({total} minutes)
      </summary>
      <ol style={{ ...s.list, marginTop: 10 }}>
        {pack.presenterScript.map((step) => (
          <li key={step.title} style={{ marginBottom: 10 }}>
            <Text weight="semibold" style={{ color: "#e6edf3" }}>{step.title}</Text>
            <Caption1 style={{ color: "#8b949e" }}> · {step.minutes} min</Caption1>
            <div><em>Say:</em> {step.say}</div>
            <div><em>Do:</em> {step.do}</div>
          </li>
        ))}
      </ol>
    </details>
  );
}
