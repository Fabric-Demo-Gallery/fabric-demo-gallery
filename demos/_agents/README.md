# AI agent packs

An agent pack is a set of Microsoft Foundry agents for one industry, grounded on
that industry's demo data and a small synthetic document set. The gallery
deploys a pack into the user's Azure subscription; users chat with the agents in
the Foundry agent playground. No containers, images, or Fabric capacity are
involved.

## Manufacturing

| Agent | Tools | Grounding |
| --- | --- | --- |
| `maintenance-assistant` | File Search + Code Interpreter | Alarm codes, sensor limits, PM plan, lockout/tagout; equipment, batch and sensor data |
| `quality-analyst` | Code Interpreter + File Search | Batch, equipment and sensor data; sensor limits and quality standard |
| `shift-handover` | Code Interpreter | Batch, equipment and sensor data (limits embedded in the instructions) |
| `visual-inspector` | Vision + File Search | Quality inspection standard and drawing checklist |

The data files are reused from [`../manufacturing-qc/data`](../manufacturing-qc/data):
50 machines, 5 lines, 45 days. Machine age and type drive failures; shift
barely matters, which the quality analyst can show. The documents in
[`manufacturing/knowledge`](manufacturing/knowledge) are synthetic, and their
limits are derived from the data's percentiles.

## Layout

```text
_agents/<pack>/
  pack.json            # regions, model fallbacks, data files, agents
  instructions/*.md    # one system prompt per agent
  knowledge/*.md       # documents indexed for File Search
```

`pack.json` fields:

- `dataFiles`: maps a file name to a path under `demos/`. It is uploaded once and
  attached to every agent that lists it in `data` (Code Interpreter).
- `agents[].knowledge`: documents put into that agent's own vector store
  (File Search). Leave it empty for a data-only agent.
- `modelCandidates`: deployed in order of available GlobalStandard quota in the
  chosen region. All candidates must support Code Interpreter, File Search and
  image input.

The frontend display text, tool badges, and "try asking" prompts are in
[`frontend/src/lib/agentPacks.ts`](../../frontend/src/lib/agentPacks.ts). Keep the ids in sync.

## How a deployment works

[`backend/app/agent_packs.py`](../../backend/app/agent_packs.py) runs it as a job:

1. **Pre-flight.** The caller needs `resourceGroups/write` and
   `roleAssignments/write` (Owner, or Contributor + User Access Administrator),
   and the region needs GlobalStandard quota for at least one model candidate.
2. **Resource group.** It creates a new, dedicated resource group
   `rg-fdg-agents-<pack>-<random>`.
3. **Foundry.** It creates the account and project, then deploys the model at
   150K tokens/min. GlobalStandard is billed per token, so capacity costs nothing
   extra.
4. **Access.** The caller gets **Azure AI User** on the account. This role
   allows the data-plane calls below and chatting in the playground.
5. **Data plane.** It uploads the files and creates the vector stores and
   prompt agents, using the caller's delegated `ai.azure.com` token (the
   gallery already requests this scope). Account keys are not used, because many
   tenants disable local auth.
6. **Warm-up.** A tiny model request is retried until the fresh deployment stops
   returning 429.

Any failure deletes the resource group. Monitoring's **Delete** deletes it later.

## Adding a pack for another industry

1. Create `_agents/<industry-slug>/` with `pack.json`, instructions and knowledge.
   Point `dataFiles` at that industry's CSVs.
2. Add a matching entry to `AGENT_PACKS` in `frontend/src/lib/agentPacks.ts`.
   The id must equal the industry slug.
3. Add `/ai-agents/<industry-slug>/` to `frontend/public/sitemap.xml`.
4. Run `python -m unittest discover -s tests` in `backend/`. The pack tests check
   that every file resolves.
