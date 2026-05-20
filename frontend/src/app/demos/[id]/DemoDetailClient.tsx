"use client";

import { useParams } from "next/navigation";
import NextLink from "next/link";
import { useState, useRef } from "react";
import { useAuth } from "@/lib/AuthProvider";
import {
  Button,
  Card,
  Badge,
  Input,
  Select,
  Spinner,
  Text,
  Title2,
  Title3,
  Subtitle2,
  Body1,
  Caption1,
  Divider,
  MessageBar,
  MessageBarBody,
  MessageBarTitle,
  MessageBarActions,
  Link as FluentLink,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  ArrowLeftRegular,
  CheckmarkCircleFilled,
  DismissCircleFilled,
  CircleRegular,
  ArrowRightRegular,
  DeleteRegular,
  OpenRegular,
  DatabaseRegular,
  TableRegular,
} from "@fluentui/react-icons";

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
        description: "50,000 IoT sensor readings: temperature, pressure, vibration, humidity",
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
      { type: "Notebook", name: "01_bronze_ingest", description: "Ingest raw CSVs to Bronze Delta tables", order: 1 },
      { type: "Notebook", name: "02_silver_transform", description: "Clean, deduplicate, flag anomalies", order: 2 },
      { type: "Notebook", name: "03_gold_aggregate", description: "6 Gold tables: OEE, equipment health, shift, product rankings, weekly trends, scorecards", order: 3 },
      { type: "Notebook", name: "04_reporting_views", description: "SQL views: executive dashboard, equipment alerts, production trends, scorecard", order: 4 },
      { type: "Notebook", name: "05_dashboard", description: "Interactive analytics dashboard rendered inline + saved as HTML", order: 5 },
      { type: "SemanticModel", name: "quality_analytics_model", description: "Direct Lake model with 6 tables, 30+ measures, relationships" },
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
      { type: "Notebook", name: "01_bronze_ingest", description: "Ingest raw CSVs to Bronze Delta tables", order: 1 },
      { type: "Notebook", name: "02_silver_transform", description: "Clean, conform, calculate line totals", order: 2 },
      { type: "Notebook", name: "03_gold_aggregate", description: "Sales KPIs, product performance, weekly trends, dimension tables", order: 3 },
      { type: "SemanticModel", name: "retail_analytics_model", description: "Star schema: 6 tables (2 dims + 4 facts), 40+ measures, relationships" },
      { type: "Report", name: "Retail Sales Dashboard", description: "3-page dashboard: Sales, Inventory, Margin & Basket" },
      { type: "DataPipeline", name: "daily_retail_pipeline", description: "Orchestrates all notebooks sequentially" },
    ],
  },
  "energy-grid": {
    id: "energy-grid",
    industry: "Energy & Utilities",
    title: "Smart Grid Monitoring",
    description:
      "Monitor power grid health with real-time sensor data, detect voltage anomalies, track outages, and analyze renewable energy generation.",
    longDescription:
      "This demo deploys a real-time intelligence environment for smart grid monitoring. It provisions an Eventhouse with a KQL Database, then ingests synthetic grid sensor readings (voltage, frequency, power factor, load), outage events, and renewable generation data. PySpark notebooks load the data into a Lakehouse staging area, then batch-ingest into the KQL Database for high-performance time-series analytics. A Power BI dashboard provides grid health overview, outage analysis, and renewable performance tracking.",
    estimatedTime: "10-15 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "event-driven",
      layers: [
        "Ingest (CSV Landing)",
        "KQL Database (Time-Series)",
        "Analytics (KQL Queries & Dashboards)",
      ],
    },
    sampleData: [
      { fileName: "grid_sensors.csv", description: "100,000 grid sensor readings: voltage, frequency, power factor, load, temperature", format: "csv", rows: 100000 },
      { fileName: "power_events.csv", description: "5,000 power events: outages, surges, sags, restorations with severity", format: "csv", rows: 5000 },
      { fileName: "renewable_generation.csv", description: "20,000 renewable generation readings from solar, wind, hydro plants", format: "csv", rows: 20000 },
    ],
    fabricItems: [
      { type: "Lakehouse", name: "grid_lakehouse", description: "Staging area for CSV data before KQL ingestion" },
      { type: "Eventhouse", name: "grid_eventhouse", description: "Real-time analytics engine for time-series grid data" },
      { type: "KQLDatabase", name: "grid_telemetry_db", description: "KQL database for sensor readings, events, and renewable generation" },
      { type: "Notebook", name: "01_ingest_to_kql", description: "Create KQL tables and ingest CSV data from Lakehouse", order: 1 },
      { type: "Notebook", name: "02_kql_analytics", description: "KQL queries for anomaly detection, time-series analysis, Gold table creation", order: 2 },
      { type: "Notebook", name: "03_simulate_realtime", description: "Real-time simulator — generates live sensor readings with current timestamps. Schedule via pipeline for continuous data.", order: 3 },
      { type: "SemanticModel", name: "grid_analytics_model", description: "Direct Lake model with grid health, outage, and renewable measures" },
      { type: "Report", name: "Smart Grid Dashboard", description: "3-page Power BI dashboard: Grid Health, Outage Analysis, Renewable Performance" },
      { type: "KQLDashboard", name: "Grid Real-Time Dashboard", description: "Real-time KQL dashboard with live grid sensor queries and outage tracking" },
      { type: "DataPipeline", name: "grid_monitoring_pipeline", description: "Orchestrates ingestion and analytics notebooks" },
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
  itemId?: string;
};

/* Fabric workload icons — official SVGs from Microsoft */
function FabricItemIcon({ type, size = 16 }: { type: string; size?: number }) {
  const FILE_MAP: Record<string, string> = {
    Lakehouse: "lakehouse_24_item.svg",
    Notebook: "notebook_24_item.svg",
    SemanticModel: "semantic_model_24_item.svg",
    Report: "report_24_item.svg",
    DataPipeline: "pipeline_24_item.svg",
    Dashboard: "dashboard_24_item.svg",
    Eventhouse: "eventhouse_24_item.svg",
    KQLDatabase: "kql_database_24_item.svg",
    KQLDashboard: "kql_dashboard_24_item.svg",
  };
  const file = FILE_MAP[type];
  if (!file) return null;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={`/icons/${file}`} alt={type} width={size} height={size} style={{ objectFit: "contain" }} />;
}

const LAYER_COLORS = ["#3fb68b", "#238636", "#196c2e"];

const useStyles = makeStyles({
  page: {
    minHeight: "100vh",
    backgroundColor: "#0d1117",
  },
  headerBar: {
    backgroundColor: "#0d1117",
    borderBottom: "1px solid #21262d",
  },
  headerInner: {
    maxWidth: "1200px",
    marginLeft: "auto",
    marginRight: "auto",
    paddingLeft: "40px",
    paddingRight: "40px",
    paddingTop: "28px",
    paddingBottom: "28px",
  },
  backLink: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    marginBottom: "16px",
    color: "#484f58",
    textDecoration: "none",
    fontSize: "13px",
    ":hover": { color: "#8b949e", textDecoration: "none" },
  },
  titleRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "24px",
  },
  titleLeft: {},
  metaRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    marginBottom: "8px",
  },
  title: {
    fontSize: "24px",
    fontWeight: 700,
    color: "#e6edf3",
    lineHeight: "32px",
    marginBottom: "8px",
  },
  longDesc: {
    maxWidth: "680px",
    lineHeight: "21px",
    color: "#8b949e",
    fontSize: "14px",
  },
  contentArea: {
    maxWidth: "1200px",
    marginLeft: "auto",
    marginRight: "auto",
    paddingLeft: "40px",
    paddingRight: "40px",
    paddingTop: "24px",
    paddingBottom: "48px",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 340px",
    gap: "24px",
  },
  leftCol: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  section: {
    backgroundColor: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "8px",
    overflow: "hidden",
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "14px 20px",
    borderBottom: "1px solid #21262d",
    fontSize: "13px",
    fontWeight: 600,
    color: "#e6edf3",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
  },
  sectionBody: {
    padding: "0",
  },
  flowRow: {
    display: "flex",
    alignItems: "center",
    padding: "20px",
    gap: "0",
    flexWrap: "wrap" as const,
  },
  flowBox: {
    borderRadius: "6px",
    paddingLeft: "16px",
    paddingRight: "16px",
    paddingTop: "12px",
    paddingBottom: "12px",
    minWidth: "140px",
  },
  flowLabel: {
    fontSize: "10px",
    fontWeight: 700,
    textTransform: "uppercase" as const,
    letterSpacing: "0.8px",
    marginBottom: "2px",
  },
  flowValue: {
    fontSize: "13px",
    fontWeight: 500,
    color: "#ffffff",
  },
  flowArrow: {
    marginLeft: "6px",
    marginRight: "6px",
    color: "#30363d",
  },
  itemRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: "10px",
    paddingBottom: "10px",
    paddingLeft: "20px",
    paddingRight: "20px",
    borderBottom: "1px solid #21262d",
    ":hover": {
      backgroundColor: "#1c2128",
    },
  },
  itemRowLast: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: "10px",
    paddingBottom: "10px",
    paddingLeft: "20px",
    paddingRight: "20px",
    ":hover": {
      backgroundColor: "#1c2128",
    },
  },
  itemLeft: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  itemIconWrap: {
    width: "28px",
    height: "28px",
    borderRadius: "6px",
    backgroundColor: "#21262d",
    border: "1px solid #30363d",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  dataRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: "10px",
    paddingBottom: "10px",
    paddingLeft: "20px",
    paddingRight: "20px",
    borderBottom: "1px solid #21262d",
  },
  dataLeft: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  sidebar: {
    position: "sticky" as const,
    top: "64px",
    alignSelf: "start" as const,
  },
  sidebarCard: {
    backgroundColor: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "8px",
    overflow: "hidden",
  },
  sidebarHeader: {
    padding: "14px 20px",
    borderBottom: "1px solid #21262d",
    fontSize: "13px",
    fontWeight: 600,
    color: "#e6edf3",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
  },
  sidebarBody: {
    padding: "20px",
  },
  prereq: {
    fontSize: "12px",
    color: "#484f58",
    lineHeight: "18px",
    marginBottom: "4px",
  },
  formField: {
    marginBottom: "16px",
  },
  formLabel: {
    display: "block",
    fontSize: "12px",
    fontWeight: 600,
    color: "#e6edf3",
    marginBottom: "6px",
  },
  stepRow: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    paddingTop: "4px",
    paddingBottom: "4px",
  },
  stepIcon: {
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
  },
  stepCompleted: {
    fontSize: "13px",
    color: "#484f58",
  },
  stepRunning: {
    fontSize: "13px",
    fontWeight: 500,
    color: "#e6edf3",
  },
  stepPending: {
    fontSize: "13px",
    color: "#30363d",
  },
  stepFailed: {
    fontSize: "13px",
    color: "#f85149",
  },
  buttonRow: {
    display: "flex",
    gap: "8px",
    marginTop: "4px",
  },
});

export default function DemoDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const demo = DEMOS[id];
  const { account, authError, login, getFabricToken, getStorageToken } = useAuth();
  const styles = useStyles();

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
  const abortRef = useRef<AbortController | null>(null);

  if (!demo) {
    return (
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "80px 32px", textAlign: "center" }}>
        <Title2>Demo not found</Title2>
        <div style={{ marginTop: 12 }}>
          <FluentLink href="/">
            <ArrowLeftRegular /> Back to gallery
          </FluentLink>
        </div>
      </div>
    );
  }

  const handleDeploy = async () => {
    setDeploying(true);
    setError(null);
    setCompleted(false);
    setSteps([]);

    const controller = new AbortController();
    abortRef.current = controller;

    const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

    try {
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
        signal: controller.signal,
      });

      if (!resp.ok) {
        const text = await resp.text();
        setError(`Backend error ${resp.status}: ${text.slice(0, 200)}`);
        setDeploying(false);
        return;
      }

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
                  if (step.detail) {
                    try {
                      const info = JSON.parse(step.detail as string);
                      if (info.workspaceId) setDeployedWorkspaceId(info.workspaceId);
                    } catch { /* detail might not be JSON */ }
                  }
                }
                if (step.name === "workspace" && step.itemId) {
                  setDeployedWorkspaceId(step.itemId);
                }
              } else if (currentEvent === "error") {
                setError(data.message || "Deployment failed");
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
      if (e instanceof DOMException && e.name === "AbortError") {
        setError("Deployment stopped by user. The workspace may be partially created.");
      } else {
        setError(e instanceof Error ? e.message : "Connection failed");
      }
    } finally {
      abortRef.current = null;
      setDeploying(false);
    }
  };

  const handleStop = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      // Mark currently running steps as stopped
      setSteps((prev) =>
        prev.map((s) =>
          s.status === "running" ? { ...s, status: "failed" as const, detail: "Stopped by user" } : s
        )
      );
    }
  };

  const handleCleanup = async () => {
    if (!confirm("Delete the entire workspace and all items?")) return;
    setCleaning(true);
    try {
      const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const headers: Record<string, string> = {};
      if (account) {
        try {
          const t = await getFabricToken();
          if (t) headers["Authorization"] = `Bearer ${t}`;
        } catch { /* ignore */ }
      }
      const res = await fetch(`${API}/api/deploy/${deployedWorkspaceId}`, { method: "DELETE", headers });
      if (res.ok) setCleaned(true);
      else alert(`Failed: ${res.statusText}`);
    } catch (e) {
      alert(`Error: ${e}`);
    } finally {
      setCleaning(false);
    }
  };

  const handlePartialCleanup = async () => {
    if (!confirm("Delete the partially created workspace?")) return;
    setCleaning(true);
    try {
      const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const res = await fetch(`${API}/api/deploy/${deployedWorkspaceId}`, { method: "DELETE" });
      if (res.ok) { setCleaned(true); setError(null); }
      else alert(`Failed: ${res.statusText}`);
    } catch (e) {
      alert(`Error: ${e}`);
    } finally {
      setCleaning(false);
    }
  };

  const resetState = () => {
    setShowDeploy(false);
    setDeploying(false);
    setCompleted(false);
    setSteps([]);
    setError(null);
    setDeployedWorkspaceId("");
    setCleaned(false);
  };

  const loadCapacities = async () => {
    setShowDeploy(true);
    setLoadingCapacities(true);
    setError(null);
    try {
      if (!account) {
        setError("Please sign in first.");
        setLoadingCapacities(false);
        return;
      }

      // Get Fabric token and call Fabric API directly (no backend needed)
      const token = await getFabricToken();
      const res = await fetch("https://api.fabric.microsoft.com/v1/capacities", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const caps = (data.value || [])
          .filter((c: { state: string }) => c.state === "Active")
          .map((c: { id: string; displayName: string; sku: string; state: string }) => ({
            id: c.id,
            displayName: c.displayName,
            sku: c.sku,
            isTrial: c.sku?.startsWith("FT") || false,
          }));
        setCapacities(caps);
        if (caps.length > 0) setSelectedCapacity(caps[0].id);
      } else {
        const text = await res.text();
        setError(`Fabric API error ${res.status}: ${text.slice(0, 200)}`);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`Failed to load capacities: ${msg}`);
    } finally {
      setLoadingCapacities(false);
    }
  };

  return (
    <div className={styles.page}>
      {/* Header bar */}
      <div className={styles.headerBar}>
        <div className={styles.headerInner}>
          <div className={styles.titleRow}>
            <div className={styles.titleLeft}>
              <div className={styles.metaRow}>
                <Badge appearance="filled" color="brand" size="small">
                  {demo.industry}
                </Badge>
                <Caption1>{demo.estimatedTime}</Caption1>
                <Caption1>{demo.fabricItems.length} Fabric items</Caption1>
              </div>
              <div className={styles.title}>{demo.title}</div>
              <div className={styles.longDesc}>{demo.longDescription}</div>
            </div>
          </div>
        </div>
      </div>

      <div className={styles.contentArea}>
        <div className={styles.grid}>
          {/* Left column */}
          <div className={styles.leftCol}>

            {/* Architecture */}
            <div className={styles.section}>
              <div className={styles.sectionHeader}>
                <ArrowRightRegular fontSize={16} /> Data Flow
              </div>
              <div className={styles.flowRow}>
                {demo.architecture.layers.map((layer, i) => {
                  const medalLabels = ["Bronze", "Silver", "Gold"];
                  const isMedallion = /^(Bronze|Silver|Gold)\s*\(/.test(layer);
                  const label = isMedallion ? medalLabels[i] : "";
                  const value = isMedallion
                    ? layer.replace(/^(Bronze|Silver|Gold)\s*\(/, "").replace(/\)$/, "")
                    : layer;
                  return (
                  <div key={i} style={{ display: "flex", alignItems: "center" }}>
                    <div
                      className={styles.flowBox}
                      style={{ backgroundColor: LAYER_COLORS[i] }}
                    >
                      {label && (
                      <div className={styles.flowLabel} style={{ color: "rgba(255,255,255,0.7)" }}>
                        {label}
                      </div>
                      )}
                      <div className={styles.flowValue}>
                        {value}
                      </div>
                    </div>
                    {i < demo.architecture.layers.length - 1 && (
                      <ArrowRightRegular className={styles.flowArrow} fontSize={18} />
                    )}
                  </div>
                  );
                })}
              </div>
            </div>

            {/* Fabric Items */}
            <div className={styles.section}>
              <div className={styles.sectionHeader}>
                <DatabaseRegular fontSize={16} /> What Gets Created
              </div>
              <div className={styles.sectionBody}>
                {demo.fabricItems.map((item, i) => (
                  <div
                    key={i}
                    className={i < demo.fabricItems.length - 1 ? styles.itemRow : styles.itemRowLast}
                  >
                    <div className={styles.itemLeft}>
                      <span className={styles.itemIconWrap}>
                        <FabricItemIcon type={item.type} size={20} />
                      </span>
                      <div>
                        <Text weight="medium" size={300}>{item.name}</Text>
                        <div><Caption1>{item.description}</Caption1></div>
                      </div>
                    </div>
                    <Badge appearance="tint" size="small" color="informative">
                      {item.type}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>

            {/* Sample Data */}
            <div className={styles.section}>
              <div className={styles.sectionHeader}>
                <TableRegular fontSize={16} /> Sample Data
              </div>
              <div className={styles.sectionBody}>
                {demo.sampleData.map((d, i) => (
                  <div key={i} className={styles.dataRow} style={i === demo.sampleData.length - 1 ? { borderBottom: "none" } : undefined}>
                    <div className={styles.dataLeft}>
                      <Badge appearance="tint" color="severe" size="small">
                        {d.format}
                      </Badge>
                      <div>
                        <Text weight="medium" size={200}>{d.fileName}</Text>
                        <div><Caption1>{d.description}</Caption1></div>
                      </div>
                    </div>
                    <Caption1 style={{ fontVariantNumeric: "tabular-nums" }}>
                      {d.rows.toLocaleString()} rows
                    </Caption1>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right sidebar — Deploy */}
          <div className={styles.sidebar}>
            <div className={styles.sidebarCard}>
              <div className={styles.sidebarHeader}>Deploy</div>
              <div className={styles.sidebarBody}>

              {!showDeploy && !deploying && !completed && (
                <div>
                  <div style={{ marginBottom: 16 }}>
                    {demo.prerequisites.map((p, i) => (
                      <div key={i} className={styles.prereq}>— {p}</div>
                    ))}
                  </div>
                  {account ? (
                    <div>
                      <Caption1 style={{ display: "block", marginBottom: 12 }}>
                        Signed in as {account.username}
                      </Caption1>
                      <Button
                        appearance="primary"
                        style={{ width: "100%" }}
                        onClick={loadCapacities}
                      >
                        Configure deployment
                      </Button>
                    </div>
                  ) : (
                    <Button
                      appearance="primary"
                      style={{ width: "100%" }}
                      onClick={login}
                    >
                      Sign in to deploy
                    </Button>
                  )}
                  {authError && (
                    <div style={{ marginTop: 8, color: "#f85149", fontSize: 12 }}>
                      Auth error: {authError}
                    </div>
                  )}
                </div>
              )}

              {showDeploy && !deploying && !completed && (
                <div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>Workspace name</label>
                    <Input
                      value={workspaceName}
                      onChange={(_, data) => setWorkspaceName(data.value)}
                      placeholder={`${demo.title} Demo`}
                      style={{ width: "100%" }}
                    />
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>Capacity</label>
                    {loadingCapacities ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0" }}>
                        <Spinner size="tiny" />
                        <Caption1>Loading capacities...</Caption1>
                      </div>
                    ) : capacities.length > 0 ? (
                      <Select
                        value={selectedCapacity}
                        onChange={(_, data) => setSelectedCapacity(data.value)}
                        style={{ width: "100%" }}
                      >
                        {capacities.map((cap) => (
                          <option key={cap.id} value={cap.id}>
                            {cap.displayName} ({cap.sku}){cap.isTrial ? " — Trial" : ""}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <MessageBar intent="error">
                        <MessageBarBody>{error || "No capacities found."}</MessageBarBody>
                      </MessageBar>
                    )}
                  </div>
                  <div className={styles.buttonRow}>
                    <Button
                      appearance="primary"
                      onClick={handleDeploy}
                      style={{ flex: 1 }}
                    >
                      Deploy
                    </Button>
                    <Button
                      appearance="outline"
                      onClick={() => setShowDeploy(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {(deploying || completed) && (
                <div>
                  {steps.map((step, i) => (
                    <div key={i} className={styles.stepRow}>
                      <span className={styles.stepIcon}>
                        {step.status === "completed" && (
                          <CheckmarkCircleFilled fontSize={16} style={{ color: tokens.colorPaletteGreenForeground1 }} />
                        )}
                        {step.status === "running" && (
                          <Spinner size="extra-tiny" />
                        )}
                        {step.status === "pending" && (
                          <CircleRegular fontSize={16} style={{ color: tokens.colorNeutralStroke1 }} />
                        )}
                        {step.status === "failed" && (
                          <DismissCircleFilled fontSize={16} style={{ color: tokens.colorPaletteRedForeground1 }} />
                        )}
                      </span>
                      <span className={
                        step.status === "completed" ? styles.stepCompleted :
                        step.status === "running" ? styles.stepRunning :
                        step.status === "failed" ? styles.stepFailed :
                        styles.stepPending
                      }>
                        {step.description}
                      </span>
                    </div>
                  ))}

                  {deploying && !completed && (
                    <div style={{ marginTop: 12 }}>
                      <Button
                        appearance="outline"
                        style={{ width: "100%", color: "#f85149", borderColor: "#f8514966" }}
                        onClick={handleStop}
                      >
                        Stop deployment
                      </Button>
                    </div>
                  )}

                  {completed && (
                    <div style={{ marginTop: 16 }}>
                      <Divider style={{ marginBottom: 16 }} />
                      <MessageBar intent="success" style={{ marginBottom: 12 }}>
                        <MessageBarBody>
                          Deployment complete.{" "}
                          <FluentLink
                            href={deployedWorkspaceId ? `https://app.fabric.microsoft.com/groups/${deployedWorkspaceId}` : "https://app.fabric.microsoft.com"}
                            target="_blank"
                            inline
                          >
                            Open workspace <OpenRegular fontSize={12} />
                          </FluentLink>
                        </MessageBarBody>
                      </MessageBar>
                      {deployedWorkspaceId && !cleaned && (
                        <Button
                          appearance="outline"
                          icon={<DeleteRegular />}
                          onClick={handleCleanup}
                          disabled={cleaning}
                          style={{ width: "100%", marginBottom: 8 }}
                        >
                          {cleaning ? "Deleting..." : "Delete workspace"}
                        </Button>
                      )}
                      {cleaned && <Caption1>Workspace deleted.</Caption1>}
                      {!cleaned && (
                        <Button
                          appearance="subtle"
                          onClick={resetState}
                          style={{ width: "100%" }}
                        >
                          Deploy another
                        </Button>
                      )}
                    </div>
                  )}

                  {error && (
                    <div style={{ marginTop: 16 }}>
                      <Divider style={{ marginBottom: 16 }} />
                      <MessageBar intent="error" style={{ marginBottom: 12 }}>
                        <MessageBarBody>{error}</MessageBarBody>
                      </MessageBar>
                      {deployedWorkspaceId && !cleaned && (
                        <Button
                          appearance="outline"
                          icon={<DeleteRegular />}
                          onClick={handlePartialCleanup}
                          disabled={cleaning}
                          style={{ width: "100%", marginBottom: 8 }}
                        >
                          {cleaning ? "Cleaning up..." : "Delete partial workspace"}
                        </Button>
                      )}
                      {cleaned && <Caption1>Workspace deleted.</Caption1>}
                      <Button
                        appearance="subtle"
                        onClick={resetState}
                        style={{ width: "100%" }}
                      >
                        Try again
                      </Button>
                    </div>
                  )}
                </div>
              )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
