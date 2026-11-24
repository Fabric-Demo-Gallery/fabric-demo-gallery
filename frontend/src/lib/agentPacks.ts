// Catalog of AI agent packs: general Microsoft Foundry agents grounded on an
// industry's demo data, deployed into the user's Azure subscription and used in
// the Foundry agent playground. The deploy spec (instructions, knowledge, data
// files, model fallbacks) lives in demos/_agents/<pack>/pack.json - keep the
// pack and agent ids in sync. generateStaticParams() in
// app/ai-agents/[industry]/page.tsx derives from AGENT_PACKS.

export type AgentTool = "File Search" | "Code Interpreter" | "Vision";

export interface PackAgent {
  id: string;
  title: string;
  description: string;
  tools: AgentTool[];
  /** Grounding the agent gets at deploy time. */
  grounding: string;
  /** Showcase questions to paste into the playground. */
  prompts: string[];
  /** Downloadable sample inputs under /ai-agents/<pack>/. */
  samples?: { fileName: string; label: string }[];
}

export interface AgentPack {
  id: string;
  industrySlug: string;
  title: string;
  description: string;
  longDescription: string;
  estimatedTime: string;
  agents: PackAgent[];
}

export const AGENT_PACK_PREREQUISITES = [
  "Azure subscription where you are Owner, or Contributor + User Access Administrator (you get the 'Azure AI User' role on the new Foundry account)",
  "GlobalStandard quota for gpt-5.4-mini, gpt-5.4 or gpt-4.1-mini in the chosen region",
  "Pay-per-use only: model tokens, Code Interpreter sessions and a few MB of File Search storage. Nothing runs when you are not chatting.",
];

export const AGENT_PACK_RESOURCES = [
  "A dedicated resource group (deleting it removes everything)",
  "A Microsoft Foundry account and project with one model deployment",
  "The agents, their knowledge indexes (File Search) and the plant data files (Code Interpreter)",
  "An 'Azure AI User' role assignment for you, so you can chat with the agents in the Foundry playground",
];

export const AGENT_PACKS: Record<string, AgentPack> = {
  manufacturing: {
    id: "manufacturing",
    industrySlug: "manufacturing",
    title: "Manufacturing AI Agents",
    description:
      "Four Microsoft Foundry agents for the shop floor - maintenance, quality root cause, shift handover and visual inspection - grounded on plant data and documents.",
    longDescription:
      "One click deploys a Microsoft Foundry project with four ready-to-demo agents. They work on the same plant data as the Manufacturing Fabric demo (50 machines, 5 lines, 45 days of production batches and 100,000 sensor readings) and on a small synthetic plant handbook: alarm codes, sensor limits, maintenance plan, lockout/tagout and the quality inspection standard. Each agent shows a different pattern: retrieval over documents, Python analysis with charts, structured reporting, and vision.",
    estimatedTime: "5-8 min",
    agents: [
      {
        id: "maintenance-assistant",
        title: "Maintenance Assistant",
        description:
          "Diagnoses machine alarms by combining the alarm code reference with the machine's real sensor history, and plans preventive maintenance.",
        tools: ["File Search", "Code Interpreter"],
        grounding: "Alarm codes, sensor limits, PM plan, lockout/tagout + equipment, batch and sensor data",
        prompts: [
          "MCH-0002 is showing alarm SP-214. What does it mean, what should I check first, and how has this machine been running over the last 7 days?",
          "Which five machines should get preventive maintenance first next week, and why?",
          "What is the lockout/tagout procedure before I reach into the die area of a stamping press?",
        ],
      },
      {
        id: "quality-analyst",
        title: "Quality Root-Cause Analyst",
        description:
          "Answers 'why' questions about defects, yield and failures with Python analysis and charts - and is happy to disprove a common belief.",
        tools: ["Code Interpreter", "File Search"],
        grounding: "Production batches, equipment catalog, sensor readings + sensor limits and quality standard",
        prompts: [
          "Does the night shift really produce more defects than the other shifts? Test it, and tell me what actually drives the defect rate.",
          "Why does Line-B have the most defects? Show me a chart.",
          "How does machine age affect failure events? Break it down by machine type.",
        ],
      },
      {
        id: "shift-handover",
        title: "Shift Handover Reporter",
        description:
          "Turns the last shift's production, downtime, failures and sensor alerts into a two-minute handover with prioritized actions.",
        tools: ["Code Interpreter"],
        grounding: "Production batches, equipment catalog and sensor readings, with the plant's sensor limits and reporting rules built in",
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
          "Review this drawing against our drawing checklist. What's missing before release?",
          "Classify the visible defects on this part and decide accept or reject per our standard.",
        ],
        samples: [
          { fileName: "bracket-holder.png", label: "Bracket holder drawing" },
          { fileName: "adapter-plate.png", label: "Adapter plate drawing" },
          { fileName: "shaft-collar.png", label: "Shaft collar drawing" },
        ],
      },
    ],
  },
};

export function agentPackForIndustry(slug: string): AgentPack | undefined {
  return Object.values(AGENT_PACKS).find((p) => p.industrySlug === slug);
}
