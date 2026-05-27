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
}

export const DEMOS: Record<string, DemoDetail> = {
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

  "healthcare": {
    id: "healthcare",
    industry: "Healthcare & Life Sciences",
    title: "Patient & Care Quality Analytics",
    description:
      "Analyze patient admissions, track readmission rates, monitor clinical outcomes, and measure operational efficiency across departments.",
    longDescription:
      "This demo deploys a healthcare analytics environment using a medallion architecture. It ingests synthetic patient admission records, clinical vital-sign readings, and staff roster data. The pipeline produces KPIs including readmission rates, average length of stay, bed occupancy, department throughput, and staff-to-patient ratios. A Direct Lake semantic model powers dashboards showing patient flow, outcome trends, and department performance.",
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
      { fileName: "clinical_records.csv", description: "80,000 vital-sign readings per patient — blood pressure, heart rate, temperature, O2 saturation", format: "csv", rows: 80000 },
      { fileName: "staff_catalog.csv", description: "200 staff records — ID, role (doctor/nurse/technician), department, shift", format: "csv", rows: 200 },
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
      "Detect fraud patterns, score credit risk, monitor portfolio performance, and track transaction volumes across accounts and customer segments.",
    longDescription:
      "This demo deploys a financial services analytics environment on the medallion architecture. It ingests synthetic transaction records, account master data, and customer profiles. The pipeline produces fraud-flag rates, credit risk distributions, daily transaction volumes, and segment-level portfolio KPIs. A Direct Lake semantic model powers dashboards with real-time fraud alerts, risk heat-maps, and revenue contribution by customer segment.",
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
      { fileName: "accounts.csv", description: "5,000 account records — account type, balance, credit limit, open date, status", format: "csv", rows: 5000 },
      { fileName: "customers.csv", description: "2,000 customer profiles — age group, region, segment (Retail/SME/Corporate), risk tier", format: "csv", rows: 2000 },
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
      "Monitor RevPAR, occupancy rates, guest satisfaction scores, and loyalty programme performance across properties.",
    longDescription:
      "This demo deploys a hospitality analytics environment on the medallion architecture. It ingests synthetic booking records, guest profiles, property master data, and guest review scores. The pipeline produces KPIs including Revenue Per Available Room (RevPAR), Average Daily Rate (ADR), occupancy rate, guest satisfaction score, Net Promoter indicators, and loyalty tier distributions. A Direct Lake semantic model powers dashboards with revenue heat-maps, property comparisons, and loyalty cohort analysis.",
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
      "Track subscriber churn, content performance, ad revenue, and audience engagement across streaming plans and content genres.",
    longDescription:
      "This demo deploys a media and telecom analytics environment using the medallion architecture. It ingests synthetic subscriber records, a content catalog, viewing history, and ad impression data. The pipeline produces subscriber churn rates, ARPU (Average Revenue Per User), content completion rates, top-performing genres, and ad revenue by type. A Direct Lake semantic model powers dashboards with churn cohort analysis, content performance rankings, and ad revenue trends.",
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
};
