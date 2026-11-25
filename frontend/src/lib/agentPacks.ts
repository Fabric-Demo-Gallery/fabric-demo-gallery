// Catalog of AI agent packs: general Microsoft Foundry agents grounded on an
// industry's demo data, deployed into the user's Azure subscription and used in
// the Foundry agent playground and in a guided multi-agent incident. The deploy
// spec (instructions, knowledge, data files, actions, workflow, evaluations,
// model fallbacks) lives in demos/_agents/<pack>/pack.json - keep the pack and
// agent ids in sync. generateStaticParams() in app/ai-agents/[industry]/page.tsx
// derives from AGENT_PACKS.

export type AgentTool = "File Search" | "Code Interpreter" | "Vision" | "Actions";

export interface PackAgent {
  id: string;
  title: string;
  description: string;
  tools: AgentTool[];
  /** Grounding the agent gets at deploy time. */
  grounding: string;
  /** What the agent can do in the plant system (its OpenAPI actions). */
  actions?: string;
  /** Showcase questions to paste into the playground. */
  prompts: string[];
  /** Downloadable sample inputs under /ai-agents/<pack>/. */
  samples?: { fileName: string; label: string }[];
}

export interface IncidentScenario {
  title: string;
  summary: string;
  line: string;
  shift: "night" | "day" | "evening";
  date: string;
  /** Part photos under /ai-agents/<pack>/ the presenter can send with the incident. */
  photos: { fileName: string; label: string }[];
  /** How the workflow runs, in order (shown before and during the run). */
  flow: string[];
}

export interface AgentPack {
  id: string;
  industrySlug: string;
  title: string;
  description: string;
  longDescription: string;
  estimatedTime: string;
  agents: PackAgent[];
  incident?: IncidentScenario;
  /** Talk track for a live demo, in order. */
  presenterScript?: { title: string; minutes: number; say: string; do: string }[];
}

export const AGENT_PACK_PREREQUISITES = [
  "Azure subscription where you are Owner, or Contributor + User Access Administrator (you get the 'Azure AI User' role on the new Foundry account, and the workflows get least-privilege roles)",
  "GlobalStandard quota for gpt-5.4-mini, gpt-5.4 or gpt-4.1-mini in the chosen region",
  "Pay-per-use only: model tokens, Code Interpreter sessions, Logic Apps runs (fractions of a cent each), a few MB of storage and tracing data. Nothing runs when you are not demoing.",
];

export const AGENT_PACK_RESOURCES = [
  "A dedicated resource group (deleting it removes everything)",
  "A Microsoft Foundry account and project with one model deployment",
  "The agents, their knowledge indexes (File Search) and the plant data files (Code Interpreter)",
  "A simulated plant maintenance system (a Logic App and storage tables) the agents create work orders and quality holds in",
  "The incident response workflow (a Logic App) that orchestrates the agents, with a human approval step",
  "Application Insights for agent tracing, and agent evaluations you can run from this page",
  "An 'Azure AI User' role assignment for you, so you can chat with the agents in the Foundry playground",
];

export const AGENT_PACKS: Record<string, AgentPack> = {
  manufacturing: {
    id: "manufacturing",
    industrySlug: "manufacturing",
    title: "Manufacturing AI Agents",
    description:
      "Four Microsoft Foundry agents for the shop floor that analyze plant data, act in a maintenance system and work together in an incident workflow with human approval - with tracing and evaluations.",
    longDescription:
      "One click deploys a Microsoft Foundry project with four agents and everything around them. The agents work on the same plant data as the Manufacturing Fabric demo (50 machines, 5 lines, 45 days of production batches and 100,000 sensor readings) and on a synthetic plant handbook. They don't only answer: they create work orders and quality holds in a simulated maintenance system. An incident workflow (Azure Logic Apps) chains the agents from detection to shift handover and stops for your approval. All agent calls are traced in Application Insights, and the agents are scored by Foundry evaluations.",
    estimatedTime: "5-8 min",
    agents: [
      {
        id: "maintenance-assistant",
        title: "Maintenance Assistant",
        description:
          "Diagnoses machine alarms by combining the alarm code reference with the machine's real sensor history, plans preventive maintenance and raises work orders.",
        tools: ["File Search", "Code Interpreter", "Actions"],
        grounding: "Alarm codes, sensor limits, PM plan, lockout/tagout, work order procedure + equipment, batch and sensor data",
        actions: "Creates work orders and reads the open work orders in the plant maintenance system",
        prompts: [
          "MCH-0002 is showing alarm SP-214. What does it mean, what should I check first, and how has this machine been running over the last 7 days?",
          "Which five machines should get preventive maintenance first next week, and why?",
          "Raise a work order for the most urgent of them, following our work order procedure.",
          "What is the lockout/tagout procedure before I reach into the die area of a stamping press?",
        ],
      },
      {
        id: "quality-analyst",
        title: "Quality Root-Cause Analyst",
        description:
          "Answers 'why' questions about defects, yield and failures with Python analysis and charts, disproves common beliefs, and places quality holds when the procedure requires it.",
        tools: ["Code Interpreter", "File Search", "Actions"],
        grounding: "Production batches, equipment catalog, sensor readings + sensor limits, quality standard and quality hold procedure",
        actions: "Places quality holds on batches and reads the open holds",
        prompts: [
          "Does the night shift really produce more defects than the other shifts? Test it, and tell me what actually drives the defect rate.",
          "Why does Line-B have the most defects? Show me a chart.",
          "Which batches of 2025-03-17 need a quality hold under our procedure? Place the holds.",
        ],
      },
      {
        id: "shift-handover",
        title: "Shift Handover Reporter",
        description:
          "Turns the last shift's production, downtime, failures, sensor alerts and open work orders into a two-minute handover with prioritized actions.",
        tools: ["Code Interpreter", "Actions"],
        grounding: "Production batches, equipment catalog and sensor readings, with the plant's sensor limits and reporting rules built in",
        actions: "Reads the open work orders and quality holds (read-only)",
        prompts: [
          "Write the handover for the last shift on Line-B.",
          "Summarize the last 24 hours across all lines for the morning production meeting.",
        ],
      },
      {
        id: "visual-inspector",
        title: "Visual Inspection Assistant",
        description:
          "Classifies defects in part photos and reviews engineering drawings against the plant's inspection standard and drawing checklist.",
        tools: ["Vision", "File Search"],
        grounding: "Quality inspection standard and drawing review checklist",
        prompts: [
          "Classify the visible defects on this weld and decide accept or reject per our standard.",
          "Review this drawing against our drawing checklist. What's missing before release?",
        ],
        samples: [
          { fileName: "weld-porosity.jpg", label: "Weld with porosity and spatter (photo)" },
          { fileName: "weld-good.jpg", label: "Good weld (photo)" },
          { fileName: "bracket-holder.png", label: "Bracket holder drawing" },
          { fileName: "adapter-plate.png", label: "Adapter plate drawing" },
          { fileName: "shaft-collar.png", label: "Shaft collar drawing" },
        ],
      },
    ],
    incident: {
      title: "Incident: defect spike on Line-B",
      summary:
        "Production reports a defect spike on the Line-B evening shift of 2025-03-17 and sends a photo of a welded part. A Logic Apps workflow hands the incident from agent to agent and waits for your approval before anything is changed on the machine.",
      line: "Line-B",
      shift: "evening",
      date: "2025-03-17",
      photos: [
        { fileName: "weld-porosity.jpg", label: "Defective weld" },
        { fileName: "weld-good.jpg", label: "Good weld" },
      ],
      flow: [
        "Quality Root-Cause Analyst finds the machine and batches behind the spike and places quality holds",
        "Visual Inspection Assistant classifies the defects in the part photo",
        "Maintenance Assistant diagnoses the machine and proposes a work order",
        "You approve or reject the work order",
        "Maintenance Assistant creates the approved work order in the maintenance system",
        "Shift Handover Reporter writes the handover, including the incident and the open work orders",
      ],
    },
    presenterScript: [
      {
        title: "Set the scene",
        minutes: 1,
        say: "A plant with 50 machines on 5 lines. The data is the same as in the Fabric demo; the agents add reasoning and action on top of it.",
        do: "Show the four agent cards and the tools each one has.",
      },
      {
        title: "One agent, real analysis",
        minutes: 2,
        say: "The Quality Analyst doesn't guess - it runs Python on the data and is happy to disprove a belief.",
        do: "In Foundry, ask the Quality Analyst whether the night shift really produces more defects. Show the code and the chart.",
      },
      {
        title: "Start the incident",
        minutes: 1,
        say: "Now something goes wrong on Line-B. Instead of one chatbot, a workflow hands the incident from specialist to specialist.",
        do: "Click Start incident with the defective weld photo. Walk through the steps as they light up.",
      },
      {
        title: "Agents that act - with a human in the loop",
        minutes: 2,
        say: "The Quality Analyst placed a hold on the worst batch by itself, following the procedure. The Maintenance Assistant only proposes the work order: changes to the machine need a supervisor.",
        do: "Open the triage result, then approve the proposed work order. Show it appear on the maintenance board.",
      },
      {
        title: "Handover",
        minutes: 1,
        say: "The incoming shift gets one handover with the incident, the hold and the work order - from live records, not from memory.",
        do: "Open the final handover.",
      },
      {
        title: "Trust: tracing and evaluations",
        minutes: 2,
        say: "Every agent call and tool call is traced, and each agent is scored on a test set before anyone relies on it.",
        do: "Before the demo, click Run evaluations. Now show the scores and open the report, then open tracing in Application Insights or the agent's Traces tab in Foundry.",
      },
      {
        title: "Under the hood",
        minutes: 1,
        say: "The workflow is a Logic App - one of the recommended replacements for Foundry workflows, which retire in December 2026 - and the maintenance system is an OpenAPI tool. Both run pay-per-use in your own resource group.",
        do: "Open the workflow in the Azure portal designer.",
      },
    ],
  },
};

export function agentPackForIndustry(slug: string): AgentPack | undefined {
  return Object.values(AGENT_PACKS).find((p) => p.industrySlug === slug);
}
