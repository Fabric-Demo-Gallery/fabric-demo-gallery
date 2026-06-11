// Presenter content for solution engineers — talking track, headline metrics,
// suggested live demo flow, and post-deploy "what to show next" pointers.
// Keyed by demo id. Consumed by DemoDetailClient (Presenter section + post-deploy panel).
// Kept separate from demoCatalog.ts so the large demo objects stay easy to maintain.

export interface PresenterContent {
  /** One- or two-sentence "why this matters" framing for a customer conversation. */
  businessValue: string;
  /** Short bullet narrative an SE can speak to while presenting. */
  talkingPoints: string[];
  /** Headline metrics/results to call out (KPIs the demo produces + the AI/ML model result). */
  sampleInsights: { label: string; value: string }[];
  /** Suggested live walk-through order once the workspace is deployed. */
  demoFlow: { step: string; detail: string }[];
  /** "What to show next" pointers shown after a successful deploy. */
  postDeploy: { label: string; detail: string }[];
}

export const PRESENTER: Record<string, PresenterContent> = {
  "manufacturing-qc": {
    businessValue:
      "Turn production-line sensor data into live OEE, yield, and defect KPIs, then predict defects before they reach the customer.",
    talkingPoints: [
      "One medallion pipeline unifies sensor telemetry and batch records.",
      "Direct Lake reads Delta directly: no import refresh, near-real-time KPIs.",
      "The AI/ML scenario adds a per-batch RandomForest defect classifier.",
      "Every layer is an open notebook the customer can read and extend.",
    ],
    sampleInsights: [
      { label: "Sensor rows ingested", value: "50,000" },
      { label: "KPIs", value: "OEE · Yield · Defect rate · MTBF" },
      { label: "AI/ML model", value: "Defect prediction (RandomForest)" },
      { label: "Report pages", value: "Quality · Equipment Health · Product" },
    ],
    demoFlow: [
      { step: "Open the lakehouse", detail: "Show Bronze→Silver→Gold Delta tables created by the notebooks." },
      { step: "Walk one notebook", detail: "03_gold_aggregate, with OEE and defect logic in PySpark." },
      { step: "Open the report", detail: "Quality Overview page, with live control charts and defect trends." },
      { step: "Pivot to AI/ML", detail: "Show the defect-prediction model metrics + per-batch risk scoring." },
    ],
    postDeploy: [
      { label: "Quality Control Dashboard", detail: "3-page Power BI report. Start on Quality Overview." },
      { label: "quality_analytics_model", detail: "Direct Lake semantic model with measures and relationships." },
      { label: "03_gold_aggregate notebook", detail: "The KPI logic in open, editable PySpark." },
    ],
  },

  "retail-sales": {
    businessValue:
      "One view of sales, margin, and inventory for merchandising teams, with demand forecasting to cut stockouts and markdowns.",
    talkingPoints: [
      "Familiar star-schema gold model for Power BI users.",
      "Basket and inventory-turnover metrics come from the medallion pipeline.",
      "The AI/ML scenario forecasts daily demand per product and store.",
      "Direct Lake keeps 100k+ transactions queryable with no refresh.",
    ],
    sampleInsights: [
      { label: "POS line items", value: "100,000" },
      { label: "KPIs", value: "Revenue · Margin · Inventory turnover · Basket" },
      { label: "AI/ML model", value: "Demand forecast (regression, R²)" },
      { label: "Report pages", value: "Sales · Inventory · Margin & Basket" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Sales page, with revenue trend and top products." },
      { step: "Show inventory", detail: "Inventory page, with turnover and low-stock alerts." },
      { step: "Walk the gold notebook", detail: "Sales KPIs and weekly trends in PySpark." },
      { step: "Pivot to AI/ML", detail: "Demand forecast, predicted vs actual by category." },
    ],
    postDeploy: [
      { label: "Retail Sales Dashboard", detail: "3-page Power BI report. Open Sales first." },
      { label: "retail_analytics_model", detail: "Star-schema Direct Lake model with 40+ measures." },
      { label: "03_gold_aggregate notebook", detail: "Sales/inventory aggregation logic." },
    ],
  },

  "energy-grid": {
    businessValue:
      "Real-time visibility into voltage, frequency, and outages, with failure prediction to prioritise at-risk substations.",
    talkingPoints: [
      "Eventhouse and KQL handle high-volume time-series a warehouse can't.",
      "A simulator notebook streams live readings during the demo.",
      "The KQL dashboard refreshes continuously; Power BI covers executive views.",
      "The AI/ML scenario predicts failures to prioritise at-risk substations.",
    ],
    sampleInsights: [
      { label: "Sensor readings", value: "100,000" },
      { label: "Engine", value: "Eventhouse / KQL time-series" },
      { label: "AI/ML model", value: "Outage prediction (RandomForest)" },
      { label: "Surfaces", value: "KQL real-time dashboard + Power BI" },
    ],
    demoFlow: [
      { step: "Open the KQL dashboard", detail: "Live grid health with voltage and frequency tiles." },
      { step: "Run a KQL query", detail: "Show anomaly detection over the time-series." },
      { step: "Start the simulator", detail: "03_simulate_realtime, watch new readings flow in." },
      { step: "Pivot to AI/ML", detail: "Outage prediction model + per-substation risk." },
    ],
    postDeploy: [
      { label: "Grid Real-Time Dashboard", detail: "KQL dashboard for the live time-series story." },
      { label: "Smart Grid Dashboard", detail: "3-page Power BI report for executive views." },
      { label: "03_simulate_realtime notebook", detail: "Schedule it to keep data flowing during a demo." },
    ],
  },

  "healthcare": {
    businessValue:
      "Patient-flow, length-of-stay, and readmission analytics, with risk scoring that supports early intervention.",
    talkingPoints: [
      "Admissions, vitals, and staffing in one governed lakehouse.",
      "30-day readmission rate ties directly to reimbursement penalties.",
      "The AI/ML scenario predicts readmission risk before discharge.",
      "Explainable features suit clinical stakeholders.",
    ],
    sampleInsights: [
      { label: "Admissions", value: "20,000" },
      { label: "KPIs", value: "Readmission rate · ALOS · Bed occupancy" },
      { label: "AI/ML model", value: "Readmission risk · AUC 0.79" },
      { label: "Report pages", value: "Patient Flow · Readmission · Department" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Patient Flow with admissions, occupancy, and length of stay." },
      { step: "Show readmission", detail: "Readmission Risk page, with hotspots by department." },
      { step: "Walk the gold notebook", detail: "Outcome and efficiency KPI logic." },
      { step: "Pivot to AI/ML", detail: "Readmission model + per-patient risk scoring." },
    ],
    postDeploy: [
      { label: "Patient & Care Quality Dashboard", detail: "3-page report. Start on Patient Flow." },
      { label: "healthcare_analytics_model", detail: "Direct Lake model with readmission measures." },
      { label: "Readmission predictions", detail: "Per-patient risk from the AI/ML gold_ml_predictions table." },
    ],
  },

  "financial-services": {
    businessValue:
      "Transaction monitoring and credit-risk analytics, with a model that flags suspicious activity in near-real time.",
    talkingPoints: [
      "Fraud rate and credit-risk bands come from the medallion pipeline.",
      "Segment-level portfolio KPIs tie analytics to revenue.",
      "The AI/ML scenario scores fraud probability per transaction.",
      "Direct Lake keeps 100k transactions interactive without refresh.",
    ],
    sampleInsights: [
      { label: "Transactions", value: "100,000" },
      { label: "KPIs", value: "Fraud rate · Credit risk · Portfolio by segment" },
      { label: "AI/ML model", value: "Fraud detection · AUC 0.85" },
      { label: "Report pages", value: "Transactions · Fraud · Credit Risk" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Transaction Overview, with volumes and trends." },
      { step: "Show fraud", detail: "Fraud Analysis page, with hotspots by merchant category." },
      { step: "Walk the gold notebook", detail: "Risk-flagging and segment portfolio logic." },
      { step: "Pivot to AI/ML", detail: "Fraud model metrics + per-transaction probability." },
    ],
    postDeploy: [
      { label: "Risk & Transaction Dashboard", detail: "3-page report. Open Fraud Analysis." },
      { label: "financial_analytics_model", detail: "Direct Lake model with fraud and risk measures." },
      { label: "Fraud predictions", detail: "Risk-ranked transactions from AI/ML gold_ml_predictions." },
    ],
  },

  "technology": {
    businessValue:
      "Subscription, usage, and support analytics for customer-success teams, with churn scoring to prioritise at-risk accounts.",
    talkingPoints: [
      "Product usage, billing, and support tickets in one account-360 view.",
      "Health-score and MRR roll up from the medallion pipeline.",
      "The AI/ML scenario predicts account churn to focus renewals.",
      "Feature importance shows why an account is at risk, not just a score.",
    ],
    sampleInsights: [
      { label: "Accounts", value: "2,000" },
      { label: "KPIs", value: "Churn rate · MRR · Health score · Usage" },
      { label: "AI/ML model", value: "Churn prediction · AUC 0.83" },
      { label: "Report pages", value: "Model · Churn Predictions · Industry Risk" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Subscription health and MRR overview." },
      { step: "Show usage signals", detail: "Engagement and support-ticket trends per account." },
      { step: "Pivot to AI/ML", detail: "Churn model + per-account probability and risk tier." },
      { step: "Show feature importance", detail: "Explain the top drivers of churn." },
    ],
    postDeploy: [
      { label: "Churn predictions", detail: "Risk-ranked accounts from AI/ML gold_ml_predictions." },
      { label: "Industry Risk page", detail: "Aggregated churn risk by industry." },
      { label: "predictions_model", detail: "Direct Lake model behind the churn report." },
    ],
  },

  "transportation": {
    businessValue:
      "Delivery, route, and fuel analytics for logistics teams, with a model that flags shipments likely to miss SLA.",
    talkingPoints: [
      "Delivery, vehicle, route, and fuel data in one lakehouse.",
      "On-time rate and cost-per-km come from the medallion pipeline.",
      "The AI/ML scenario predicts delivery delays for proactive dispatch.",
      "Per-depot risk turns predictions into an operational worklist.",
    ],
    sampleInsights: [
      { label: "Deliveries", value: "50,000" },
      { label: "KPIs", value: "On-time rate · Cost/km · Utilisation" },
      { label: "AI/ML model", value: "Delivery delay · AUC 0.84" },
      { label: "Report pages", value: "Model · Delay Predictions · Depot Risk" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Delivery performance and on-time trends." },
      { step: "Show depot risk", detail: "Depot Risk page, where delays concentrate." },
      { step: "Pivot to AI/ML", detail: "Delay model + per-delivery probability." },
      { step: "Show drivers", detail: "Feature importance, the top predictors of late delivery." },
    ],
    postDeploy: [
      { label: "Delay predictions", detail: "At-risk shipments from AI/ML gold_ml_predictions." },
      { label: "Depot Risk page", detail: "Aggregated delay risk by depot." },
      { label: "predictions_model", detail: "Direct Lake model behind the delay report." },
    ],
  },

  "hospitality": {
    businessValue:
      "RevPAR, occupancy, and satisfaction analytics, with cancellation prediction to protect revenue.",
    talkingPoints: [
      "Bookings, guests, properties, and reviews in one lakehouse.",
      "RevPAR, ADR, and occupancy roll up from the medallion pipeline.",
      "The AI/ML scenario predicts cancellations to guide overbooking.",
      "Channel-level risk shows which sources cancel most.",
    ],
    sampleInsights: [
      { label: "Bookings", value: "50,000" },
      { label: "KPIs", value: "RevPAR · ADR · Occupancy · Satisfaction" },
      { label: "AI/ML model", value: "Cancellation · AUC 0.80" },
      { label: "Report pages", value: "Model · Cancellation · Channel Risk" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Revenue & Occupancy, with RevPAR and ADR trends." },
      { step: "Show satisfaction", detail: "Guest Satisfaction and loyalty performance." },
      { step: "Pivot to AI/ML", detail: "Cancellation model + per-booking probability." },
      { step: "Show channel risk", detail: "Which channels drive the most cancellations." },
    ],
    postDeploy: [
      { label: "Cancellation predictions", detail: "At-risk bookings from AI/ML gold_ml_predictions." },
      { label: "Channel Risk page", detail: "Cancellation risk by booking channel." },
      { label: "predictions_model", detail: "Direct Lake model behind the cancellation report." },
    ],
  },

  "media": {
    businessValue:
      "Subscriber, content, and ad-revenue analytics, with completion prediction to drive recommendations.",
    talkingPoints: [
      "Subscribers, catalog, viewing history, and ad impressions in one lakehouse.",
      "Churn, ARPU, and completion metrics from the medallion pipeline.",
      "The AI/ML scenario predicts session completion at 200k-row scale.",
      "Genre-level engagement informs programming decisions.",
    ],
    sampleInsights: [
      { label: "Viewing records", value: "200,000" },
      { label: "KPIs", value: "Churn · ARPU · Completion rate · Ad revenue" },
      { label: "AI/ML model", value: "Content completion · AUC 0.77" },
      { label: "Report pages", value: "Model · Completion · Genre Engagement" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Subscriber health and ARPU overview." },
      { step: "Show content", detail: "Content performance top-10 and ad revenue." },
      { step: "Pivot to AI/ML", detail: "Completion model + per-session probability (200k rows)." },
      { step: "Show genre engagement", detail: "Which genres drive completion." },
    ],
    postDeploy: [
      { label: "Completion predictions", detail: "Engagement scoring from AI/ML gold_ml_predictions." },
      { label: "Genre Engagement page", detail: "Aggregated completion by genre." },
      { label: "predictions_model", detail: "Direct Lake model behind the completion report." },
    ],
  },

  "professional-services": {
    businessValue:
      "Margin, utilisation, and project-health analytics, with a model that flags engagements heading over budget.",
    talkingPoints: [
      "Clients, consultants, engagements, and timesheets in one lakehouse.",
      "Margin and utilisation roll up from the medallion pipeline.",
      "The AI/ML scenario predicts budget overruns early.",
      "Per-practice risk gives a portfolio-management view.",
    ],
    sampleInsights: [
      { label: "Engagements", value: "8,000" },
      { label: "KPIs", value: "Margin · Utilisation · Realisation" },
      { label: "AI/ML model", value: "Budget overrun · AUC 0.75" },
      { label: "Report pages", value: "Model · Overrun Predictions · Practice Risk" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Engagement margin and utilisation overview." },
      { step: "Show practice risk", detail: "Where overruns concentrate by practice." },
      { step: "Pivot to AI/ML", detail: "Overrun model + per-engagement probability." },
      { step: "Show drivers", detail: "Feature importance, the top predictors of an overrun." },
    ],
    postDeploy: [
      { label: "Overrun predictions", detail: "At-risk engagements from AI/ML gold_ml_predictions." },
      { label: "Practice Risk page", detail: "Aggregated overrun risk by practice." },
      { label: "predictions_model", detail: "Direct Lake model behind the overrun report." },
    ],
  },

  "construction": {
    businessValue:
      "Schedule, cost, and subcontractor analytics, with a model that flags tasks at risk of delay.",
    talkingPoints: [
      "Projects, tasks, cost ledger, and subcontractors in one lakehouse.",
      "Schedule variance and cost overrun roll up from the medallion pipeline.",
      "The AI/ML scenario predicts task delays for proactive re-sequencing.",
      "Per-trade risk gives a subcontractor-management view.",
    ],
    sampleInsights: [
      { label: "Tasks", value: "15,000" },
      { label: "KPIs", value: "Schedule variance · Cost overrun · On-time %" },
      { label: "AI/ML model", value: "Task delay · AUC 0.78" },
      { label: "Report pages", value: "Model · Delay Predictions · Trade Risk" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Portfolio schedule and cost overview." },
      { step: "Show trade risk", detail: "Where delays concentrate by trade." },
      { step: "Pivot to AI/ML", detail: "Delay model + per-task probability." },
      { step: "Show drivers", detail: "Feature importance, the top predictors of a delay." },
    ],
    postDeploy: [
      { label: "Delay predictions", detail: "At-risk tasks from AI/ML gold_ml_predictions." },
      { label: "Trade Risk page", detail: "Aggregated delay risk by subcontractor trade." },
      { label: "predictions_model", detail: "Direct Lake model behind the delay report." },
    ],
  },

  "education": {
    businessValue:
      "Enrolment, assessment, and outcome analytics, with a model that flags students at risk of dropping out.",
    talkingPoints: [
      "Students, enrolments, assessments, and faculty in one lakehouse.",
      "Dropout rate and outcome KPIs roll up from the medallion pipeline.",
      "The AI/ML scenario predicts dropout risk for early intervention.",
      "Explainable features suit academic stakeholders.",
    ],
    sampleInsights: [
      { label: "Enrolments", value: "24,000" },
      { label: "KPIs", value: "Dropout rate · Pass rate · Outcomes" },
      { label: "AI/ML model", value: "Dropout risk · AUC 0.80" },
      { label: "Report pages", value: "Model · Dropout Predictions · Department Risk" },
    ],
    demoFlow: [
      { step: "Open the report", detail: "Enrolment and outcome overview." },
      { step: "Show department risk", detail: "Where dropout risk concentrates." },
      { step: "Pivot to AI/ML", detail: "Dropout model + per-enrolment probability." },
      { step: "Show drivers", detail: "Feature importance, the top predictors of dropout." },
    ],
    postDeploy: [
      { label: "Dropout predictions", detail: "At-risk students from AI/ML gold_ml_predictions." },
      { label: "Department Risk page", detail: "Aggregated dropout risk by department." },
      { label: "predictions_model", detail: "Direct Lake model behind the dropout report." },
    ],
  },
};
