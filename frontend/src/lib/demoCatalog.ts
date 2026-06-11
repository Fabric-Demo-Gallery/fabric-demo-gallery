// Central catalog of standard demo definitions.
// To add a new demo: append an entry to DEMOS with the demo id as the key.
// generateStaticParams() in app/demos/[id]/page.tsx derives its list from Object.keys(DEMOS)
// automatically, so no other file needs to change.

export interface DemoDetail {
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

  // ---- Presenter content (optional; powers the "Presenter" view + post-deploy guidance) ----
  /** One- or two-sentence "why this matters" framing for a customer conversation. */
  businessValue?: string;
  /** Short bullet narrative an SE can speak to while presenting the demo. */
  talkingPoints?: string[];
  /** Headline metrics/results to call out (e.g. model AUC, rows scored). */
  sampleInsights?: { label: string; value: string }[];
  /** Suggested live walk-through order once the workspace is deployed. */
  demoFlow?: { step: string; detail: string }[];
  /** "What to show next" links/pointers shown after a successful deploy. */
  postDeploy?: { label: string; detail: string }[];
}

export const DEMOS: Record<string, DemoDetail> = {
  "manufacturing-qc": {
    id: "manufacturing-qc",
    industry: "Manufacturing",
    title: "Quality Control Analytics",
    description:
      "Track OEE, defect rate, and yield from production-line sensor data.",
    longDescription:
      "Ingests production-line sensor data and batch records through a medallion pipeline to track OEE, defect rate, yield, and MTBF. A Direct Lake semantic model feeds a Power BI dashboard with control charts and trend analysis.",
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
      { fileName: "sensor_readings.csv", description: "50,000 IoT sensor readings: temperature, pressure, vibration, humidity", format: "csv", rows: 50000 },
      { fileName: "production_batches.csv", description: "2,000 production batch records with units, defects, downtime", format: "csv", rows: 2000 },
      { fileName: "equipment_catalog.csv", description: "50 machines across 4 production lines", format: "csv", rows: 50 },
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
      "Analyse sales, margin, and inventory turnover from POS data.",
    longDescription:
      "Combines POS transactions with product, store, and inventory data through a medallion pipeline to produce sales, basket, and inventory-turnover metrics. A star-schema semantic model drives dashboards for revenue trends, top products, and stock alerts.",
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
      "Monitor grid health, detect outages, and track renewable output in real time.",
    longDescription:
      "Streams grid sensor readings, outage events, and renewable output into an Eventhouse and KQL Database for time-series analytics. A KQL dashboard tracks live grid health while Power BI covers outage analysis and renewable performance.",
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
      { type: "Notebook", name: "03_simulate_realtime", description: "Real-time simulator that generates live sensor readings with current timestamps. Schedule via pipeline for continuous data.", order: 3 },
      { type: "SemanticModel", name: "grid_analytics_model", description: "Direct Lake model with grid health, outage, and renewable measures" },
      { type: "Report", name: "Smart Grid Dashboard", description: "3-page Power BI dashboard: Grid Health, Outage Analysis, Renewable Performance" },
      { type: "KQLDashboard", name: "Grid Real-Time Dashboard", description: "Real-time KQL dashboard with live grid sensor queries and outage tracking" },
      { type: "DataPipeline", name: "grid_monitoring_pipeline", description: "Orchestrates ingestion and analytics notebooks" },
    ],
  },

  "healthcare": {
    id: "healthcare",
    industry: "Healthcare & Life Sciences",
    title: "Patient & Care Quality Analytics",
    description:
      "Track readmission rates, length of stay, and department efficiency.",
    longDescription:
      "Combines admissions, vital-sign readings, and staffing data through a medallion pipeline to track readmission rate, length of stay, bed occupancy, and department throughput. A Direct Lake semantic model drives patient-flow and outcome dashboards.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Admissions & Vitals)",
        "Silver (Cleaned & Enriched)",
        "Gold (Outcome & Efficiency KPIs)",
      ],
    },
    sampleData: [
      { fileName: "patient_admissions.csv", description: "20,000 patient admission records with department, admission/discharge dates, diagnosis code, insurance type, and readmission flag", format: "csv", rows: 20000 },
    { fileName: "clinical_records.csv", description: "80,000 vital-sign readings per patient: blood pressure, heart rate, temperature, O2 saturation", format: "csv", rows: 80000 },
    { fileName: "staff_catalog.csv", description: "200 staff records: ID, role (doctor/nurse/technician), department, shift", format: "csv", rows: 200 },
    ],
    fabricItems: [
      { type: "Lakehouse", name: "healthcare_lakehouse", description: "Central lakehouse for all healthcare analytics data" },
      { type: "Notebook", name: "01_bronze_ingest", description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook", name: "02_silver_transform", description: "Clean, validate, and enrich admissions and vitals; derive length of stay and risk flags", order: 2 },
      { type: "Notebook", name: "03_gold_aggregate", description: "6 Gold tables: department summary, readmission analysis, patient flow, staff utilisation, weekly trends, outcome scorecards", order: 3 },
      { type: "Notebook", name: "04_reporting_views", description: "SQL reporting views: executive dashboard, bed occupancy, readmission hotspots, department scorecards", order: 4 },
      { type: "Notebook", name: "05_dashboard", description: "Interactive HTML dashboard with KPI cards, patient flow trends, readmission risk, department comparison", order: 5 },
      { type: "SemanticModel", name: "healthcare_analytics_model", description: "Direct Lake model with patient flow, readmission, and department KPI measures" },
      { type: "Report", name: "Patient & Care Quality Dashboard", description: "3-page dashboard: Patient Flow, Readmission Risk, Department Performance" },
      { type: "DataPipeline", name: "daily_healthcare_pipeline", description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },

  "financial-services": {
    id: "financial-services",
    industry: "Financial Services",
    title: "Risk & Transaction Analytics",
    description:
      "Detect fraud, score credit risk, and monitor portfolio performance.",
    longDescription:
      "Combines transactions, accounts, and customer profiles through a medallion pipeline to surface fraud rates, credit-risk distribution, and portfolio KPIs by segment. A Direct Lake semantic model drives fraud-alert and risk dashboards.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Transactions)",
        "Silver (Cleaned & Risk-Flagged)",
        "Gold (Risk, Fraud & Portfolio KPIs)",
      ],
    },
    sampleData: [
      { fileName: "transactions.csv", description: "100,000 financial transactions with account, amount, merchant category, timestamp, and fraud flag", format: "csv", rows: 100000 },
    { fileName: "accounts.csv", description: "5,000 account records: account type, balance, credit limit, open date, status", format: "csv", rows: 5000 },
    { fileName: "customers.csv", description: "2,000 customer profiles: age group, region, segment (Retail/SME/Corporate), risk tier", format: "csv", rows: 2000 },
    ],
    fabricItems: [
      { type: "Lakehouse", name: "financial_lakehouse", description: "Central lakehouse for all financial analytics data" },
      { type: "Notebook", name: "01_bronze_ingest", description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook", name: "02_silver_transform", description: "Clean transactions, validate accounts, derive fraud risk scores and credit utilisation bands", order: 2 },
      { type: "Notebook", name: "03_gold_aggregate", description: "6 Gold tables: daily transaction summary, fraud analysis, credit risk distribution, segment portfolio, weekly trends, account scorecards", order: 3 },
      { type: "Notebook", name: "04_reporting_views", description: "SQL reporting views: executive dashboard, fraud hotspots, risk heat-map, segment performance", order: 4 },
      { type: "Notebook", name: "05_dashboard", description: "Interactive HTML dashboard with KPI cards, fraud trends, risk distribution, portfolio by segment", order: 5 },
      { type: "SemanticModel", name: "financial_analytics_model", description: "Direct Lake model with fraud, risk, and portfolio KPI measures" },
      { type: "Report", name: "Risk & Transaction Dashboard", description: "3-page dashboard: Transaction Overview, Fraud Analysis, Credit Risk & Portfolio" },
      { type: "DataPipeline", name: "daily_financial_pipeline", description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },

  "hospitality": {
    id: "hospitality",
    industry: "Hospitality & Travel",
    title: "Guest Experience & Revenue Analytics",
    description:
      "Track RevPAR, occupancy, and guest satisfaction across properties.",
    longDescription:
      "Combines bookings, guest profiles, property data, and reviews through a medallion pipeline to track RevPAR, ADR, occupancy, and guest satisfaction. A Direct Lake semantic model drives revenue, property-comparison, and loyalty dashboards.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Bookings, Guests, Properties, Reviews)",
        "Silver (Cleaned & Enriched)",
        "Gold (Revenue, Occupancy & Loyalty KPIs)",
      ],
    },
    sampleData: [
      { fileName: "bookings.csv",   description: "50,000 hotel bookings with channel, room type, nightly rate, and status", format: "csv", rows: 50000 },
      { fileName: "guests.csv",     description: "5,000 guest profiles with loyalty tier, region, and lifetime stay history", format: "csv", rows: 5000 },
      { fileName: "properties.csv", description: "50 hotel properties with star rating, city, country, and room count", format: "csv", rows: 50 },
      { fileName: "reviews.csv",    description: "20,000 guest reviews with category scores and sentiment classification", format: "csv", rows: 20000 },
    ],
    fabricItems: [
      { type: "Lakehouse",      name: "hospitality_lakehouse",       description: "Central lakehouse for all hospitality analytics data" },
      { type: "Notebook",       name: "01_bronze_ingest",            description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook",       name: "02_silver_transform",         description: "Clean bookings, derive ADR, length of stay, satisfaction scores, and repeat-guest flags", order: 2 },
      { type: "Notebook",       name: "03_gold_aggregate",           description: "6 Gold tables: daily revenue, occupancy analysis, loyalty segments, channel performance, weekly trends, property scorecards", order: 3 },
      { type: "Notebook",       name: "04_reporting_views",          description: "SQL reporting views: executive summary, revenue heat-map, loyalty analysis, property performance", order: 4 },
      { type: "Notebook",       name: "05_dashboard",                description: "Interactive HTML dashboard with KPI cards, revenue trends, and property comparison table", order: 5 },
      { type: "SemanticModel",  name: "hospitality_analytics_model", description: "Direct Lake model with revenue, occupancy, and guest satisfaction measures" },
      { type: "Report",         name: "Guest Experience Dashboard",  description: "3-page dashboard: Revenue & Occupancy, Guest Satisfaction, Loyalty Performance" },
      { type: "DataPipeline",   name: "daily_hospitality_pipeline",  description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },

  "media": {
    id: "media",
    industry: "Media, Telecommunications & Entertainment",
    title: "Subscriber & Content Analytics",
    description:
      "Track subscriber churn, content performance, and ad revenue.",
    longDescription:
      "Combines subscribers, content catalog, viewing history, and ad impressions through a medallion pipeline to track churn, ARPU, completion rate, and ad revenue. A Direct Lake semantic model drives churn, content-performance, and ad-revenue dashboards.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Subscribers, Content, Viewing History, Ads)",
        "Silver (Cleaned & Enriched)",
        "Gold (Churn, Content & Ad Revenue KPIs)",
      ],
    },
    sampleData: [
      { fileName: "subscribers.csv",     description: "10,000 subscriber records with plan type, region, churn flag, and monthly fee", format: "csv", rows: 10000 },
      { fileName: "content_catalog.csv", description: "2,000 content items with genre, type, duration, release year, and cost bucket", format: "csv", rows: 2000 },
      { fileName: "viewing_history.csv", description: "200,000 viewing records with watch duration, completion flag, device type, and rating", format: "csv", rows: 200000 },
      { fileName: "ad_impressions.csv",  description: "100,000 ad impression records with clicks, CPM, revenue, and ad type", format: "csv", rows: 100000 },
    ],
    fabricItems: [
      { type: "Lakehouse",      name: "media_lakehouse",            description: "Central lakehouse for all media analytics data" },
      { type: "Notebook",       name: "01_bronze_ingest",           description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook",       name: "02_silver_transform",        description: "Clean subscribers, derive tenure, churn flags, content completion rates, and ad CTR", order: 2 },
      { type: "Notebook",       name: "03_gold_aggregate",          description: "6 Gold tables: daily subscriber metrics, content performance, churn analysis, ad revenue, weekly trends, subscriber scorecards", order: 3 },
      { type: "Notebook",       name: "04_reporting_views",         description: "SQL reporting views: executive summary, churn risk, content performance, ad revenue breakdown", order: 4 },
      { type: "Notebook",       name: "05_dashboard",               description: "Interactive HTML dashboard with KPI cards, churn trends, content top-10, and ad revenue by type", order: 5 },
      { type: "SemanticModel",  name: "media_analytics_model",     description: "Direct Lake model with subscriber, content performance, and ad revenue measures" },
      { type: "Report",         name: "Subscriber & Content Dashboard", description: "3-page dashboard: Subscriber Health, Content Performance, Ad Revenue" },
      { type: "DataPipeline",   name: "daily_media_pipeline",       description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },

  "construction": {
    id: "construction",
    industry: "Construction & Real Estate",
    title: "Project Cost & Portfolio Analytics",
    description:
      "Track schedule variance, cost overruns, and subcontractor performance.",
    longDescription:
      "Combines projects, task schedules, cost ledger, and subcontractor data through a medallion pipeline to track schedule risk, cost variance, and supplier performance. A Direct Lake semantic model drives portfolio dashboards for on-time delivery and budget overruns.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Projects, Tasks, Subcontractors, Cost Ledger)",
        "Silver (Cleaned & Enriched)",
        "Gold (Schedule, Cost & Portfolio KPIs)",
      ],
    },
    sampleData: [
      { fileName: "projects.csv",       description: "200 construction projects with type, region, budget, planned/actual dates, and schedule variance", format: "csv", rows: 200 },
      { fileName: "tasks.csv",          description: "10,000 project tasks with planned/actual dates, completion status, and assigned subcontractor", format: "csv", rows: 10000 },
      { fileName: "cost_ledger.csv",    description: "50,000 cost entries with category, supplier, planned vs actual spend, and overrun flag", format: "csv", rows: 50000 },
      { fileName: "subcontractors.csv", description: "100 subcontractors with trade, region, rating, and accreditation status", format: "csv", rows: 100 },
    ],
    fabricItems: [
      { type: "Lakehouse",     name: "construction_lakehouse",           description: "Central lakehouse for all construction analytics data" },
      { type: "Notebook",      name: "01_bronze_ingest",                 description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook",      name: "02_silver_transform",              description: "Clean data, derive schedule variance bands, cost overrun flags, and task completion rates", order: 2 },
      { type: "Notebook",      name: "03_gold_aggregate",                description: "6 Gold tables: project summary, cost analysis, subcontractor performance, weekly trends, overrun alerts, portfolio scorecards", order: 3 },
      { type: "Notebook",      name: "04_reporting_views",               description: "SQL reporting views: executive summary, cost overruns, schedule risk, subcontractor scorecard", order: 4 },
      { type: "Notebook",      name: "05_dashboard",                     description: "Interactive HTML dashboard with KPI cards, top overrun projects, and subcontractor performance table", order: 5 },
      { type: "SemanticModel", name: "construction_analytics_model",     description: "Direct Lake model with project, cost, and subcontractor performance measures" },
      { type: "Report",        name: "Construction Portfolio Dashboard", description: "3-page dashboard: Portfolio Overview, Cost Analysis, Subcontractor Health" },
      { type: "DataPipeline",  name: "daily_construction_pipeline",      description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },

  "education": {
    id: "education",
    industry: "Education",
    title: "Student Outcomes & Institutional Analytics",
    description:
      "Track pass rates, retention, and at-risk students across departments.",
    longDescription:
      "Combines student records, enrolments, assessments, and faculty data through a medallion pipeline to track pass rates, retention risk, and course performance. A Direct Lake semantic model drives dashboards for at-risk students and department benchmarks.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Students, Enrolments, Assessments, Faculty)",
        "Silver (Cleaned & Enriched)",
        "Gold (Cohort, Course & Retention KPIs)",
      ],
    },
    sampleData: [
      { fileName: "students.csv",    description: "5,000 student records with programme, department, level, cohort year, and status", format: "csv", rows: 5000 },
      { fileName: "enrolments.csv",  description: "20,000 course enrolment records with credits, completion, and withdrawal status", format: "csv", rows: 20000 },
      { fileName: "assessments.csv", description: "80,000 assessment submissions with score, grade, pass flag, and attempt number", format: "csv", rows: 80000 },
      { fileName: "faculty.csv",     description: "200 faculty members with department, role, courses assigned, and research status", format: "csv", rows: 200 },
    ],
    fabricItems: [
      { type: "Lakehouse",     name: "education_lakehouse",           description: "Central lakehouse for all education analytics data" },
      { type: "Notebook",      name: "01_bronze_ingest",              description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook",      name: "02_silver_transform",           description: "Derive GPA proxy, pass rates, retention risk flags, grade bands, and faculty load bands", order: 2 },
      { type: "Notebook",      name: "03_gold_aggregate",             description: "6 Gold tables: cohort outcomes, course performance, retention analysis, faculty workload, weekly trends, student scorecards", order: 3 },
      { type: "Notebook",      name: "04_reporting_views",            description: "SQL reporting views: executive summary, at-risk students, course pass rates, faculty performance", order: 4 },
      { type: "Notebook",      name: "05_dashboard",                  description: "Interactive HTML dashboard with KPI cards, lowest-performing courses, and department performance table", order: 5 },
      { type: "SemanticModel", name: "education_analytics_model",     description: "Direct Lake model with cohort, course performance, and retention measures" },
      { type: "Report",        name: "Student Outcomes Dashboard",    description: "3-page dashboard: Cohort Health, Course Performance, Faculty & Workload" },
      { type: "DataPipeline",  name: "daily_education_pipeline",      description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },

  "transportation": {
    id: "transportation",
    industry: "Transportation & Logistics",
    title: "Fleet & Route Performance Analytics",
    description:
      "Track on-time delivery, route efficiency, and fuel cost across the fleet.",
    longDescription:
      "Combines vehicle, route, delivery, and fuel data through a medallion pipeline to track on-time rate, route profitability, fuel efficiency, and depot scorecards. A Direct Lake semantic model drives a three-page Power BI dashboard for operations, route planning, and fuel teams.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Vehicles, Routes, Deliveries, Fuel Logs)",
        "Silver (Cleaned & Enriched with derived metrics)",
        "Gold (Fleet, Delivery, Route & Depot KPIs)",
      ],
    },
    sampleData: [
      { fileName: "vehicles.csv",   description: "100 fleet vehicles with type, depot, capacity, and registration year", format: "csv", rows: 100 },
      { fileName: "routes.csv",     description: "500 route definitions with origin, destination, distance, SLA, and toll cost", format: "csv", rows: 500 },
      { fileName: "deliveries.csv", description: "50,000 delivery records with timing, load, delay, and on-time status", format: "csv", rows: 50000 },
      { fileName: "fuel_logs.csv",  description: "20,000 fuel fill events with litres, cost, and fuel type per vehicle", format: "csv", rows: 20000 },
    ],
    fabricItems: [
      { type: "Lakehouse",     name: "transportation_lakehouse",          description: "Central lakehouse for all fleet and logistics analytics data" },
      { type: "Notebook",      name: "01_bronze_ingest",                  description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook",      name: "02_silver_transform",               description: "Derive delay bands, load utilisation percentages, and fuel efficiency metrics", order: 2 },
      { type: "Notebook",      name: "03_gold_aggregate",                 description: "6 Gold tables: fleet summary, delivery performance, route analysis, weekly trends, late alerts, depot scorecards", order: 3 },
      { type: "Notebook",      name: "04_reporting_views",                description: "SQL reporting views: executive summary, late deliveries, fuel analysis, route efficiency", order: 4 },
      { type: "Notebook",      name: "05_dashboard",                      description: "Interactive HTML dashboard with KPI cards, top late routes, and fleet performance by vehicle type", order: 5 },
      { type: "SemanticModel", name: "transportation_analytics_model",    description: "Direct Lake model with fleet, delivery, and route performance measures" },
      { type: "Report",        name: "Fleet Performance Dashboard",       description: "3-page dashboard: Operations Overview, Route Analysis, Fuel & Depot" },
      { type: "DataPipeline",  name: "daily_transportation_pipeline",     description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },

  "technology": {
    id: "technology",
    industry: "Technology & Software",
    title: "SaaS Product & Customer Analytics",
    description:
      "Track account health, MRR, churn risk, and feature adoption.",
    longDescription:
      "Combines accounts, user activity, product events, and support tickets through a medallion pipeline to track account health, feature adoption, churn, and SLA performance. A Direct Lake semantic model drives a three-page Power BI dashboard for customer success, product, and support teams.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Accounts, Users, Events, Support Tickets)",
        "Silver (Cleaned & Enriched with churn and engagement signals)",
        "Gold (Account Health, Feature Adoption & Support KPIs)",
      ],
    },
    sampleData: [
      { fileName: "accounts.csv",         description: "2,000 customer accounts with plan, MRR, health score, and churn status", format: "csv", rows: 2000 },
      { fileName: "users.csv",            description: "10,000 user records with role, activity, and login frequency", format: "csv", rows: 10000 },
      { fileName: "events.csv",           description: "200,000 product events with feature, action, session, and duration", format: "csv", rows: 200000 },
      { fileName: "support_tickets.csv",  description: "20,000 support tickets with category, priority, SLA, and CSAT score", format: "csv", rows: 20000 },
    ],
    fabricItems: [
      { type: "Lakehouse",     name: "technology_lakehouse",          description: "Central lakehouse for all SaaS product and customer analytics data" },
      { type: "Notebook",      name: "01_bronze_ingest",              description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook",      name: "02_silver_transform",           description: "Derive churn risk flags, engagement bands, feature categories, and SLA margins", order: 2 },
      { type: "Notebook",      name: "03_gold_aggregate",             description: "6 Gold tables: account health, feature adoption, churn analysis, support performance, engagement trends, account scorecards", order: 3 },
      { type: "Notebook",      name: "04_reporting_views",            description: "SQL reporting views: executive summary, churn risk accounts, feature usage, SLA breaches", order: 4 },
      { type: "Notebook",      name: "05_dashboard",                  description: "Interactive HTML dashboard with KPI cards, churn risk table, and feature adoption table", order: 5 },
      { type: "SemanticModel", name: "technology_analytics_model",    description: "Direct Lake model with MRR, churn, engagement, and support measures" },
      { type: "Report",        name: "SaaS Analytics Dashboard",      description: "3-page dashboard: Account Health, Product Engagement, Support Operations" },
      { type: "DataPipeline",  name: "daily_technology_pipeline",     description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },

  "professional-services": {
    id: "professional-services",
    industry: "Professional Services",
    title: "Project Profitability & Utilisation Analytics",
    description:
      "Track utilisation, project margin, and delivery health.",
    longDescription:
      "Combines consultants, clients, engagements, and timesheets through a medallion pipeline to track utilisation, project margin, client revenue, and delivery health. A Direct Lake semantic model drives a three-page Power BI dashboard for practice leads, account managers, and finance.",
    estimatedTime: "8-12 min",
    prerequisites: [
      "Microsoft Fabric capacity (F2+ or Trial)",
      "Azure AD account with Fabric workspace creation permissions",
    ],
    architecture: {
      pattern: "medallion",
      layers: [
        "Bronze (Raw Consultants, Clients, Engagements, Timesheets)",
        "Silver (Cleaned & Enriched with margin and utilisation metrics)",
        "Gold (Utilisation, Profitability, Client & Delivery KPIs)",
      ],
    },
    sampleData: [
      { fileName: "consultants.csv",  description: "200 consultants with grade, practice, region, daily rate, and billability", format: "csv", rows: 200 },
      { fileName: "clients.csv",      description: "100 client accounts with tier, industry, contract value, and NPS score", format: "csv", rows: 100 },
      { fileName: "engagements.csv",  description: "1,000 project engagements with budget, actual spend, margin, and delivery status", format: "csv", rows: 1000 },
      { fileName: "timesheets.csv",   description: "50,000 weekly timesheet entries with task type, hours, billability, and billed value", format: "csv", rows: 50000 },
    ],
    fabricItems: [
      { type: "Lakehouse",     name: "proservices_lakehouse",              description: "Central lakehouse for all professional services analytics data" },
      { type: "Notebook",      name: "01_bronze_ingest",                   description: "Ingest raw CSV files into Bronze Delta tables with metadata columns", order: 1 },
      { type: "Notebook",      name: "02_silver_transform",                description: "Derive grade bands, NPS bands, margin bands, delivery health flags, and billable utilisation rates", order: 2 },
      { type: "Notebook",      name: "03_gold_aggregate",                  description: "6 Gold tables: consultant utilisation, project profitability, client revenue, delivery health, weekly trends, portfolio scorecards", order: 3 },
      { type: "Notebook",      name: "04_reporting_views",                 description: "SQL reporting views: executive summary, low-margin projects, underutilised consultants, client revenue concentration", order: 4 },
      { type: "Notebook",      name: "05_dashboard",                       description: "Interactive HTML dashboard with KPI cards, low-margin projects table, and consultant utilisation table", order: 5 },
      { type: "SemanticModel", name: "proservices_analytics_model",        description: "Direct Lake model with utilisation, margin, revenue, and delivery health measures" },
      { type: "Report",        name: "Professional Services Dashboard",    description: "3-page dashboard: Portfolio Overview, Project Profitability, Client & Revenue" },
      { type: "DataPipeline",  name: "daily_proservices_pipeline",         description: "Orchestrates all notebooks sequentially with retry" },
    ],
  },
};
