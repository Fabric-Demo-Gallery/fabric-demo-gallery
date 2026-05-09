"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/AuthProvider";

// Full demo details (in production, fetched from backend)
const DEMOS: Record<string, DemoDetail> = {
  "manufacturing-qc": {
    id: "manufacturing-qc",
    industry: "Manufacturing",
    title: "Quality Control Analytics",
    description:
      "Monitor production quality with IoT sensor data, track OEE, defect rates, and yield across production lines.",
    longDescription:
      "This demo deploys a complete manufacturing quality control analytics environment. It ingests synthetic IoT sensor data (temperature, pressure, vibration) from production lines along with batch production records. The data flows through a Bronze-Silver-Gold medallion architecture, producing KPIs like Overall Equipment Effectiveness (OEE), defect rates, yield percentages, and Mean Time Between Failures (MTBF). A Power BI semantic model with Direct Lake connectivity powers real-time dashboards with control charts and trend analysis.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Sensor Data)",
        "Silver (Cleaned & Enriched)",
        "Gold (KPI Aggregations)",
      ],
    },
    sampleData: [
      {
        fileName: "sensor_readings.csv",
        description: "50,000 IoT sensor readings — temperature, pressure, vibration, humidity",
        format: "csv",
        rows: 50000,
      },
      {
        fileName: "production_batches.csv",
        description: "2,000 production batch records with units, defects, downtime",
        format: "csv",
        rows: 2000,
      },
      {
        fileName: "equipment_catalog.csv",
        description: "50 machines across 4 production lines",
        format: "csv",
        rows: 50,
      },
    ],
    fabricItems: [
      { type: "Lakehouse", name: "quality_lakehouse", description: "Central data lakehouse" },
      { type: "Notebook", name: "01_bronze_ingest", description: "Ingest raw CSVs → Bronze Delta tables", order: 1 },
      { type: "Notebook", name: "02_silver_transform", description: "Clean, deduplicate, flag anomalies", order: 2 },
      { type: "Notebook", name: "03_gold_aggregate", description: "6 Gold tables: OEE, equipment health, shift, product rankings, weekly trends, scorecards", order: 3 },
      { type: "Notebook", name: "04_reporting_views", description: "SQL views: executive dashboard, equipment alerts, production trends, scorecard", order: 4 },
      { type: "Notebook", name: "05_dashboard", description: "Interactive analytics dashboard rendered inline + saved as HTML", order: 5 },
      { type: "SemanticModel", name: "quality_analytics_model", description: "Direct Lake model — 6 tables, 30+ measures, relationships" },
      { type: "Report", name: "Quality Control Dashboard", description: "3-page dashboard: Quality Overview, Equipment Health, Product Quality" },
      { type: "DataPipeline", name: "daily_quality_pipeline", description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },
  "retail-sales": {
    id: "retail-sales",
    industry: "Retail",
    title: "Sales & Inventory Analytics",
    description:
      "Analyze POS transactions, track sales trends, monitor inventory turnover, and identify top products.",
    longDescription:
      "This demo deploys a retail analytics environment built on the medallion architecture. It ingests synthetic point-of-sale transaction data along with product catalog, store location, and inventory snapshot dimensions. The pipeline produces daily and weekly sales aggregations, basket analysis metrics, inventory turnover rates, and demand indicators. A star-schema semantic model powers dashboards showing revenue trends, top products, store-level comparisons, and inventory health alerts.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Transactions)",
        "Silver (Cleaned & Conformed)",
        "Gold (Sales & Inventory KPIs)",
      ],
    },
    sampleData: [
      { fileName: "pos_transactions.csv", description: "100,000 POS line items across 30 stores", format: "csv", rows: 100000 },
      { fileName: "products.csv", description: "541 products in 4 categories", format: "csv", rows: 541 },
      { fileName: "stores.csv", description: "30 store locations across the US", format: "csv", rows: 30 },
      { fileName: "inventory_snapshots.csv", description: "15,750 inventory snapshots", format: "csv", rows: 15750 },
    ],
    fabricItems: [
      { type: "Lakehouse", name: "retail_lakehouse", description: "Central data lakehouse" },
      { type: "Notebook", name: "01_bronze_ingest", description: "Ingest raw CSVs → Bronze Delta tables", order: 1 },
      { type: "Notebook", name: "02_silver_transform", description: "Clean, conform, calculate line totals", order: 2 },
      { type: "Notebook", name: "03_gold_aggregate", description: "Sales & inventory KPIs", order: 3 },
      { type: "SemanticModel", name: "retail_analytics_model", description: "Direct Lake — sales & inventory with 14 measures" },
      { type: "Report", name: "Retail Sales Dashboard", description: "3-page dashboard: Sales, Inventory, Margin & Basket" },
      { type: "DataPipeline", name: "daily_retail_pipeline", description: "Orchestrates all notebooks sequentially" },
    ],
  },
};

interface DemoDetail {
  id: string;
  industry: string;
  title: string;
  description: string;
  longDescription: string;
  estimatedTime: string;
  prerequisites: string[];
  architecture: { pattern: string; layers: string[] };
  sampleData: { fileName: string; description: string; format: string; rows: number }[];
  fabricItems: { type: string; name: string; description: string; order?: number }[];
}

type DeployStep = {
  name: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  detail?: string | null;
};

export default function DemoDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const demo = DEMOS[id];
  const { account, login, getFabricToken, getStorageToken } = useAuth();

  const [showDeploy, setShowDeploy] = useState(false);
  const [workspaceName, setWorkspaceName] = useState("");
  const [deploying, setDeploying] = useState(false);
  const [steps, setSteps] = useState<DeployStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [capacities, setCapacities] = useState<{id: string; displayName: string; sku: string; isTrial?: boolean}[]>([]);
  const [selectedCapacity, setSelectedCapacity] = useState("");
  const [loadingCapacities, setLoadingCapacities] = useState(false);
  const [deployedWorkspaceId, setDeployedWorkspaceId] = useState("");
  const [cleaning, setCleaning] = useState(false);
  const [cleaned, setCleaned] = useState(false);

  if (!demo) {
    return (
      <div className="mx-auto max-w-[1012px] px-6 py-20 text-center">
        <h1 className="text-[18px] font-semibold" style={{ color: "var(--color-fg)" }}>Demo not found</h1>
        <a href="/" className="mt-3 inline-block text-[14px]" style={{ color: "var(--color-accent)" }}>&larr; Back</a>
      </div>
    );
  }

  const itemsByType = demo.fabricItems.reduce((acc: Record<string, typeof demo.fabricItems>, item) => {
    (acc[item.type] = acc[item.type] || []).push(item);
    return acc;
  }, {});

  const handleDeploy = async () => {
    setDeploying(true);
    setError(null);
    setCompleted(false);
    setSteps([]);

    const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

    try {
      // Get tokens — MSAL if signed in, otherwise backend uses az CLI fallback
      let fabricToken = "";
      let storageToken = "";
      if (account) {
        [fabricToken, storageToken] = await Promise.all([
          getFabricToken(),
          getStorageToken(),
        ]);
      }

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (fabricToken) {
        headers["Authorization"] = `Bearer ${fabricToken}`;
        headers["X-Storage-Token"] = storageToken;
      }

      const resp = await fetch(`${API}/api/deploy/${id}`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          demo_id: id,
          workspace_name: workspaceName || `${demo.title} Demo`,
          capacity_id: selectedCapacity || undefined,
        }),
      });

      if (!resp.ok) {
        const text = await resp.text();
        setError(`Backend error ${resp.status}: ${text.slice(0, 200)}`);
        setDeploying(false);
        return;
      }

      // Read SSE stream
      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        setError("No response stream");
        setDeploying(false);
        return;
      }

      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (currentEvent === "plan") {
                setSteps(data as DeployStep[]);
              } else if (currentEvent === "step") {
                const step = data as DeployStep;
                setSteps((prev) =>
                  prev.map((s) => (s.name === step.name ? { ...s, ...step } : s))
                );
                if (step.name === "done" && step.status === "completed") {
                  setCompleted(true);
                  // Extract workspace ID from the done step detail
                  if (step.detail) {
                    try {
                      const info = JSON.parse(step.detail as string);
                      if (info.workspaceId) setDeployedWorkspaceId(info.workspaceId);
                    } catch { /* detail might not be JSON */ }
                  }
                }
                // Also capture workspace ID from the workspace step
                if (step.name === "workspace" && step.status === "completed" && step.detail) {
                  // itemId contains the workspace ID
                }
                if (step.name === "workspace" && (step as any).itemId) {
                  setDeployedWorkspaceId((step as any).itemId);
                }
              } else if (currentEvent === "error") {
                setError(data.message || "Deployment failed");
                // Capture workspace ID from error for cleanup
                if (data.workspaceId) setDeployedWorkspaceId(data.workspaceId);
              }
            } catch {
              // ignore malformed data lines
            }
            currentEvent = "";
          }
        }
      }

      if (!completed) setCompleted(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connection failed");
    } finally {
      setDeploying(false);
    }
  };

  return (
    <div style={{ background: "var(--color-bg-subtle)" }} className="min-h-screen">
      {/* Header bar */}
      <div style={{ background: "var(--color-bg-canvas)" }} className="border-b" >
        <div className="mx-auto max-w-[1012px] px-6 py-8">
          <a href="/" className="text-[14px] hover:underline mb-4 inline-block" style={{ color: "var(--color-accent)" }}>&larr; All demos</a>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[12px] font-medium" style={{ background: "#e8f0fe", color: "#0550ae" }}>{demo.industry}</span>
            <span className="text-[12px]" style={{ color: "var(--color-fg-subtle)" }}>{demo.estimatedTime}</span>
          </div>
          <h1 className="text-[24px] font-bold" style={{ color: "var(--color-fg)" }}>{demo.title}</h1>
          <p className="mt-2 text-[14px] max-w-2xl leading-relaxed" style={{ color: "var(--color-fg-muted)" }}>{demo.longDescription}</p>
        </div>
      </div>

      <div className="mx-auto max-w-[1012px] px-6 py-8">
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left column */}
          <div className="lg:col-span-2 space-y-6">

            {/* Architecture */}
            <div className="rounded-lg border bg-white p-5" style={{ borderColor: "var(--color-border)" }}>
              <h3 className="text-[14px] font-semibold mb-4" style={{ color: "var(--color-fg)" }}>Data Flow</h3>
              <div className="flex items-center gap-0 flex-wrap">
                {demo.architecture.layers.map((layer, i) => (
                  <div key={i} className="flex items-center">
                    <div className="rounded-md border px-4 py-2.5" style={{ borderColor: "var(--color-border)", background: i === 2 ? "#e8f0fe" : "var(--color-bg-subtle)" }}>
                      <div className="text-[10px] font-semibold uppercase tracking-wider mb-0.5" style={{ color: "var(--color-fg-subtle)" }}>
                        {["Bronze", "Silver", "Gold"][i]}
                      </div>
                      <div className="text-[13px] font-medium" style={{ color: i === 2 ? "#0550ae" : "var(--color-fg)" }}>
                        {layer.replace(/^(Bronze|Silver|Gold)\s*\(/, "").replace(/\)$/, "")}
                      </div>
                    </div>
                    {i < demo.architecture.layers.length - 1 && (
                      <svg width="24" height="12" viewBox="0 0 24 12" fill="none" className="mx-1 shrink-0"><path d="M0 6h20M17 1l5 5-5 5" stroke="#d1d9e0" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Items */}
            <div className="rounded-lg border bg-white p-5" style={{ borderColor: "var(--color-border)" }}>
              <h3 className="text-[14px] font-semibold mb-4" style={{ color: "var(--color-fg)" }}>What Gets Created</h3>
              <div className="space-y-0 divide-y" style={{ borderColor: "var(--color-border-subtle)" }}>
                {demo.fabricItems.map((item, i) => (
                  <div key={i} className="flex items-center justify-between py-2.5">
                    <div>
                      <span className="text-[14px] font-medium" style={{ color: "var(--color-fg)" }}>{item.name}</span>
                      <span className="ml-2 text-[12px]" style={{ color: "var(--color-fg-subtle)" }}>{item.description}</span>
                    </div>
                    <span className="rounded-full border px-2 py-0.5 text-[11px] font-medium shrink-0 ml-3"
                      style={{ borderColor: "var(--color-border)", color: "var(--color-fg-subtle)" }}>
                      {item.type}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Sample Data */}
            <div className="rounded-lg border bg-white p-5" style={{ borderColor: "var(--color-border)" }}>
              <h3 className="text-[14px] font-semibold mb-4" style={{ color: "var(--color-fg)" }}>Sample Data</h3>
              <div className="divide-y" style={{ borderColor: "var(--color-border-subtle)" }}>
                {demo.sampleData.map((d, i) => (
                  <div key={i} className="flex items-center justify-between py-2.5">
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] font-mono font-medium rounded px-1.5 py-0.5" style={{ background: "var(--color-bg-subtle)", color: "var(--color-fg-subtle)" }}>{d.format}</span>
                      <div>
                        <div className="text-[13px] font-medium" style={{ color: "var(--color-fg)" }}>{d.fileName}</div>
                        <div className="text-[12px]" style={{ color: "var(--color-fg-subtle)" }}>{d.description}</div>
                      </div>
                    </div>
                    <span className="text-[12px] tabular-nums shrink-0 ml-3" style={{ color: "var(--color-fg-subtle)" }}>{d.rows.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right sidebar — Deploy */}
          <div>
            <div className="sticky top-[60px] rounded-lg border bg-white p-5" style={{ borderColor: "var(--color-border)" }}>
              <h3 className="text-[14px] font-semibold mb-4" style={{ color: "var(--color-fg)" }}>Deploy</h3>

          {!showDeploy && !deploying && !completed && (
            <div>
              <div className="mb-4 text-[12px] space-y-1" style={{ color: "var(--color-fg-subtle)" }}>
                {demo.prerequisites.map((p, i) => (
                  <div key={i}>— {p}</div>
                ))}
              </div>
              {account ? (
                <div>
                  <div className="mb-3 text-[12px]" style={{ color: "var(--color-fg-subtle)" }}>
                    Signed in as {account.username}
                  </div>
                  <button
                    onClick={async () => {
                      setShowDeploy(true);
                      setLoadingCapacities(true);
                      try {
                        const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
                        let res = await fetch(`${API}/api/workspaces/capacities`);
                        if (!res.ok && account) {
                          try {
                            const token = await getFabricToken();
                            res = await fetch(`${API}/api/workspaces/capacities`, {
                              headers: { Authorization: `Bearer ${token}` },
                            });
                          } catch (e) {
                            console.warn("Token acquisition failed:", e);
                          }
                        }
                        if (res.ok) {
                          const caps = await res.json();
                          setCapacities(caps);
                          if (caps.length > 0) setSelectedCapacity(caps[0].id);
                        }
                      } catch (e) {
                        console.error("Failed to load capacities:", e);
                      } finally {
                        setLoadingCapacities(false);
                      }
                    }}
                    className="w-full rounded-md bg-[#0078d4] px-4 py-2 text-[14px] font-medium text-white hover:bg-[#106ebe] transition-colors"
                  >
                    Configure deployment
                  </button>
                </div>
              ) : (
                <button
                  onClick={login}
                  className="w-full rounded-md bg-[#0078d4] px-4 py-2 text-[14px] font-medium text-white hover:bg-[#106ebe] transition-colors"
                >
                  Sign in to deploy
                </button>
              )}
            </div>
          )}

          {showDeploy && !deploying && !completed && (
            <div className="space-y-4">
              <div>
                <label className="block text-[12px] font-medium mb-1.5" style={{ color: "var(--color-fg)" }}>Workspace name</label>
                <input type="text" value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)}
                  placeholder={`${demo.title} Demo`}
                  className="w-full rounded-md border px-3 py-[7px] text-[14px] focus:border-[#0078d4] focus:ring-1 focus:ring-[#0078d4] focus:outline-none transition-colors"
                  style={{ borderColor: "var(--color-border)", color: "var(--color-fg)" }}
                />
              </div>
              <div>
                <label className="block text-[12px] font-medium mb-1.5" style={{ color: "var(--color-fg)" }}>Capacity</label>
                {loadingCapacities ? (
                  <div className="flex items-center gap-2 text-[13px] py-2" style={{ color: "var(--color-fg-subtle)" }}>
                    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#0078d4] border-t-transparent" />
                    Loading...
                  </div>
                ) : capacities.length > 0 ? (
                  <select value={selectedCapacity} onChange={(e) => setSelectedCapacity(e.target.value)}
                    className="w-full rounded-md border px-3 py-[7px] text-[14px] focus:border-[#0078d4] focus:ring-1 focus:ring-[#0078d4] focus:outline-none transition-colors"
                    style={{ borderColor: "var(--color-border)", color: "var(--color-fg)" }}
                  >
                    {capacities.map((cap: any) => (
                      <option key={cap.id} value={cap.id}>{cap.displayName} ({cap.sku}){cap.isTrial ? " — Trial" : ""}</option>
                    ))}
                  </select>
                ) : (
                  <p className="text-[12px]" style={{ color: "var(--color-danger)" }}>No capacities found.</p>
                )}
              </div>
              <div className="flex gap-2 pt-1">
                <button onClick={handleDeploy}
                  className="flex-1 rounded-md bg-[#0078d4] px-4 py-[7px] text-[14px] font-medium text-white hover:bg-[#106ebe] transition-colors">
                  Deploy
                </button>
                <button onClick={() => setShowDeploy(false)}
                  className="rounded-md border px-4 py-[7px] text-[14px] hover:bg-[#f6f8fa] transition-colors"
                  style={{ borderColor: "var(--color-border)", color: "var(--color-fg)" }}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {(deploying || completed) && (
            <div className="space-y-1">
              {steps.map((step, i) => (
                <div key={i} className="flex items-center gap-2.5 py-0.5">
                  <span className="w-4 shrink-0 flex justify-center">
                    {step.status === "completed" && (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="7" fill="#1a7f37"/><path d="M4 7l2 2 4-4" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    )}
                    {step.status === "running" && (
                      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#0078d4] border-t-transparent" />
                    )}
                    {step.status === "pending" && (
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-border)" }} />
                    )}
                    {step.status === "failed" && (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="7" fill="#cf222e"/><path d="M5 5l4 4M9 5l-4 4" stroke="#fff" strokeWidth="1.5" strokeLinecap="round"/></svg>
                    )}
                  </span>
                  <span className={`text-[13px] ${
                    step.status === "completed" ? "text-[#656d76]" :
                    step.status === "running" ? "text-[#1f2328] font-medium" :
                    step.status === "failed" ? "text-[#cf222e]" :
                    "text-[#b1bac4]"
                  }`}>
                    {step.description}
                  </span>
                </div>
              ))}

              {completed && (
                <div className="mt-4 pt-4 border-t space-y-3" style={{ borderColor: "var(--color-border-subtle)" }}>
                  <div className="rounded-md p-3 text-[13px]" style={{ background: "#dafbe1", color: "#1a7f37" }}>
                    Deployment complete.{" "}
                    <a href={deployedWorkspaceId ? `https://app.fabric.microsoft.com/groups/${deployedWorkspaceId}` : "https://app.fabric.microsoft.com"}
                      target="_blank" rel="noopener noreferrer" className="font-medium underline">
                      Open workspace &rarr;
                    </a>
                  </div>
                  {deployedWorkspaceId && !cleaned && (
                    <button
                      onClick={async () => {
                        if (!confirm("Delete the entire workspace and all items?")) return;
                        setCleaning(true);
                        try {
                          const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
                          let headers: Record<string, string> = {};
                          if (account) { try { const t = await getFabricToken(); if (t) headers["Authorization"] = `Bearer ${t}`; } catch {} }
                          const res = await fetch(`${API}/api/deploy/${deployedWorkspaceId}`, { method: "DELETE", headers });
                          if (res.ok) setCleaned(true); else alert(`Failed: ${res.statusText}`);
                        } catch (e) { alert(`Error: ${e}`); }
                        finally { setCleaning(false); }
                      }}
                      disabled={cleaning}
                      className="w-full rounded-md border px-4 py-[7px] text-[13px] hover:text-[#cf222e] hover:border-[#cf222e] transition-colors disabled:opacity-50"
                      style={{ borderColor: "var(--color-border)", color: "var(--color-fg-muted)" }}
                    >
                      {cleaning ? "Deleting..." : "Delete workspace"}
                    </button>
                  )}
                  {cleaned && <p className="text-[12px]" style={{ color: "var(--color-fg-subtle)" }}>Workspace deleted.</p>}
                  {!cleaned && (
                    <button onClick={() => { setShowDeploy(false); setDeploying(false); setCompleted(false); setSteps([]); setError(null); setDeployedWorkspaceId(""); }}
                      className="w-full text-[13px] hover:underline" style={{ color: "var(--color-accent)" }}>Deploy another</button>
                  )}
                </div>
              )}

              {error && (
                <div className="mt-4 pt-4 border-t space-y-3" style={{ borderColor: "var(--color-border-subtle)" }}>
                  <div className="rounded-md border p-3 text-[13px]" style={{ borderColor: "#ff818266", background: "#ffebe9", color: "#cf222e" }}>
                    <p className="whitespace-pre-line">{error}</p>
                  </div>
                  {deployedWorkspaceId && !cleaned && (
                    <button onClick={async () => {
                        if (!confirm("Delete the partially created workspace?")) return;
                        setCleaning(true);
                        try { const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"; const res = await fetch(`${API}/api/deploy/${deployedWorkspaceId}`, { method: "DELETE" }); if (res.ok) { setCleaned(true); setError(null); } else alert(`Failed: ${res.statusText}`); }
                        catch (e) { alert(`Error: ${e}`); } finally { setCleaning(false); }
                      }}
                      disabled={cleaning}
                      className="w-full rounded-md border px-4 py-[7px] text-[13px] hover:text-[#cf222e] hover:border-[#cf222e] transition-colors disabled:opacity-50"
                      style={{ borderColor: "var(--color-border)", color: "var(--color-fg-muted)" }}
                    >{cleaning ? "Cleaning up..." : "Delete partial workspace"}</button>
                  )}
                  {cleaned && <p className="text-[12px]" style={{ color: "var(--color-fg-subtle)" }}>Workspace deleted.</p>}
                  <button onClick={() => { setShowDeploy(false); setDeploying(false); setCompleted(false); setSteps([]); setError(null); setDeployedWorkspaceId(""); setCleaned(false); }}
                    className="w-full text-[13px] hover:underline" style={{ color: "var(--color-accent)" }}>Try again</button>
                </div>
              )}
            </div>
          )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
