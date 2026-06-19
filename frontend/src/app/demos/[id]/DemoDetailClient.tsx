"use client";

import { useParams, useSearchParams, useRouter } from "next/navigation";
import { Fragment, useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/AuthProvider";
import { oneLakeScopes } from "@/lib/msal";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { industries } from "@/lib/industryCatalog";
import {
  fetchSubscriptions, fetchResourceGroups, fetchLocations, fetchDatasetPreview,
  startLiveStream, stopLiveStream, getStreamStatus,
} from "@/lib/api";
import type { ScenarioInfo, AzureSubscription, AzureResourceGroup, AzureLocation, DatasetPreview, StreamSession } from "@/lib/api";
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
  MessageBarActions,
  MessageBarTitle,
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
  BrainCircuit24Regular,
  Database24Regular,
  DatabaseArrowRight24Regular,
  Sparkle24Regular,
  FlashRegular,
  Bot24Regular,
} from "@fluentui/react-icons";
import type { FluentIcon } from "@fluentui/react-icons";
import { DEMOS } from "@/lib/demoCatalog";
import { PRESENTER } from "@/lib/presenterContent";
import { explainError } from "@/lib/errorHelp";

// Coerce an SSE error payload's `message` into a readable string. The backend
// usually sends a string, but some failure paths send a nested object (e.g.
// {detail: "..."} or an ARM error), which would otherwise render as
// "[object Object]" in the UI.
function coerceErrorMessage(message: unknown, fallback = "Deployment failed"): string {
  if (typeof message === "string" && message.trim()) return message;
  if (message && typeof message === "object") {
    const o = message as Record<string, unknown>;
    const nested = o.message ?? o.detail ?? o.error ?? o.title;
    if (typeof nested === "string" && nested.trim()) return nested;
    try {
      const j = JSON.stringify(message);
      if (j && j !== "{}") return j;
    } catch { /* fall through */ }
  }
  return fallback;
}

// Universal scenarios — identical across all industries (IDs match backend _scenarios/)
const ALL_SCENARIOS: ScenarioInfo[] = [
  {
    id: "data-virtualization-batch",
    title: "Data Virtualization & Batch Analytics (Shortcuts)",
    description: "Provision ADLS Gen2, connect external data in-place via Fabric Shortcuts, then process through Bronze→Silver→Gold medallion layers orchestrated with Data Factory pipelines.",
    estimatedTime: "20–30 min",
    tags: ["shortcut", "adls", "medallion", "pipeline"],
    enabled: true,
    requiresAzure: true,
    azureParams: [],
    feature: "Shortcuts",
  },
  {
    id: "real-time-intelligence",
    title: "Real-Time Intelligence",
    description: "Eventhouse + Eventstream for live data ingestion, KQL analytics, a Real-Time Dashboard, and an Activator for threshold-based alerts.",
    estimatedTime: "3–5 min",
    tags: ["eventhouse", "kql", "streaming", "activator"],
    enabled: true,
    requiresAzure: false,
    azureParams: [],
    feature: "RTI",
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
    description: "Provision an Azure SQL Database, seed it with operational data, then mirror it into Fabric OneLake. Live, zero-ETL replication you can watch happen.",
    estimatedTime: "15–25 min",
    tags: ["mirroring", "azure-sql", "zero-etl", "replication"],
    enabled: true,
    requiresAzure: true,
    azureParams: [],
    feature: "Mirroring",
  },
  {
    id: "genai-applications",
    title: "Fabric IQ",
    description: "Showcase Fabric IQ: build a semantic ontology over your data, expose it through Fabric Data Agents, and explore relationships with the knowledge graph for natural-language, context-aware analytics.",
    estimatedTime: "15–20 min",
    tags: ["fabric-iq", "ontology", "data-agent", "knowledge-graph"],
    enabled: false,
    requiresAzure: false,
    azureParams: [],
    feature: "Fabric IQ",
  },
  {
    id: "fabric-foundry-agent",
    title: "Fabric & Foundry AI Agent",
    description: "Deploy a Fabric data foundation, publish a Fabric data agent over it, then provision a Microsoft Foundry agent grounded on that data — data + AI in one click. (Preview: provisions billable Azure Foundry resources in your subscription.)",
    estimatedTime: "20–30 min",
    tags: ["foundry", "ai-agent", "data-agent", "rag", "preview"],
    enabled: false,
    requiresAzure: true,
    azureParams: [],
    feature: "Foundry AI Agent",
  },
];

// Professional Fluent System icons per scenario (replaces emoji).
const SCENARIO_ICON: Record<string, FluentIcon> = {
  "data-virtualization-batch": DatabaseLink24Regular,
  "real-time-intelligence": Pulse24Regular,
  "ai-ml": BrainCircuit24Regular,
  "data-warehouse": Database24Regular,
  "external-data-integration": DatabaseArrowRight24Regular,
  "genai-applications": Sparkle24Regular,
  "fabric-foundry-agent": Bot24Regular,
};

const SCENARIO_FEATURES = [
  "RTI",
  "Fabric IQ",
  "Fabric Data Agents",
  "Foundry AI Agent",
  "Power BI",
  "Machine Learning",
  "Shortcuts",
  "Mirroring",
];

type DeployStep = {
  name: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  detail?: string | null;
  itemId?: string;
};

type SampleDataItem = {
  fileName: string;
  description: string;
  format: string;
  rows: number;
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
    Eventstream: "dataflow_gen2_24_item.svg",
    KQLQueryset: "kql_database_24_item.svg",
    Reflex: "bolt.svg",
    Connection: "dataflow_gen2_24_item.svg",
    Shortcut: "lakehouse_24_item.svg",
  };
  const file = FILE_MAP[type];
  if (!file) return <span style={{ fontSize: size * 0.65, color: "#8b949e", fontWeight: 700, lineHeight: 1 }}>{type.charAt(0)}</span>;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={`/icons/${file}`} alt={type} width={size} height={size} style={{ objectFit: "contain" }} />;
}

const LAYER_COLORS = ["#3fb68b", "#238636", "#196c2e"];

// Per-sector AI/ML pipeline details, shown in the "ML Pipeline" section of the
// AI & Machine Learning scenario. Target variables and feature counts are taken
// from each sector's actual ML notebooks (notebooks/ml/02_model_training), so
// every industry shows consistent, accurate detail instead of a sparse section.
const ML_DETAILS: Record<string, { target: string; featureCount: string; features: string; model: string }> = {
  "manufacturing-qc": {
    target: "needs_maintenance: binary flag (1 = daily downtime > 60 min, indicating maintenance required)",
    featureCount: "(25 total)",
    features: "Sensor stats (temp, pressure, vibration, humidity: mean/std/max/range), anomaly ratios, production metrics (units, defects, yield), equipment age, production line, machine type",
    model: "SynapseML LightGBM Classifier: 200 iterations, 0.05 learning rate, class imbalance handling. Outputs probability and risk level (critical/high/medium/low).",
  },
  "retail-sales": {
    target: "daily_quantity: continuous (units sold per store-product per day)",
    featureCount: "(18 total)",
    features: "Transaction count, avg price/discount, calendar (day of week, month, weekend), lag features (1-day, 7-day demand), product category/subcategory, store region/format, margin",
    model: "SynapseML LightGBM Regressor: 200 iterations, 0.05 learning rate. Outputs predicted demand and a demand signal (high/stable/low).",
  },
  "energy-grid": {
    target: "had_outage: binary flag (1 = outage/surge/sag event at substation that day)",
    featureCount: "(19 total)",
    features: "Voltage stats (avg/std/min/max/range/deviation from 230V), frequency (avg/std/deviation from 50Hz), power factor, load, temperature, reading count, calendar (day of week, month), region",
    model: "SynapseML LightGBM Classifier: 200 iterations, 0.05 learning rate, class imbalance handling. Outputs outage probability and risk level (critical/high/medium/low).",
  },
  healthcare: {
    target: "is_readmission: binary flag (1 = patient readmitted)",
    featureCount: "(12 total)",
    features: "Length of stay, prior admissions, admission hour, vital-sign counts/ratios/averages, department, admission type, insurance type, age group, diagnosis chapter",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs a readmission probability and risk level (high/medium/low).",
  },
  "financial-services": {
    target: "is_flagged_fraud: binary flag (1 = transaction flagged as fraud)",
    featureCount: "(18 total)",
    features: "Amount (+log), transaction hour, night/international/high-value flags, balance, credit limit & utilisation, transaction type, merchant category, channel, country, account type, age group, segment, region, risk tier",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs a fraud probability and risk level (high/medium/low).",
  },
  technology: {
    target: "is_churned: binary flag (1 = account churned)",
    featureCount: "(17 total)",
    features: "MRR, seat count, tenure, health score, user & active-user counts, avg logins (30d), event count, distinct features used, avg session duration, support ticket & SLA-breach counts, avg CSAT & resolution hours, plan, industry, region",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs a churn probability and risk level (high/medium/low).",
  },
  transportation: {
    target: "is_late: binary flag (1 = delivery arrived late)",
    featureCount: "(15 total)",
    features: "Planned duration, distance, load tonnes & utilisation, SLA hours, toll cost, vehicle capacity & age, departure hour/day, weekend/rush flags, vehicle type, depot, route type",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs a late-delivery probability and risk level (high/medium/low).",
  },
  hospitality: {
    target: "is_cancelled: binary flag (1 = booking cancelled)",
    featureCount: "(15 total)",
    features: "Nights, room rate, lead time, refundable flag, total stays & spend, star rating, room count, room type, channel, meal plan, loyalty tier, region, age group, property type",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs a cancellation probability and risk level (high/medium/low).",
  },
  media: {
    target: "is_completed: binary flag (1 = content watched to completion)",
    featureCount: "(14 total)",
    features: "Duration, release year, monthly fee, view hour/day, weekend flag, genre, content type, production-cost bucket, language, plan type, region, age group, device type",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs a completion probability and engagement signal (high/medium/low).",
  },
  "professional-services": {
    target: "is_over_budget: binary flag (1 = engagement over budget)",
    featureCount: "(13 total)",
    features: "Budget, headcount, planned duration, contract value, relationship years, NPS, lead consultant experience & daily rate, practice, industry, tier, region, lead grade",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs an over-budget probability and risk level (high/medium/low).",
  },
  construction: {
    target: "is_delayed: binary flag (1 = task delayed)",
    featureCount: "(9 total)",
    features: "Planned duration, budget, subcontractor rating/years/accreditation, task name, project type, project region, subcontractor trade",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs a delay probability and risk level (high/medium/low).",
  },
  education: {
    target: "is_withdrawn: binary flag (1 = student withdrew)",
    featureCount: "(11 total)",
    features: "Credits, age at enrolment, average score, pass rate, assessment count, cohort year, department, level, programme, gender, region",
    model: "LightGBM + RandomForest classifiers (MLflow-tracked). Outputs a withdrawal probability and risk level (high/medium/low).",
  },
};

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
    // Single continuous pipeline: never wrap (a wrapped box leaves a connector
    // arrow dangling at a row edge). Scroll horizontally on narrow widths instead.
    flexWrap: "nowrap" as const,
    overflowX: "auto" as const,
  },
  flowBox: {
    borderRadius: "6px",
    paddingLeft: "16px",
    paddingRight: "16px",
    paddingTop: "12px",
    paddingBottom: "12px",
    minWidth: "132px",
    flexShrink: 0,
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
    flexShrink: 0,
  },
  flowGroupLabel: {
    fontSize: "10px",
    fontWeight: 700,
    color: "#8b949e",
    letterSpacing: "0.8px",
    textTransform: "uppercase" as const,
    marginBottom: "8px",
  },
  flowSubRow: {
    display: "flex",
    alignItems: "center",
    // Single continuous pipeline row — scroll instead of wrapping so connector
    // arrows never dangle at a row edge.
    flexWrap: "nowrap" as const,
    overflowX: "auto" as const,
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
    flex: 1,
    minWidth: 0,
  },
  dataRight: {
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: "12px",
    flexShrink: 0,
  },
  previewPanel: {
    paddingLeft: "20px",
    paddingRight: "20px",
    paddingBottom: "18px",
    backgroundColor: "#0d1117",
  },
  previewStatus: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    paddingTop: "14px",
    color: "#8b949e",
  },
  previewMeta: {
    paddingTop: "12px",
    paddingBottom: "8px",
    color: "#8b949e",
  },
  previewTableWrap: {
    maxHeight: "360px",
    overflow: "auto",
    border: "1px solid #30363d",
    borderRadius: "6px",
    backgroundColor: "#161b22",
  },
  previewTable: {
    width: "100%",
    minWidth: "640px",
    borderCollapse: "collapse" as const,
    fontSize: "12px",
  },
  previewTh: {
    position: "sticky" as const,
    top: 0,
    backgroundColor: "#21262d",
    color: "#e6edf3",
    fontWeight: 600,
    textAlign: "left" as const,
    padding: "8px 10px",
    borderBottom: "1px solid #30363d",
    whiteSpace: "nowrap" as const,
  },
  previewTd: {
    color: "#c9d1d9",
    padding: "8px 10px",
    borderBottom: "1px solid #21262d",
    maxWidth: "260px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
  previewEmpty: {
    padding: "14px 0 0",
    color: "#8b949e",
  },
  // ── Fullscreen preview modal ──────────────────────────────────────────────
  modalBackdrop: {
    position: "fixed" as const,
    inset: 0,
    backgroundColor: "rgba(0,0,0,0.72)",
    zIndex: 9000,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  modalPanel: {
    width: "92vw",
    height: "88vh",
    maxWidth: "1400px",
    backgroundColor: "#0d1117",
    border: "1px solid #30363d",
    borderRadius: "10px",
    display: "flex",
    flexDirection: "column" as const,
    overflow: "hidden",
  },
  modalHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "14px 20px",
    borderBottom: "1px solid #30363d",
    backgroundColor: "#161b22",
    flexShrink: 0,
  },
  modalHeaderLeft: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    minWidth: 0,
  },
  modalBody: {
    display: "flex",
    flex: 1,
    overflow: "hidden",
  },
  modalSidebar: {
    width: "220px",
    flexShrink: 0,
    borderRight: "1px solid #30363d",
    overflowY: "auto" as const,
    backgroundColor: "#0d1117",
    padding: "8px 0",
  },
  modalSidebarItem: {
    padding: "8px 16px",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column" as const,
    gap: "2px",
    ":hover": { backgroundColor: "#161b22" },
  },
  modalSidebarItemActive: {
    backgroundColor: "#1c2128",
    borderLeft: "3px solid #388bfd",
    paddingLeft: "13px",
  },
  modalMain: {
    flex: 1,
    display: "flex",
    flexDirection: "column" as const,
    overflow: "hidden",
  },
  modalMeta: {
    padding: "10px 20px",
    borderBottom: "1px solid #21262d",
    color: "#8b949e",
    flexShrink: 0,
  },
  modalTableWrap: {
    flex: 1,
    overflow: "auto",
    backgroundColor: "#161b22",
  },
  modalTable: {
    width: "100%",
    minWidth: "640px",
    borderCollapse: "collapse" as const,
    fontSize: "12px",
  },
  modalTh: {
    position: "sticky" as const,
    top: 0,
    backgroundColor: "#21262d",
    color: "#e6edf3",
    fontWeight: 600,
    textAlign: "left" as const,
    padding: "10px 12px",
    borderBottom: "1px solid #30363d",
    whiteSpace: "nowrap" as const,
    zIndex: 1,
  },
  modalTd: {
    color: "#c9d1d9",
    padding: "8px 12px",
    borderBottom: "1px solid #21262d",
    maxWidth: "300px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
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

// Renders a horizontal pipeline of labeled boxes connected by arrows. The arrow
// LEADS each box (rendered before it) and is grouped with that box, so when the
// row wraps to a new line the arrow wraps with its box — never left dangling at
// the end of a row (the old trailing-arrow layout broke on wrap).
function FlowSteps({ steps }: { steps: { label?: string; value: string; color: string }[] }) {
  const styles = useStyles();
  return (
    <>
      {steps.map((step, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
          {i > 0 && <ArrowRightRegular className={styles.flowArrow} fontSize={18} />}
          <div className={styles.flowBox} style={{ backgroundColor: step.color }}>
            {step.label && (
              <div className={styles.flowLabel} style={{ color: "rgba(255,255,255,0.7)" }}>{step.label}</div>
            )}
            <div className={styles.flowValue}>{step.value}</div>
          </div>
        </div>
      ))}
    </>
  );
}

export default function DemoDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const id = params.id as string;
  const demo = DEMOS[id];
  const isCustomMode = searchParams.get("mode") === "custom";
  const { account, authError, login, getFabricToken, getStorageToken, getManagementToken, getSearchToken, getAgentToken } = useAuth();
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
  // ── Live Eventstream replay (RTI demo) ──────────────────────────────────
  const [streamConnStr, setStreamConnStr] = useState("");
  const [streamSession, setStreamSession] = useState<StreamSession | null>(null);
  const [streamStarting, setStreamStarting] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const streamPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
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
  const [azureRegion, setAzureRegion] = useState("westus2");
  const [createRG, setCreateRG] = useState(false);
  const [loadingSubs, setLoadingSubs] = useState(false);
  const [subscriptionsError, setSubscriptionsError] = useState<string | null>(null);
  const [loadingRGs, setLoadingRGs] = useState(false);
  const [azureLocations, setAzureLocations] = useState<AzureLocation[]>([]);
  const [loadingLocations, setLoadingLocations] = useState(false);
  const FALLBACK_REGIONS: AzureLocation[] = [
    { name: "westus2", displayName: "West US 2" },
    { name: "westus3", displayName: "West US 3" },
    { name: "eastus2", displayName: "East US 2" },
    { name: "westeurope", displayName: "West Europe" },
    { name: "swedencentral", displayName: "Sweden Central" },
    { name: "germanywestcentral", displayName: "Germany West Central" },
    { name: "switzerlandnorth", displayName: "Switzerland North" },
    { name: "centralus", displayName: "Central US" },
    { name: "eastus", displayName: "East US" },
  ];
  const [previewFileName, setPreviewFileName] = useState<string | null>(null);
  const [datasetPreviews, setDatasetPreviews] = useState<Record<string, DatasetPreview>>({});
  const [previewLoadingFile, setPreviewLoadingFile] = useState<string | null>(null);
  const [previewErrors, setPreviewErrors] = useState<Record<string, string>>({});

  // Validate an optional, user-supplied Azure Storage account name against the
  // Azure naming rules (3–24 chars, lowercase letters + digits only, globally
  // unique). Returns an error string, or null when valid/blank (blank = auto-gen).
  const storAcctNameError: string | null = (() => {
    const v = storAcctName.trim();
    if (!v) return null; // blank → backend auto-generates a valid name
    if (v.length < 3 || v.length > 24) return "Must be 3–24 characters.";
    if (!/^[a-z0-9]+$/.test(v)) return "Only lowercase letters (a–z) and numbers (0–9) — no spaces, hyphens, or uppercase.";
    return null;
  })();

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

  // Fetch the subscription's available Azure regions for the region picker
  useEffect(() => {
    if (!selectedSub || !account) return;
    setLoadingLocations(true);
    stableGetManagementToken({ interactive: false })
      .then((tok) => fetchLocations(tok, selectedSub))
      .then(setAzureLocations)
      .catch(() => {})
      .finally(() => setLoadingLocations(false));
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
                  setError(coerceErrorMessage(data.message));
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

  // These hooks must run unconditionally (before the `!demo` early return) to
  // satisfy the rules of hooks. They only depend on top-level state/refs.
  const handleStopStream = useCallback(async () => {
    if (streamPollRef.current) {
      clearInterval(streamPollRef.current);
      streamPollRef.current = null;
    }
    const sid = streamSession?.sessionId;
    if (sid) {
      try {
        await stopLiveStream(sid);
      } catch {
        /* best effort */
      }
      setStreamSession((prev) => (prev ? { ...prev, running: false } : prev));
    }
  }, [streamSession]);

  // Clean up the poll timer on unmount
  useEffect(() => {
    return () => {
      if (streamPollRef.current) clearInterval(streamPollRef.current);
    };
  }, []);

  // Close preview modal on ESC
  useEffect(() => {
    if (!previewFileName) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setPreviewFileName(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [previewFileName]);

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
    // Guard: never POST a deploy with required fields missing (would send an
    // undefined capacity/subscription to the backend). The Deploy button is
    // also disabled in these cases — this is defense in depth.
    if (!selectedCapacity) {
      setError("Select a Fabric capacity before deploying.");
      return;
    }
    if (selectedScenario?.requiresAzure && (!selectedSub || !selectedRG)) {
      setError("Select an Azure subscription and resource group for this scenario before deploying.");
      return;
    }
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
      // Fabric + Foundry scenario also needs Azure AI Search + Foundry agent
      // data-plane tokens so the deploy can build the Foundry IQ knowledge base
      // and the grounded agent. Best-effort: the backend degrades those steps to
      // manual follow-ups if a token is missing.
      if (selectedScenario?.id === "fabric-foundry-agent") {
        try {
          const searchTok = await getSearchToken({ allowRedirect: false });
          if (searchTok) headers["X-Search-Token"] = searchTok;
        } catch { /* continue — knowledge base becomes a manual step */ }
        try {
          const agentTok = await getAgentToken({ allowRedirect: false });
          if (agentTok) headers["X-Agent-Token"] = agentTok;
        } catch { /* continue — agent becomes a manual step */ }
      }

      // Note: the historical data seed (optional) uses the Eventhouse/KQL data
      // plane, whose audience (kusto.fabric.microsoft.com) isn't registered in
      // every tenant. We deliberately do NOT request that scope here (it breaks
      // sign-in with AADSTS500011). The table is created via the Fabric API and
      // the live Eventstream is the primary data source; in local dev the backend
      // falls back to an az CLI Kusto token to perform the seed.

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
          azure_location: azureRegion || "westus2",
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

      // Step 2: Stream progress from the job's SSE endpoint.
      //
      // The deploy runs as a decoupled background job on the server, and the
      // stream endpoint replays all past events before tailing live updates.
      // So if the connection drops mid-deploy (a transient network blip, proxy
      // idle timeout, Wi-Fi/VPN switch, laptop sleep, etc.) we simply reconnect
      // and resume — the replay re-syncs the UI — instead of failing the whole
      // deploy with a scary "network error" while the job is still running.
      // Only a server-sent "error" event or the "done" event is terminal.
      const decoder = new TextDecoder();
      let streamHadError = false;
      let sawDone = false;
      let connectionLost = false;
      let reconnectAttempts = 0;
      const MAX_RECONNECTS = 150; // consecutive failures (reset whenever data arrives)

      while (!sawDone && !streamHadError) {
        let streamResp: Response;
        try {
          streamResp = await fetch(`${API}/api/jobs/${job_id}/stream`, {
            headers: fabricToken ? { Authorization: `Bearer ${fabricToken}` } : {},
            signal: controller.signal,
          });
        } catch {
          if (controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
          if (++reconnectAttempts > MAX_RECONNECTS) { connectionLost = true; break; }
          await new Promise((r) => setTimeout(r, 2000));
          continue;
        }

        if (streamResp.status === 404) {
          // Job no longer exists server-side — nothing left to resume.
          connectionLost = true;
          break;
        }
        if (!streamResp.ok || !streamResp.body) {
          if (++reconnectAttempts > MAX_RECONNECTS) { connectionLost = true; break; }
          await new Promise((r) => setTimeout(r, 2000));
          continue;
        }

        const reader = streamResp.body.getReader();
        let buffer = "";
        let currentEvent = "";
        let gotData = false;

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            gotData = true;
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
                    setError(coerceErrorMessage(data.message));
                    if (data.workspaceId) setDeployedWorkspaceId(data.workspaceId);
                  }
                } catch {
                  // ignore malformed data lines
                }
                currentEvent = "";
              }
            }

            if (sawDone || streamHadError) break;
          }
        } catch {
          // Mid-stream read failure = dropped connection. Fall through to
          // reconnect (the server replays past events so the UI re-syncs).
          if (controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
        }

        if (sawDone || streamHadError) break;
        // Stream ended/dropped before the deploy finished — reconnect & resume.
        if (gotData) reconnectAttempts = 0;
        if (++reconnectAttempts > MAX_RECONNECTS) { connectionLost = true; break; }
        await new Promise((r) => setTimeout(r, 1500));
      }

      if (sawDone) {
        setCompleted(true);
      } else if (streamHadError) {
        // Error already surfaced via setError from the "error" event.
      } else if (connectionLost) {
        setError("Lost connection to the deployment server after several retries. The deploy may still be running — check the Monitoring page.");
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

  const handleStartStream = async () => {
    const conn = streamConnStr.trim();
    if (!conn) {
      setStreamError("Paste the custom endpoint connection string from the Fabric portal.");
      return;
    }
    setStreamError(null);
    setStreamStarting(true);
    try {
      const session = await startLiveStream({
        demoId: id,
        scenarioId: "real-time-intelligence",
        connectionString: conn,
      });
      setStreamSession(session);
      // Poll status so the UI shows live "events sent" and surfaces errors
      if (streamPollRef.current) clearInterval(streamPollRef.current);
      streamPollRef.current = setInterval(async () => {
        try {
          const s = await getStreamStatus(session.sessionId);
          setStreamSession(s);
          if (!s.running && streamPollRef.current) {
            clearInterval(streamPollRef.current);
            streamPollRef.current = null;
            if (s.error) setStreamError(s.error);
          }
        } catch {
          /* ignore transient poll errors */
        }
      }, 2000);
    } catch (e: unknown) {
      setStreamError(e instanceof Error ? e.message : "Failed to start live stream");
    } finally {
      setStreamStarting(false);
    }
  };

  const resetState = () => {
    setShowDeploy(true);
    setDeploying(false);
    setCompleted(false);
    setSteps([]);
    setError(null);
    setDeployedWorkspaceId("");
    setCleaned(false);
    handleStopStream();
    setStreamConnStr("");
    setStreamSession(null);
    setStreamError(null);
    router.replace(`/demos/${id}?mode=custom`);
    setSelectedSub("");
    setSelectedRG("");
    setStorAcctName("");
    setAzureRegion("westus2");
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
        if (caps.length > 0) setSelectedCapacity((prev) => prev || caps[0].id);
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

  const handlePreviewDataset = async (fileName: string) => {
    if (previewFileName === fileName) {
      setPreviewFileName(null);
      return;
    }

    setPreviewFileName(fileName);
    if (datasetPreviews[fileName]) return;

    setPreviewLoadingFile(fileName);
    setPreviewErrors((prev) => {
      const next = { ...prev };
      delete next[fileName];
      return next;
    });

    try {
      const preview = await fetchDatasetPreview(id, fileName);
      setDatasetPreviews((prev) => ({ ...prev, [fileName]: preview }));
    } catch (e) {
      setPreviewErrors((prev) => ({
        ...prev,
        [fileName]: e instanceof Error ? e.message : "Could not load preview",
      }));
    } finally {
      setPreviewLoadingFile((current) => (current === fileName ? null : current));
    }
  };

  const renderSampleDataSection = (items: SampleDataItem[] = demo.sampleData) => (
    <div className={styles.section}>
      <div className={styles.sectionHeader}>
        <TableRegular fontSize={16} /> Sample Data
      </div>
      <div className={styles.sectionBody}>
        {items.map((dataset, index) => {
          const loading = previewLoadingFile === dataset.fileName;
          return (
            <div
              key={dataset.fileName}
              className={styles.dataRow}
              style={index === items.length - 1 ? { borderBottom: "none" } : undefined}
            >
              <div className={styles.dataLeft}>
                <Badge appearance="tint" color="severe" size="small">{dataset.format}</Badge>
                <div style={{ minWidth: 0 }}>
                  <Text weight="medium" size={200}>{dataset.fileName}</Text>
                  <div><Caption1>{dataset.description}</Caption1></div>
                </div>
              </div>
              <div className={styles.dataRight}>
                <Caption1 style={{ fontVariantNumeric: "tabular-nums" }}>{dataset.rows.toLocaleString()} rows</Caption1>
                <Button
                  appearance="subtle"
                  size="small"
                  icon={loading ? <Spinner size="extra-tiny" /> : <TableRegular />}
                  onClick={() => void handlePreviewDataset(dataset.fileName)}
                >
                  Preview
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <>
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
                    .slice()
                    .sort((a, b) => Number(b.enabled) - Number(a.enabled))
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
                  <div style={{ padding: "20px" }}>
                    {/* Row 1: Ingest layer */}
                    <div className={styles.flowGroupLabel}>Ingest</div>
                    <div className={styles.flowSubRow} style={{ marginBottom: 16 }}>
                      <FlowSteps steps={[
                        { label: "Source", value: "CSV Files", color: "#1f6feb" },
                        { label: "Azure", value: "ADLS Gen2", color: "#1f6feb" },
                        { label: "Shortcut", value: "Virtual Link", color: "#8957e5" },
                        { label: "Lakehouse", value: "Delta Tables", color: "#3fb68b" },
                      ]} />
                    </div>
                    {/* Row 2: Analyze + Serve layer */}
                    <div className={styles.flowGroupLabel}>Analyze &amp; Serve</div>
                    <div className={styles.flowSubRow}>
                      <FlowSteps steps={[
                        { label: "Notebooks", value: "Bronze→Gold", color: "#238636" },
                        { label: "Semantic Model", value: "Direct Lake", color: "#bb8009" },
                        { label: "Power BI", value: "Reports", color: "#da3633" },
                      ]} />
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
                {renderSampleDataSection()}
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
                      Zero-ETL: an operational Azure SQL database mirrored live into Fabric OneLake, with no pipeline, schedule, or code. The deploy already set everything up, so your job is to <strong style={{ color: "#e6edf3" }}>show it</strong>.
                    </div>

                    <div>
                      <div className={styles.presenterSubhead}>Talking points</div>
                      <ul className={styles.pointList}>
                        <li className={styles.pointItem}>Azure SQL stands in for an operational POS/ERP system; the data lives outside Fabric.</li>
                        <li className={styles.pointItem}>Mirroring replicates it into OneLake as Delta tables automatically. No copy job to build or maintain.</li>
                        <li className={styles.pointItem}>Replicated tables are queryable instantly with Spark, T-SQL, and Direct Lake.</li>
                        <li className={styles.pointItem}>Entra-only auth (no SQL passwords) via the workspace identity. Enterprise-ready.</li>
                      </ul>
                    </div>

                    <div>
                      <div className={styles.presenterSubhead}>Suggested demo flow</div>
                      <div className={styles.flowList}>
                        {[
                          { step: "Show replication is live", detail: "Open the mirrored database, then Monitor replication. Its tables show Replicating with row counts." },
                          { step: "Query with zero ETL", detail: "Run 01_explore_mirrored. It reads the replicated tables from OneLake and joins them. No copy, no transform." },
                          { step: "The wow moment", detail: "In 02_live_change, UPDATE a price in Azure SQL and watch the Fabric copy catch up in seconds. Then insert a new sale and watch it land." },
                          { step: "Land the message", detail: "Nothing moved that data except Fabric Mirroring itself. No pipeline, no refresh, no code." },
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
                        <li className={styles.pointItem}>Keep the Fabric capacity running; replication stalls if it is paused.</li>
                        <li className={styles.pointItem}>If a table shows 0 rows just after deploy, wait 2-3 minutes for the initial snapshot.</li>
                        <li className={styles.pointItem}>00_seed_sql already ran; 01 and 02 are left for you to run live.</li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Mirroring-specific data flow — 2-row labeled pipeline */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <ArrowRightRegular fontSize={16} /> Data Flow
                  </div>
                  <div style={{ padding: "20px" }}>
                    {/* Row 1: Replicate layer */}
                    <div className={styles.flowGroupLabel}>Replicate (zero-ETL)</div>
                    <div className={styles.flowSubRow} style={{ marginBottom: 16 }}>
                      <FlowSteps steps={[
                        { label: "Source", value: "CSV Files", color: "#1f6feb" },
                        { label: "Azure SQL", value: "Operational DB", color: "#1f6feb" },
                        { label: "Mirroring", value: "Live Replication", color: "#8957e5" },
                        { label: "OneLake", value: "Delta Tables", color: "#3fb68b" },
                      ]} />
                    </div>
                    {/* Row 2: Explore + Prove layer */}
                    <div className={styles.flowGroupLabel}>Explore &amp; Prove</div>
                    <div className={styles.flowSubRow}>
                      <FlowSteps steps={[
                        { label: "Notebooks", value: "Spark on OneLake", color: "#238636" },
                        { label: "Live Change", value: "Watch It Sync", color: "#bb8009" },
                      ]} />
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
                      { type: "MirroredDatabase", name: "Mirrored database", description: "Live, continuously replicated copy of the Azure SQL database in OneLake" },
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
                {renderSampleDataSection()}
              </>
            )}

            {/* === CUSTOM MODE: Real-Time Intelligence scenario selected === */}
            {isCustomMode && selectedScenario?.id === "real-time-intelligence" && (
              <>
                {/* RTI data flow diagram */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <ArrowRightRegular fontSize={16} /> Data Flow
                  </div>
                  <div style={{ padding: "16px 20px" }}>
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#8b949e", letterSpacing: "0.8px", textTransform: "uppercase", marginBottom: 8 }}>Ingest</div>
                    <div style={{ display: "flex", alignItems: "center", marginBottom: 16, flexWrap: "nowrap" }}>
                      {[
                        { label: "Source", value: "CSV / Stream", color: "#1f3a5c" },
                        { label: "Eventstream", value: "Live Ingestion", color: "#1a3d6e" },
                        { label: "Eventhouse", value: "KQL Storage", color: "#1a4a5c" },
                        { label: "KQL DB", value: "Auto-Created", color: "#1a3d4a" },
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
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#8b949e", letterSpacing: "0.8px", textTransform: "uppercase", marginBottom: 8 }}>Analyze &amp; Act</div>
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "nowrap" }}>
                      {[
                        { label: "KQL Queryset", value: "Analytics", color: "#1a4a3d" },
                        { label: "Dashboard", value: "Live Tiles", color: "#2d4a1a" },
                        { label: "Activator", value: "Alert Rules", color: "#4a3d1a" },
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

                {/* What Gets Created — RTI items */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <DatabaseRegular fontSize={16} /> What Gets Created
                  </div>
                  <div className={styles.sectionBody}>
                    {(() => {
                      const sid = id.replace(/-/g, '_');
                      return [
                        { type: "Workspace",    name: "New Fabric Workspace",              description: "Dedicated workspace for this deployment" },
                        { type: "Eventhouse",   name: sid,                                 description: "KQL-native storage engine for real-time analytics" },
                        { type: "KQLDatabase",  name: sid,                                  description: "Default KQL database (auto-created by the Eventhouse), seeded with sample data" },
                        { type: "Eventstream",  name: `${sid}_eventstream`,                description: "Custom endpoint → Eventhouse pipeline for live streaming (push your data after deploy)" },
                        { type: "KQLQueryset",  name: `${sid}_kql_queries`,                description: "Saved KQL queries for analytics and exploration" },
                        { type: "KQLDashboard", name: `${sid}_realtime_dashboard`,         description: "Real-time dashboard with auto-refreshing KQL tiles" },
                        { type: "Reflex",       name: `${sid}_activator`,                  description: "Activator item — add an alert rule yourself via 'Set alert' on a dashboard tile or queryset" },
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
                    ));
                    })()}
                  </div>
                </div>

                {/* Sample Data — with preview support */}
                {renderSampleDataSection()}

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
                    <FlowSteps steps={demo.architecture.layers.map((layer, i) => {
                      const medalLabels = ["Bronze", "Silver", "Gold"];
                      const isMedallion = /^(Bronze|Silver|Gold)\s*\(/.test(layer);
                      const label = isMedallion ? medalLabels[i] : "";
                      const value = isMedallion
                        ? layer.replace(/^(Bronze|Silver|Gold)\s*\(/, "").replace(/\)$/, "")
                        : layer;
                      return { label, value, color: LAYER_COLORS[i] ?? "#3fb68b" };
                    })} />
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
                {renderSampleDataSection()}
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
                    <FlowSteps steps={[
                      { label: "Bronze", value: "Raw Ingest", color: "#3fb68b" },
                      { label: "Silver", value: "Clean & Enrich", color: "#238636" },
                      { label: "Features", value: "ML Feature Table", color: "#1f6feb" },
                      { label: "Train", value: "LightGBM", color: "#8957e5" },
                      { label: "Score", value: "Predictions & Risk", color: "#da3633" },
                    ]} />
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
                {renderSampleDataSection()}

                {/* ML Pipeline Details */}
                <div className={styles.section}>
                  <div className={styles.sectionHeader}>
                    <BrainCircuit24Regular fontSize={16} /> ML Pipeline
                  </div>
                  <div className={styles.sectionBody}>
                    {(() => {
                      const ml = ML_DETAILS[id];
                      return (
                        <>
                          {ml && (
                            <>
                              <div style={{ padding: "8px 0" }}>
                                <Text weight="medium" size={300}>Target Variable</Text>
                                <div><Caption1>{ml.target}</Caption1></div>
                              </div>
                              <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                                <Text weight="medium" size={300}>Features {ml.featureCount}</Text>
                                <div><Caption1>{ml.features}</Caption1></div>
                              </div>
                              <div style={{ padding: "8px 0", borderTop: "1px solid #21262d" }}>
                                <Text weight="medium" size={300}>Model</Text>
                                <div><Caption1>{ml.model}</Caption1></div>
                              </div>
                            </>
                          )}
                          <div style={{ padding: "8px 0", borderTop: ml ? "1px solid #21262d" : undefined }}>
                            <Text weight="medium" size={300}>Gold Tables</Text>
                            <div><Caption1>gold_ml_features, gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary</Caption1></div>
                          </div>
                        </>
                      );
                    })()}
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
              {showDeploy && (!isCustomMode || !!selectedScenario) && !deploying && !completed && !error && (
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
                      <div className={styles.azureSectionTitle}>{
                        selectedScenario?.id === "external-data-integration" ? "Azure Resources (SQL Database)"
                        : selectedScenario?.id === "fabric-foundry-agent" ? "Azure Resources (Foundry + AI Search)"
                        : "Azure Resources (ADLS Gen2)"
                      }</div>

                      {selectedScenario?.id === "fabric-foundry-agent" && (
                        <MessageBar intent="warning" style={{ marginBottom: 10 }}>
                          <MessageBarBody>
                            <strong>Preview · billable.</strong> This provisions a Microsoft Foundry account
                            (gpt-4o-mini) and a standing <strong>Azure AI Search</strong> service in your
                            subscription. Both incur Azure cost until deleted — use the cleanup button when done.
                          </MessageBarBody>
                        </MessageBar>
                      )}

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
                        <Caption1 style={{ display: "block", marginTop: 4, color: storAcctNameError ? "#f85149" : "#484f58" }}>
                          {storAcctNameError ?? "3–24 characters, lowercase letters and numbers only. Must be globally unique."}
                        </Caption1>
                      </div>
                      )}

                      {/* Azure Region */}
                      <div>
                        <label className={styles.formLabel}>Azure Region</label>
                        {loadingLocations ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}><Spinner size="tiny" /><Caption1>Loading…</Caption1></div>
                        ) : (
                          <Select value={azureRegion} onChange={(_, data) => setAzureRegion(data.value)} style={{ width: "100%" }}>
                            {(azureLocations.length > 0 ? azureLocations : FALLBACK_REGIONS).map((loc) => (
                              <option key={loc.name} value={loc.name}>{loc.displayName}</option>
                            ))}
                          </Select>
                        )}
                        <Caption1 style={{ color: "#484f58" }}>
                          Some subscriptions restrict Azure SQL in certain regions — the deploy auto-falls back to an available region if needed.
                        </Caption1>
                      </div>
                    </div>
                  )}

                  <div className={styles.buttonRow}>
                    {account ? (
                      <Button
                        appearance="primary"
                        onClick={handleDeploy}
                        disabled={
                          loadingCapacities ||
                          !selectedCapacity ||
                          !!storAcctNameError ||
                          (!!selectedScenario?.requiresAzure && (loadingSubs || !selectedSub || !selectedRG))
                        }
                        style={{ flex: 1 }}
                      >
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
                  {account && (loadingCapacities || !selectedCapacity || !!storAcctNameError || (!!selectedScenario?.requiresAzure && (!selectedSub || !selectedRG))) && (
                    <Caption1 style={{ display: "block", marginTop: 8, color: storAcctNameError ? "#f85149" : "#8b949e" }}>
                      {loadingCapacities
                        ? "Loading capacities…"
                        : !selectedCapacity
                        ? "Select a Fabric capacity to deploy."
                        : storAcctNameError
                        ? `Fix the storage account name: ${storAcctNameError}`
                        : "Select an Azure subscription and resource group to deploy."}
                    </Caption1>
                  )}
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
                      {selectedScenario?.id === "real-time-intelligence" && (
                        <Card style={{ marginBottom: 12, padding: 14, background: "#0d1117", border: "1px solid #30363d" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                            <FlashRegular fontSize={16} style={{ color: "#3fb68b" }} />
                            <Text weight="semibold" style={{ fontSize: 13 }}>Live Eventstream demo</Text>
                          </div>
                          <Caption1 style={{ display: "block", marginBottom: 10, color: "#8b949e", lineHeight: 1.5 }}>
                            In the workspace, open the Eventstream → select the{" "}
                            <strong>LiveCustomEndpoint</strong> source → <strong>Details → Keys</strong>, and copy the
                            Event Hub <strong>Connection string-primary key</strong>. Paste it below to push live data
                            into the Eventhouse so the dashboard and Activator react in real time.
                          </Caption1>
                          {!streamSession?.running ? (
                            <>
                              <Input
                                value={streamConnStr}
                                onChange={(_, d) => setStreamConnStr(d.value)}
                                placeholder="Endpoint=sb://...;SharedAccessKeyName=...;SharedAccessKey=...;EntityPath=es_..."
                                style={{ width: "100%", marginBottom: 8 }}
                                disabled={streamStarting}
                              />
                              <Button
                                appearance="primary"
                                icon={<FlashRegular />}
                                onClick={handleStartStream}
                                disabled={streamStarting || !streamConnStr.trim()}
                                style={{ width: "100%" }}
                              >
                                {streamStarting ? "Starting..." : "Start live stream"}
                              </Button>
                            </>
                          ) : (
                            <>
                              <MessageBar intent="info" style={{ marginBottom: 8 }}>
                                <MessageBarBody>
                                  Streaming live — {streamSession.sent.toLocaleString()} events sent to{" "}
                                  <strong>{streamSession.tableName}</strong>.
                                </MessageBarBody>
                              </MessageBar>
                              <Button
                                appearance="outline"
                                onClick={handleStopStream}
                                style={{ width: "100%", color: "#f85149", borderColor: "#f8514966" }}
                              >
                                Stop live stream
                              </Button>
                            </>
                          )}
                          {streamError && (
                            <Caption1 style={{ display: "block", marginTop: 8, color: "#f85149" }}>
                              {streamError}
                            </Caption1>
                          )}
                        </Card>
                      )}
                      {selectedScenario?.id === "real-time-intelligence" && (
                        <MessageBar intent="info" style={{ marginBottom: 12 }}>
                          <MessageBarBody>
                            <strong>Set up the Activator alert yourself:</strong> open the
                            real-time dashboard (or the KQL queryset), select <strong>Set alert</strong>{" "}
                            on a tile, choose a metric and threshold, and pick an action (email/Teams).
                            Fabric wires the rule into the <em>{`${id.replace(/-/g, "_")}_activator`}</em> item.
                            Alert rules can&apos;t be created reliably through the API, so this step is done in the Fabric UI.
                          </MessageBarBody>
                        </MessageBar>
                      )}
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

    {/* ── Fullscreen data preview modal ───────────────────────────────── */}
    {previewFileName && (
      <div
        className={styles.modalBackdrop}
        onClick={(e) => { if (e.target === e.currentTarget) setPreviewFileName(null); }}
      >
        <div className={styles.modalPanel}>
          {/* Header */}
          <div className={styles.modalHeader}>
            <div className={styles.modalHeaderLeft}>
              <TableRegular fontSize={20} style={{ color: "#8b949e", flexShrink: 0 }} />
              <Text weight="semibold" size={400} style={{ color: "#e6edf3", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {previewFileName}
              </Text>
              {demo.sampleData.find(d => d.fileName === previewFileName) && (
                <Caption1 style={{ color: "#8b949e", whiteSpace: "nowrap" }}>
                  · {demo.sampleData.find(d => d.fileName === previewFileName)!.rows.toLocaleString()} rows
                </Caption1>
              )}
            </div>
            <Button
              appearance="subtle"
              size="small"
              icon={<span style={{ fontSize: 16 }}>✕</span>}
              onClick={() => setPreviewFileName(null)}
              aria-label="Close preview"
            />
          </div>

          {/* Body */}
          <div className={styles.modalBody}>
            {/* Sidebar — file list */}
            <div className={styles.modalSidebar}>
              {demo.sampleData.map((dataset) => {
                const isActive = previewFileName === dataset.fileName;
                return (
                  <div
                    key={dataset.fileName}
                    className={`${styles.modalSidebarItem}${isActive ? ` ${styles.modalSidebarItemActive}` : ""}`}
                    onClick={() => void handlePreviewDataset(dataset.fileName)}
                  >
                    <Text weight={isActive ? "semibold" : "regular"} size={200} style={{ color: isActive ? "#e6edf3" : "#8b949e", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {dataset.fileName}
                    </Text>
                    <Caption1 style={{ color: "#484f58" }}>{dataset.rows.toLocaleString()} rows</Caption1>
                  </div>
                );
              })}
            </div>

            {/* Main — table */}
            <div className={styles.modalMain}>
              {(() => {
                const loading = previewLoadingFile === previewFileName;
                const preview = datasetPreviews[previewFileName];
                const previewError = previewErrors[previewFileName];
                const dataset = demo.sampleData.find(d => d.fileName === previewFileName);

                if (loading) return (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "20px 24px", color: "#8b949e" }}>
                    <Spinner size="tiny" /><Caption1>Loading preview…</Caption1>
                  </div>
                );
                if (previewError) return (
                  <div style={{ padding: "16px 24px" }}>
                    <MessageBar intent="error"><MessageBarBody>{previewError}</MessageBarBody></MessageBar>
                  </div>
                );
                if (!preview) return (
                  <div style={{ padding: "20px 24px", color: "#8b949e" }}>
                    <Caption1>No data loaded yet.</Caption1>
                  </div>
                );
                if (preview.columns.length === 0 || preview.rows.length === 0) return (
                  <div style={{ padding: "20px 24px", color: "#8b949e" }}>
                    <Caption1>No preview rows available for this dataset.</Caption1>
                  </div>
                );
                return (
                  <>
                    <div className={styles.modalMeta}>
                      <Caption1>
                        Showing {preview.shownRows.toLocaleString()} of {(preview.totalRows ?? dataset?.rows ?? 0).toLocaleString()} rows · {preview.columns.length} columns
                      </Caption1>
                    </div>
                    <div className={styles.modalTableWrap}>
                      <table className={styles.modalTable}>
                        <thead>
                          <tr>
                            {preview.columns.map((col) => (
                              <th key={col} className={styles.modalTh} title={col}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {preview.rows.map((row, i) => (
                            <tr key={i}>
                              {preview.columns.map((col) => {
                                const val = row[col] ?? "";
                                return <td key={col} className={styles.modalTd} title={val}>{val}</td>;
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      </div>
    )}
    </>
  );
}
