"use client";

import { useParams, useSearchParams, useRouter } from "next/navigation";
import NextLink from "next/link";
import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/AuthProvider";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { industries } from "@/lib/industryCatalog";
import {
  fetchSubscriptions, fetchResourceGroups,
} from "@/lib/api";
import type { ScenarioInfo, AzureSubscription, AzureResourceGroup } from "@/lib/api";
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
  Checkbox,
  Link as FluentLink,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  ArrowLeftRegular,
  CheckmarkCircleFilled,
  DismissCircleFilled,
  CircleRegular,
  SubtractCircleRegular,
  ArrowRightRegular,
  DeleteRegular,
  OpenRegular,
  DatabaseRegular,
  TableRegular,
} from "@fluentui/react-icons";

// Universal scenarios — identical across all industries (IDs match backend _scenarios/)
const ALL_SCENARIOS: ScenarioInfo[] = [
  {
    id: "data-virtualization-batch",
    title: "Data Virtualization & Batch Analytics",
    description: "Provision ADLS Gen2, connect external data in-place via Fabric Shortcuts, then process through Bronze→Silver→Gold medallion layers orchestrated with Data Factory pipelines.",
    icon: "🔗",
    estimatedTime: "20–30 min",
    tags: ["shortcut", "adls", "medallion", "pipeline"],
    enabled: true,
    requiresAzure: true,
    azureParams: [],
  },
  {
    id: "real-time-monitoring",
    title: "Real-Time Monitoring",
    description: "Eventhouse + KQL Database for streaming ingestion, real-time analytics, and live dashboards.",
    icon: "⚡",
    estimatedTime: "12–18 min",
    tags: ["eventhouse", "kql", "streaming", "real-time"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
  },
  {
    id: "anomaly-detection-alerts",
    title: "Anomaly Detection & Alerts",
    description: "ML-based anomaly detection on historical data with alert pipeline and drill-through report.",
    icon: "🔔",
    estimatedTime: "15–20 min",
    tags: ["ml", "anomaly", "alerts", "lakehouse"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
  },
  {
    id: "ai-ml",
    title: "AI & Machine Learning",
    description: "End-to-end ML lifecycle: feature engineering, MLflow model training, evaluation, and batch scoring.",
    icon: "🤖",
    estimatedTime: "15–25 min",
    tags: ["ml", "mlflow", "experiment", "lakehouse"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
  },
  {
    id: "data-warehouse",
    title: "Data Warehouse",
    description: "Fabric Warehouse with SQL-native ingestion, T-SQL transformations, semantic model, and Power BI.",
    icon: "🗄️",
    estimatedTime: "12–18 min",
    tags: ["warehouse", "sql", "power-bi"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
  },
  {
    id: "external-data-integration",
    title: "External Database Integration (Mirroring)",
    description: "Mirror an Azure SQL Database or Databricks catalog into Fabric OneLake for near-real-time analytics.",
    icon: "🪞",
    estimatedTime: "10–15 min",
    tags: ["mirroring", "azure-sql", "databricks", "external"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
  },
  {
    id: "genai-applications",
    title: "GenAI Applications",
    description: "AI Skills (Data Agent) + RAG pattern — build a natural-language Q&A interface on your industry dataset.",
    icon: "✨",
    estimatedTime: "15–20 min",
    tags: ["genai", "data-agent", "rag", "lakehouse"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
  },
];

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
  status: "pending" | "running" | "completed" | "failed" | "skipped";
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
    Connection: "dataflow_gen2_24_item.svg",
    Shortcut: "lakehouse_24_item.svg",
  };
  const file = FILE_MAP[type];
  if (!file) return <span style={{ fontSize: size * 0.65, color: "#8b949e", fontWeight: 700, lineHeight: 1 }}>{type.charAt(0)}</span>;
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
  scenarioPicker: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  scenarioItem: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "8px 10px",
    borderRadius: "6px",
    border: "1px solid #21262d",
    backgroundColor: "#0d1117",
    transition: "border-color 0.1s",
  },
  scenarioItemActive: {
    cursor: "pointer",
    ":hover": {
      borderTopColor: "#388bfd",
      borderRightColor: "#388bfd",
      borderBottomColor: "#388bfd",
      borderLeftColor: "#388bfd",
      backgroundColor: "#1c2128",
    },
  },
  scenarioItemSelected: {
    borderTopColor: "#238636",
    borderRightColor: "#238636",
    borderBottomColor: "#238636",
    borderLeftColor: "#238636",
    backgroundColor: "#0d2310",
  },
  scenarioItemDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  azureSection: {
    border: "1px solid #30363d",
    borderRadius: "6px",
    padding: "12px",
    marginBottom: "16px",
    backgroundColor: "#0d1117",
  },
  azureSectionTitle: {
    fontSize: "10px",
    fontWeight: 700,
    color: "#8b949e",
    textTransform: "uppercase" as const,
    letterSpacing: "0.8px",
    marginBottom: "12px",
  },
  scenarioGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "12px",
  },
  scenarioCard: {
    borderRadius: "8px",
    padding: "16px",
    border: "1px solid #30363d",
    backgroundColor: "#161b22",
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
  },
  scenarioCardActive: {
    cursor: "pointer",
    ":hover": {
      borderTopColor: "#388bfd",
      borderRightColor: "#388bfd",
      borderBottomColor: "#388bfd",
      borderLeftColor: "#388bfd",
      backgroundColor: "#1c2128",
    },
  },
  scenarioCardDisabled: {
    opacity: 0.45,
    cursor: "default",
  },
  groupLabel: {
    padding: "8px 20px 6px",
    fontSize: "10px",
    fontWeight: 700,
    color: "#8b949e",
    textTransform: "uppercase" as const,
    letterSpacing: "0.8px",
    backgroundColor: "#0d1117",
    borderBottom: "1px solid #21262d",
  },
});

export default function DemoDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const id = params.id as string;
  const demo = DEMOS[id];
  const isCustomMode = searchParams.get("mode") === "custom";
  const { account, authError, login, getFabricToken, getStorageToken, getManagementToken } = useAuth();
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

  // ── Scenario state — derived from URL (?scenario=<id>) ──────────────────
  const selectedScenario = ALL_SCENARIOS.find(s => s.id === searchParams.get("scenario")) ?? null;
  // Azure params (used by the data-virtualization shortcut scenario)
  const [azureSubs, setAzureSubs] = useState<AzureSubscription[]>([]);
  const [azureRGs, setAzureRGs] = useState<AzureResourceGroup[]>([]);
  const [selectedSub, setSelectedSub] = useState("");
  const [selectedRG, setSelectedRG] = useState("");
  const [storAcctName, setStorAcctName] = useState("");
  const [azureRegion, setAzureRegion] = useState("eastus");
  const [createRG, setCreateRG] = useState(false);
  const [loadingSubs, setLoadingSubs] = useState(false);
  const [loadingRGs, setLoadingRGs] = useState(false);

  // Auto-open deploy panel when arriving via ?mode=custom
  useEffect(() => {
    if (isCustomMode && !showDeploy) {
      setShowDeploy(true);
    }
  }, [isCustomMode, showDeploy]);

  // Fetch Azure subscriptions once a scenario requiring Azure is selected
  const stableGetManagementToken = useCallback(getManagementToken, [getManagementToken]);
  useEffect(() => {
    if (!selectedScenario?.requiresAzure || !account) return;
    setLoadingSubs(true);
    stableGetManagementToken()
      .then((tok) => fetchSubscriptions(tok))
      .then(setAzureSubs)
      .catch(() => {})
      .finally(() => setLoadingSubs(false));
  }, [selectedScenario, account, stableGetManagementToken]);

  // Fetch resource groups when subscription changes
  useEffect(() => {
    if (!selectedSub || !account) return;
    setAzureRGs([]);
    setSelectedRG("");
    setLoadingRGs(true);
    stableGetManagementToken()
      .then((tok) => fetchResourceGroups(tok, selectedSub))
      .then(setAzureRGs)
      .catch(() => {})
      .finally(() => setLoadingRGs(false));
  }, [selectedSub, account, stableGetManagementToken]);

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

  const handleSelectScenario = async (sc: ScenarioInfo) => {
    router.replace(`/demos/${id}?mode=custom&scenario=${sc.id}`);
    setLoadingCapacities(true);
    setError(null);
    try {
      const token = await getFabricToken();
      const res = await fetch("https://api.fabric.microsoft.com/v1/capacities", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const caps = (data.value || [])
          .filter((c: { state: string }) => c.state === "Active")
          .map((c: { id: string; displayName: string; sku: string }) => ({
            id: c.id,
            displayName: c.displayName,
            sku: c.sku,
            isTrial: c.sku?.startsWith("FT") || false,
          }));
        setCapacities(caps);
        if (caps.length > 0) setSelectedCapacity(caps[0].id);
      } else {
        setError("Failed to load Fabric capacities");
      }
    } catch (e: unknown) {
      setError(`Failed to load capacities: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoadingCapacities(false);
    }
  };

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
      // Include management token when scenario requires Azure provisioning
      if (selectedScenario?.requiresAzure) {
        try {
          const mgmtTok = await getManagementToken();
          if (mgmtTok) headers["X-Management-Token"] = mgmtTok;
        } catch { /* continue without management token */ }
      }

      const resp = await fetch(`${API}/api/deploy/${id}`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          demo_id: id,
          workspace_name: workspaceName || `${selectedScenario?.title ?? demo.title} Demo`,
          capacity_id: selectedCapacity || undefined,
          ...(selectedScenario && { scenario_id: selectedScenario.id }),
          ...(selectedSub && { subscription_id: selectedSub }),
          ...(selectedRG && { resource_group: selectedRG }),
          ...(storAcctName && { storage_account_name: storAcctName }),
          azure_location: azureRegion || "eastus",
          create_resource_group: createRG,
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
    router.replace(`/demos/${id}?mode=custom`);
    setSelectedSub("");
    setSelectedRG("");
    setStorAcctName("");
    setAzureRegion("eastus");
    setCreateRG(false);
  };

  const loadCapacities = async () => {
    setShowDeploy(true);
    setError(null);
    // In custom mode, a scenario must be chosen first (shown in the main content area)
    if (isCustomMode && !selectedScenario) return;
    setLoadingCapacities(true);
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
      {/* Breadcrumb — rendered client-side so it can read ?mode from URL */}
      {(() => { const ind = industries.find(i => i.demoId === id); return ind ? <Breadcrumbs industrySlug={ind.slug} deploymentType={isCustomMode ? "custom" : "standard"} scenarioTitle={isCustomMode && selectedScenario ? selectedScenario.title : undefined} demoId={id} /> : null; })()}
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

            {/* === CUSTOM MODE: No scenario selected → scenario picker grid === */}
            {isCustomMode && !selectedScenario && (
              <>
                <div style={{ marginBottom: 4 }}>
                  <div style={{ fontSize: 17, fontWeight: 700, color: "#e6edf3", marginBottom: 6 }}>Choose a deployment scenario</div>
                  <div style={{ fontSize: 13, color: "#8b949e", marginBottom: 16, lineHeight: "20px" }}>
                    Select how you want to deploy the {demo.title} demo. Only <strong style={{ color: "#e6edf3" }}>External Data Integration</strong> is available today.
                  </div>
                </div>
                <div className={styles.scenarioGrid}>
                  {ALL_SCENARIOS.map((sc) => (
                    <div
                      key={sc.id}
                      onClick={sc.enabled && account ? () => handleSelectScenario(sc) : undefined}
                      className={[
                        styles.scenarioCard,
                        sc.enabled && account ? styles.scenarioCardActive : styles.scenarioCardDisabled,
                      ].join(" ")}
                    >
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                        <span style={{ fontSize: 28, lineHeight: 1, flexShrink: 0, marginTop: 2 }}>{sc.icon}</span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 14, fontWeight: 700, color: sc.enabled ? "#e6edf3" : "#484f58", marginBottom: 4 }}>{sc.title}</div>
                          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" as const }}>
                            {sc.enabled ? (
                              <Badge appearance="tint" color="success" size="small">Active</Badge>
                            ) : (
                              <Badge appearance="tint" color="subtle" size="small">Coming soon</Badge>
                            )}
                            <Caption1 style={{ color: sc.enabled ? "#8b949e" : "#484f58" }}>{sc.estimatedTime}</Caption1>
                          </div>
                        </div>
                      </div>
                      <div style={{ fontSize: 12, color: sc.enabled ? "#8b949e" : "#3d444d", lineHeight: "18px" }}>{sc.description}</div>
                      {!account && sc.enabled && (
                        <Caption1 style={{ color: "#f0883e", marginTop: 2 }}>Sign in first to select</Caption1>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* === CUSTOM MODE: External Data Integration scenario selected === */}
            {isCustomMode && selectedScenario?.id === "data-virtualization-batch" && (
              <>
                {/* Shortcut-specific data flow — 2-row labeled pipeline */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <ArrowRightRegular fontSize={16} /> Data Flow
                  </div>
                  <div style={{ padding: "16px 20px" }}>
                    {/* Row 1: Ingest layer */}
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#8b949e", letterSpacing: "0.8px", textTransform: "uppercase", marginBottom: 8 }}>Ingest</div>
                    <div style={{ display: "flex", alignItems: "center", marginBottom: 16, flexWrap: "nowrap" }}>
                      {[
                        { label: "Source", value: "CSV Files", color: "#1f3a5c" },
                        { label: "Azure", value: "ADLS Gen2", color: "#1c4a82" },
                        { label: "Shortcut", value: "Virtual Link", color: "#1a5272" },
                        { label: "Lakehouse", value: "Delta Tables", color: "#1a5c4a" },
                      ].map((step, i, arr) => (
                        <div key={i} style={{ display: "flex", alignItems: "center" }}>
                          <div style={{ backgroundColor: step.color, borderRadius: 6, padding: "8px 14px", minWidth: 108, flexShrink: 0 }}>
                            <div style={{ fontSize: "9px", fontWeight: 700, color: "rgba(255,255,255,0.55)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 2 }}>{step.label}</div>
                            <div style={{ fontSize: "13px", fontWeight: 500, color: "#fff" }}>{step.value}</div>
                          </div>
                          {i < arr.length - 1 && <ArrowRightRegular style={{ color: "#30363d", flexShrink: 0, margin: "0 2px" }} fontSize={16} />}
                        </div>
                      ))}
                    </div>
                    {/* Row 2: Analyze + Serve layer */}
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#8b949e", letterSpacing: "0.8px", textTransform: "uppercase", marginBottom: 8 }}>Analyze &amp; Serve</div>
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "nowrap" }}>
                      {[
                        { label: "Notebooks", value: "Bronze→Gold", color: "#2d6a1a" },
                        { label: "Semantic Model", value: "Direct Lake", color: "#4a5219" },
                        { label: "Power BI", value: "Reports", color: "#5c3a19" },
                      ].map((step, i, arr) => (
                        <div key={i} style={{ display: "flex", alignItems: "center" }}>
                          <div style={{ backgroundColor: step.color, borderRadius: 6, padding: "8px 14px", minWidth: 108, flexShrink: 0 }}>
                            <div style={{ fontSize: "9px", fontWeight: 700, color: "rgba(255,255,255,0.55)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 2 }}>{step.label}</div>
                            <div style={{ fontSize: "13px", fontWeight: 500, color: "#fff" }}>{step.value}</div>
                          </div>
                          {i < arr.length - 1 && <ArrowRightRegular style={{ color: "#30363d", flexShrink: 0, margin: "0 2px" }} fontSize={16} />}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* What Gets Created — shortcut scenario items */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <DatabaseRegular fontSize={16} /> What Gets Created
                  </div>
                  <div className={styles.sectionBody}>
                    <div className={styles.groupLabel}>Azure Resources</div>
                    {[
                      { type: "StorageAccount", name: "ADLS Gen2 Storage Account", description: "Auto-provisioned container holding demo data files", badge: "Azure" },
                      { type: "RBACRole", name: "Storage Blob Data Contributor", description: "Role assignment granting Fabric read access to the storage account", badge: "RBAC" },
                    ].map((item, i) => (
                      <div key={i} className={styles.itemRow}>
                        <div className={styles.itemLeft}>
                          <span className={styles.itemIconWrap}>
                            <FabricItemIcon type={item.type} size={20} />
                          </span>
                          <div>
                            <Text weight="medium" size={300}>{item.name}</Text>
                            <div><Caption1>{item.description}</Caption1></div>
                          </div>
                        </div>
                        <Badge appearance="tint" size="small" color="warning">{item.badge}</Badge>
                      </div>
                    ))}
                    <div className={styles.groupLabel}>Fabric Resources</div>
                    {[
                      { type: "Workspace", name: "New Fabric Workspace", description: "Dedicated workspace for this deployment" },
                      { type: "Connection", name: "ADLS Gen2 Connection", description: "Shareable cloud connection using User Delegation SAS credentials" },
                      { type: "Lakehouse", name: demo.fabricItems.find(f => f.type === "Lakehouse")?.name ?? "demo_lakehouse", description: demo.fabricItems.find(f => f.type === "Lakehouse")?.description ?? "Central data lakehouse" },
                      { type: "Shortcut", name: "adls_shortcut", description: "ADLS Gen2 shortcut pointing to the provisioned storage container" },
                      ...demo.fabricItems
                        .filter(f => ["Notebook", "Eventhouse", "KQLDatabase", "SemanticModel", "Report", "DataPipeline", "KQLDashboard"].includes(f.type))
                        .map(f => ({ type: f.type, name: f.name, description: f.description })),
                    ].map((item, i, arr) => (
                      <div key={i} className={i < arr.length - 1 ? styles.itemRow : styles.itemRowLast}>
                        <div className={styles.itemLeft}>
                          <span className={styles.itemIconWrap}>
                            <FabricItemIcon type={item.type} size={20} />
                          </span>
                          <div>
                            <Text weight="medium" size={300}>{item.name}</Text>
                            <div><Caption1>{item.description}</Caption1></div>
                          </div>
                        </div>
                        <Badge appearance="tint" size="small" color="informative">{item.type}</Badge>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Sample Data — industry-specific */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <TableRegular fontSize={16} /> Sample Data
                  </div>
                  <div className={styles.sectionBody}>
                    {demo.sampleData.map((d, i) => (
                      <div key={i} className={styles.dataRow} style={i === demo.sampleData.length - 1 ? { borderBottom: "none" } : undefined}>
                        <div className={styles.dataLeft}>
                          <Badge appearance="tint" color="severe" size="small">{d.format}</Badge>
                          <div>
                            <Text weight="medium" size={200}>{d.fileName}</Text>
                            <div><Caption1>{d.description}</Caption1></div>
                          </div>
                        </div>
                        <Caption1 style={{ fontVariantNumeric: "tabular-nums" }}>{d.rows.toLocaleString()} rows</Caption1>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* === STANDARD MODE: Original demo overview === */}
            {!isCustomMode && (
              <>
                {/* Architecture / Data Flow */}
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
                          <div className={styles.flowBox} style={{ backgroundColor: LAYER_COLORS[i] }}>
                            {label && (
                              <div className={styles.flowLabel} style={{ color: "rgba(255,255,255,0.7)" }}>{label}</div>
                            )}
                            <div className={styles.flowValue}>{value}</div>
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
                      <div key={i} className={i < demo.fabricItems.length - 1 ? styles.itemRow : styles.itemRowLast}>
                        <div className={styles.itemLeft}>
                          <span className={styles.itemIconWrap}>
                            <FabricItemIcon type={item.type} size={20} />
                          </span>
                          <div>
                            <Text weight="medium" size={300}>{item.name}</Text>
                            <div><Caption1>{item.description}</Caption1></div>
                          </div>
                        </div>
                        <Badge appearance="tint" size="small" color="informative">{item.type}</Badge>
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
                          <Badge appearance="tint" color="severe" size="small">{d.format}</Badge>
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
              </>
            )}
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

              {/* ── Custom mode: waiting for scenario selection ── */}
              {isCustomMode && showDeploy && !selectedScenario && !deploying && !completed && (
                <div>
                  {account ? (
                    <Caption1 style={{ display: "block", color: "#8b949e", marginBottom: 12 }}>
                      Signed in as {account.username}
                    </Caption1>
                  ) : (
                    <Button appearance="primary" style={{ width: "100%", marginBottom: 12 }} onClick={login}>
                      Sign in to deploy
                    </Button>
                  )}
                  <div style={{ padding: "16px", borderRadius: 6, border: "1px dashed #30363d", backgroundColor: "#0d1117", textAlign: "center" }}>
                    <Caption1 style={{ color: "#484f58" }}>← Select a scenario to configure</Caption1>
                  </div>
                  {authError && (
                    <div style={{ marginTop: 8, color: "#f85149", fontSize: 12 }}>Auth error: {authError}</div>
                  )}
                </div>
              )}

              {/* ── Phase 2: Configure (workspace + capacity + Azure params) ── */}
              {showDeploy && (!isCustomMode || !!selectedScenario) && !deploying && !completed && (
                <div>
                  {/* Selected scenario chip */}
                  {selectedScenario && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 6, marginBottom: 16, border: "1px solid #238636", backgroundColor: "#0d2310" }}>
                      <span style={{ fontSize: 18 }}>{selectedScenario.icon}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: "#3fb68b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{selectedScenario.title}</div>
                        <Caption1 style={{ color: "#238636" }}>{selectedScenario.estimatedTime}</Caption1>
                      </div>
                      <button
                        onClick={() => router.replace(`/demos/${id}?mode=custom`)}
                        style={{ background: "none", border: "none", color: "#484f58", cursor: "pointer", fontSize: 14, padding: "0 2px" }}
                        title="Change scenario"
                      >✕</button>
                    </div>
                  )}

                  <div className={styles.formField}>
                    <label className={styles.formLabel}>Workspace name</label>
                    <Input
                      value={workspaceName}
                      onChange={(_, data) => setWorkspaceName(data.value)}
                      placeholder={`${selectedScenario?.title ?? demo.title} Demo`}
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

                  {/* Azure params — only for shortcut scenarios */}
                  {selectedScenario?.requiresAzure && (
                    <div className={styles.azureSection}>
                      <div className={styles.azureSectionTitle}>Azure Resources (ADLS Gen2)</div>

                      {/* Subscription */}
                      <div style={{ marginBottom: 10 }}>
                        <label className={styles.formLabel}>Subscription</label>
                        {loadingSubs ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}><Spinner size="tiny" /><Caption1>Loading…</Caption1></div>
                        ) : azureSubs.length > 0 ? (
                          <Select value={selectedSub} onChange={(_, data) => setSelectedSub(data.value)} style={{ width: "100%" }}>
                            <option value="">— select —</option>
                            {azureSubs.map((s) => (
                              <option key={s.id} value={s.id}>{s.displayName}</option>
                            ))}
                          </Select>
                        ) : (
                          <Caption1 style={{ color: "#f85149" }}>No subscriptions found. Check sign-in.</Caption1>
                        )}
                      </div>

                      {/* Resource Group */}
                      {selectedSub && (
                        <div style={{ marginBottom: 10 }}>
                          <label className={styles.formLabel}>Resource Group</label>
                          {loadingRGs ? (
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}><Spinner size="tiny" /><Caption1>Loading…</Caption1></div>
                          ) : (
                            <Select value={selectedRG} onChange={(_, data) => setSelectedRG(data.value)} style={{ width: "100%", marginBottom: 4 }}>
                              <option value="">— select or type name —</option>
                              {azureRGs.map((rg) => (
                                <option key={rg.name} value={rg.name}>{rg.name} ({rg.location})</option>
                              ))}
                            </Select>
                          )}
                          <Input
                            value={selectedRG}
                            onChange={(_, data) => setSelectedRG(data.value)}
                            placeholder="my-resource-group"
                            style={{ width: "100%", marginTop: 4 }}
                            size="small"
                          />
                          <div style={{ marginTop: 6 }}>
                            <Checkbox
                              label={<Caption1>Create resource group if not found</Caption1>}
                              checked={createRG}
                              onChange={(_, data) => setCreateRG(data.checked === true)}
                            />
                          </div>
                        </div>
                      )}

                      {/* Storage Account Name */}
                      <div style={{ marginBottom: 10 }}>
                        <label className={styles.formLabel}>
                          Storage Account <Caption1 style={{ color: "#484f58" }}>(optional — auto-generated if blank)</Caption1>
                        </label>
                        <Input
                          value={storAcctName}
                          onChange={(_, data) => setStorAcctName(data.value)}
                          placeholder="myaccount"
                          style={{ width: "100%" }}
                        />
                      </div>

                      {/* Azure Region */}
                      <div>
                        <label className={styles.formLabel}>Azure Region</label>
                        <Input
                          value={azureRegion}
                          onChange={(_, data) => setAzureRegion(data.value)}
                          placeholder="eastus"
                          style={{ width: "100%" }}
                        />
                      </div>
                    </div>
                  )}

                  <div className={styles.buttonRow}>
                    <Button appearance="primary" onClick={handleDeploy} style={{ flex: 1 }}>
                      Deploy
                    </Button>
                    <Button
                      appearance="outline"
                      onClick={() => { if (isCustomMode) router.replace(`/demos/${id}?mode=custom`); else setShowDeploy(false); }}
                    >
                      {isCustomMode ? "← Back" : "Cancel"}
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
                        {step.status === "skipped" && (
                          <SubtractCircleRegular fontSize={16} style={{ color: tokens.colorNeutralForeground3 }} />
                        )}
                      </span>
                      <span className={
                        step.status === "completed" ? styles.stepCompleted :
                        step.status === "running" ? styles.stepRunning :
                        step.status === "failed" ? styles.stepFailed :
                        step.status === "skipped" ? styles.stepPending :
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
