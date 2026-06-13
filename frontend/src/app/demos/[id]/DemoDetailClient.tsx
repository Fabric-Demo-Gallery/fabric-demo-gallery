"use client";

import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/AuthProvider";
import { oneLakeScopes } from "@/lib/msal";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { industries } from "@/lib/industryCatalog";
import {
  fetchSubscriptions, fetchResourceGroups,
} from "@/lib/api";
import type { ScenarioInfo, AzureSubscription, AzureResourceGroup } from "@/lib/api";
import NextLink from "next/link";
import { useDeployment } from "@/lib/DeploymentContext";
// import type { DeployStep } from "@/lib/DeploymentContext";
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
  ToggleButton,
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
  DatabaseLink24Regular,
  Pulse24Regular,
  AlertUrgent24Regular,
  BrainCircuit24Regular,
  Database24Regular,
  DatabaseArrowRight24Regular,
  Sparkle24Regular,
} from "@fluentui/react-icons";
import type { FluentIcon } from "@fluentui/react-icons";
import { DEMOS } from "@/lib/demoCatalog";
import { PRESENTER } from "@/lib/presenterContent";
import { explainError } from "@/lib/errorHelp";

// Universal scenarios — identical across all industries (IDs match backend _scenarios/)
const ALL_SCENARIOS: ScenarioInfo[] = [
  {
    id: "data-virtualization-batch",
    title: "Data Virtualization & Batch Analytics",
    description: "Provision ADLS Gen2, connect external data in-place via Fabric Shortcuts, then process through Bronze→Silver→Gold medallion layers orchestrated with Data Factory pipelines.",
    estimatedTime: "20–30 min",
    tags: ["shortcut", "adls", "medallion", "pipeline"],
    enabled: true,
    requiresAzure: true,
    azureParams: [],
    feature: "Shortcuts & Mirroring",
  },
  {
    id: "real-time-monitoring",
    title: "Real-Time Monitoring",
    description: "Eventhouse + KQL Database for streaming ingestion, real-time analytics, and live dashboards.",
    estimatedTime: "12–18 min",
    tags: ["eventhouse", "kql", "streaming", "real-time"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
    feature: "RTI",
  },
  {
    id: "anomaly-detection-alerts",
    title: "Anomaly Detection & Alerts",
    description: "ML-based anomaly detection on historical data with alert pipeline and drill-through report.",
    estimatedTime: "15–20 min",
    tags: ["ml", "anomaly", "alerts", "lakehouse"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
    feature: "Machine Learning",
  },
  {
    id: "ai-ml",
    title: "AI & Machine Learning",
    description: "End-to-end ML lifecycle: feature engineering, SynapseML LightGBM model training, evaluation, and batch scoring with risk rankings.",
    estimatedTime: "15–25 min",
    tags: ["ml", "lightgbm", "experiment", "lakehouse"],
    enabled: true,
    requiresAzure: false,
    azureParams: [],
    feature: "Machine Learning",
  },
  {
    id: "data-warehouse",
    title: "Data Warehouse",
    description: "Fabric Warehouse with SQL-native ingestion, T-SQL transformations, semantic model, and Power BI.",
    estimatedTime: "12–18 min",
    tags: ["warehouse", "sql", "power-bi"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
    feature: "Power BI",
  },
  {
    id: "external-data-integration",
    title: "External Database Integration (Mirroring)",
    description: "Provision an Azure SQL Database, seed it with operational data, then mirror it into Fabric — live, zero-ETL replication you can watch happen.",
    estimatedTime: "15–25 min",
    tags: ["mirroring", "azure-sql", "zero-etl", "replication"],
    enabled: true,
    requiresAzure: true,
    azureParams: [],
    feature: "Shortcuts & Mirroring",
    postDeploy: [
      { label: "02_live_change notebook", detail: "The wow moment: change a row in Azure SQL and watch it replicate into Fabric in seconds — no pipeline, no refresh." },
      { label: "mirrored_retail_db", detail: "Open the mirrored database and select Monitor replication to see all tables syncing live." },
      { label: "01_explore_mirrored notebook", detail: "Query the replicated tables directly from OneLake with Spark — no copy, always current." },
    ],
  },
  {
    id: "genai-applications",
    title: "GenAI Applications",
    description: "AI Skills (Data Agent) and a RAG pattern for a natural-language Q&A interface on your industry dataset.",
    estimatedTime: "15–20 min",
    tags: ["genai", "data-agent", "rag", "lakehouse"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
    feature: "Fabric Data Agents",
  },
];

// Professional Fluent System icons per scenario (replaces emoji).
const SCENARIO_ICON: Record<string, FluentIcon> = {
  "data-virtualization-batch": DatabaseLink24Regular,
  "real-time-monitoring": Pulse24Regular,
  "anomaly-detection-alerts": AlertUrgent24Regular,
  "ai-ml": BrainCircuit24Regular,
  "data-warehouse": Database24Regular,
  "external-data-integration": DatabaseArrowRight24Regular,
  "genai-applications": Sparkle24Regular,
};

const SCENARIO_FEATURES = [
  "RTI",
  "Fabric IQ",
  "Fabric Data Agents",
  "Power BI",
  "Machine Learning",
  "Shortcuts & Mirroring",
];

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
  /* ---- Presenter section ---- */
  presenterBody: {
    padding: "18px 20px",
    display: "flex",
    flexDirection: "column" as const,
    gap: "18px",
  },
  presenterValue: {
    fontSize: "14px",
    lineHeight: "21px",
    color: "#c9d1d9",
  },
  insightGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: "10px",
  },
  insightCard: {
    backgroundColor: "#0d1117",
    border: "1px solid #21262d",
    borderRadius: "8px",
    padding: "12px 14px",
    display: "flex",
    flexDirection: "column" as const,
    justifyContent: "space-between",
    gap: "8px",
  },
  insightValue: {
    fontSize: "15px",
    fontWeight: 600,
    color: "#3fb68b",
    lineHeight: "20px",
  },
  insightLabel: {
    fontSize: "11px",
    color: "#8b949e",
  },
  presenterSubhead: {
    fontSize: "11px",
    fontWeight: 600,
    color: "#8b949e",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    marginBottom: "8px",
  },
  pointList: {
    margin: "0",
    paddingLeft: "18px",
    display: "flex",
    flexDirection: "column" as const,
    gap: "6px",
  },
  pointItem: {
    fontSize: "13px",
    lineHeight: "19px",
    color: "#c9d1d9",
  },
  flowList: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
  },
  flowStep: {
    display: "flex",
    gap: "10px",
    alignItems: "flex-start",
  },
  flowStepNum: {
    flexShrink: 0,
    width: "20px",
    height: "20px",
    borderRadius: "50%",
    backgroundColor: "#132f27",
    color: "#3fb68b",
    fontSize: "11px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginTop: "1px",
  },
  flowStepText: {
    fontSize: "13px",
    lineHeight: "19px",
    color: "#c9d1d9",
  },
  /* ---- Post-deploy guidance ---- */
  nextList: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
    marginBottom: "12px",
  },
  nextItem: {
    display: "flex",
    gap: "10px",
    alignItems: "flex-start",
    backgroundColor: "#0d1117",
    border: "1px solid #21262d",
    borderRadius: "8px",
    padding: "10px 12px",
  },
  nextDot: {
    flexShrink: 0,
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    backgroundColor: "#3fb68b",
    marginTop: "6px",
  },
  nextLabel: {
    fontSize: "13px",
    fontWeight: 600,
    color: "#e6edf3",
    lineHeight: "18px",
  },
  nextDetail: {
    fontSize: "12px",
    color: "#8b949e",
    lineHeight: "17px",
    marginTop: "1px",
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
  const currentJobIdRef = useRef<string | null>(null);

  // ── Scenario state — derived from URL (?scenario=<id>) ──────────────────
  const selectedScenario = ALL_SCENARIOS.find(s => s.id === searchParams.get("scenario")) ?? null;
  const [scenarioFilter, setScenarioFilter] = useState("All");
  // Azure params (used by the data-virtualization shortcut scenario)
  const [azureSubs, setAzureSubs] = useState<AzureSubscription[]>([]);
  const [azureRGs, setAzureRGs] = useState<AzureResourceGroup[]>([]);
  const [selectedSub, setSelectedSub] = useState("");
  const [selectedRG, setSelectedRG] = useState("");
  const [storAcctName, setStorAcctName] = useState("");
  const [azureRegion, setAzureRegion] = useState("eastus");
  const [createRG, setCreateRG] = useState(false);
  const [loadingSubs, setLoadingSubs] = useState(false);
  const [subscriptionsError, setSubscriptionsError] = useState<string | null>(null);
  const [loadingRGs, setLoadingRGs] = useState(false);

  // Auto-open deploy panel when arriving via ?mode=custom
  useEffect(() => {
    if (isCustomMode && !showDeploy) {
      setShowDeploy(true);
    }
  }, [isCustomMode, showDeploy]);

  // Fetch capacities whenever a scenario is selected (including on page refresh)
  const stableGetFabricToken = useCallback(getFabricToken, [getFabricToken]);
  useEffect(() => {
    if (!selectedScenario || !account) return;
    setLoadingCapacities(true);
    setError(null);
    stableGetFabricToken()
      .then((token) =>
        fetch("https://api.fabric.microsoft.com/v1/capacities", {
          headers: { Authorization: `Bearer ${token}` },
        })
      )
      .then(async (res) => {
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
          if (caps.length > 0) setSelectedCapacity((prev) => prev || caps[0].id);
        } else {
          setError("Failed to load Fabric capacities");
        }
      })
      .catch((e: unknown) => {
        setError(`Failed to load capacities: ${e instanceof Error ? e.message : String(e)}`);
      })
      .finally(() => setLoadingCapacities(false));
  }, [selectedScenario, account, stableGetFabricToken]);

  // Fetch Azure subscriptions once a scenario requiring Azure is selected
  const stableGetManagementToken = useCallback(getManagementToken, [getManagementToken]);
  const loadAzureSubscriptions = useCallback(async (interactive: boolean) => {
    if (!selectedScenario?.requiresAzure || !account) return;
    setLoadingSubs(true);
    setSubscriptionsError(null);
    setAzureSubs([]);
    try {
      const tok = await Promise.race<string>([
        stableGetManagementToken({ interactive }),
        new Promise<string>((_, reject) => {
          setTimeout(() => reject(new Error("Timed out while acquiring Azure access token.")), 10000);
        }),
      ]);
      const subs = await fetchSubscriptions(tok);
      setAzureSubs(subs);
      if (!subs.length) {
        setSubscriptionsError("No subscriptions found for this account.");
      }
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e);
      const msg = /interaction_required|consent_required|login_required/i.test(raw)
        ? "Azure access needs consent. Click retry to sign in for Azure resources."
        : raw || "Could not load Azure subscriptions.";
      setSubscriptionsError(msg);
    } finally {
      setLoadingSubs(false);
    }
  }, [selectedScenario?.requiresAzure, account, stableGetManagementToken]);

  useEffect(() => {
    if (!selectedScenario?.requiresAzure || !account) return;
    void loadAzureSubscriptions(false);
  }, [selectedScenario, account, loadAzureSubscriptions]);

  // Fetch resource groups when subscription changes
  useEffect(() => {
    if (!selectedSub || !account) return;
    setAzureRGs([]);
    setSelectedRG("");
    setLoadingRGs(true);
    stableGetManagementToken({ interactive: false })
      .then((tok) => fetchResourceGroups(tok, selectedSub))
      .then(setAzureRGs)
      .catch(() => {})
      .finally(() => setLoadingRGs(false));
  }, [selectedSub, account, stableGetManagementToken]);

  // Reconnect to an existing job when ?job_id= is in the URL (e.g. from Monitoring → View)
  const jobIdParam = searchParams.get("job_id");
  useEffect(() => {
    if (!jobIdParam || !account) return;

    const controller = new AbortController();
    abortRef.current = controller;
    currentJobIdRef.current = jobIdParam;
    let cancelled = false;
    setShowDeploy(true);
    setDeploying(true);
    setError(null);
    setCompleted(false);
    setSteps([]);

    const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

    (async () => {
      try {
        const token = await getFabricToken();
        const streamResp = await fetch(`${API}/api/jobs/${jobIdParam}/stream`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!streamResp.ok) {
          if (!cancelled) setError(`Could not reconnect to job: ${streamResp.status}`);
          return;
        }

        const reader = streamResp.body?.getReader();
        const decoder = new TextDecoder();
        if (!reader) { return; }

        let buffer = "";
        let currentEvent = "";
        let streamHadError = false;

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
                      } catch { /* not JSON */ }
                    }
                  }
                  if (step.name === "workspace" && step.itemId) {
                    setDeployedWorkspaceId(step.itemId);
                  }
                } else if (currentEvent === "error") {
                  streamHadError = true;
                  setError(data.message || "Deployment failed");
                  if (data.workspaceId) setDeployedWorkspaceId(data.workspaceId);
                }
              } catch { /* ignore malformed lines */ }
              currentEvent = "";
            }
          }
        }
        if (!cancelled && !streamHadError) setCompleted((prev) => prev || true);
      } catch (e: unknown) {
        if (!(e instanceof DOMException && e.name === "AbortError") && !cancelled) {
          setError(e instanceof Error ? e.message : "Connection failed");
        }
      } finally {
        if (!cancelled) {
          abortRef.current = null;
          setDeploying(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobIdParam, account]);

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

  const handleSelectScenario = (sc: ScenarioInfo) => {
    router.replace(`/demos/${id}?mode=custom&scenario=${sc.id}`);
    // Capacities will be fetched by the useEffect watching selectedScenario
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
      let oneLakeToken = "";
      if (account) {
        const { msalInstance } = await import("@/lib/msal");
        [fabricToken, storageToken] = await Promise.all([
          getFabricToken(),
          getStorageToken(),
        ]);
        try {
          const res = await msalInstance.acquireTokenSilent({ scopes: oneLakeScopes, account });
          oneLakeToken = res.accessToken;
        } catch {
          try {
            const res = await msalInstance.acquireTokenPopup({ scopes: oneLakeScopes });
            oneLakeToken = res.accessToken;
          } catch { /* proceed without OneLake token */ }
        }
      }

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (fabricToken) {
        headers["Authorization"] = `Bearer ${fabricToken}`;
        headers["X-Storage-Token"] = storageToken;
      }
      if (oneLakeToken) {
        headers["X-OneLake-Token"] = oneLakeToken;
      }
      if (selectedScenario?.requiresAzure) {
        try {
          const mgmtTok = await getManagementToken();
          if (mgmtTok) headers["X-Management-Token"] = mgmtTok;
        } catch { /* continue without management token */ }
      }

      // Step 1: Create the job — returns immediately with a job_id
      const createResp = await fetch(`${API}/api/jobs`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          demo_id: id,
          workspace_name: workspaceName || (isCustomMode
            ? `${demo.industry} - Custom - ${selectedScenario?.title ?? demo.title}`
            : `${demo.industry} - Standard`),
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

      if (!createResp.ok) {
        let errorMsg = `Deployment failed (${createResp.status})`;
        try {
          const errData = await createResp.json();
          errorMsg = errData.detail || errData.message || errorMsg;
        } catch {
          const text = await createResp.text();
          errorMsg = text.slice(0, 300) || errorMsg;
        }
        setError(errorMsg);
        setDeploying(false);
        return;
      }

      const { job_id } = await createResp.json();
      currentJobIdRef.current = job_id;

      // Step 2: Stream progress from the job's SSE endpoint
      const streamResp = await fetch(`${API}/api/jobs/${job_id}/stream`, {
        headers: fabricToken ? { Authorization: `Bearer ${fabricToken}` } : {},
        signal: controller.signal,
      });

      if (!streamResp.ok) {
        const text = await streamResp.text();
        setError(`Stream error ${streamResp.status}: ${text.slice(0, 200)}`);
        setDeploying(false);
        return;
      }

      const reader = streamResp.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        setError("No response stream");
        setDeploying(false);
        return;
      }

      let buffer = "";
      let currentEvent = "";
      let streamHadError = false;
      let sawDone = false;

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
                  sawDone = true;
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
                streamHadError = true;
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

      // Stream ended — only mark completed if we actually got a "done" event
      // Use the local sawDone flag (not the `completed` state, which is stale
      // inside this async closure) so a successful deployment doesn't falsely
      // report a lost connection.
      if (sawDone) {
        setCompleted(true);
      } else if (!streamHadError) {
        setError("Connection to deployment server was lost. Check the Monitoring page to see if the deployment is still running.");
      }
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
    // Cancel the backend job first (fire-and-forget)
    if (currentJobIdRef.current && account) {
      const jobId = currentJobIdRef.current;
      const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      getFabricToken().then((tok) => {
        fetch(`${API}/api/jobs/${jobId}`, {
          method: "DELETE",
          headers: tok ? { Authorization: `Bearer ${tok}` } : {},
        }).catch(() => { /* best-effort */ });
      }).catch(() => { /* ignore token errors */ });
    }
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

  const deleteWorkspace = async (clearError: boolean) => {
    if (!deployedWorkspaceId) {
      alert("No workspace to delete \u2014 the workspace ID is missing.");
      return;
    }
    setCleaning(true);
    try {
      const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const headers: Record<string, string> = {};
      try {
        const t = await getFabricToken();
        if (t) headers["Authorization"] = `Bearer ${t}`;
      } catch { /* token fetch failed \u2014 backend will report 401 below */ }
      if (!headers["Authorization"]) {
        alert("Could not get a Fabric sign-in token. Please sign in again, then retry the delete.");
        return;
      }
      // Mirroring deployments also created an Azure SQL server — the backend
      // deletes it too when the request carries a management token.
      if (selectedScenario?.id === "external-data-integration") {
        try {
          const mgmt = await getManagementToken();
          if (mgmt) headers["X-Management-Token"] = mgmt;
        } catch { /* non-fatal — workspace still gets deleted */ }
      }
      const res = await fetch(`${API}/api/deploy/${deployedWorkspaceId}`, { method: "DELETE", headers });
      if (res.ok) {
        setCleaned(true);
        if (clearError) setError(null);
        return;
      }
      // Surface the backend's real error message (detail) instead of an empty statusText
      let msg = res.statusText || `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body?.detail) msg = body.detail;
      } catch { /* body wasn't JSON */ }
      if (res.status === 404) {
        // Already gone \u2014 treat as success
        setCleaned(true);
        if (clearError) setError(null);
        return;
      }
      alert(`Failed to delete workspace: ${msg}`);
    } catch (e) {
      alert(`Could not reach the backend to delete the workspace: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setCleaning(false);
    }
  };

  const handleCleanup = async () => {
    if (!confirm("Delete the entire workspace and all items?")) return;
    await deleteWorkspace(false);
  };

  const handlePartialCleanup = async () => {
    if (!confirm("Delete the partially created workspace?")) return;
    await deleteWorkspace(true);
  };

  const resetState = () => {
    setShowDeploy(true);
    setDeploying(false);
    setCompleted(false);
    setSteps([]);
    setError(null);
    setDeployedWorkspaceId("");
    setCleaned(false);
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
                <Caption1>{isCustomMode && selectedScenario ? selectedScenario.estimatedTime : demo.estimatedTime}</Caption1>
                {isCustomMode && selectedScenario
                  ? (selectedScenario.feature ? <Caption1>{selectedScenario.feature}</Caption1> : null)
                  : <Caption1>{demo.fabricItems.length} Fabric items</Caption1>}
              </div>
              <div className={styles.title}>{isCustomMode && selectedScenario ? selectedScenario.title : demo.title}</div>
              <div className={styles.longDesc}>{isCustomMode && selectedScenario ? selectedScenario.description : demo.longDescription}</div>
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
                    Select how you want to deploy the {demo.title} demo. Scenarios marked <strong style={{ color: "#e6edf3" }}>Active</strong> are available today.
                  </div>
                </div>
                {/* Feature filters */}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 16 }}>
                  {["All", ...SCENARIO_FEATURES].map((feat) => (
                    <ToggleButton
                      key={feat}
                      size="small"
                      appearance={scenarioFilter === feat ? "primary" : "subtle"}
                      checked={scenarioFilter === feat}
                      onClick={() => setScenarioFilter(feat)}
                    >
                      {feat}
                    </ToggleButton>
                  ))}
                </div>
                <div className={styles.scenarioGrid}>
                  {ALL_SCENARIOS
                    .filter((sc) => scenarioFilter === "All" || sc.feature === scenarioFilter)
                    .map((sc) => (
                    <div
                      key={sc.id}
                      onClick={sc.enabled ? () => handleSelectScenario(sc) : undefined}
                      className={[
                        styles.scenarioCard,
                        sc.enabled ? styles.scenarioCardActive : styles.scenarioCardDisabled,
                      ].join(" ")}
                    >
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                        {(() => { const Icon = SCENARIO_ICON[sc.id] ?? Sparkle24Regular; return <Icon fontSize={26} color={sc.enabled ? "#3fb68b" : "#484f58"} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden />; })()}
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

            {/* === EXTERNAL DATABASE INTEGRATION (Mirroring) === */}
            {isCustomMode && selectedScenario?.id === "external-data-integration" && (
              <>
                {/* Presenter Guide — talking track for solution engineers */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <CheckmarkCircleFilled fontSize={16} /> Presenter Guide
                  </div>
                  <div className={styles.presenterBody}>
                    <div className={styles.presenterValue}>
                      Show zero-ETL: an operational Azure SQL database mirrored into Fabric OneLake — live and continuous, with no pipeline, no schedule, and no code. The deploy already provisioned and seeded the database, created the mirrored database, and started replication. Your job is to <strong style={{ color: "#e6edf3" }}>show it</strong>.
                    </div>

                    <div>
                      <div className={styles.presenterSubhead}>Talking points</div>
                      <ul className={styles.pointList}>
                        <li className={styles.pointItem}>The Azure SQL database is a stand-in for an operational POS/ERP system — the data lives outside Fabric.</li>
                        <li className={styles.pointItem}>Mirroring replicates it into OneLake as Delta tables automatically — no pipeline, no refresh, no copy job to build or maintain.</li>
                        <li className={styles.pointItem}>Replicated tables are queryable instantly with Spark, T-SQL, and Direct Lake — analytics on operational data with zero ETL.</li>
                        <li className={styles.pointItem}>Authentication is Microsoft Entra-only (no SQL passwords) via the Fabric workspace identity — enterprise-ready and policy-compliant.</li>
                      </ul>
                    </div>

                    <div>
                      <div className={styles.presenterSubhead}>Suggested demo flow</div>
                      <div className={styles.flowList}>
                        {[
                          { step: "Show replication is live", detail: "Open the mirrored_retail_db item → Monitor replication. All 4 tables show Replicating with row counts and a recent timestamp — it populated itself." },
                          { step: "Query with zero ETL", detail: "Open 01_explore_mirrored and Run all. It reads the replicated tables straight from OneLake and runs a cross-table revenue join — no copy, no transform." },
                          { step: "The wow moment — live change", detail: "Open 02_live_change. Read a price from the Fabric copy, UPDATE it in Azure SQL, then watch the mirrored copy catch up in seconds. Then insert a new sale and watch the new row appear." },
                          { step: "Land the message", detail: "Nothing moved that data except Fabric Mirroring itself — no pipeline, no schedule, no refresh, no code." },
                        ].map((f, i) => (
                          <div key={i} className={styles.flowStep}>
                            <span className={styles.flowStepNum}>{i + 1}</span>
                            <div className={styles.flowStepText}>
                              <strong style={{ color: "#e6edf3" }}>{f.step}</strong>: {f.detail}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <div className={styles.presenterSubhead}>Before you start</div>
                      <ul className={styles.pointList}>
                        <li className={styles.pointItem}>Make sure the Fabric capacity is running (not paused) — replication stalls on a paused capacity.</li>
                        <li className={styles.pointItem}>If a table shows 0 rows right after deploy, wait 2–3 minutes for the initial snapshot to finish seeding.</li>
                        <li className={styles.pointItem}>00_seed_sql already ran during deploy; 01 and 02 are created but not auto-run so you can run them live.</li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Mirroring-specific data flow — 2-row labeled pipeline */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <ArrowRightRegular fontSize={16} /> Data Flow
                  </div>
                  <div style={{ padding: "16px 20px" }}>
                    {/* Row 1: Replicate layer */}
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#8b949e", letterSpacing: "0.8px", textTransform: "uppercase", marginBottom: 8 }}>Replicate (zero-ETL)</div>
                    <div style={{ display: "flex", alignItems: "center", marginBottom: 16, flexWrap: "nowrap" }}>
                      {[
                        { label: "Source", value: "CSV Files", color: "#1f3a5c" },
                        { label: "Azure SQL", value: "Operational DB", color: "#1c4a82" },
                        { label: "Mirroring", value: "Live Replication", color: "#1a5272" },
                        { label: "OneLake", value: "Delta Tables", color: "#1a5c4a" },
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
                    {/* Row 2: Explore + Prove layer */}
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#8b949e", letterSpacing: "0.8px", textTransform: "uppercase", marginBottom: 8 }}>Explore &amp; Prove</div>
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "nowrap" }}>
                      {[
                        { label: "Notebooks", value: "Spark on OneLake", color: "#2d6a1a" },
                        { label: "Live Change", value: "Watch It Sync", color: "#4a5219" },
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

                {/* What Gets Created — mirroring scenario items */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <DatabaseRegular fontSize={16} /> What Gets Created
                  </div>
                  <div className={styles.sectionBody}>
                    <div className={styles.groupLabel}>Azure Resources</div>
                    {[
                      { type: "SQLDatabase", name: "Azure SQL Database", description: "Auto-provisioned logical server + database with Microsoft Entra-only auth, seeded with operational tables", badge: "Azure" },
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
                      { type: "WorkspaceIdentity", name: "Workspace Identity", description: "Secret-less Microsoft Entra identity that authenticates the mirroring connection" },
                      { type: "Lakehouse", name: "staging_lakehouse", description: "Staging area that holds the seed CSVs the notebook loads into Azure SQL" },
                      { type: "Connection", name: "Azure SQL Connection", description: "Workspace-identity authenticated connection to the source database" },
                      { type: "MirroredDatabase", name: "mirrored_retail_db", description: "Live, continuously replicated copy of the Azure SQL database in OneLake" },
                      { type: "Notebook", name: "00_seed_sql", description: "Seeds Azure SQL with primary-key tables and loads the sample data" },
                      { type: "Notebook", name: "01_explore_mirrored", description: "Query the replicated tables directly from OneLake with Spark" },
                      { type: "Notebook", name: "02_live_change", description: "Change a row in Azure SQL and watch it replicate into Fabric in seconds" },
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
                {/* Presenter — talking track for solution engineers */}
                {PRESENTER[id] && (
                  <div className={styles.section}>
                    <div className={styles.sectionHeader}>
                      <CheckmarkCircleFilled fontSize={16} /> Presenter Guide
                    </div>
                    <div className={styles.presenterBody}>
                      <div className={styles.presenterValue}>{PRESENTER[id].businessValue}</div>

                      <div className={styles.insightGrid}>
                        {PRESENTER[id].sampleInsights.map((ins, i) => (
                          <div key={i} className={styles.insightCard}>
                            <div className={styles.insightValue}>{ins.value}</div>
                            <div className={styles.insightLabel}>{ins.label}</div>
                          </div>
                        ))}
                      </div>

                      <div>
                        <div className={styles.presenterSubhead}>Talking points</div>
                        <ul className={styles.pointList}>
                          {PRESENTER[id].talkingPoints.map((pt, i) => (
                            <li key={i} className={styles.pointItem}>{pt}</li>
                          ))}
                        </ul>
                      </div>

                      <div>
                        <div className={styles.presenterSubhead}>Suggested demo flow</div>
                        <div className={styles.flowList}>
                          {PRESENTER[id].demoFlow.map((f, i) => (
                            <div key={i} className={styles.flowStep}>
                              <span className={styles.flowStepNum}>{i + 1}</span>
                              <div className={styles.flowStepText}>
                                <strong style={{ color: "#e6edf3" }}>{f.step}</strong>: {f.detail}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

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

            {/* === CUSTOM MODE: AI & Machine Learning scenario selected === */}
            {isCustomMode && selectedScenario?.id === "ai-ml" && (
              <>
                {/* Data Flow */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <ArrowRightRegular fontSize={16} /> Data Flow
                  </div>
                  <div style={{ fontSize: 12, color: "#8b949e", marginBottom: 12 }}>
                    End-to-end ML pipeline: Bronze/Silver data → Feature engineering → LightGBM training → Batch scoring
                  </div>
                  <div className={styles.flowRow}>
                    {[
                      { label: "Bronze", value: "Raw Ingest", color: "#3fb68b" },
                      { label: "Silver", value: "Clean & Enrich", color: "#238636" },
                      { label: "Features", value: "ML Feature Table", color: "#1f6feb" },
                      { label: "Train", value: "SynapseML LightGBM", color: "#8957e5" },
                      { label: "Score", value: "Predictions & Risk", color: "#da3633" },
                    ].map((step, i, arr) => (
                      <div key={i} style={{ display: "flex", alignItems: "center" }}>
                        <div className={styles.flowBox} style={{ backgroundColor: step.color }}>
                          <div className={styles.flowLabel} style={{ color: "rgba(255,255,255,0.7)" }}>{step.label}</div>
                          <div className={styles.flowValue}>{step.value}</div>
                        </div>
                        {i < arr.length - 1 && <ArrowRightRegular className={styles.flowArrow} fontSize={18} />}
                      </div>
                    ))}
                  </div>
                </div>

                {/* What Gets Created */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <DatabaseRegular fontSize={16} /> What Gets Created
                  </div>
                  <div className={styles.sectionBody}>
                    {[
                      { type: "Lakehouse", name: "ml_lakehouse", desc: "Central lakehouse for features, models, and predictions" },
                      { type: "Notebook", name: "01_bronze_ingest", desc: "Ingest raw data into Bronze Delta tables" },
                      { type: "Notebook", name: "02_silver_transform", desc: "Clean, validate, enrich into Silver tables" },
                      { type: "Notebook", name: "03_feature_engineering", desc: "Aggregate data into daily ML feature vectors" },
                      { type: "Notebook", name: "04_model_training", desc: "Train SynapseML LightGBM model" },
                      { type: "Notebook", name: "05_model_evaluation", desc: "Confusion matrix, feature importance, detailed metrics" },
                      { type: "Notebook", name: "06_batch_scoring", desc: "Score all entities with risk levels (critical/high/medium/low)" },
                      { type: "SemanticModel", name: "predictions_model", desc: "Semantic model with prediction measures and risk KPIs" },
                      { type: "Report", name: "predictions_report", desc: "Power BI dashboard: Risk Overview, Drilldown, Feature Importance" },
                    ].map((item, i, arr) => (
                      <div key={i} className={i < arr.length - 1 ? styles.itemRow : styles.itemRowLast}>
                        <div className={styles.itemLeft}>
                          <span className={styles.itemIconWrap}>
                            <FabricItemIcon type={item.type} size={20} />
                          </span>
                          <div>
                            <Text weight="medium" size={300}>{item.name}</Text>
                            <div><Caption1>{item.desc}</Caption1></div>
                          </div>
                        </div>
                        <Badge appearance="tint" size="small" color="informative">{item.type}</Badge>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Sample Data — uses demo's actual data */}
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

                {/* ML Pipeline Details */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <BrainCircuit24Regular fontSize={16} /> ML Pipeline
                  </div>
                  <div className={styles.sectionBody}>
                    {id === "manufacturing-qc" && (
                      <>
                        <div style={{ padding: "8px 0" }}>
                          <Text weight="medium" size={300}>Target Variable</Text>
                          <div><Caption1>needs_maintenance: binary flag (1 = daily downtime &gt; 60 min, indicating maintenance required)</Caption1></div>
                        </div>
                        <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                          <Text weight="medium" size={300}>Features (25 total)</Text>
                          <div><Caption1>Sensor stats (temp, pressure, vibration, humidity: mean/std/max/range), anomaly ratios, production metrics (units, defects, yield), equipment age, production line, machine type</Caption1></div>
                        </div>
                        <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                          <Text weight="medium" size={300}>Model</Text>
                          <div><Caption1>SynapseML LightGBM Classifier: 200 iterations, 0.05 learning rate, class imbalance handling. Outputs probability and risk level (critical/high/medium/low).</Caption1></div>
                        </div>
                      </>
                    )}
                    {id === "retail-sales" && (
                      <>
                        <div style={{ padding: "8px 0" }}>
                          <Text weight="medium" size={300}>Target Variable</Text>
                          <div><Caption1>daily_quantity: continuous (units sold per store-product per day)</Caption1></div>
                        </div>
                        <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                          <Text weight="medium" size={300}>Features (18 total)</Text>
                          <div><Caption1>Transaction count, avg price/discount, calendar (day of week, month, weekend), lag features (1-day, 7-day demand), product category/subcategory, store region/format, margin</Caption1></div>
                        </div>
                        <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                          <Text weight="medium" size={300}>Model</Text>
                          <div><Caption1>SynapseML LightGBM Regressor: 200 iterations, 0.05 learning rate. Outputs predicted demand and a demand signal (high/stable/low).</Caption1></div>
                        </div>
                      </>
                    )}
                    {id === "energy-grid" && (
                      <>
                        <div style={{ padding: "8px 0" }}>
                          <Text weight="medium" size={300}>Target Variable</Text>
                          <div><Caption1>had_outage: binary flag (1 = outage/surge/sag event at substation that day)</Caption1></div>
                        </div>
                        <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                          <Text weight="medium" size={300}>Features (19 total)</Text>
                          <div><Caption1>Voltage stats (avg/std/min/max/range/deviation from 230V), frequency (avg/std/deviation from 50Hz), power factor, load, temperature, reading count, calendar (day of week, month), region</Caption1></div>
                        </div>
                        <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                          <Text weight="medium" size={300}>Model</Text>
                          <div><Caption1>SynapseML LightGBM Classifier: 200 iterations, 0.05 learning rate, class imbalance handling. Outputs outage probability and risk level (critical/high/medium/low).</Caption1></div>
                        </div>
                      </>
                    )}
                    <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                      <Text weight="medium" size={300}>Gold Tables</Text>
                      <div><Caption1>gold_ml_features, gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary</Caption1></div>
                    </div>
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
                      <div key={i} className={styles.prereq}>• {p}</div>
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
              {showDeploy && (!isCustomMode || !!selectedScenario) && !deploying && !completed && !error && !(!!jobIdParam && !!error) && (
                <div>
                  {/* Selected scenario chip */}
                  {selectedScenario && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 6, marginBottom: 16, border: "1px solid #238636", backgroundColor: "#0d2310" }}>
                      {(() => { const Icon = SCENARIO_ICON[selectedScenario.id] ?? Sparkle24Regular; return <Icon fontSize={18} color="#3fb68b" aria-hidden />; })()}
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
                      placeholder={isCustomMode
                        ? `${demo.industry} - Custom - ${selectedScenario?.title ?? demo.title}`
                        : `${demo.industry} - Standard`}
                      style={{ width: "100%" }}
                    />
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>Capacity</label>
                    {!account ? (
                      <Caption1 style={{ display: "block", color: "#8b949e", padding: "6px 0" }}>
                        Sign in to choose a capacity.
                      </Caption1>
                    ) : loadingCapacities ? (
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
                            {cap.displayName} ({cap.sku}){cap.isTrial ? " · Trial" : ""}
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
                      <div className={styles.azureSectionTitle}>{selectedScenario?.id === "external-data-integration" ? "Azure Resources (SQL Database)" : "Azure Resources (ADLS Gen2)"}</div>

                      {/* Subscription */}
                      <div style={{ marginBottom: 10 }}>
                        <label className={styles.formLabel}>Subscription</label>
                        {loadingSubs ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}><Spinner size="tiny" /><Caption1>Loading…</Caption1></div>
                        ) : azureSubs.length > 0 ? (
                          <Select value={selectedSub} onChange={(_, data) => setSelectedSub(data.value)} style={{ width: "100%" }}>
                            <option value="">Select…</option>
                            {azureSubs.map((s) => (
                              <option key={s.id} value={s.id}>{s.displayName}</option>
                            ))}
                          </Select>
                        ) : (
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            <Caption1 style={{ color: "#f85149" }}>{subscriptionsError || "No subscriptions found. Check sign-in."}</Caption1>
                            <Button size="small" appearance="subtle" onClick={() => { void loadAzureSubscriptions(true); }}>
                              Retry Azure sign-in
                            </Button>
                          </div>
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
                              <option value="">Select or type a name…</option>
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

                      {/* Storage Account Name (not used by the mirroring scenario) */}
                      {selectedScenario?.id !== "external-data-integration" && (
                      <div style={{ marginBottom: 10 }}>
                        <label className={styles.formLabel}>
                          Storage Account <Caption1 style={{ color: "#484f58" }}>(optional, auto-generated if blank)</Caption1>
                        </label>
                        <Input
                          value={storAcctName}
                          onChange={(_, data) => setStorAcctName(data.value)}
                          placeholder="myaccount"
                          style={{ width: "100%" }}
                        />
                      </div>
                      )}

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
                    {account ? (
                      <Button appearance="primary" onClick={handleDeploy} style={{ flex: 1 }}>
                        Deploy
                      </Button>
                    ) : (
                      <Button appearance="primary" onClick={login} style={{ flex: 1 }}>
                        Sign in to deploy
                      </Button>
                    )}
                    <Button
                      appearance="outline"
                      onClick={() => { if (isCustomMode) router.replace(`/demos/${id}?mode=custom`); else setShowDeploy(false); }}
                    >
                      {isCustomMode ? "← Back" : "Cancel"}
                    </Button>
                  </div>
                </div>
              )}

              {(deploying || completed || !!error) && (
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
                        {(step.status === "failed" || step.status === "skipped") && step.detail && (
                          <span style={{ display: "block", fontSize: 11, opacity: 0.7, marginTop: 2 }}>
                            {step.detail}
                          </span>
                        )}
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
                      {/* Post-deploy guidance — what to show the customer next.
                          A selected scenario's own postDeploy overrides the demo default. */}
                      {(() => {
                        const nextItems = selectedScenario?.postDeploy ?? PRESENTER[id]?.postDeploy;
                        return nextItems && nextItems.length > 0 ? (
                          <div style={{ marginBottom: 12 }}>
                            <div className={styles.presenterSubhead}>What to show next</div>
                            <div className={styles.nextList}>
                              {nextItems.map((n, i) => (
                                <div key={i} className={styles.nextItem}>
                                  <span className={styles.nextDot} />
                                  <div>
                                    <div className={styles.nextLabel}>{n.label}</div>
                                    <div className={styles.nextDetail}>{n.detail}</div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null;
                      })()}
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
                      {deployedWorkspaceId && !cleaned && selectedScenario?.id === "external-data-integration" && (
                        <Caption1 style={{ display: "block", color: "#8b949e", marginBottom: 8 }}>
                          Deleting the workspace also removes the provisioned Azure SQL server.
                        </Caption1>
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

                  {error && (() => {
                    const friendly = explainError(error);
                    return (
                      <div style={{ marginTop: 16 }}>
                        <Divider style={{ marginBottom: 16 }} />
                        <MessageBar intent="error" style={{ marginBottom: 12 }}>
                          <MessageBarBody>
                            <MessageBarTitle>{friendly.title}</MessageBarTitle>
                            {friendly.guidance}
                          </MessageBarBody>
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
                        {friendly.retryable && !deployedWorkspaceId && (
                          <Button
                            appearance="primary"
                            onClick={handleDeploy}
                            style={{ width: "100%", marginBottom: 8 }}
                          >
                            Retry deployment
                          </Button>
                        )}
                        <Button
                          appearance="subtle"
                          onClick={resetState}
                          style={{ width: "100%" }}
                        >
                          Start over
                        </Button>
                      </div>
                    );
                  })()}
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
