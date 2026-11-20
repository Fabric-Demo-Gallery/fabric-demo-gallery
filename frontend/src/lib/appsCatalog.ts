// Catalog of Apps & AI demos: AI applications that run in the user's Azure
// subscription (Microsoft Foundry models on Azure Container Apps) instead of
// a Fabric workspace. Deployment specs (images, ports, model fallbacks) live
// in the backend catalog demos/_apps/apps.json - keep the ids in sync.
// generateStaticParams() in app/apps/[id]/page.tsx derives from APPS.

export interface AppDemo {
  id: string;
  industrySlug: string;
  title: string;
  description: string;
  longDescription: string;
  estimatedTime: string;
  /** UI language note shown on the page (several apps are German-first). */
  language: string;
  businessValue: string;
  talkingPoints: string[];
  demoFlow: { step: string; detail: string }[];
  architecture: string[];
  /** Downloadable sample inputs shipped under /apps-ai/<id>/. */
  samples?: { fileName: string; label: string }[];
  sourcePath: string;
}

export const APP_PREREQUISITES = [
  "Azure subscription where you are Owner, or Contributor + User Access Administrator (the app's managed identity gets a role on the Foundry account)",
  "GlobalStandard quota for one of the app's models in the chosen region",
  "Billable resources: Microsoft Foundry (pay per token) and two always-on Container Apps (about 1 vCPU / 2 GiB in total) - delete the resource group when you are done",
];

export const APP_RESOURCES = [
  "Dedicated resource group (deleting it removes everything)",
  "Microsoft Foundry account, project, and model deployment",
  "Azure Container Apps environment with a public frontend and an internal-only backend",
  "Log Analytics workspace and Application Insights (GenAI traces)",
  "Role assignments so the backend's managed identity can call the model - no keys or secrets",
];

export const APPS: Record<string, AppDemo> = {
  "technical-drawing-analysis": {
    id: "technical-drawing-analysis",
    industrySlug: "manufacturing",
    title: "Technical Drawing Analysis",
    description:
      "Extract title block fields, dimensions, tolerances, surface finish, and GD&T from engineering drawings with a multimodal model.",
    longDescription:
      "Upload a manufacturing drawing (or pick one of the built-in neutral samples) and a multimodal Foundry model turns it into structured review data: title block fields, dimensions with tolerances, surface finish, GD&T callouts, notes, and review flags - each linked back to where it appears on the drawing.",
    estimatedTime: "10-15 min",
    language: "German and English sample drawings; UI follows the selected language.",
    businessValue:
      "Drawing review and quoting are slow, expert-bound steps. Structured extraction gives engineers and purchasers a checked starting point in seconds instead of re-keying every dimension.",
    talkingPoints: [
      "A real multimodal model reads the drawing - there is no fake or offline path.",
      "Every extracted value is grounded on the image, so reviewers can verify it at a glance.",
      "Runs entirely in your subscription; the backend calls Foundry with a managed identity, no API keys.",
    ],
    demoFlow: [
      { step: "Open a sample drawing", detail: "Pick the bracket holder, adapter plate, or shaft collar sample." },
      { step: "Run the analysis", detail: "Show the title block, dimensions, tolerances, and GD&T the model extracts." },
      { step: "Review the flags", detail: "Walk through the review flags and how values map back to the drawing." },
      { step: "Show the traces", detail: "Open Application Insights or the Foundry project to show the model calls." },
    ],
    architecture: [
      "Browser -> public Container App (React + Express proxy)",
      "-> internal-only Container App (FastAPI)",
      "-> Microsoft Foundry multimodal model (managed identity)",
    ],
    sourcePath: "apps-ai/technical-drawing-analysis",
  },
  "delivery-note-extraction": {
    id: "delivery-note-extraction",
    industrySlug: "manufacturing",
    title: "Delivery Note Extraction",
    description:
      "Capture scanned supplier delivery notes at goods receipt: OCR plus a multimodal model, grounded fields, and a review workflow.",
    longDescription:
      "Upload a scanned delivery note (PDF). Azure Document Intelligence (layout/OCR) and a multimodal Foundry model run in parallel; the model returns header and line items with confidences, alternatives, and handwritten corrections, and every field is mapped back to its location in the scan for a fast review-and-correct workflow.",
    estimatedTime: "10-15 min",
    language: "German UI (built for DACH goods-receipt teams).",
    businessValue:
      "Goods receipt still re-types paper delivery notes. Grounded extraction with confidences lets clerks review only what's uncertain, cutting capture time and booking errors.",
    talkingPoints: [
      "OCR and LLM extraction run in parallel - the progress bar shows the measured latency of each step.",
      "Low-confidence fields offer up to three alternative readings; one click accepts a correction.",
      "Ambiguous matches are shown as such instead of silently picking one location.",
      "Pick a different model or reasoning effort per request to compare speed and accuracy.",
    ],
    demoFlow: [
      { step: "Bring a sample", detail: "Use a scanned delivery note PDF you are allowed to show - the app is upload-only and ships no scans." },
      { step: "Upload and watch", detail: "Drop the PDF in and narrate the parallel OCR + model pipeline." },
      { step: "Review fields", detail: "Hover fields to highlight them in the scan; accept an alternative for a flagged value." },
      { step: "Compare models", detail: "Rerun with another model or reasoning effort to discuss cost versus accuracy." },
    ],
    architecture: [
      "Browser -> public Container App (React + Express proxy)",
      "-> internal-only Container App (FastAPI)",
      "-> Document Intelligence prebuilt-layout + Foundry multimodal model (managed identity)",
    ],
    sourcePath: "apps-ai/delivery-note-extraction",
  },
  "demand-portfolio-planning": {
    id: "demand-portfolio-planning",
    industrySlug: "manufacturing",
    title: "Demand Portfolio Planning",
    description:
      "An agentic, human-in-the-loop funnel from business demand to project plan, with explainable prioritization and provenance on every fact.",
    longDescription:
      "A business demand moves through intake, a PRINCE2 Agile readiness pre-check, board decision, portfolio fit, resource matching, and timeline planning - built on Microsoft Agent Framework workflows and Foundry models. Three human gates pause the workflow; nothing is auto-approved. Every fact carries provenance (fact, assumption, open question, generated, unknown) and a portfolio roadmap sequences the backlog.",
    estimatedTime: "10-15 min",
    language: "Bilingual German / English (German by default; switch in the UI).",
    businessValue:
      "The bottleneck is after the board: 70 ideas, 3 people - in which order? The agent makes resource allocation and sequencing transparent while keeping people in charge of every decision.",
    talkingPoints: [
      "Human-in-the-loop by design: three gates use Agent Framework request_info to suspend the workflow.",
      "A trust contract you can see - provenance pills separate facts from assumptions and open questions.",
      "Prioritization is a deterministic, explainable score; the model only narrates it.",
      "Built-in synthetic systems of record, so the demo works right after deployment.",
    ],
    demoFlow: [
      { step: "Pick a demand", detail: "Start a run from one of the seeded business demands." },
      { step: "Pre-check gate", detail: "Walk through the PRINCE2 readiness themes and supply missing information." },
      { step: "Board and planning", detail: "Approve at the board gate, then show portfolio fit, resource match, and the plan." },
      { step: "Roadmap", detail: "Open the Roadmap tab to show how the new demand is sequenced against the backlog." },
    ],
    architecture: [
      "Browser -> public Container App (React + Express proxy)",
      "-> internal-only Container App (FastAPI + Agent Framework workflow, SSE)",
      "-> Microsoft Foundry chat model (managed identity)",
    ],
    sourcePath: "apps-ai/demand-portfolio-planning",
  },
};

export function appsForIndustry(slug: string): AppDemo[] {
  return Object.values(APPS).filter((a) => a.industrySlug === slug);
}
