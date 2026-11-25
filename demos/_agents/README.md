# AI agent packs

An agent pack is a set of Microsoft Foundry agents for one industry, grounded on
that industry's demo data and a small synthetic document set. The gallery
deploys a pack into the user's Azure subscription. Besides the agents, a pack can
deploy a small environment around them:

- **Actions**: a simulated plant maintenance system (CMMS) that the agents call
  through an OpenAPI tool to create work orders and quality holds.
- **Incident workflow**: an Azure Logic Apps (Consumption) workflow that chains
  the agents from detection to shift handover and waits for a human approval.
  It replaces Foundry workflows, which retire on 1 December 2026.
- **Observability**: Application Insights tracing for every agent and tool call,
  and on-demand Foundry evaluations.

No containers, images, or Fabric capacity are involved, and everything is
billed per use.

## Manufacturing

| Agent | Tools | Grounding |
| --- | --- | --- |
| `maintenance-assistant` | File Search + Code Interpreter + plant system (`createWorkOrder`, `getBoard`) | Alarm codes, sensor limits, PM plan, lockout/tagout, work order procedure; equipment, batch and sensor data |
| `quality-analyst` | Code Interpreter + File Search + plant system (`placeQualityHold`, `getBoard`) | Batch, equipment and sensor data; sensor limits, quality standard and hold procedure |
| `shift-handover` | Code Interpreter + plant system (`getBoard`, read-only) | Batch, equipment and sensor data (limits embedded in the instructions) |
| `visual-inspector` | Vision + File Search | Quality inspection standard and drawing checklist |

The data files are reused from [`../manufacturing-qc/data`](../manufacturing-qc/data):
50 machines, 5 lines, 45 days. Machine age and type drive failures; shift
barely matters, which the quality analyst can show. The documents in
[`manufacturing/knowledge`](manufacturing/knowledge) are synthetic, and their
limits are derived from the data's percentiles.

### Incident workflow

[`incident.workflow.json`](manufacturing/infra/incident.workflow.json) runs on a
defect-spike report (line, shift, date, optional part photo):

1. **Triage** (`quality-analyst`): compares the shift with the line's normal
   level, names the machine and classifies the batches (hold / watch / normal).
   A second turn places a quality hold for each hold-level batch.
2. **Inspection** (`visual-inspector`, only with a photo): defects, severity and
   verdict.
3. **Diagnosis** (`maintenance-assistant`): sensor history, age and failures,
   then a proposed work order.
4. **Approval**: the workflow stops until the user approves or rejects the work
   order in the gallery.
5. **Work order** (`maintenance-assistant`): creates the approved work order.
6. **Handover** (`shift-handover`): the shift handover with an incident section
   and the open records from the plant system.

Each agent call uses the Responses API in background mode with the workflow's
managed identity. Structured fields (machine, hold batches, work order draft)
are extracted with a separate model call, because structured output can't be
combined with an agent reference. The steps that must act (holds, work order)
use `tool_choice: required` and are retried when the agent did not call the
operation. Failed agent runs, for example under a token rate limit, are retried
up to three times.

## Layout

```text
_agents/<pack>/
  pack.json            # regions, model fallbacks, data files, agents, infra, evaluations, incident steps
  instructions/*.md    # one system prompt per agent
  knowledge/*.md       # documents indexed for File Search
  infra/               # optional: Bicep template, Logic Apps definitions, OpenAPI spec
```

`pack.json` fields:

- `dataFiles`: maps a file name to a path under `demos/`. It is uploaded once and
  attached to every agent that lists it in `data` (Code Interpreter).
- `agents[].knowledge`: documents put into that agent's own vector store
  (File Search). Leave it empty for a data-only agent.
- `agents[].actions`: operations of the plant system OpenAPI spec the agent may
  call.
- `infra`: the ARM template (`main.json`, built from `main.bicep`), the OpenAPI
  spec and the resource providers to register.
- `evaluations`: test questions per agent for Foundry evaluations.
- `incident`: maps each incident step shown in the gallery to the workflow
  actions it watches and the outputs it shows.
- `modelCandidates`: deployed in order of available GlobalStandard quota in the
  chosen region. All candidates must support Code Interpreter, File Search and
  image input.

After editing the workflow generator or the Bicep file, rebuild both:

```bash
cd demos/_agents/manufacturing/infra
python build_incident_workflow.py
az bicep build --file main.bicep --outfile main.json
```

The frontend display text, tool badges, "try asking" prompts and presenter script
are in [`frontend/src/lib/agentPacks.ts`](../../frontend/src/lib/agentPacks.ts). Keep the ids in sync.

## How a deployment works

[`backend/app/agent_packs.py`](../../backend/app/agent_packs.py) runs it as a job
(about 3-5 minutes):

1. **Pre-flight.** The caller needs `resourceGroups/write` and
   `roleAssignments/write` (Owner, or Contributor + User Access Administrator),
   and the region needs GlobalStandard quota for at least one model candidate.
2. **Resource group.** It creates a new, dedicated resource group
   `rg-fdg-agents-<pack>-<random>`.
3. **Foundry.** It creates the account and project, then deploys the model at
   300K tokens/min, so parallel agent runs and evaluations don't throttle each
   other. GlobalStandard is billed per token, so capacity costs nothing extra.
4. **Infrastructure.** It starts the pack's ARM template, which runs while the
   knowledge is uploaded: a storage account (tables for the plant system), the
   plant system and incident Logic Apps, Log Analytics, Application Insights
   (connected to the project for tracing), the project connection that holds the
   plant system key, and managed identity role assignments.
5. **Access.** The caller gets **Azure AI User** on the account. This role
   allows the data-plane calls below and chatting in the playground.
6. **Data plane.** It uploads the files and creates the vector stores and
   prompt agents (with the OpenAPI tool for agents that have `actions`), using the
   caller's delegated `ai.azure.com` token (the gallery already requests this
   scope). Account keys are not used, because many tenants disable local auth.
7. **Verify.** A tiny model request is retried until the fresh deployment stops
   returning 429, and the plant system is called once.

Any failure deletes the resource group. Monitoring's **Delete** deletes it later.

After the deployment, the gallery page runs incidents, records approvals, shows
the plant system board and runs evaluations (task adherence, intent resolution
and tool call accuracy) through `/api/agent-packs/jobs/{job_id}/...`.

## Costs

Everything is pay-per-use: model tokens (most of an incident's cost; Code
Interpreter sessions are billed separately), Logic Apps Consumption actions, table
storage and Application Insights ingestion. An idle deployment costs close to nothing; delete the resource group
when the demo is over.

## Adding a pack for another industry

1. Create `_agents/<industry-slug>/` with `pack.json`, instructions and knowledge.
   Point `dataFiles` at that industry's CSVs.
2. Add a matching entry to `AGENT_PACKS` in `frontend/src/lib/agentPacks.ts`.
   The id must equal the industry slug.
3. Add `/ai-agents/<industry-slug>/` to `frontend/public/sitemap.xml`.
4. Run `python -m unittest discover -s tests` in `backend/`. The pack tests check
   that every file resolves.
