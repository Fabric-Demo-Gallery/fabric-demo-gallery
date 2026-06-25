"""Deployment orchestrator — reads a demo manifest and provisions all Fabric items."""

from __future__ import annotations

import asyncio
import base64
import csv as _csv
import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from app.fabric_client import FabricClient, FabricError, ONELAKE_API
from app.report_builder import (
    build_manufacturing_report_definition,
    build_retail_report_definition,
    build_energy_report_definition,
    build_energy_ml_report_definition,
    build_manufacturing_ml_report_definition,
    build_retail_ml_report_definition,
    build_financial_ml_report_definition,
    build_healthcare_ml_report_definition,
    build_technology_ml_report_definition,
    build_transportation_ml_report_definition,
    build_hospitality_ml_report_definition,
    build_media_ml_report_definition,
    build_professional_services_ml_report_definition,
    build_construction_ml_report_definition,
    build_education_ml_report_definition,
)
from app.report_generic import (
    build_generic_model_definition,
    build_generic_report_definition,
)
from app.azure_client import AzureClient, AzureError

logger = logging.getLogger(__name__)

# In dev: backend/app/deployer.py → ../../demos
# On Azure: /home/site/wwwroot/app/deployer.py → ../demos (demos/ is sibling of app/)
_APP_DIR = Path(__file__).resolve().parent.parent  # backend/ or wwwroot/
DEMOS_DIR = _APP_DIR.parent / "demos" if (_APP_DIR.parent / "demos").exists() else _APP_DIR / "demos"

# ── Real-Time Intelligence: build a KQL schema script that creates the table
#    and seeds a sample of CSV rows via `.ingest inline` (runs under the Fabric
#    token during KQL database provisioning — no Spark, no Kusto token needed).
_RTI_MAX_SEED_ROWS = 5000
_RTI_MAX_SEED_BYTES = 2 * 1024 * 1024  # ~2 MB of inline data keeps the definition payload small
_DT_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def _looks_datetime(v: str) -> bool:
    for fmt in _DT_FORMATS:
        try:
            datetime.strptime(v, fmt)
            return True
        except ValueError:
            continue
    return False


def _sanitize_column_name(name: str) -> str:
    """Make a CSV header a valid Kusto column identifier."""
    cleaned = "".join(c if (c.isalnum() or c == "_") else "_" for c in name.strip())
    if not cleaned:
        cleaned = "col"
    if not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = "_" + cleaned
    return cleaned


def _infer_kusto_type(values: list[str], col_name: str, timestamp_col: str) -> str:
    """Infer a Kusto column type from a sample of string values."""
    if timestamp_col and col_name == timestamp_col:
        return "datetime"
    seen = False
    is_long = is_real = is_bool = is_datetime = True
    for raw in values:
        v = (raw or "").strip()
        if v == "":
            continue
        seen = True
        if is_long:
            try:
                int(v)
            except ValueError:
                is_long = False
        if is_real:
            try:
                float(v)
            except ValueError:
                is_real = False
        if is_bool and v.lower() not in ("true", "false"):
            is_bool = False
        if is_datetime and not _looks_datetime(v):
            is_datetime = False
    if not seen:
        return "string"
    if is_bool:
        return "bool"
    if is_long:
        return "long"
    if is_real:
        return "real"
    if is_datetime:
        return "datetime"
    return "string"


def _build_rti_seed(csv_path: Path, table_name: str, timestamp_col: str = "") -> tuple[str, str]:
    """Build the table DDL and a CSV data sample for a Real-Time Intelligence seed.

    Returns ``(schema_ddl, csv_data)`` where:
      * ``schema_ddl`` is a ``.create-merge table`` command (the only data-definition
        command supported inside a KQL database ``DatabaseSchema.kql`` part), and
      * ``csv_data`` is a header-less block of well-formed CSV rows ready to be pushed
        with ``.ingest inline`` via the Kusto management REST endpoint.

    Schema is inferred from the CSV header plus a capped sample of rows.
    """
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = _csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise FabricError(400, f"CSV '{csv_path.name}' is empty")
        sample_rows: list[list[str]] = []
        total_bytes = 0
        for row in reader:
            if len(sample_rows) >= _RTI_MAX_SEED_ROWS or total_bytes >= _RTI_MAX_SEED_BYTES:
                break
            if len(row) != len(header):
                continue  # skip malformed rows
            sample_rows.append(row)
            total_bytes += sum(len(c) for c in row) + len(row)

    columns = [_sanitize_column_name(h) for h in header]
    # Infer a type per column from the sampled values
    col_types = []
    for idx, col in enumerate(columns):
        col_values = [r[idx] for r in sample_rows[:1000]]
        col_types.append(_infer_kusto_type(col_values, col, timestamp_col))

    schema_cols = ", ".join(f"{c}:{t}" for c, t in zip(columns, col_types))
    schema_ddl = f".create-merge table {table_name} ({schema_cols})"

    # Re-serialize the sampled rows to well-formed CSV for inline ingestion
    csv_data = ""
    if sample_rows:
        buf = io.StringIO()
        writer = _csv.writer(buf, lineterminator="\n")
        for row in sample_rows:
            writer.writerow(row)
        csv_data = buf.getvalue().rstrip("\n")

    return schema_ddl, csv_data


def _build_rti_queries(
    table: str, timestamp_col: str = "", signal_col: str = "", groupby_col: str = ""
) -> list[tuple[str, str]]:
    """Build a set of (title, KQL) saved queries for the Real-Time queryset.

    Queries reference real columns from the kqlConfig when available, so the
    queryset is immediately useful instead of the empty 'YOUR_TABLE_HERE' template.
    """
    t = table
    queries: list[tuple[str, str]] = [
        ("Recent records", f"{t} | sort by ingestion_time() desc | take 100"),
        ("Total row count", f"{t} | count"),
        (
            "Ingestion over time",
            f"{t} | summarize Records = count() by Timestamp = bin(ingestion_time(), 1m) | sort by Timestamp asc | render timechart",
        ),
    ]
    if signal_col and groupby_col:
        queries.append((
            f"Avg {signal_col} by {groupby_col}",
            f"{t} | summarize Avg_{signal_col} = avg({signal_col}), Max_{signal_col} = max({signal_col}) by {groupby_col} | sort by Avg_{signal_col} desc",
        ))
    if signal_col and timestamp_col:
        queries.append((
            f"{signal_col} trend",
            f"{t} | summarize avg({signal_col}) by bin({timestamp_col}, 5m) | render timechart",
        ))
    if signal_col and groupby_col:
        queries.append((
            f"{signal_col} anomalies",
            (
                f"{t} | summarize avg_val = avg({signal_col}), stdev_val = stdev({signal_col}) by {groupby_col} "
                f"| join kind=inner ({t}) on {groupby_col} "
                f"| where {signal_col} > avg_val + 3 * stdev_val "
                f"| project {groupby_col}, {signal_col}, avg_val, stdev_val | take 100"
            ),
        ))
    return queries


class DeploymentStep:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.status = "pending"  # pending | running | completed | failed
        self.detail: str | None = None
        self.item_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "detail": self.detail,
            "itemId": self.item_id,
        }


def load_manifest(demo_id: str) -> dict:
    manifest_path = DEMOS_DIR / demo_id / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Demo '{demo_id}' not found")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def list_demos() -> list[dict]:
    """List all available demos by scanning the demos directory for manifest.json files."""
    demos = []
    for d in sorted(DEMOS_DIR.iterdir()):
        manifest_path = d / "manifest.json"
        if d.is_dir() and manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                demos.append({
                    "id": manifest.get("id", d.name),
                    "industry": manifest.get("industry", "Unknown"),
                    "title": manifest.get("title", d.name),
                    "description": manifest.get("description", ""),
                    "estimatedTime": manifest.get("estimatedTime", "5-10 min"),
                    "icon": manifest.get("icon", "📦"),
                    "items": [
                        {"type": item.get("type", ""), "name": item.get("name", "")}
                        for item in manifest.get("fabricItems", [])
                    ],
                })
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Skipping demo '%s': invalid manifest.json: %s", d.name, e)
    return demos


# ── Scenario helpers ────────────────────────────────────────────────────────

# Only these scenario IDs are currently enabled for deployment.
ENABLED_SCENARIOS: set[str] = {
    "data-virtualization-batch",
    "ai-ml",
    "external-data-integration",
    "real-time-intelligence",
    "fabric-foundry-agent",
}


def load_scenario(scenario_id: str) -> dict:
    """Load a scenario template from _scenarios/{scenario_id}.json."""
    path = DEMOS_DIR / "_scenarios" / f"{scenario_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario '{scenario_id}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


def list_scenarios_for_demo(demo_id: str) -> list[dict]:
    """
    Return all scenarios for a demo, merging manifest.custom.json overrides
    with the global _scenarios/*.json definitions.
    """
    custom_path = DEMOS_DIR / demo_id / "manifest.custom.json"
    if not custom_path.exists():
        return []
    try:
        custom = json.loads(custom_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    result = []
    for entry in custom.get("scenarios", []):
        scenario_id = entry.get("id", "")
        if not scenario_id:
            continue
        try:
            scenario = load_scenario(scenario_id)
        except FileNotFoundError:
            scenario = {}

        title = entry.get("titleOverride") or scenario.get("title", scenario_id)
        result.append({
            "id": scenario_id,
            "title": title,
            "description": scenario.get("description", ""),
            "icon": scenario.get("icon", "📦"),
            "estimatedTime": scenario.get("estimatedTime", ""),
            "tags": scenario.get("tags", []),
            "enabled": scenario_id in ENABLED_SCENARIOS,
            "requiresAzure": bool(scenario.get("azureParams")),
            "azureParams": scenario.get("azureParams", []),
        })
    return result


async def deploy_demo(
    client: FabricClient,
    demo_id: str,
    workspace_name: str | None = None,
    workspace_id: str | None = None,
    capacity_id: str | None = None,
    manifest_override: dict | None = None,
    scenario_id: str | None = None,
    azure_client: AzureClient | None = None,
    onelake_token: str | None = None,
    subscription_id: str | None = None,
    resource_group: str | None = None,
    storage_account_name: str | None = None,
    azure_location: str = "eastus",
    create_resource_group: bool = False,
    sql_server_name: str | None = None,
    search_token: str | None = None,
    agent_token: str | None = None,
    kusto_token: str | None = None,
) -> AsyncIterator[dict]:
    """
    Deploy a demo end-to-end, yielding progress events as SSE-compatible dicts.

    Steps:
    1. Create or reuse workspace
    2. (Optional) Provision ADLS Gen2 storage account + upload data + create Fabric connection + shortcut
    3. Create lakehouse(s)
    4. Upload sample data  OR  create ADLS shortcut (depending on manifest)
    5. Create & deploy notebooks
    6. Execute notebooks (Bronze → Silver → Gold)
    7. Wait for SQL endpoint
    8. Create semantic model
    9. Create pipeline
    """
    manifest = manifest_override if manifest_override is not None else load_manifest(demo_id)
    demo_dir = DEMOS_DIR / demo_id
    items = manifest["fabricItems"]
    scenario_id = scenario_id if scenario_id is not None else manifest.get("id")

    # Mirroring scenario has a fundamentally different flow — delegate.
    if any(i["type"] == "MirroredDatabase" for i in items):
        async for ev in _deploy_mirroring(
            client=client,
            demo_id=demo_id,
            demo_dir=demo_dir,
            items=items,
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            capacity_id=capacity_id,
            azure_client=azure_client,
            subscription_id=subscription_id,
            resource_group=resource_group,
            azure_location=azure_location,
            create_resource_group=create_resource_group,
            sql_server_name=sql_server_name,
        ):
            yield ev
        return

    # Fabric + Foundry AI agent scenario — standard Fabric deploy + a published
    # data agent + a Microsoft Foundry agent grounded on it. Delegate.
    if scenario_id == "fabric-foundry-agent":
        async for ev in _deploy_fabric_foundry(
            client=client,
            demo_id=demo_id,
            demo_dir=demo_dir,
            items=items,
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            capacity_id=capacity_id,
            azure_client=azure_client,
            subscription_id=subscription_id,
            resource_group=resource_group,
            azure_location=azure_location,
            create_resource_group=create_resource_group,
            search_token=search_token,
            agent_token=agent_token,
        ):
            yield ev
        return

    steps: list[DeploymentStep] = []
    created_ids: dict[str, str] = {}  # logical name → Fabric item ID

    # ── Pre-flight: check for duplicate workspace name ────────────────────
    if not workspace_id and workspace_name:
        try:
            existing = await client.list_workspaces()
            conflict = next(
                (w for w in existing if w.get("displayName", "").lower() == workspace_name.lower()),
                None,
            )
            if conflict:
                yield {
                    "event": "error",
                    "data": {
                        "message": (
                            f"A workspace named \"{workspace_name}\" already exists in your Fabric tenant. "
                            "Please choose a different name, or delete the existing workspace "
                            "from the Fabric portal before deploying."
                        ),
                        "workspaceId": "",
                    },
                }
                return
        except FabricError:
            pass  # If the list call fails, let the create attempt handle it

    # Detect shortcut items — forks the data ingestion path
    shortcuts = [i for i in items if i["type"] == "Shortcut"]
    has_shortcut = len(shortcuts) > 0

    # ── Plan steps ───────────────────────────────────────────────────────
    if not workspace_id:
        steps.append(DeploymentStep("workspace", f"Create workspace '{workspace_name}'"))

    eventhouses = [i for i in items if i["type"] == "Eventhouse"]
    for eh in eventhouses:
        steps.append(DeploymentStep(f"eventhouse:{eh['name']}", f"Create eventhouse '{eh['name']}'"))

    kql_databases = [i for i in items if i["type"] == "KQLDatabase"]
    for kdb in kql_databases:
        steps.append(DeploymentStep(f"kqldb:{kdb['name']}", f"Create KQL database '{kdb['name']}'"))

    # Real-Time Intelligence seed: the Eventhouse auto-creates a default KQL
    # database (same display name as the eventhouse). When the scenario provides
    # seed CSV info, create the table and ingest sample rows into that default DB.
    _extra = manifest.get("extraNbVars", {})
    _seed_table = _extra.get("RTI_TABLE_NAME", "")
    _seed_csv = _extra.get("RTI_CSV_FILENAME", "")
    _seed_ts = _extra.get("RTI_TIMESTAMP_COLUMN", "")
    _do_seed = bool(_seed_table and _seed_csv and eventhouses)
    if _do_seed:
        steps.append(DeploymentStep("seed-kql", f"Create table '{_seed_table}' and load sample data"))

    lakehouses = [i for i in items if i["type"] == "Lakehouse"]
    for lh in lakehouses:
        steps.append(DeploymentStep(f"lakehouse:{lh['name']}", f"Create lakehouse '{lh['name']}'"))

    data_files = list((demo_dir / "data").glob("*")) if (demo_dir / "data").exists() else []
    if has_shortcut:
        # Replace single upload step with the full ADLS provisioning sequence
        steps.append(DeploymentStep("adls-account", f"Provision ADLS Gen2 storage account"))
        steps.append(DeploymentStep("adls-upload", f"Upload {len(data_files)} sample file(s) to blob storage"))
        steps.append(DeploymentStep("fabric-connection", "Create Fabric connection to ADLS Gen2"))
        for sc in shortcuts:
            steps.append(DeploymentStep(f"shortcut:{sc['name']}", f"Create shortcut '{sc['name']}' → ADLS Gen2"))
    elif data_files and lakehouses:
        steps.append(DeploymentStep("upload-data", f"Upload {len(data_files)} sample data file(s)"))

    notebooks = [i for i in items if i["type"] == "Notebook"]
    notebooks_to_run = [nb for nb in notebooks if nb.get("order") is not None]
    for nb in notebooks:
        steps.append(DeploymentStep(f"notebook:{nb['name']}", f"Create notebook '{nb['name']}'"))
    for nb in notebooks_to_run:
        steps.append(DeploymentStep(f"run:{nb['name']}", f"Execute notebook '{nb['name']}'"))

    # SQL endpoint only applies to lakehouse-based demos
    if lakehouses:
        steps.append(DeploymentStep("sql-endpoint", "Wait for SQL endpoint provisioning"))

    semantic_models = [i for i in items if i["type"] == "SemanticModel"]
    for sm in semantic_models:
        steps.append(DeploymentStep(f"model:{sm['name']}", f"Create semantic model '{sm['name']}'"))
    for sm in semantic_models:
        steps.append(DeploymentStep(f"refresh:{sm['name']}", f"Refresh semantic model '{sm['name']}'"))

    reports = [i for i in items if i["type"] == "Report"]
    for rp in reports:
        steps.append(DeploymentStep(f"report:{rp['name']}", f"Create report '{rp['name']}'"))

    kql_dashboards = [i for i in items if i["type"] == "KQLDashboard"]
    eventstreams = [i for i in items if i["type"] == "Eventstream"]
    kql_querysets = [i for i in items if i["type"] == "KQLQueryset"]
    reflexes = [i for i in items if i["type"] == "Reflex"]

    # Real-Time Intelligence flow order: Eventstream → Queryset → Dashboard → Activator
    for es in eventstreams:
        steps.append(DeploymentStep(f"eventstream:{es['name']}", f"Create eventstream '{es['name']}'"))
    for qs in kql_querysets:
        steps.append(DeploymentStep(f"kqlqueryset:{qs['name']}", f"Create KQL queryset '{qs['name']}'"))
    for kd in kql_dashboards:
        steps.append(DeploymentStep(f"kqldash:{kd['name']}", f"Create real-time dashboard '{kd['name']}'"))
    for rx in reflexes:
        steps.append(DeploymentStep(f"reflex:{rx['name']}", f"Create Activator (Reflex) '{rx['name']}'"))

    pipelines = [i for i in items if i["type"] == "DataPipeline"]
    for pl in pipelines:
        steps.append(DeploymentStep(f"pipeline:{pl['name']}", f"Create pipeline '{pl['name']}'"))

    steps.append(DeploymentStep("done", "Deployment complete"))

    # Emit initial plan
    yield {"event": "plan", "data": [s.to_dict() for s in steps]}

    # ── Execute steps ────────────────────────────────────────────────────
    try:
        ws_id = workspace_id
        # Track an Azure storage account we auto-provision so a failed deploy can
        # tear it down. Only set when WE generate the name (never delete a
        # user-supplied, pre-existing account).
        created_storage_account: str | None = None

        # Pre-flight: fail fast on a paused/inactive capacity.
        cap_err = await _capacity_inactive_error(client, capacity_id, workspace_id)
        if cap_err:
            yield {"event": "error", "data": {"message": cap_err, "workspaceId": ""}}
            return

        # 1. Workspace
        if not ws_id:
            step = _find_step(steps, "workspace")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                ws = await client.create_workspace(workspace_name or manifest["title"], capacity_id)
                ws_id = ws["id"]
                step.status = "completed"
                step.item_id = ws_id
                yield {"event": "step", "data": step.to_dict()}
            except FabricError as e:
                step.status = "failed"
                if e.status == 409:
                    step.detail = f"A workspace named '{workspace_name}' already exists. Please choose a different name."
                elif e.status == 403:
                    # Surface Fabric's actual reason — a 403 here can be workspace-create
                    # rights OR capacity-assignment rights on the selected capacity, and
                    # only Fabric's message says which. Don't hide it behind a guess.
                    step.detail = (
                        "Fabric denied the workspace creation (403). This is a permission on "
                        "either creating workspaces or assigning one to the selected capacity. "
                        "Fabric said: " + (e.detail[:400] if e.detail else "(no detail returned)")
                    )
                elif e.status == 401:
                    step.detail = "Authentication expired. Please sign out and sign in again."
                else:
                    step.detail = f"Failed to create workspace: {e.detail[:200]}"
                yield {"event": "step", "data": step.to_dict()}
                yield {"event": "error", "data": {"message": step.detail, "workspaceId": ""}}
                return

        # 2a. Eventhouses
        eventhouse_uri = ""
        for eh in eventhouses:
            step = _find_step(steps, f"eventhouse:{eh['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            result = await client.create_eventhouse(ws_id, eh["name"])
            eh_id = result["id"]
            created_ids[eh["name"]] = eh_id
            # Get the query URI for Kusto connector
            try:
                eh_details = await client.get_eventhouse(ws_id, eh_id)
                eventhouse_uri = eh_details.get("properties", {}).get("queryServiceUri", "")
            except Exception as e:
                logger.warning("Could not get Eventhouse URI: %s", e)
            step.status = "completed"
            step.item_id = eh_id
            step.detail = eventhouse_uri or "Created"
            yield {"event": "step", "data": step.to_dict()}

        # 2b. KQL Databases (explicit — only when a manifest defines them; RTI relies
        #     on the Eventhouse's auto-created default database instead).
        kql_db_name = ""
        for kdb in kql_databases:
            step = _find_step(steps, f"kqldb:{kdb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            parent_eh = kdb.get("parentEventhouse", "")
            parent_id = created_ids.get(parent_eh, "")
            if not parent_id:
                for eh in eventhouses:
                    parent_id = created_ids.get(eh["name"], "")
                    if parent_id:
                        break
            result = await client.create_kql_database(ws_id, kdb["name"], parent_id)
            created_ids[kdb["name"]] = result["id"]
            kql_db_name = kdb["name"]
            step.status = "completed"
            step.item_id = result["id"]
            yield {"event": "step", "data": step.to_dict()}

        # When no explicit KQL Database is in the manifest, Fabric auto-creates one
        # with the same display name as the Eventhouse — use that name.
        if not kql_db_name and eventhouses:
            kql_db_name = eventhouses[0]["name"]

        # KQL database item id of the (default) database — resolved during the seed
        # step and reused for the Eventstream's Eventhouse destination.
        kql_db_item_id = ""

        # 2c. Create the table (Fabric API — no Kusto token) and seed sample data
        #     (best-effort, Kusto data plane) into the Eventhouse's default DB (RTI).
        if _do_seed:
            step = _find_step(steps, "seed-kql")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            seed_path = demo_dir / "data" / _seed_csv
            eh_item_id = created_ids.get(eventhouses[0]["name"], "") if eventhouses else ""
            if not seed_path.exists():
                step.status = "failed"
                step.detail = f"Sample file '{_seed_csv}' not found."
            else:
                schema_ddl, csv_data = _build_rti_seed(seed_path, _seed_table, _seed_ts)
                table_created = False
                # 1) Create the table via the Fabric definition API (reliable, no token).
                #    The default database is provisioned asynchronously, so poll for it.
                db_item_id = ""
                try:
                    for attempt in range(8):
                        db = await client.find_database_by_name(ws_id, kql_db_name)
                        if db:
                            db_item_id = db["id"]
                            kql_db_item_id = db_item_id
                            break
                        await asyncio.sleep(8)
                    if db_item_id and eh_item_id:
                        await client.add_table_schema_to_database(
                            ws_id, db_item_id, eh_item_id, schema_ddl
                        )
                        table_created = True
                except (FabricError, Exception) as e:
                    logger.warning("Fabric-API table creation failed: %s", str(e)[:300])

                # 1b) Fallback: create the table via the Kusto data plane (needs token).
                if not table_created and eventhouse_uri and kusto_token:
                    try:
                        await client.kusto_mgmt(
                            eventhouse_uri, kql_db_name, schema_ddl, kusto_token
                        )
                        table_created = True
                    except (FabricError, Exception) as e:
                        logger.warning("Kusto table creation failed: %s", str(e)[:300])

                # 2) Seed sample rows via the Kusto data plane (best-effort, fail fast).
                seeded_rows = 0
                seed_err = ""
                if table_created and csv_data and eventhouse_uri and kusto_token:
                    try:
                        await client.kusto_ingest_inline(
                            eventhouse_uri, kql_db_name, _seed_table, csv_data, kusto_token
                        )
                        seeded_rows = csv_data.count("\n") + 1
                    except (FabricError, Exception) as e:
                        seed_err = str(e)[:120]
                        logger.warning("Kusto seed ingest failed: %s", str(e)[:300])

                if table_created and seeded_rows:
                    step.status = "completed"
                    step.detail = f"Table '{_seed_table}' created · seeded ~{seeded_rows} rows"
                elif table_created:
                    step.status = "completed"
                    reason = f" ({seed_err})" if seed_err else ""
                    step.detail = (
                        f"Table '{_seed_table}' created. Historical seed skipped{reason} — "
                        "the live Eventstream will populate data."
                    )
                else:
                    step.status = "failed"
                    step.detail = f"Could not create table '{_seed_table}'. Check permissions."
            yield {"event": "step", "data": step.to_dict()}


        # 2c. Lakehouses
        lakehouse_id = None
        lakehouse_name = None
        for lh in lakehouses:
            step = _find_step(steps, f"lakehouse:{lh['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            result = await client.create_lakehouse(ws_id, lh["name"])
            lh_id = result["id"]
            created_ids[lh["name"]] = lh_id
            if lakehouse_id is None:
                lakehouse_id = lh_id
                lakehouse_name = lh["name"]
            step.status = "completed"
            step.item_id = lh_id
            yield {"event": "step", "data": step.to_dict()}

        # 3. Upload data — fork on whether this is a shortcut deployment
        shortcut_name = shortcuts[0]["name"] if shortcuts else "raw_data"
        nb_variables = {}
        if eventhouse_uri:
            nb_variables["EVENTHOUSE_URI"] = eventhouse_uri
        if kql_db_name:
            nb_variables["KQL_DATABASE_NAME"] = kql_db_name
        # Merge any extra per-scenario variables (e.g. RTI_TABLE_NAME, RTI_CSV_FILENAME)
        nb_variables.update(manifest.get("extraNbVars", {}))

        if has_shortcut:
            # ── Shortcut path: provision ADLS Gen2 + upload + create connection + shortcut ──
            if not azure_client or not subscription_id or not resource_group:
                raise FabricError(400, "Shortcut deployment requires subscription_id, resource_group, and Azure credentials (x-management-token header).")

            # 3a. Provision storage account
            step = _find_step(steps, "adls-account")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            acct_name = storage_account_name
            if not acct_name:
                import random, string
                prefix = demo_id.replace("-", "")[:8]
                suffix = "".join(random.choices(string.digits, k=4))
                acct_name = f"{prefix}{suffix}"[:24]
            try:
                if create_resource_group:
                    await azure_client.create_resource_group(subscription_id, resource_group, azure_location)
                await azure_client.create_storage_account(
                    subscription_id, resource_group, acct_name, azure_location
                )
                # Remember it for teardown ONLY if we generated the name — never
                # auto-delete a storage account the user already owned.
                if not storage_account_name:
                    created_storage_account = acct_name
                # Grant Storage Blob Data Contributor so OAuth uploads work.
                # Non-fatal — user may already have access via a group or higher role.
                caller_oid = azure_client.get_caller_oid()
                if caller_oid:
                    try:
                        await azure_client.assign_blob_data_contributor(
                            subscription_id, resource_group, acct_name, caller_oid
                        )
                    except AzureError as rbac_err:
                        logger.warning("Could not assign blob role (will retry on 403): %s", rbac_err.detail)
            except AzureError as e:
                raise FabricError(e.status, f"ADLS provisioning failed: {e.detail}")
            step.status = "completed"
            step.detail = f"{acct_name}.dfs.core.windows.net"
            yield {"event": "step", "data": step.to_dict()}

            # 3b. Upload sample files to blob storage
            step = _find_step(steps, "adls-upload")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            container = demo_id.replace("-", "")
            try:
                await azure_client.create_blob_container(
                    subscription_id, resource_group, acct_name, container
                )
                for f in data_files:
                    blob_name = f.name
                    await client.upload_blob_oauth(
                        acct_name, container, blob_name, Path(f).read_bytes()
                    )
            except (AzureError, FabricError) as e:
                status = e.status if hasattr(e, "status") else 500
                detail = e.detail if hasattr(e, "detail") else str(e)
                raise FabricError(status, f"ADLS upload failed: {detail}")
            step.status = "completed"
            step.detail = f"Uploaded {len(data_files)} file(s) to {acct_name}/{container}/"
            yield {"event": "step", "data": step.to_dict()}

            # 3c. Create Fabric connection to ADLS Gen2
            step = _find_step(steps, "fabric-connection")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            adls_dfs_url = f"https://{acct_name}.dfs.core.windows.net"
            connection_id = ""
            try:
                # Unique connection name per deploy (include the workspace id) so we
                # never reuse a stale connection — the embedded User Delegation SAS
                # expires after a few hours, and a reused expired connection makes
                # the shortcut creation fail with HTTP 400.
                conn_result = await client.create_connection_oauth(
                    display_name=f"{demo_id}-{acct_name}-{ws_id[:8]}-conn",
                    adls_account_url=adls_dfs_url,
                    container=container,
                )
                connection_id = conn_result.get("id") or conn_result.get("connectionId") or ""
                if not connection_id:
                    logger.warning("[shortcut] connection_id empty after connection step; conn_result keys: %s",
                                   list(conn_result.keys()))
                    step.status = "failed"
                    step.detail = f"Connection created but no ID in response. Keys: {list(conn_result.keys())}"
                else:
                    step.status = "completed"
                    step.detail = f"Connection ID: {connection_id}"
            except FabricError as conn_err:
                logger.warning("Fabric connection failed (HTTP %s): %s",
                               conn_err.status, conn_err.detail)
                step.status = "skipped"
                step.detail = f"HTTP {conn_err.status}: {conn_err.detail[:200]}"
            yield {"event": "step", "data": step.to_dict()}

            # 3d. Create shortcut(s) in the lakehouse
            shortcut_created = False
            if connection_id:
                for sc in shortcuts:
                    step = _find_step(steps, f"shortcut:{sc['name']}")
                    step.status = "running"
                    yield {"event": "step", "data": step.to_dict()}
                    parent_lh_name = sc.get("parentLakehouse", "")
                    lh_id_for_sc = created_ids.get(parent_lh_name, lakehouse_id)
                    try:
                        sc_result = await client.create_shortcut(
                            workspace_id=ws_id,
                            lakehouse_id=lh_id_for_sc,
                            name=sc["name"],
                            parent_path=sc.get("path", "Files"),
                            adls_location=adls_dfs_url,
                            adls_subpath=f"/{container}",
                            connection_id=connection_id,
                            onelake_token=onelake_token,
                        )
                        created_ids[sc["name"]] = sc_result.get("name", sc["name"])
                        step.status = "completed"
                        step.detail = f"Files/{sc['name']} → {adls_dfs_url}/{container}"
                        shortcut_created = True
                    except FabricError as sc_err:
                        if sc_err.status == 409:
                            # Shortcut already exists (e.g. re-deploying same workspace)
                            logger.info("[shortcut] 409 — shortcut '%s' already exists, treating as success", sc["name"])
                            step.status = "completed"
                            step.detail = f"Files/{sc['name']} already exists (reused)"
                            shortcut_created = True
                        else:
                            logger.warning("Shortcut creation failed (HTTP %s): %s", sc_err.status, sc_err.detail[:300])
                            step.status = "skipped"
                            step.detail = f"HTTP {sc_err.status}: {sc_err.detail[:200]}"
                    yield {"event": "step", "data": step.to_dict()}
            else:
                for sc in shortcuts:
                    step = _find_step(steps, f"shortcut:{sc['name']}")
                    step.status = "skipped"
                    step.detail = "Skipped — no Fabric connection available"
                    yield {"event": "step", "data": step.to_dict()}

            if shortcut_created:
                # Notebooks read via shortcut
                nb_variables["DATA_SOURCE_PATH"] = f"Files/{shortcut_name}"
            else:
                # Fallback: upload data files directly to the lakehouse via OneLake
                for f in data_files:
                    await client.upload_file_to_lakehouse(
                        ws_id, lakehouse_id, f"raw_data/{f.name}", f
                    )
                nb_variables["DATA_SOURCE_PATH"] = "Files/raw_data"

        elif data_files and lakehouse_id:
            # ── Standard path: upload directly to OneLake ──────────────────────────────
            step = _find_step(steps, "upload-data")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            for f in data_files:
                await client.upload_file_to_lakehouse(
                    ws_id, lakehouse_id, f"landing/{f.name}", f
                )
            step.status = "completed"
            step.detail = f"Uploaded {len(data_files)} files"
            yield {"event": "step", "data": step.to_dict()}
            nb_variables["DATA_SOURCE_PATH"] = "Files/landing"

        # 4. Create notebooks
        notebook_ids: dict[str, str] = {}
        for nb in notebooks:
            step = _find_step(steps, f"notebook:{nb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            def_path = nb.get("definitionPath", f"notebooks/{nb['name']}.ipynb")
            if def_path.startswith("_scenarios/"):
                # Notebook lives in the _scenarios folder, not the demo folder
                ipynb_path = DEMOS_DIR / def_path
            else:
                ipynb_path = demo_dir / def_path
            result = await client.create_notebook(
                ws_id, nb["name"], ipynb_path, lakehouse_id, lakehouse_name,
                variables=nb_variables or None,
            )
            nb_id = result["id"]
            notebook_ids[nb["name"]] = nb_id
            created_ids[nb["name"]] = nb_id
            step.status = "completed"
            step.item_id = nb_id
            yield {"event": "step", "data": step.to_dict()}

        # 5. Execute notebooks.
        #
        # On constrained Fabric capacities (Trial / small F-SKUs) the dominant
        # cause of deploy failures is TooManyRequestsForCapacity (HTTP 430):
        # every run_notebook API call spins up its own Spark/Livy session, and
        # notebook jobs submitted through the public API are never queued, so a
        # busy capacity rejects them outright. To minimise that, when there are
        # 2+ notebooks to run we orchestrate them inside ONE shared Spark session
        # via notebookutils.notebook.runMultiple (the documented "high concurrency
        # session sharing" pattern) — the deploy then only has to win capacity
        # admission once instead of once per notebook, and puts ~3× less pressure
        # on the Spark API rate limit.
        #
        # Two budgets: a single notebook gets 30 min, but the orchestrator runs
        # the WHOLE medallion pipeline (3-5 notebooks) inside one session, so it
        # needs a much larger budget — otherwise a pipeline that is legitimately
        # running on a busy/small capacity gets killed mid-run and looks like it
        # "never finishes".
        notebook_timeout = 1800
        pipeline_timeout = 3600
        max_attempts = 5

        runnable = [nb for nb in notebooks_to_run if notebook_ids.get(nb["name"])]
        for nb in notebooks_to_run:
            if not notebook_ids.get(nb["name"]):
                step = _find_step(steps, f"run:{nb['name']}")
                step.status = "failed"
                step.detail = "Notebook was not created — skipping execution"
                yield {"event": "step", "data": step.to_dict()}

        # The single-session orchestrator (notebookutils.notebook.runMultiple)
        # is DISABLED. It reliably failed with
        # System_Cancelled_Session_Statements_Failed on EVERY capacity — including
        # F32/F64 with plenty of headroom — because packing all medallion
        # notebooks into one shared Spark session via reference runs destabilised
        # the session mid-pipeline. The direct path below (one clean Spark session
        # per notebook, sequential, with retry) is proven to deploy end-to-end
        # reliably. Re-enable ONLY if runMultiple stability is fixed + verified.
        USE_SINGLE_SESSION_ORCHESTRATOR = False

        if USE_SINGLE_SESSION_ORCHESTRATOR and len(runnable) >= 2:
            # ── Single shared Spark session via an orchestrator notebook ──────
            run_steps = [_find_step(steps, f"run:{nb['name']}") for nb in runnable]
            for st in run_steps:
                st.status = "running"
                st.detail = "Running in one shared Spark session…"
                yield {"event": "step", "data": st.to_dict()}

            # Cosmetic dashboards are best-effort: a render hiccup must not fail
            # an otherwise-good deploy (the pipeline data + reports are intact).
            optional_names = {
                nb["name"] for nb in runnable if "dashboard" in nb["name"].lower()
            }
            orch_source = _build_orchestrator_source(runnable, optional_names)
            orch = await client.create_notebook_from_source(
                ws_id, "_fdg_pipeline_runner", orch_source, lakehouse_id, lakehouse_name,
            )
            orch_id = orch["id"]
            created_ids["_fdg_pipeline_runner"] = orch_id

            last_err: FabricError | None = None
            for attempt in range(max_attempts):
                try:
                    result = await client.run_notebook(
                        ws_id, orch_id, lakehouse_id, lakehouse_name, timeout=pipeline_timeout,
                    )
                    job_status = result.get("status", "").lower() if isinstance(result, dict) else ""
                    if job_status == "failed":
                        failure = result.get("failureReason", {})
                        err_msg = failure.get("message", "Notebook execution failed")
                        raise FabricError(500, err_msg[:500])
                    last_err = None
                    break
                except FabricError as e:
                    last_err = e
                    # Only retry when the Spark *session could not be created*
                    # (capacity 430 / Livy admission). That happens before any
                    # work runs, so retrying is cheap and safe. A failure AFTER
                    # the session starts — an in-notebook error, or a run that
                    # exceeds the pipeline timeout — fails fast: re-running the
                    # whole pipeline would just repeat the same long, doomed run.
                    if attempt < max_attempts - 1 and _is_admission_error(e.detail):
                        wait = _retry_wait_seconds(e.detail, attempt)
                        for st in run_steps:
                            st.detail = f"Spark capacity busy — retrying ({attempt + 1}/{max_attempts - 1}) in {wait}s…"
                            yield {"event": "step", "data": st.to_dict()}
                        await asyncio.sleep(wait)
                        continue
                    break
            if last_err is not None:
                msg = _friendly_capacity_error(last_err.detail or "")
                # Attribute the failure to the specific notebook when we can.
                failed_idx = next(
                    (i for i, nb in enumerate(runnable) if f"'{nb['name']}'" in (last_err.detail or "")),
                    0,
                )
                for i, st in enumerate(run_steps):
                    if i < failed_idx:
                        st.status = "completed"
                    elif i == failed_idx:
                        st.status = "failed"
                        st.detail = msg[:400]
                    else:
                        break
                    yield {"event": "step", "data": st.to_dict()}
                raise FabricError(last_err.status, msg)

            for st in run_steps:
                st.status = "completed"
                st.detail = "Completed in one shared Spark session"
                yield {"event": "step", "data": st.to_dict()}
        else:
            # ── Default path: one clean Spark session per notebook, in order ──
            # A fresh session per notebook is rock-solid. A short pause between
            # notebooks lets the previous Spark session release so sequential runs
            # don't overlap and trip TooManyRequestsForCapacity on smaller
            # capacities (the retry below is the backstop if they still do).
            for i, nb in enumerate(runnable):
                if i > 0:
                    await asyncio.sleep(20)
                step = _find_step(steps, f"run:{nb['name']}")
                nb_id = notebook_ids[nb["name"]]
                step.status = "running"
                yield {"event": "step", "data": step.to_dict()}

                last_err = None
                for attempt in range(max_attempts):
                    try:
                        result = await client.run_notebook(
                            ws_id, nb_id, lakehouse_id, lakehouse_name, timeout=notebook_timeout,
                        )
                        job_status = result.get("status", "").lower() if isinstance(result, dict) else ""
                        if job_status == "failed":
                            failure = result.get("failureReason", {})
                            err_msg = failure.get("message", "Notebook execution failed")
                            raise FabricError(500, f"Notebook '{nb['name']}' failed: {err_msg[:200]}")
                        last_err = None
                        break
                    except FabricError as e:
                        last_err = e
                        if attempt < max_attempts - 1 and _is_transient_run_error(e.detail):
                            wait = _retry_wait_seconds(e.detail, attempt)
                            step.detail = f"Spark capacity busy / transient hiccup — retrying ({attempt + 1}/{max_attempts - 1}) in {wait}s…"
                            yield {"event": "step", "data": step.to_dict()}
                            await asyncio.sleep(wait)
                            continue
                        break
                if last_err is not None:
                    friendly = _friendly_capacity_error(last_err.detail or "")
                    step.status = "failed"
                    step.detail = friendly[:400]
                    yield {"event": "step", "data": step.to_dict()}
                    raise FabricError(last_err.status, friendly)

                step.status = "completed"
                yield {"event": "step", "data": step.to_dict()}

        # 6. Wait for SQL endpoint (only relevant for lakehouse-based demos)
        conn_string = ""
        if lakehouses:
            step = _find_step(steps, "sql-endpoint")
            if lakehouse_id:
                step.status = "running"
                yield {"event": "step", "data": step.to_dict()}
                conn_string = await client.wait_for_sql_endpoint(ws_id, lakehouse_id)
                step.status = "completed"
                step.detail = conn_string
            else:
                step.status = "completed"
                step.detail = "Skipped — no lakehouse"
            yield {"event": "step", "data": step.to_dict()}

        # 7. Semantic models (with dynamic SQL endpoint injection)
        #
        # Sectors that ship a hand-authored tmdl/model.bim use it. Sectors that
        # don't get a lightweight Direct Lake model auto-generated from the gold
        # tables discovered in the lakehouse, so every deploy produces a working
        # model + report instead of a silent skip. ``gold_schema`` is discovered
        # lazily (once) and reused by the report step.
        gold_schema: dict | None = None
        generic_models: set[str] = set()

        async def _discover_gold_schema() -> dict:
            nonlocal gold_schema
            if gold_schema is not None:
                return gold_schema
            gold_schema = {}
            if not (lakehouse_id and lakehouse_name):
                return gold_schema
            try:
                all_tables = await client.discover_lakehouse_schema(
                    ws_id, lakehouse_id, lakehouse_name
                )
                # Only surface the analytics-facing tables in the model/report.
                gold_schema = {
                    t: cols for t, cols in all_tables.items()
                    if t.startswith("gold_") or t.startswith("dim_")
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("Gold schema discovery failed; model/report will be skipped: %s", e)
                gold_schema = {}
            return gold_schema

        for sm in semantic_models:
            step = _find_step(steps, f"model:{sm['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            tmdl_path = demo_dir / sm.get("definitionPath", "tmdl")
            model_bim = tmdl_path / "model.bim"
            if model_bim.exists():
                definition = _build_bim_definition(model_bim, variables={
                    "SQL_ENDPOINT": conn_string,
                    "LAKEHOUSE_NAME": lakehouse_name or "",
                    "WORKSPACE_ID": ws_id,
                    "LAKEHOUSE_ID": lakehouse_id or "",
                })
                result = await client.create_semantic_model(ws_id, sm["name"], definition)
                created_ids[sm["name"]] = result.get("id", "")
                step.item_id = result.get("id")
                step.status = "completed"
            else:
                # No hand-authored model — auto-generate one from the gold tables.
                schema = await _discover_gold_schema()
                if schema:
                    definition = build_generic_model_definition(
                        schema, conn_string, lakehouse_name or ""
                    )
                    result = await client.create_semantic_model(ws_id, sm["name"], definition)
                    created_ids[sm["name"]] = result.get("id", "")
                    generic_models.add(sm["name"])
                    step.item_id = result.get("id")
                    step.status = "completed"
                    step.detail = f"Auto-generated Direct Lake model over {len(schema)} gold tables"
                else:
                    # Genuinely nothing to model — be honest, not falsely green.
                    step.status = "skipped"
                    step.detail = "Skipped — no gold tables found to model"
            yield {"event": "step", "data": step.to_dict()}


        # 7b. Refresh semantic models
        for sm in semantic_models:
            sm_id = created_ids.get(sm["name"])
            step = _find_step(steps, f"refresh:{sm['name']}")
            if sm_id:
                step.status = "running"
                yield {"event": "step", "data": step.to_dict()}
                try:
                    await client.refresh_semantic_model(ws_id, sm_id)
                    step.status = "completed"
                    step.detail = "Data loaded from Gold tables"
                except FabricError as e:
                    # The initial refresh can lag behind the SQL endpoint syncing
                    # the freshly-written gold tables. This is NOT fatal: the
                    # Direct Lake model frames automatically on first query, so
                    # the report still works. Mark it skipped (neutral) rather
                    # than failed (red) so a healthy deploy isn't shown as broken.
                    logger.warning("Semantic model refresh did not complete: %s", e.detail)
                    step.status = "skipped"
                    step.detail = "Direct Lake model frames automatically on first query — no action needed."
            else:
                step.status = "completed"
                step.detail = "Skipped — no model created"
            yield {"event": "step", "data": step.to_dict()}

        # 8. Reports (Power BI) — create with PBIR-Legacy definition
        for rp in reports:
            step = _find_step(steps, f"report:{rp['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            sm_id = None
            sm_is_generic = False
            for sm in semantic_models:
                sm_id = created_ids.get(sm["name"])
                if sm_id:
                    sm_is_generic = sm["name"] in generic_models
                    break
            if sm_id:
                try:
                    if sm_is_generic:
                        # The model was auto-generated from the gold tables, so the
                        # report must be too (a hand-authored report references
                        # sector-specific tables that may not exist here).
                        schema = await _discover_gold_schema()
                        report_title = f"{demo_id.replace('-', ' ').title()} Analytics"
                        report_def = build_generic_report_definition(schema, sm_id, report_title)
                    else:
                        report_def = _build_report_definition(demo_id, sm_id, scenario_id)
                    logger.info("Report definition built, %d parts, creating item...", len(report_def.get("parts", [])))
                    result = await client.create_item(ws_id, "Report", rp["name"], report_def)
                    rp_id = result.get("id", "")
                    logger.info("Report created: id=%s, result=%s", rp_id, json.dumps(result)[:200])
                    created_ids[rp["name"]] = rp_id
                    step.item_id = rp_id
                    step.status = "completed"
                except FabricError as e:
                    logger.error("Report FabricError: %s", e.detail[:500])
                    step.status = "failed"
                    step.detail = f"{e.detail[:200]}"
                except Exception as e:
                    logger.exception("Report unexpected error")
                    step.status = "failed"
                    step.detail = f"Unexpected: {str(e)[:200]}"
            else:
                step.status = "skipped"
                step.detail = "Skipped — no semantic model available"
            yield {"event": "step", "data": step.to_dict()}

        # 8b. Eventstreams (Custom Endpoint source → Eventhouse destination for the live demo)
        for es in eventstreams:
            step = _find_step(steps, f"eventstream:{es['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                # The Eventhouse destination resolves the cluster URL from the KQL
                # database item id (not the eventhouse id). Resolve it if not already.
                if not kql_db_item_id and kql_db_name:
                    db = await client.find_database_by_name(ws_id, kql_db_name)
                    if db:
                        kql_db_item_id = db["id"]
                if kql_db_item_id and kql_db_name and _seed_table:
                    result = await client.create_eventstream_with_topology(
                        ws_id, es["name"], kql_db_item_id, kql_db_name, _seed_table
                    )
                    step.detail = (
                        "Custom endpoint → Eventhouse. Copy the endpoint connection "
                        "string from the Fabric portal to start live streaming."
                    )
                else:
                    result = await client.create_item(ws_id, "Eventstream", es["name"])
                    step.detail = "Eventstream created (configure source in Fabric portal)"
                created_ids[es["name"]] = result.get("id", "")
                step.status = "completed"
                step.item_id = result.get("id")
            except (FabricError, Exception) as e:
                detail = e.detail if isinstance(e, FabricError) else str(e)
                logger.warning("Eventstream creation failed: %s", str(detail)[:300])
                step.status = "failed"
                step.detail = f"Eventstream failed: {str(detail)[:180]}"
            yield {"event": "step", "data": step.to_dict()}

        # 8c. KQL Querysets (pre-populated with saved queries against the table)
        for qs in kql_querysets:
            step = _find_step(steps, f"kqlqueryset:{qs['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                if eventhouse_uri and kql_db_name and _seed_table:
                    queries = _build_rti_queries(
                        _seed_table, _seed_ts,
                        _extra.get("RTI_SIGNAL_COLUMN", ""),
                        _extra.get("RTI_GROUPBY_COLUMN", ""),
                    )
                    result = await client.create_kql_queryset_with_queries(
                        ws_id, qs["name"], eventhouse_uri, kql_db_name, queries
                    )
                    step.detail = f"{len(queries)} saved queries"
                else:
                    result = await client.create_item(ws_id, "KQLQueryset", qs["name"])
                created_ids[qs["name"]] = result.get("id", "")
                step.status = "completed"
                step.item_id = result.get("id")
            except (FabricError, Exception) as e:
                detail = e.detail if isinstance(e, FabricError) else str(e)
                logger.warning("KQL Queryset creation failed: %s", str(detail)[:300])
                step.status = "completed"
                step.detail = f"⚠ Queryset basic create ({str(detail)[:120]})"
                try:
                    result = await client.create_item(ws_id, "KQLQueryset", qs["name"])
                    created_ids[qs["name"]] = result.get("id", "")
                    step.item_id = result.get("id")
                except FabricError:
                    step.status = "failed"
            yield {"event": "step", "data": step.to_dict()}

        # 8d. KQL Dashboards (Real-Time Dashboards)
        for kd in kql_dashboards:
            step = _find_step(steps, f"kqldash:{kd['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                # Resolve the KQL database GUID (the dashboard dataSource 'database'
                # field requires the database item id, not its name).
                if not kql_db_item_id and kql_db_name:
                    db = await client.find_database_by_name(ws_id, kql_db_name)
                    if db:
                        kql_db_item_id = db["id"]
                kdb_id = kql_db_item_id
                for kdb in kql_databases:
                    _id = created_ids.get(kdb["name"], "")
                    if _id:
                        kdb_id = _id
                        break
                result = await client.create_kql_dashboard(
                    ws_id, kd["name"], kdb_id, eventhouse_uri, kql_db_name,
                    table_name=_seed_table,
                    signal_col=_extra.get("RTI_SIGNAL_COLUMN", ""),
                    groupby_col=_extra.get("RTI_GROUPBY_COLUMN", ""),
                    timestamp_col=_seed_ts,
                )
                created_ids[kd["name"]] = result.get("id", "")
                step.item_id = result.get("id")
                step.status = "completed"
                step.detail = "Real-time tiles for live data"
            except (FabricError, Exception) as e:
                logger.warning("KQL Dashboard creation failed: %s", str(e)[:300])
                step.status = "skipped"
                step.detail = f"Dashboard not created: {str(e)[:150]}. You can add it manually in Fabric."
            yield {"event": "step", "data": step.to_dict()}

        # 8e. Reflexes (Activator) — created empty. The Activator rule format
        #     (ReflexEntities.json) is not reliably authorable via the API; the
        #     supported path is the UI ('Set alert' on a dashboard tile/queryset),
        #     so we create the item and let the user add the rule there.
        for rx in reflexes:
            step = _find_step(steps, f"reflex:{rx['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                result = await client.create_item(ws_id, "Reflex", rx["name"])
                created_ids[rx["name"]] = result.get("id", "")
                step.status = "completed"
                step.item_id = result.get("id")
                step.detail = "Add an alert via 'Set alert' on a dashboard tile or queryset"
            except FabricError as e:
                step.status = "completed"
                step.detail = f"⚠ Activator failed: {e.detail[:150]}. Create manually."
            yield {"event": "step", "data": step.to_dict()}

        # 9. Pipelines (with notebook orchestration activities)
        for pl in pipelines:
            step = _find_step(steps, f"pipeline:{pl['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                pipeline_def = _build_pipeline_definition(
                    ws_id, notebooks, notebook_ids
                )
                result = await client.create_pipeline(ws_id, pl["name"], pipeline_def)
                created_ids[pl["name"]] = result.get("id", "")
                step.status = "completed"
                step.item_id = result.get("id")
            except FabricError as e:
                logger.warning("Pipeline creation failed: %s", e.detail)
                step.status = "skipped"
                step.detail = f"Pipeline not created: {e.detail[:150]}. You can add it manually in Fabric."
            yield {"event": "step", "data": step.to_dict()}

        # 10. Auto-schedule pipeline for real-time demos (energy-grid)
        if demo_id == "energy-grid":
            for pl in pipelines:
                pl_id = created_ids.get(pl["name"])
                if pl_id:
                    try:
                        sched = await client.create_item_schedule(ws_id, pl_id, interval_minutes=10)
                        if sched:
                            logger.info("Pipeline scheduled every 10 min: %s", sched.get("id", ""))
                    except Exception as e:
                        logger.warning("Auto-schedule failed: %s", str(e)[:200])

        # Done
        step = _find_step(steps, "done")
        step.status = "completed"
        step.detail = json.dumps({
            "workspaceId": ws_id,
            "items": created_ids,
        })
        yield {"event": "step", "data": step.to_dict()}

    except FabricError as e:
        # Mark current running step as failed
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = e.detail[:300]
                yield {"event": "step", "data": s.to_dict()}
                break

        # Best-effort teardown so a failed deploy leaves nothing orphaned.
        cleanup_note, ws_remaining = await _best_effort_teardown(
            client, azure_client, ws_id, subscription_id, resource_group,
            storage_account=created_storage_account,
        )
        error_msg = str(e)
        if cleanup_note:
            error_msg += "\n\n" + cleanup_note
        yield {"event": "error", "data": {"message": error_msg, "workspaceId": ws_id if ws_remaining else ""}}

    except AzureError as e:
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = e.detail[:300]
                yield {"event": "step", "data": s.to_dict()}
                break
        cleanup_note, ws_remaining = await _best_effort_teardown(
            client, azure_client, ws_id, subscription_id, resource_group,
            storage_account=created_storage_account,
        )
        error_msg = f"Azure provisioning error: {e.detail}"
        if cleanup_note:
            error_msg += "\n\n" + cleanup_note
        yield {"event": "error", "data": {"message": error_msg, "workspaceId": ws_id if ws_remaining else ""}}

    except Exception as e:
        logger.exception("Unexpected deployment error")
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = str(e)[:300]
                yield {"event": "step", "data": s.to_dict()}
                break

        cleanup_note, ws_remaining = await _best_effort_teardown(
            client, azure_client, ws_id, subscription_id, resource_group,
            storage_account=created_storage_account,
        )
        error_msg = f"Unexpected error: {type(e).__name__}: {e}"
        if cleanup_note:
            error_msg += "\n\n" + cleanup_note
        yield {"event": "error", "data": {"message": error_msg, "workspaceId": ws_id if ws_remaining else ""}}


async def _capacity_inactive_error(
    client: FabricClient, capacity_id: str | None, workspace_id: str | None
) -> str | None:
    """Pre-flight: when a NEW workspace is requested on a specific capacity,
    return a user-facing error if that capacity isn't active — so we fail fast
    with a clear message instead of dying mid-deploy with Fabric's cryptic
    "Target capacity is not in active state".

    Returns None when the check passes OR can't be performed (a transient
    listing failure must never block an otherwise-valid deploy).
    """
    if not capacity_id or workspace_id:
        return None
    try:
        active = await client.list_capacities()  # already filtered to state == active
    except Exception as e:  # noqa: BLE001 — pre-flight is advisory, never fatal
        logger.warning("Capacity pre-flight skipped (list_capacities failed): %s", e)
        return None
    if any((c.get("id") or "").lower() == capacity_id.lower() for c in active):
        return None
    return (
        "The selected Fabric capacity is paused or not active. Resume it in the "
        "Azure portal (or choose an active capacity), then retry."
    )


async def _best_effort_teardown(
    client: FabricClient,
    azure_client: "AzureClient | None",
    ws_id: str | None,
    subscription_id: str | None = None,
    resource_group: str | None = None,
    sql_server: str | None = None,
    storage_account: str | None = None,
    foundry_account: str | None = None,
    search_service: str | None = None,
) -> tuple[str, bool]:
    """Best-effort removal of resources a failed deploy created, so nothing is
    left orphaned (and an Azure SQL server doesn't keep billing).

    Never raises. Returns ``(note, ws_still_exists)`` where ``note`` is a short
    human-readable summary to append to the error message, and
    ``ws_still_exists`` is True only when a workspace was created but could NOT
    be deleted (so the caller keeps the workspace id for a manual cleanup).
    """
    cleaned: list[str] = []
    failed: list[str] = []
    ws_still_exists = False

    # SQL server first — it's the resource that keeps billing if left behind.
    if azure_client and subscription_id and resource_group and sql_server:
        try:
            await azure_client.delete_sql_server(subscription_id, resource_group, sql_server)
            cleaned.append("Azure SQL server")
        except Exception as te:  # noqa: BLE001 — teardown must never mask the real error
            logger.warning("[teardown] SQL server '%s' delete failed: %s", sql_server, te)
            failed.append(f"Azure SQL server '{sql_server}'")

    # Foundry account next — it (and its model deployment) also bill if left behind.
    if azure_client and subscription_id and resource_group and foundry_account:
        try:
            await azure_client.delete_foundry_account(subscription_id, resource_group, foundry_account)
            cleaned.append("Foundry account")
        except Exception as te:  # noqa: BLE001
            logger.warning("[teardown] Foundry account '%s' delete failed: %s", foundry_account, te)
            failed.append(f"Foundry account '{foundry_account}'")

    # Azure AI Search — a STANDING-cost resource; must always be removed.
    if azure_client and subscription_id and resource_group and search_service:
        try:
            await azure_client.delete_search_service(subscription_id, resource_group, search_service)
            cleaned.append("Azure AI Search service")
        except Exception as te:  # noqa: BLE001
            logger.warning("[teardown] Search service '%s' delete failed: %s", search_service, te)
            failed.append(f"Azure AI Search service '{search_service}'")

    if azure_client and subscription_id and resource_group and storage_account:
        try:
            await azure_client.delete_storage_account(subscription_id, resource_group, storage_account)
            cleaned.append("storage account")
        except Exception as te:  # noqa: BLE001
            logger.warning("[teardown] storage account '%s' delete failed: %s", storage_account, te)
            failed.append(f"storage account '{storage_account}'")

    if ws_id:
        try:
            await client.delete_workspace(ws_id)
            cleaned.append("Fabric workspace")
        except Exception as te:  # noqa: BLE001
            logger.warning("[teardown] workspace '%s' delete failed: %s", ws_id, te)
            failed.append("Fabric workspace")
            ws_still_exists = True

    parts: list[str] = []
    if cleaned:
        parts.append("Cleaned up partially-created resources (" + ", ".join(cleaned) + ").")
    if failed:
        parts.append(
            "Could not auto-remove " + ", ".join(failed)
            + " — please delete manually to avoid charges."
        )
    return " ".join(parts), ws_still_exists


def _find_step(steps: list[DeploymentStep], name: str) -> DeploymentStep:
    for s in steps:
        if s.name == name:
            return s
    raise ValueError(f"Step '{name}' not found")


def _build_report_definition(demo_id: str, semantic_model_id: str, scenario_id: str | None = None) -> dict:
    """Build a Power BI report definition for the given demo and scenario."""
    # AI & ML scenario uses dedicated reports over the gold_ml_* tables
    if scenario_id == "ai-ml":
        if demo_id == "energy-grid":
            return build_energy_ml_report_definition(semantic_model_id)
        if demo_id == "manufacturing-qc":
            return build_manufacturing_ml_report_definition(semantic_model_id)
        if demo_id == "retail-sales":
            return build_retail_ml_report_definition(semantic_model_id)
        if demo_id == "financial-services":
            return build_financial_ml_report_definition(semantic_model_id)
        if demo_id == "healthcare":
            return build_healthcare_ml_report_definition(semantic_model_id)
        if demo_id == "technology":
            return build_technology_ml_report_definition(semantic_model_id)
        if demo_id == "transportation":
            return build_transportation_ml_report_definition(semantic_model_id)
        if demo_id == "hospitality":
            return build_hospitality_ml_report_definition(semantic_model_id)
        if demo_id == "media":
            return build_media_ml_report_definition(semantic_model_id)
        if demo_id == "professional-services":
            return build_professional_services_ml_report_definition(semantic_model_id)
        if demo_id == "construction":
            return build_construction_ml_report_definition(semantic_model_id)
        if demo_id == "education":
            return build_education_ml_report_definition(semantic_model_id)
        # other sectors fall through to their default report until ML reports are added
    if demo_id == "manufacturing-qc":
        return build_manufacturing_report_definition(semantic_model_id)
    elif demo_id == "retail-sales":
        return build_retail_report_definition(semantic_model_id)
    elif demo_id == "energy-grid":
        return build_energy_report_definition(semantic_model_id)
    return build_manufacturing_report_definition(semantic_model_id)


def _build_bim_definition(bim_path: Path, variables: dict[str, str] | None = None) -> dict:
    """Build a semantic model definition from a model.bim file with variable substitution."""
    import base64

    variables = variables or {}
    text = bim_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    bim_encoded = base64.b64encode(text.encode("utf-8")).decode()

    pbism = json.dumps({
        "version": "1.0",
        "settings": {}
    })
    pbism_encoded = base64.b64encode(pbism.encode("utf-8")).decode()

    return {
        "parts": [
            {
                "path": "model.bim",
                "payload": bim_encoded,
                "payloadType": "InlineBase64",
            },
            {
                "path": "definition.pbism",
                "payload": pbism_encoded,
                "payloadType": "InlineBase64",
            }
        ]
    }


def _build_pipeline_definition(
    workspace_id: str,
    notebooks: list[dict],
    notebook_ids: dict[str, str],
) -> dict:
    """Build a pipeline definition with sequential TridentNotebook activities."""
    import base64

    activities = []
    prev_name = None

    for nb in sorted(notebooks, key=lambda x: x.get("order", 99)):
        nb_name = nb["name"]
        nb_id = notebook_ids.get(nb_name, "")
        if not nb_id:
            continue

        activity = {
            "name": nb_name,
            "type": "TridentNotebook",
            "dependsOn": [],
            "policy": {
                "timeout": "0.12:00:00",
                "retry": 1,
                "retryIntervalInSeconds": 60,
                "secureOutput": False,
                "secureInput": False,
            },
            "typeProperties": {
                "notebookId": nb_id,
                "workspaceId": workspace_id,
            },
        }

        # Chain sequentially: each notebook depends on the previous one
        if prev_name:
            activity["dependsOn"] = [
                {"activity": prev_name, "dependencyConditions": ["Succeeded"]}
            ]

        activities.append(activity)
        prev_name = nb_name

    pipeline_json = {
        "properties": {
            "description": "Automated Bronze → Silver → Gold medallion pipeline",
            "activities": activities,
        }
    }

    encoded = base64.b64encode(json.dumps(pipeline_json).encode()).decode()
    return {
        "parts": [
            {
                "path": "pipeline-content.json",
                "payload": encoded,
                "payloadType": "InlineBase64",
            }
        ]
    }


# ── Mirroring scenario (Azure SQL → Fabric Mirrored Database) ──────────────


def _is_transient_run_error(detail: str) -> bool:
    """True when a notebook-run failure is a transient Spark/capacity hiccup
    that's worth retrying (cold-start, a platform-cancelled session, first-run
    flakiness, throttling) rather than a real error in the notebook code.

    Covers System_Cancelled_Session_State — the Spark session being cancelled by
    the platform before the notebook ran, which a single retry almost always
    clears. Without this, one transient cancellation killed the whole deploy.
    """
    d = (detail or "").lower()
    signatures = (
        "livy",
        "failed to create livy session",
        "system_cancelled_session_state",
        "cancelled_session",
        "session_statements_failed",
        "sessiontimeout",
        "session timed out",
        "toomanyrequests",
        "430",
        "throttl",
        # Transient Fabric / infrastructure server errors ("Fabric returned a
        # server error" — gateway, internal, service-unavailable). These are not
        # notebook code errors and almost always clear on a retry.
        "internalerror",
        "internal server error",
        "service unavailable",
        "serviceunavailable",
        "temporarily unavailable",
        "bad gateway",
        "gateway timeout",
        "502",
        "503",
        "504",
        "an unexpected error",
    )
    return any(s in d for s in signatures)


def _retry_wait_seconds(detail: str, attempt: int) -> int:
    """Backoff (seconds) before the next notebook-run retry. A saturated Spark
    capacity (TooManyRequestsForCapacity / HTTP 430) needs minutes to free up, so
    it waits noticeably longer than a one-off Spark cold-start or session blip."""
    d = (detail or "").lower()
    if "toomanyrequestsforcapacity" in d or "430" in d or "compute or api rate limit" in d:
        return min(60 + attempt * 45, 200)   # capacity saturated: 60,105,150,195,200
    return min(45 + attempt * 30, 150)        # cold-start / blip: 45,75,105,135,150


def _is_capacity_error(detail: str) -> bool:
    """True when a failure is specifically a Fabric Spark capacity limit (430)."""
    d = (detail or "").lower()
    return (
        "toomanyrequestsforcapacity" in d
        or "430" in d
        or "compute or api rate limit" in d
        or "spark compute or api rate limit" in d
    )


def _is_admission_error(detail: str) -> bool:
    """True only when the Spark *session could not be created* (capacity 430 /
    Livy admission). These failures happen BEFORE any notebook runs, so retrying
    is cheap and safe. Anything that fails AFTER the session starts — an
    in-notebook error, or a run that exceeds the pipeline timeout — is NOT an
    admission error and must fail fast rather than re-run the whole pipeline."""
    d = (detail or "").lower()
    return (
        "failed to create livy session" in d
        or "toomanyrequestsforcapacity" in d
        or "430" in d
        or "compute or api rate limit" in d
        or "toomanyrequests" in d
        or "throttl" in d
    )


def _friendly_capacity_error(detail: str) -> str:
    """Turn a raw 430/TooManyRequestsForCapacity error into clear, actionable
    guidance. A notebook job submitted through the Fabric public API can't be
    queued (by design), so when the capacity has no free Spark vCores the deploy
    can't proceed — the only fix is on the capacity side, not in the demo."""
    if _is_capacity_error(detail):
        return (
            "Your Fabric capacity is out of Spark compute right now "
            "(TooManyRequestsForCapacity / HTTP 430). This is a capacity limit, "
            "not a problem with the demo or your account. To deploy: open the "
            "Fabric Monitoring hub and cancel any running Spark jobs, wait a few "
            "minutes for compute to free up, or switch to a larger capacity "
            "(an F-SKU with more Spark vCores than Trial), then redeploy. The "
            "deploy already runs the whole pipeline in a single, minimal Spark "
            "session to use as little capacity as possible."
        )
    d = (detail or "").lower()
    if "did not finish within" in d or "timed out" in d:
        return (
            "The deployment didn't finish in time and was stopped. The notebooks "
            "were running but took longer than the allowed window — usually "
            "because the Fabric capacity is busy or under-sized. Try again when "
            "the capacity is less loaded, or use a larger capacity (an F-SKU), "
            "then redeploy."
        )
    return detail


def _build_orchestrator_source(
    notebooks_to_run: list[dict], optional_names: set[str] | None = None
) -> str:
    """Build the Python source for an *orchestrator* notebook that runs every
    medallion notebook inside ONE shared Spark session via
    ``notebookutils.notebook.runMultiple``.

    ``optional_names`` are best-effort activities (e.g. the cosmetic dashboard):
    if one of them fails, the pipeline data is still good, so the deploy is NOT
    failed — the failure is logged and the run still exits successfully.

    Why: each ``run_notebook`` API call creates its own Livy/Spark session. On
    constrained Fabric capacities (Trial / small F-SKUs) firing one session per
    notebook (bronze → silver → gold) means the deploy has to win capacity
    admission three separate times, and notebook jobs submitted via the public
    API are never queued — so a busy capacity returns HTTP 430. Running them as a
    single sequential DAG inside one session (the documented "high concurrency
    session sharing" pattern for small capacities) means the deploy only needs to
    win admission once and puts ~3× less pressure on the Spark API rate limit.

    A child failure raises ``Notebook '<name>' failed: ...`` so the caller can map
    it back to the matching ``run:<name>`` step.
    """
    ordered = sorted(notebooks_to_run, key=lambda n: n.get("order", 0))
    activities: list[dict] = []
    prev: str | None = None
    for nb in ordered:
        name = nb["name"]
        activity: dict = {
            "name": name,
            "path": name,
            "timeoutPerCellInSeconds": 1200,
        }
        if prev is not None:
            activity["dependencies"] = [prev]
        activities.append(activity)
        prev = name

    dag = {
        "activities": activities,
        # Bound the DAG just under the deployer's pipeline_timeout (3600s) so the
        # DAG self-terminates and releases the Spark session before the API stops
        # waiting, instead of lingering.
        "timeoutInSeconds": 3300,
        "concurrency": 1,  # run sequentially: bronze → silver → gold, minimal footprint
    }
    # json.dumps output is also a valid Python literal here (no bool/null values).
    dag_literal = json.dumps(dag, indent=4)
    optional_literal = json.dumps(sorted(optional_names or []))

    return (
        "import notebookutils\n"
        "from notebookutils.common.exceptions import RunMultipleFailedException\n"
        "\n"
        f"DAG = {dag_literal}\n"
        f"OPTIONAL = {optional_literal}\n"
        "\n"
        "notebookutils.notebook.validateDAG(DAG)\n"
        "\n"
        "try:\n"
        "    results = notebookutils.notebook.runMultiple(DAG)\n"
        "except RunMultipleFailedException as ex:\n"
        "    results = ex.result\n"
        "\n"
        "required_failures = []\n"
        "optional_failures = []\n"
        "for _name, _res in (results or {}).items():\n"
        "    _exc = _res.get('exception') if isinstance(_res, dict) else None\n"
        "    if _exc:\n"
        "        _msg = \"Notebook '%s' failed: %s\" % (_name, str(_exc)[:500])\n"
        "        if _name in OPTIONAL:\n"
        "            optional_failures.append(_msg)\n"
        "        else:\n"
        "            required_failures.append(_msg)\n"
        "\n"
        "if optional_failures:\n"
        "    print('Non-fatal best-effort notebook failure(s): ' + ' | '.join(optional_failures))\n"
        "\n"
        "if required_failures:\n"
        "    raise Exception(' | '.join(required_failures))\n"
        "\n"
        "notebookutils.notebook.exit('ok')\n"
    )


async def _deploy_mirroring(
    client: FabricClient,
    demo_id: str,
    demo_dir: Path,
    items: list[dict],
    workspace_name: str | None,
    workspace_id: str | None,
    capacity_id: str | None,
    azure_client: AzureClient | None,
    subscription_id: str | None,
    resource_group: str | None,
    azure_location: str,
    create_resource_group: bool,
    sql_server_name: str | None,
) -> AsyncIterator[dict]:
    """Deploy the mirroring scenario:

    workspace → workspace identity → lakehouse (staging) → upload CSVs →
    provision Azure SQL (Entra-only server w/ SAMI + firewall + database) →
    seed notebook (Entra-token JDBC: tables + data + workspace-identity grants) →
    Fabric SQL connection (workspace identity) → SAMI workspace role →
    MirroredDatabase item → start replication → wait for tables →
    exploration notebooks (not run).
    """
    import random
    import string as _string

    lakehouses = [i for i in items if i["type"] == "Lakehouse"]
    mirrored_items = [i for i in items if i["type"] == "MirroredDatabase"]
    notebooks = [i for i in items if i["type"] == "Notebook"]
    seed_notebooks = [nb for nb in notebooks if nb.get("order") is not None]
    explore_notebooks = [nb for nb in notebooks if nb.get("order") is None]

    # Per-sector mirroring spec: tables, primary keys, explore query, live-change.
    # The seed/explore/live-change notebooks are SHARED and generic; everything
    # sector-specific comes from demos/<demo>/mirroring.json.
    spec_path = demo_dir / "mirroring.json"
    mirroring_spec = None
    if spec_path.exists():
        try:
            mirroring_spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            mirroring_spec = None
    mirrored_name = (
        (mirroring_spec or {}).get("mirroredDbName")
        or (mirrored_items[0]["name"] if mirrored_items else "mirrored_db")
    )
    row_cap = int((mirroring_spec or {}).get("rowCap") or 200000)
    # Shared mirroring notebooks live under demos/_scenarios/, not the demo folder.
    scenarios_dir = demo_dir.parent / "_scenarios"

    data_files = list((demo_dir / "data").glob("*")) if (demo_dir / "data").exists() else []

    # ── Plan ─────────────────────────────────────────────────────────────
    steps: list[DeploymentStep] = []
    if not workspace_id:
        steps.append(DeploymentStep("workspace", f"Create workspace '{workspace_name}'"))
    steps.append(DeploymentStep("ws-identity", "Provision workspace identity (secure mirroring auth)"))
    for lh in lakehouses:
        steps.append(DeploymentStep(f"lakehouse:{lh['name']}", f"Create lakehouse '{lh['name']}'"))
    if data_files:
        steps.append(DeploymentStep("upload-data", f"Upload {len(data_files)} sample data file(s)"))
    steps.append(DeploymentStep("sql-server", "Provision Azure SQL server + database"))
    for nb in seed_notebooks:
        steps.append(DeploymentStep(f"notebook:{nb['name']}", f"Create notebook '{nb['name']}'"))
    for nb in seed_notebooks:
        steps.append(DeploymentStep(f"run:{nb['name']}", f"Execute notebook '{nb['name']}' (seed SQL tables)"))
    steps.append(DeploymentStep("sql-connection", "Create Fabric connection to Azure SQL"))
    steps.append(DeploymentStep(f"mirrored-db:{mirrored_name}", f"Create mirrored database '{mirrored_name}'"))
    steps.append(DeploymentStep("mirror-sync", "Wait for initial replication"))
    for nb in explore_notebooks:
        steps.append(DeploymentStep(f"notebook:{nb['name']}", f"Create notebook '{nb['name']}'"))
    steps.append(DeploymentStep("done", "Deployment complete"))

    yield {"event": "plan", "data": [s.to_dict() for s in steps]}

    ws_id = workspace_id
    created_ids: dict[str, str] = {}
    sql_server = ""

    try:
        # Pre-flight: fail fast on a paused/inactive capacity.
        cap_err = await _capacity_inactive_error(client, capacity_id, workspace_id)
        if cap_err:
            yield {"event": "error", "data": {"message": cap_err, "workspaceId": ""}}
            return

        if not azure_client or not subscription_id or not resource_group:
            raise FabricError(
                400,
                "Mirroring deployment requires an Azure subscription, resource group, "
                "and management token (sign in and select them in the Azure section).",
            )

        # The deploying user becomes the Azure SQL Microsoft Entra ID administrator.
        # The server is created with Entra-only auth (no SQL login/password ever),
        # which is mandatory in MCAPS/MSIT-governed tenants.
        entra_login, entra_oid, entra_tenant = azure_client.get_caller_entra_admin()
        if not entra_oid or not entra_tenant:
            raise FabricError(
                400,
                "Could not determine your Microsoft Entra identity from the management "
                "token. Sign out, sign back in, and retry.",
            )

        if not mirroring_spec or not mirroring_spec.get("tables"):
            raise FabricError(
                500,
                "This demo is missing a valid mirroring.json spec (tables, primary keys, "
                "explore query, and live-change). Cannot run the mirroring scenario.",
            )
        spec_b64 = base64.b64encode(
            json.dumps(mirroring_spec).encode("utf-8")
        ).decode("ascii")

        # 1. Workspace
        if not ws_id:
            step = _find_step(steps, "workspace")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                ws = await client.create_workspace(workspace_name or demo_id, capacity_id)
                ws_id = ws["id"]
                step.status = "completed"
                step.item_id = ws_id
            except FabricError as e:
                step.status = "failed"
                if e.status == 409:
                    step.detail = f"A workspace named '{workspace_name}' already exists. Please choose a different name."
                else:
                    step.detail = f"Failed to create workspace: {e.detail[:200]}"
                yield {"event": "step", "data": step.to_dict()}
                yield {"event": "error", "data": {"message": step.detail, "workspaceId": ""}}
                return
            yield {"event": "step", "data": step.to_dict()}

        # 1b. Workspace identity — the secret-less Microsoft Entra principal the
        # Mirrored Database connection authenticates with (no service principal
        # to register, no interactive sign-in). Its SP name == the workspace name.
        step = _find_step(steps, "ws-identity")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        await client.provision_workspace_identity(ws_id)
        ws_info = await client.get_workspace(ws_id)
        ws_identity_name = ws_info.get("displayName") or (workspace_name or demo_id)
        # The workspace identity's Application (client) ID lets the seed notebook
        # create the contained SQL user BY SID, avoiding the Microsoft Graph lookup
        # that `CREATE USER ... FROM EXTERNAL PROVIDER` performs (which fails in
        # governed tenants where the SQL server identity lacks Directory Readers).
        ws_identity_app_id = (ws_info.get("workspaceIdentity") or {}).get("applicationId") or ""
        if ws_identity_app_id:
            logger.info("[ws-identity] applicationId %s", ws_identity_app_id)
        else:
            logger.warning(
                "[ws-identity] no applicationId in workspace response; seed notebook "
                "will fall back to FROM EXTERNAL PROVIDER (needs Directory Readers)"
            )
        # Region for the Azure SQL server. Honor the user's chosen region
        # (azure_location, the scenario's "Azure Region" field) FIRST: mirroring
        # replicates cross-region, and many governed subscriptions (e.g. MCAPS)
        # actually RESTRICT Azure SQL provisioning in the Fabric capacity's region,
        # so blindly co-locating there hard-fails ("Subscriptions are restricted
        # from provisioning in this region"). Fall back to the capacity's region
        # only when the user supplied no region. Azure region codes are the display
        # name lowercased with spaces removed ("West US 3" -> "westus3").
        cap_region = (ws_info.get("capacityRegion") or "").strip()
        sql_location = (
            (azure_location or "").strip().lower().replace(" ", "")
            or cap_region.lower().replace(" ", "")
            or "eastus"
        )
        step.status = "completed"
        step.detail = f"Workspace identity '{ws_identity_name}' ready"
        yield {"event": "step", "data": step.to_dict()}

        # 2. Lakehouse (staging area for the CSVs the seed notebook reads)
        lakehouse_id = None
        lakehouse_name = None
        for lh in lakehouses:
            step = _find_step(steps, f"lakehouse:{lh['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            result = await client.create_lakehouse(ws_id, lh["name"])
            lh_id = result["id"]
            created_ids[lh["name"]] = lh_id
            if lakehouse_id is None:
                lakehouse_id = lh_id
                lakehouse_name = lh["name"]
            step.status = "completed"
            step.item_id = lh_id
            yield {"event": "step", "data": step.to_dict()}

        # 3. Upload data files
        if data_files and lakehouse_id:
            step = _find_step(steps, "upload-data")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            for f in data_files:
                await client.upload_file_to_lakehouse(ws_id, lakehouse_id, f"landing/{f.name}", f)
            step.status = "completed"
            step.detail = f"Uploaded {len(data_files)} files"
            yield {"event": "step", "data": step.to_dict()}

        # 4. Provision Azure SQL (server with SAMI + firewall + database)
        step = _find_step(steps, "sql-server")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}

        def _gen_sql_name() -> str:
            return sql_server_name or (
                f"fdg-{demo_id.replace('-', '')[:8]}-"
                + "".join(random.choices(_string.ascii_lowercase + _string.digits, k=6))
            )

        sql_server = _gen_sql_name()
        sql_database = f"{demo_id.replace('-', '')[:12]}ops"
        sami_principal_id = ""
        # The resource group is just a metadata container and isn't subject to the
        # SQL per-region provisioning deny policy, so create it once up front.
        try:
            if create_resource_group:
                await azure_client.create_resource_group(subscription_id, resource_group, sql_location)
        except AzureError as e:
            raise FabricError(e.status, f"Azure SQL provisioning failed: {e.detail}")

        # Provision the SQL server, self-healing around two transient classes:
        #  - region restriction: some subscriptions (e.g. MCAPS) deny SQL
        #    provisioning in specific regions ("Provisioning is restricted in this
        #    region"), only detectable at create time -> fall back across regions.
        #  - global name collision: Azure SQL server names are globally unique and
        #    stay reserved for a while after deletion ("already exists / taken /
        #    not available") -> regenerate the name and retry (unless the caller
        #    pinned an explicit sql_server_name we must not change).
        chosen_region = sql_location
        _fallback_regions = ["westus2", "westus3", "westeurope", "centralus", "eastus2", "swedencentral", "germanywestcentral", "switzerlandnorth"]
        region_candidates = [chosen_region] + [r for r in _fallback_regions if r != chosen_region]
        srv = None
        _last_err: AzureError | None = None
        _restricted_regions: list[str] = []   # regions the subscription blocks SQL in
        _tried_regions: list[str] = []
        # Iterate regions, using a FRESH globally-unique server name for each region
        # attempt (unless the caller pinned an explicit name). This prevents a
        # self-inflicted 409 "name already taken": a region-restricted create
        # returns 202 first and only fails async, which leaves the name reserved —
        # reusing it in the next region would then 409 and be misreported as a name
        # collision rather than the real region restriction.
        for _region in region_candidates:
            _name_for_region = sql_server_name or _gen_sql_name()
            _tried_regions.append(_region)
            try:
                srv = await azure_client.create_sql_server(
                    subscription_id, resource_group, _name_for_region, _region,
                    entra_login, entra_oid, entra_tenant,
                )
                sql_server = _name_for_region
                sql_location = _region
                break
            except AzureError as e:
                _last_err = e
                _msg = (e.detail or "").lower()
                # Best-effort cleanup of any half-created server holding this name,
                # so it can't poison later attempts or linger as an orphan.
                try:
                    await azure_client.delete_sql_server(subscription_id, resource_group, _name_for_region)
                except Exception:
                    pass
                if "restricted" in _msg and "region" in _msg:
                    _restricted_regions.append(_region)
                    continue  # region-restriction → try the next region
                if (
                    "already" in _msg or "not available" in _msg or "taken" in _msg
                ) and ("name" in _msg or "server" in _msg):
                    if sql_server_name:
                        # Caller pinned a name we can't change — fail clearly.
                        raise FabricError(
                            409,
                            f"SQL server name '{sql_server_name}' is already taken globally. "
                            "Choose a different name.",
                        )
                    continue  # fresh name next region anyway → just move on
                raise FabricError(e.status, f"Azure SQL provisioning failed: {e.detail}")

        if srv is None:
            # If every region we attempted was region-restricted, the subscription
            # simply can't provision Azure SQL there — say so plainly and point the
            # user at the region picker, rather than a misleading "name taken".
            if _restricted_regions and len(_restricted_regions) == len(_tried_regions):
                raise FabricError(
                    403,
                    "Your Azure subscription is restricted from provisioning Azure SQL in all "
                    f"attempted regions ({', '.join(_tried_regions)}). Pick a region your "
                    "subscription allows in the Azure Region dropdown and retry. If none work, "
                    "your subscription likely has a provisioning policy on Azure SQL — request an "
                    "exception via Azure support (Issue type: 'Service and subscription limits').",
                )
            raise FabricError(
                getattr(_last_err, "status", 500),
                "Azure SQL provisioning failed "
                f"(regions tried: {', '.join(_tried_regions)}). Last error: "
                f"{getattr(_last_err, 'detail', 'unknown error')}",
            )

        try:
            sami_principal_id = (srv.get("identity") or {}).get("principalId", "")
            # 'Allow Azure services' — required by both Fabric Spark and the mirroring service
            await azure_client.create_sql_firewall_rule(
                subscription_id, resource_group, sql_server,
                "AllowAllWindowsAzureIps", "0.0.0.0", "0.0.0.0",
            )
            await azure_client.create_sql_database(
                subscription_id, resource_group, sql_server, sql_database, sql_location
            )
        except AzureError as e:
            raise FabricError(e.status, f"Azure SQL provisioning failed: {e.detail}")
        step.status = "completed"
        _fallback_note = "" if sql_location == chosen_region else f" (fell back from {chosen_region})"
        step.detail = f"{sql_server}.database.windows.net / {sql_database} (S3 tier, {sql_location}){_fallback_note}"
        yield {"event": "step", "data": step.to_dict()}

        sql_fqdn = f"{sql_server}.database.windows.net"
        nb_variables = {
            "SQL_SERVER": sql_fqdn,
            "SQL_DATABASE": sql_database,
            "WORKSPACE_IDENTITY_NAME": ws_identity_name,
            "WORKSPACE_IDENTITY_APP_ID": ws_identity_app_id,
            "DATA_SOURCE_PATH": "Files/landing",
            "WORKSPACE_ID": ws_id,
            "MIRRORING_SPEC_B64": spec_b64,
            "ROW_CAP": str(row_cap),
        }

        # 5. Seed notebook — create and run (writes tables with PKs via JDBC)
        notebook_ids: dict[str, str] = {}
        for nb in seed_notebooks:
            step = _find_step(steps, f"notebook:{nb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            ipynb_path = scenarios_dir / nb.get("definitionPath", f"notebooks/mirroring/{nb['name']}.ipynb")
            result = await client.create_notebook(
                ws_id, nb["name"], ipynb_path, lakehouse_id, lakehouse_name,
                variables=nb_variables,
            )
            notebook_ids[nb["name"]] = result["id"]
            created_ids[nb["name"]] = result["id"]
            step.status = "completed"
            step.item_id = result["id"]
            yield {"event": "step", "data": step.to_dict()}

        for nb in seed_notebooks:
            step = _find_step(steps, f"run:{nb['name']}")
            step.status = "running"
            step.detail = (
                "Loading tables, then registering the Fabric workspace identity in Azure SQL. "
                "The identity can take 1–3 min to propagate in Microsoft Entra before SQL can "
                "resolve it — this step is waiting on that, not stuck."
            )
            yield {"event": "step", "data": step.to_dict()}

            async def _run_seed() -> dict:
                res = await client.run_notebook(
                    ws_id, notebook_ids[nb["name"]], lakehouse_id, lakehouse_name, timeout=1800
                )
                job_status = res.get("status", "").lower() if isinstance(res, dict) else ""
                if job_status == "failed":
                    failure = res.get("failureReason", {})
                    raise FabricError(500, f"Seed notebook failed: {failure.get('message', '')[:200]}")
                return res or {}

            # Run with bounded retries on transient Spark/capacity hiccups
            # (cold-start, platform-cancelled session, throttling). A real code
            # error in the notebook is not transient and fails immediately.
            max_attempts = 5
            last_err: FabricError | None = None
            for attempt in range(max_attempts):
                try:
                    await _run_seed()
                    last_err = None
                    break
                except FabricError as e:
                    last_err = e
                    if attempt < max_attempts - 1 and _is_transient_run_error(e.detail):
                        wait = _retry_wait_seconds(e.detail, attempt)
                        step.detail = f"Spark capacity busy / transient hiccup — retrying ({attempt + 1}/{max_attempts - 1}) in {wait}s..."
                        yield {"event": "step", "data": step.to_dict()}
                        await asyncio.sleep(wait)
                        continue
                    raise
            if last_err is not None:
                raise last_err

            step.status = "completed"
            step.detail = "SQL tables created and loaded"
            yield {"event": "step", "data": step.to_dict()}

        # 6. Fabric connection to the SQL database (workspace identity / Entra auth)
        step = _find_step(steps, "sql-connection")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        conn = await client.create_sql_connection(
            display_name=f"{demo_id}-{sql_server}-conn",
            server=sql_fqdn,
            database=sql_database,
        )
        connection_id = conn.get("id") or conn.get("connectionId") or ""
        if not connection_id:
            raise FabricError(500, "SQL connection created but no ID returned")
        step.status = "completed"
        step.detail = f"Connection ID: {connection_id}"
        yield {"event": "step", "data": step.to_dict()}

        # Grant the SQL server's SAMI a workspace role so the mirroring
        # service can write replicated data (documented prerequisite).
        if sami_principal_id:
            try:
                await client.add_workspace_role_assignment(
                    ws_id, sami_principal_id, "ServicePrincipal", "Contributor"
                )
                logger.info("[mirroring] SAMI %s granted Contributor", sami_principal_id)
            except FabricError as e:
                logger.warning("[mirroring] SAMI role assignment failed: %s", e.detail[:200])

        # 7. Mirrored database item + start replication
        step = _find_step(steps, f"mirrored-db:{mirrored_name}")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        md = await client.create_mirrored_database(ws_id, mirrored_name, connection_id)
        md_id = md["id"]
        created_ids[mirrored_name] = md_id
        # start_mirroring self-verifies (retries until Running) — a fresh mirrored
        # DB often ignores the first startMirroring call.
        try:
            await client.start_mirroring(ws_id, md_id)
        except FabricError as e:
            logger.warning("[mirroring] startMirroring: %s", e.detail[:200])
        step.status = "completed"
        step.item_id = md_id
        yield {"event": "step", "data": step.to_dict()}

        # 8. Wait for the initial snapshot to replicate
        step = _find_step(steps, "mirror-sync")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        # One mirrored table per CSV — exclude helper files (e.g. _generate_data.py,
        # .gitkeep) that are staged in the data folder but never become tables.
        expected = max(1, len([f for f in data_files if f.suffix.lower() == ".csv"]))
        table_status = await client.wait_for_mirrored_tables(ws_id, md_id, expected, timeout=900)
        replicating = [
            t for t in table_status
            if (t.get("status") or "").lower() in ("replicating", "replicated")
            or (t.get("metrics") or {}).get("processedRows", 0) > 0
        ]
        step.status = "completed"
        if len(replicating) >= expected:
            step.detail = f"{len(replicating)} tables replicating"
        else:
            step.detail = (
                f"{len(replicating)}/{expected} tables replicating so far — initial sync "
                "can take a few more minutes; check the mirrored database item."
            )
        yield {"event": "step", "data": step.to_dict()}

        # 9. Exploration notebooks (created with mirror context, not auto-run).
        # These are conveniences added AFTER replication is already live, so a
        # transient failure here must NOT fail (and tear down) a working mirror —
        # mark the step skipped and carry on to "done".
        nb_variables["MIRRORED_DB_ID"] = md_id
        for nb in explore_notebooks:
            step = _find_step(steps, f"notebook:{nb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            ipynb_path = scenarios_dir / nb.get("definitionPath", f"notebooks/mirroring/{nb['name']}.ipynb")
            try:
                result = await client.create_notebook(
                    ws_id, nb["name"], ipynb_path, lakehouse_id, lakehouse_name,
                    variables=nb_variables,
                )
                created_ids[nb["name"]] = result["id"]
                step.status = "completed"
                step.item_id = result["id"]
            except (FabricError, Exception) as e:  # noqa: BLE001 — non-critical step
                logger.warning("[mirroring] explore notebook '%s' creation skipped: %s", nb["name"], e)
                step.status = "skipped"
                detail = e.detail if isinstance(e, FabricError) else str(e)
                step.detail = f"Optional notebook skipped (mirroring is live): {detail[:160]}"
            yield {"event": "step", "data": step.to_dict()}

        # Done — include Azure metadata so teardown can delete the SQL server
        step = _find_step(steps, "done")
        step.status = "completed"
        step.detail = json.dumps({
            "workspaceId": ws_id,
            "items": created_ids,
            "azure": {
                "subscriptionId": subscription_id,
                "resourceGroup": resource_group,
                "sqlServer": sql_server,
            },
        })
        yield {"event": "step", "data": step.to_dict()}

    except FabricError as e:
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = e.detail[:300]
                yield {"event": "step", "data": s.to_dict()}
                break
        cleanup_note, ws_remaining = await _best_effort_teardown(
            client, azure_client, ws_id, subscription_id, resource_group,
            sql_server=sql_server or None,
        )
        error_msg = str(e)
        if cleanup_note:
            error_msg += "\n\n" + cleanup_note
        data: dict = {"message": error_msg, "workspaceId": ws_id if ws_remaining else ""}
        # Keep Azure cleanup info only if the workspace couldn't be torn down
        # (so the gallery's cleanup button can still remove both).
        if ws_remaining and sql_server:
            data["azure"] = {"subscriptionId": subscription_id, "resourceGroup": resource_group, "sqlServer": sql_server}
        yield {"event": "error", "data": data}

    except AzureError as e:
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = e.detail[:300]
                yield {"event": "step", "data": s.to_dict()}
                break
        cleanup_note, ws_remaining = await _best_effort_teardown(
            client, azure_client, ws_id, subscription_id, resource_group,
            sql_server=sql_server or None,
        )
        error_msg = f"Azure error: {e.detail}"
        if cleanup_note:
            error_msg += "\n\n" + cleanup_note
        data = {"message": error_msg, "workspaceId": ws_id if ws_remaining else ""}
        if ws_remaining and sql_server:
            data["azure"] = {"subscriptionId": subscription_id, "resourceGroup": resource_group, "sqlServer": sql_server}
        yield {"event": "error", "data": data}

    except Exception as e:
        logger.exception("Mirroring deployment failed")
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = str(e)[:300]
                yield {"event": "step", "data": s.to_dict()}
                break
        cleanup_note, ws_remaining = await _best_effort_teardown(
            client, azure_client, ws_id, subscription_id, resource_group,
            sql_server=sql_server or None,
        )
        error_msg = f"Unexpected error: {str(e)[:300]}"
        if cleanup_note:
            error_msg += "\n\n" + cleanup_note
        data = {"message": error_msg, "workspaceId": ws_id if ws_remaining else ""}
        if ws_remaining and sql_server:
            data["azure"] = {"subscriptionId": subscription_id, "resourceGroup": resource_group, "sqlServer": sql_server}
        yield {"event": "error", "data": data}


# ── Fabric + Foundry AI agent scenario (preview) ─────────────────────────────


async def _foundry_quota_warning(
    azure_client: "AzureClient | None",
    subscription_id: str | None,
    location: str,
    model_name: str,
    model_version: str,
) -> str | None:
    """Advisory model-quota pre-flight (never fatal): return a human note if the
    chosen model has no capacity in the requested region. Mirrors the spirit of
    ``_capacity_inactive_error`` — a listing hiccup must not block the deploy."""
    if not azure_client or not subscription_id:
        return None
    caps = await azure_client.check_model_capacity(subscription_id, model_name, model_version)
    if not caps:
        return None
    loc = (location or "").lower().replace(" ", "")
    here = next((c for c in caps if (c.get("location") or "").lower() == loc), None)
    if here and here.get("availableCapacity", 0) > 0:
        return None
    available = sorted({c["location"] for c in caps if c.get("availableCapacity", 0) > 0})
    if not available:
        return (
            f"No '{model_name}' quota is available in your subscription. Request quota "
            "in the Microsoft Foundry portal, then retry."
        )
    return (
        f"'{model_name}' has no quota in '{location}'. Regions with capacity: "
        + ", ".join(list(available)[:6])
        + "."
    )


async def _select_foundry_model(
    azure_client: "AzureClient | None",
    subscription_id: str | None,
    location: str,
    candidates: list[tuple[str, str]],
) -> tuple[str, str, str | None]:
    """Pick the first candidate ``(name, version)`` that has quota in ``location``,
    falling back to the next when the preferred model is capped. Never fatal: if we
    can't determine capacity (no creds or a listing hiccup) we return the first
    candidate so the deploy proceeds and the normal advisory warning still applies.
    Returns ``(model_name, model_version, note)`` where ``note`` explains a downgrade."""
    primary_name, primary_version = candidates[0]
    if not azure_client or not subscription_id:
        return primary_name, primary_version, None
    loc = (location or "").lower().replace(" ", "")
    for idx, (name, version) in enumerate(candidates):
        caps = await azure_client.check_model_capacity(subscription_id, name, version)
        if not caps:
            # Unknown (listing hiccup). Trust it only for the preferred model — use
            # it and move on; for a fallback candidate keep looking.
            if idx == 0:
                return primary_name, primary_version, None
            continue
        here = next((c for c in caps if (c.get("location") or "").lower() == loc), None)
        if here and here.get("availableCapacity", 0) > 0:
            if idx == 0:
                return name, version, None
            return name, version, (
                f"'{primary_name}' has no quota in '{location}' — deployed '{name}' instead."
            )
    # No candidate had quota in this region: keep the preferred model and let the
    # advisory warning + graceful skip explain it.
    return primary_name, primary_version, None


async def _deploy_fabric_foundry(
    client: FabricClient,
    demo_id: str,
    demo_dir: Path,
    items: list[dict],
    workspace_name: str | None,
    workspace_id: str | None,
    capacity_id: str | None,
    azure_client: AzureClient | None,
    subscription_id: str | None,
    resource_group: str | None,
    azure_location: str,
    create_resource_group: bool,
    search_token: str | None = None,
    agent_token: str | None = None,
) -> AsyncIterator[dict]:
    """Deploy the Fabric + Foundry AI agent scenario (one-click, all headless):

    workspace → lakehouse → upload CSVs → run batch notebooks (populate gold
    tables) → create & PUBLISH a Fabric data agent over the lakehouse (via item
    definition — no notebook/SDK) → provision a Microsoft Foundry account +
    project + chat model → provision Azure AI Search (Foundry IQ engine) →
    wire the 3-way managed-identity RBAC → create the Foundry IQ knowledge
    source + base → create the project connection + agent grounded on it.

    Each Foundry/Search step is best-effort: a preview-API failure degrades that
    step to "skipped" with a manual follow-up, so the Fabric foundation + data
    agent still succeed.
    """
    import random
    import string as _string
    from app.azure_client import AzureError
    from app.foundry_iq_client import FoundryIQClient, FoundryAgentClient, FoundryAgentError

    # Preferred model first, then a graceful fallback when the preferred one has no
    # quota in the chosen region. Both deploy as GlobalStandard (capacity pooled
    # across regions — the most quota/region-flexible SKU).
    FOUNDRY_MODEL_CANDIDATES = [
        ("gpt-4.1-mini", "2025-04-14"),  # preferred: stronger reasoning + tool-calling
        ("gpt-4o-mini", "2024-07-18"),   # fallback: widest availability + highest quota
    ]
    MODEL_NAME, MODEL_VERSION, model_note = await _select_foundry_model(
        azure_client, subscription_id, azure_location, FOUNDRY_MODEL_CANDIDATES
    )
    # Deployment names allow only alphanumerics, '_' and '-' (no dots).
    DEPLOYMENT_NAME = MODEL_NAME.replace(".", "")

    lakehouses = [i for i in items if i["type"] == "Lakehouse"]
    notebooks = [i for i in items if i["type"] == "Notebook"]
    run_notebooks = [nb for nb in notebooks if nb.get("order") is not None]
    data_agents = [i for i in items if i["type"] == "DataAgent"]
    agent_name = data_agents[0]["name"] if data_agents else "analytics_data_agent"
    da_instructions = (
        "You answer questions about manufacturing quality-control data "
        "(production batches, sensor readings, equipment, defects). "
        "Prefer the gold tables in the lakehouse."
    )
    data_files = list((demo_dir / "data").glob("*")) if (demo_dir / "data").exists() else []

    # ── Plan ─────────────────────────────────────────────────────────────
    steps: list[DeploymentStep] = []
    if not workspace_id:
        steps.append(DeploymentStep("workspace", f"Create workspace '{workspace_name}'"))
    for lh in lakehouses:
        steps.append(DeploymentStep(f"lakehouse:{lh['name']}", f"Create lakehouse '{lh['name']}'"))
    if data_files:
        steps.append(DeploymentStep("upload-data", f"Upload {len(data_files)} sample data file(s)"))
    for nb in run_notebooks:
        steps.append(DeploymentStep(f"notebook:{nb['name']}", f"Create notebook '{nb['name']}'"))
    for nb in run_notebooks:
        steps.append(DeploymentStep(f"run:{nb['name']}", f"Execute notebook '{nb['name']}'"))
    steps.append(DeploymentStep("data-agent", f"Create & publish Fabric data agent '{agent_name}'"))
    steps.append(DeploymentStep("foundry-account", "Provision Microsoft Foundry account + project"))
    steps.append(DeploymentStep("foundry-model", f"Deploy model '{MODEL_NAME}'"))
    steps.append(DeploymentStep("search-service", "Provision Azure AI Search (Foundry IQ engine)"))
    steps.append(DeploymentStep("rbac", "Wire managed-identity permissions"))
    steps.append(DeploymentStep("knowledge", "Create Foundry IQ knowledge source + base"))
    steps.append(DeploymentStep("agent", "Create Foundry agent grounded on the data"))
    steps.append(DeploymentStep("done", "Deployment complete"))
    yield {"event": "plan", "data": [s.to_dict() for s in steps]}

    ws_id = workspace_id
    created_ids: dict[str, str] = {}
    foundry_account = ""
    foundry_project = ""
    search_service = ""
    artifact_id = ""
    agent_created = ""
    next_steps: list[str] = []  # manual follow-ups for any skipped Foundry steps

    try:
        # Pre-flight: fail fast on a paused/inactive capacity.
        cap_err = await _capacity_inactive_error(client, capacity_id, workspace_id)
        if cap_err:
            yield {"event": "error", "data": {"message": cap_err, "workspaceId": ""}}
            return

        if not azure_client or not subscription_id or not resource_group:
            raise FabricError(
                400,
                "The Fabric + Foundry scenario needs an Azure subscription and resource "
                "group (sign in and select them in the Azure section).",
            )

        # 1. Workspace
        if not ws_id:
            step = _find_step(steps, "workspace")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                ws = await client.create_workspace(workspace_name or demo_id, capacity_id)
                ws_id = ws["id"]
                step.status = "completed"
                step.item_id = ws_id
            except FabricError as e:
                step.status = "failed"
                if e.status == 409:
                    step.detail = f"A workspace named '{workspace_name}' already exists. Please choose a different name."
                else:
                    step.detail = f"Failed to create workspace: {e.detail[:200]}"
                yield {"event": "step", "data": step.to_dict()}
                yield {"event": "error", "data": {"message": step.detail, "workspaceId": ""}}
                return
            yield {"event": "step", "data": step.to_dict()}

        # 2. Lakehouse
        lakehouse_id = None
        lakehouse_name = None
        for lh in lakehouses:
            step = _find_step(steps, f"lakehouse:{lh['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            result = await client.create_lakehouse(ws_id, lh["name"])
            lh_id = result["id"]
            created_ids[lh["name"]] = lh_id
            if lakehouse_id is None:
                lakehouse_id = lh_id
                lakehouse_name = lh["name"]
            step.status = "completed"
            step.item_id = lh_id
            yield {"event": "step", "data": step.to_dict()}

        # 3. Upload data → Files/landing (same convention as the standard deploy)
        nb_variables: dict[str, str] = {"DATA_SOURCE_PATH": "Files/landing"}
        if data_files and lakehouse_id:
            step = _find_step(steps, "upload-data")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            for f in data_files:
                await client.upload_file_to_lakehouse(ws_id, lakehouse_id, f"landing/{f.name}", f)
            step.status = "completed"
            step.detail = f"Uploaded {len(data_files)} files"
            yield {"event": "step", "data": step.to_dict()}

        # 4. Create batch notebooks (bronze → silver → gold)
        notebook_ids: dict[str, str] = {}
        for nb in run_notebooks:
            step = _find_step(steps, f"notebook:{nb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            ipynb_path = demo_dir / nb.get("definitionPath", f"notebooks/{nb['name']}.ipynb")
            result = await client.create_notebook(
                ws_id, nb["name"], ipynb_path, lakehouse_id, lakehouse_name,
                variables=nb_variables or None,
            )
            notebook_ids[nb["name"]] = result["id"]
            created_ids[nb["name"]] = result["id"]
            step.status = "completed"
            step.item_id = result["id"]
            yield {"event": "step", "data": step.to_dict()}

        # 5. Run batch notebooks sequentially (populate the gold tables the agent queries)
        for i, nb in enumerate(run_notebooks):
            step = _find_step(steps, f"run:{nb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            if i > 0:
                await asyncio.sleep(45)  # avoid Spark throttling between runs
            nb_id = notebook_ids[nb["name"]]
            max_attempts = 5
            last_err: FabricError | None = None
            for attempt in range(max_attempts):
                try:
                    res = await client.run_notebook(ws_id, nb_id, lakehouse_id, lakehouse_name, timeout=1800)
                    js = res.get("status", "").lower() if isinstance(res, dict) else ""
                    if js == "failed":
                        raise FabricError(500, f"Notebook '{nb['name']}' failed: {res.get('failureReason', {}).get('message', '')[:200]}")
                    last_err = None
                    break
                except FabricError as e:
                    last_err = e
                    if attempt < max_attempts - 1 and _is_transient_run_error(e.detail):
                        wait = _retry_wait_seconds(e.detail, attempt)
                        step.detail = f"Spark capacity busy / transient hiccup — retrying ({attempt + 1}/{max_attempts - 1}) in {wait}s..."
                        yield {"event": "step", "data": step.to_dict()}
                        await asyncio.sleep(wait)
                        continue
                    raise
            if last_err is not None:
                raise last_err
            step.status = "completed"
            yield {"event": "step", "data": step.to_dict()}

        # 6. Create & publish the Fabric data agent via a no-pip notebook that
        # drives the AISkill workload API (create item -> add lakehouse datasource
        # -> select all tables -> instructions -> publish info -> deploy). This is
        # the only path that yields a *runtime-queryable* published agent; writing
        # the item definition headlessly does not actually publish it.
        step = _find_step(steps, "data-agent")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        artifact_id = ""
        try:
            publish_nb = demo_dir.parent / "_scenarios" / "notebooks" / "foundry" / "publish_data_agent.ipynb"
            lh_name = lakehouse_name or "analytics_lakehouse"
            nb = await client.create_notebook(
                ws_id, f"publish_{agent_name}", str(publish_nb), lakehouse_id, lh_name,
                variables={
                    "DATA_AGENT_NAME": agent_name,
                    "LAKEHOUSE_ID": lakehouse_id,
                    "INSTRUCTIONS": da_instructions,
                },
            )
            await client.run_notebook(ws_id, nb["id"], lakehouse_id, lh_name, timeout=900)
            # The notebook writes its outcome to the lakehouse — read it back.
            pub: dict = {}
            try:
                pr = await client._storage_client.get(
                    f"{ONELAKE_API}/{ws_id}/{lakehouse_id}/Files/publish_result.json"
                )
                if pr.status_code < 400:
                    pub = json.loads(pr.text)
            except Exception as re:  # noqa: BLE001
                logger.warning("[foundry] could not read publish_result.json: %s", re)
            artifact_id = pub.get("dataAgentId", "")
            if pub.get("status") != "published" or not artifact_id:
                reason = pub.get("error") or f"stopped at step '{pub.get('step', 'unknown')}'"
                raise FabricError(500, f"publish notebook did not finish: {reason}")
            created_ids[agent_name] = artifact_id
            step.status = "completed"
            step.item_id = artifact_id
            step.detail = f"Published '{agent_name}' (id {artifact_id})"
        except (FabricError, Exception) as e:  # noqa: BLE001 — degrade gracefully
            logger.warning("[foundry] data agent publish skipped: %s", e)
            step.status = "skipped"
            detail = e.detail if isinstance(e, FabricError) else str(e)
            step.detail = f"Data agent step skipped: {detail[:160]}"
            next_steps.append("Create a Fabric data agent over the lakehouse and publish it.")
        yield {"event": "step", "data": step.to_dict()}

        # 7. Provision the Foundry account + project (best-effort)
        step = _find_step(steps, "foundry-account")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        rand6 = "".join(random.choices(_string.ascii_lowercase + _string.digits, k=6))
        foundry_account = f"fdg-foundry-{demo_id.replace('-', '')[:8]}-{rand6}"
        foundry_project = f"{demo_id.replace('-', '')[:12]}proj"
        project_principal_id = ""
        qwarn = await _foundry_quota_warning(azure_client, subscription_id, azure_location, MODEL_NAME, MODEL_VERSION)
        try:
            if create_resource_group:
                await azure_client.create_resource_group(subscription_id, resource_group, azure_location)
            await azure_client.create_foundry_account(subscription_id, resource_group, foundry_account, azure_location)
            proj = await azure_client.create_foundry_project(
                subscription_id, resource_group, foundry_account, foundry_project,
                azure_location, display_name=f"{demo_id} Foundry",
            )
            project_principal_id = (proj.get("identity") or {}).get("principalId", "")
            step.status = "completed"
            step.detail = f"{foundry_account} / {foundry_project}" + (f" — note: {qwarn}" if qwarn else "")
        except (AzureError, Exception) as e:  # noqa: BLE001 — preview; degrade gracefully
            logger.warning("[foundry] account/project provisioning skipped: %s", e)
            step.status = "skipped"
            detail = e.detail if isinstance(e, AzureError) else str(e)
            step.detail = f"Foundry provisioning skipped (preview): {detail[:160]}"
            next_steps.append("Create a Microsoft Foundry project (ai.azure.com).")
            foundry_account = ""  # nothing to tear down / deploy onto
        yield {"event": "step", "data": step.to_dict()}

        # 8. Deploy the model (best-effort, only if the account exists)
        step = _find_step(steps, "foundry-model")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        if foundry_account:
            try:
                await azure_client.create_model_deployment(
                    subscription_id, resource_group, foundry_account,
                    DEPLOYMENT_NAME, MODEL_NAME, MODEL_VERSION,
                )
                step.status = "completed"
                step.detail = f"{DEPLOYMENT_NAME} ({MODEL_NAME})" + (f" — {model_note}" if model_note else "")
            except (AzureError, Exception) as e:  # noqa: BLE001
                logger.warning("[foundry] model deployment skipped: %s", e)
                step.status = "skipped"
                detail = e.detail if isinstance(e, AzureError) else str(e)
                step.detail = f"Model deployment skipped: {detail[:140]}" + (f" — {qwarn}" if qwarn else "")
                next_steps.append(f"Deploy '{MODEL_NAME}' in the Foundry project.")
        else:
            step.status = "skipped"
            step.detail = "Skipped — no Foundry account"
        yield {"event": "step", "data": step.to_dict()}

        # 9. Provision Azure AI Search (the Foundry IQ retrieval engine).
        search_principal_id = ""
        search_endpoint = ""
        step = _find_step(steps, "search-service")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        if foundry_account:
            try:
                await azure_client.register_search_provider(subscription_id)
                search_service = f"fdg-srch-{demo_id.replace('-', '')[:8]}-{rand6}"[:60]
                svc = await azure_client.create_search_service(
                    subscription_id, resource_group, search_service, azure_location
                )
                search_principal_id = (svc.get("identity") or {}).get("principalId", "")
                search_endpoint = f"https://{search_service}.search.windows.net"
                step.status = "completed"
                step.detail = f"{search_service} (S1)"
            except (AzureError, Exception) as e:  # noqa: BLE001
                logger.warning("[foundry] search service skipped: %s", e)
                step.status = "skipped"
                detail = e.detail if isinstance(e, AzureError) else str(e)
                step.detail = f"Azure AI Search skipped: {detail[:140]}"
                next_steps.append("Create an Azure AI Search service for Foundry IQ.")
                search_service = ""
        else:
            step.status = "skipped"
            step.detail = "Skipped — no Foundry account"
        yield {"event": "step", "data": step.to_dict()}

        # 10. Wire the managed-identity RBAC.
        backend_mi_agent_token: str | None = None
        step = _find_step(steps, "rbac")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        if search_service and search_principal_id and project_principal_id:
            try:
                from app.azure_client import (
                    SEARCH_INDEX_DATA_READER, SEARCH_SERVICE_CONTRIBUTOR, COGNITIVE_SERVICES_USER,
                )
                search_scope = (
                    f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
                    f"/providers/Microsoft.Search/searchServices/{search_service}"
                )
                foundry_scope = (
                    f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
                    f"/providers/Microsoft.CognitiveServices/accounts/{foundry_account}"
                )
                # Project MI → query the search service.
                await azure_client.assign_role(search_scope, SEARCH_INDEX_DATA_READER, project_principal_id)
                await azure_client.assign_role(search_scope, SEARCH_SERVICE_CONTRIBUTOR, project_principal_id)
                # Search MI → invoke the Foundry data agent.
                await azure_client.assign_role(foundry_scope, COGNITIVE_SERVICES_USER, search_principal_id)
                # Grant the agent-creating identities the Foundry data-plane role on
                # the project. VERIFIED end-to-end: a token carrying only "Foundry User"
                # (Microsoft.CognitiveServices/*) can create agents — the 403's
                # "MachineLearningServices/agents" wording is misleading. We grant to
                # BOTH identities the agent step may use:
                #   • the deploying USER (caller) — makes a delegated ai.azure.com token
                #     (agent_token) work; reliable because the user is in their own
                #     tenant and owns the resources just created; and
                #   • the backend MANAGED IDENTITY — the no-consent fallback, which only
                #     works when the deploy targets the gallery's own tenant (a single-
                #     tenant MI can't be granted in another tenant's directory).
                # "Azure AI Developer" is added too (broader agent actions).
                from app.azure_client import AZURE_AI_DEVELOPER, FOUNDRY_USER
                project_scope = f"{foundry_scope}/projects/{foundry_project}"
                grant_notes: list[str] = []

                async def _grant_foundry_role(principal_id: str, principal_type: str, label: str) -> None:
                    if not principal_id:
                        grant_notes.append(f"{label}: no-oid")
                        return
                    ok, err = False, ""
                    for _scope in (foundry_scope, project_scope):
                        for _role in (FOUNDRY_USER, AZURE_AI_DEVELOPER):
                            try:
                                await azure_client.assign_role(_scope, _role, principal_id, principal_type)
                                ok = True
                            except Exception as ge:  # noqa: BLE001 — best-effort per assignment
                                err = str(ge)
                                logger.warning("[foundry] grant %s/%s skipped: %s", label, _role, ge)
                    grant_notes.append(f"{label}: {'ok' if ok else 'FAILED ' + err[:80]}")

                # The deploying user — enables the delegated agent_token path.
                await _grant_foundry_role(azure_client.get_caller_oid(), "User", "user")
                # The backend managed identity — the no-consent fallback.
                if not agent_token:
                    try:
                        backend_mi_agent_token = await azure_client.get_managed_identity_token("https://ai.azure.com")
                        await _grant_foundry_role(
                            azure_client.oid_from_token(backend_mi_agent_token), "ServicePrincipal", "backend-mi"
                        )
                    except Exception as mie:  # noqa: BLE001
                        logger.warning("[foundry] backend-MI token/grant skipped: %s", mie)
                        backend_mi_agent_token = None
                        grant_notes.append("backend-mi: token unavailable")
                step.status = "completed"
                step.detail = "Foundry role grants — " + "; ".join(grant_notes)
            except (AzureError, Exception) as e:  # noqa: BLE001
                logger.warning("[foundry] rbac skipped: %s", e)
                step.status = "skipped"
                detail = e.detail if isinstance(e, AzureError) else str(e)
                step.detail = f"RBAC skipped — grant roles manually: {detail[:120]}"
                next_steps.append("Grant the Foundry project + search managed identities their roles.")
        else:
            step.status = "skipped"
            step.detail = "Skipped — search service or identities unavailable"
        yield {"event": "step", "data": step.to_dict()}

        # 11. Create the Foundry IQ knowledge source + base (Search data-plane).
        ks_name = f"{demo_id}-ks"[:60]
        kb_name = f"{demo_id}-kb".replace("-", "")[:24] or "fdgkb"
        kb_ready = False
        step = _find_step(steps, "knowledge")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        # Prefer the Search service ADMIN KEY (fetched via ARM with the management
        # token every user grants) so this works for EVERYONE — not just users who
        # consented to the search.azure.com delegated scope. Fall back to the user's
        # delegated search token if the key can't be fetched.
        search_key = None
        if search_service and azure_client and subscription_id and resource_group:
            try:
                search_key = await azure_client.get_search_admin_key(subscription_id, resource_group, search_service)
            except Exception as e:  # noqa: BLE001
                logger.warning("[foundry] search admin key fetch failed: %s", e)
        if search_service and artifact_id and (search_key or search_token):
            iq = FoundryIQClient(search_service, token=search_token, api_key=search_key)
            try:
                await iq.create_fabric_knowledge_source(ks_name, ws_id, artifact_id)
                await iq.create_knowledge_base(kb_name, ks_name, foundry_account, DEPLOYMENT_NAME, MODEL_NAME)
                kb_ready = True
                step.status = "completed"
                step.detail = f"Knowledge base '{kb_name}' over the data agent"
            except Exception as e:  # noqa: BLE001
                logger.warning("[foundry] knowledge base skipped: %s", e)
                step.status = "skipped"
                step.detail = f"Knowledge base skipped: {str(e)[:140]}"
                next_steps.append("In Foundry IQ: create a knowledge base over the Fabric data agent.")
            finally:
                await iq.close()
        else:
            step.status = "skipped"
            step.detail = "Skipped — search service or data agent unavailable"
            next_steps.append("In Foundry IQ: create a knowledge base over the Fabric data agent.")
        yield {"event": "step", "data": step.to_dict()}

        # 12. Create the project connection + Foundry agent grounded on the KB.
        step = _find_step(steps, "agent")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        # Prefer the delegated ai.azure.com token (known-good path); if absent, fall
        # back to the Foundry account key so non-consented users still get an agent
        # attempt instead of an automatic skip.
        # Auth precedence: user delegated token > backend managed-identity token >
        # Foundry account key. The MI path works for everyone (no user consent).
        agent_auth = agent_token or backend_mi_agent_token
        foundry_key = None
        if kb_ready and not agent_auth and azure_client and subscription_id and resource_group:
            try:
                foundry_key = await azure_client.get_cognitive_account_key(subscription_id, resource_group, foundry_account)
            except Exception as e:  # noqa: BLE001
                logger.warning("[foundry] foundry account key fetch failed: %s", e)
        # Which identity actually creates the agent — surfaced in the step detail so a
        # failure is diagnosable (user-token = delegated; backend-mi = no-consent MI).
        _auth_label = (
            "user-token" if agent_token else
            "backend-mi" if backend_mi_agent_token else
            "account-key" if foundry_key else "none"
        )
        if kb_ready and (agent_auth or foundry_key):
            conn_name = f"{demo_id}-kb-conn"[:60]
            project_endpoint = (
                f"https://{foundry_account}.services.ai.azure.com/api/projects/{foundry_project}"
            )
            ag = FoundryAgentClient(project_endpoint, token=agent_auth, api_key=foundry_key)
            try:
                await azure_client.create_kb_connection(
                    subscription_id, resource_group, foundry_account, foundry_project,
                    conn_name, search_endpoint, kb_name,
                )
                # Retry on 401/403 — the backend-MI role assignment may still be
                # propagating through Entra / the data-plane when we first call the
                # agents API (can take a couple of minutes).
                agent = {}
                for attempt in range(12):
                    try:
                        agent = await ag.create_agent(
                            f"{demo_id}-agent"[:60], DEPLOYMENT_NAME, search_endpoint, kb_name, conn_name,
                        )
                        break
                    except FoundryAgentError as ae:
                        if ae.status in (401, 403) and attempt < 11:
                            await asyncio.sleep(20)
                            continue
                        raise
                agent_created = agent.get("name", f"{demo_id}-agent")
                step.status = "completed"
                step.detail = f"Agent '{agent_created}' ready (auth: {_auth_label}) — ask it about your data"
            except Exception as e:  # noqa: BLE001
                logger.warning("[foundry] agent creation skipped: %s", e)
                step.status = "skipped"
                step.detail = f"Agent skipped (auth: {_auth_label}) — {str(e)[:280]}"
                next_steps.append("In Foundry: New Agent → Add knowledge → your knowledge base.")
            finally:
                await ag.close()
        else:
            step.status = "skipped"
            step.detail = "Skipped — knowledge base unavailable; finish in the Foundry portal"
            if kb_ready:
                next_steps.append("In Foundry: New Agent → Add knowledge → your knowledge base.")
        yield {"event": "step", "data": step.to_dict()}

        # Done — include Foundry + Azure metadata so the UI can link out and
        # teardown can delete the billable resources.
        step = _find_step(steps, "done")
        step.status = "completed"
        playground = (
            f"https://ai.azure.com/build/agents?wsid=/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}/providers/Microsoft.CognitiveServices/accounts/{foundry_account}"
            if (foundry_account and agent_created) else "https://ai.azure.com/"
        )
        step.detail = json.dumps({
            "workspaceId": ws_id,
            "items": created_ids,
            "foundry": {
                "portalUrl": "https://ai.azure.com/",
                "playgroundUrl": playground,
                "account": foundry_account,
                "project": foundry_project,
                "agent": agent_created,
                "searchService": search_service,
                "dataAgentEndpoint": (
                    f"https://fabric.microsoft.com/groups/{ws_id}/aiskills/{artifact_id}"
                    if artifact_id else ""
                ),
                "nextSteps": next_steps,
            },
            "azure": {
                "subscriptionId": subscription_id,
                "resourceGroup": resource_group,
                "foundryAccount": foundry_account,
                "searchService": search_service,
            },
        })
        yield {"event": "step", "data": step.to_dict()}

    except (FabricError, AzureError, Exception) as e:  # noqa: BLE001
        is_fabric = isinstance(e, FabricError)
        is_azure = isinstance(e, AzureError)
        if not (is_fabric or is_azure):
            logger.exception("Fabric+Foundry deployment failed")
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = (e.detail if (is_fabric or is_azure) else str(e))[:300]
                yield {"event": "step", "data": s.to_dict()}
                break
        cleanup_note, ws_remaining = await _best_effort_teardown(
            client, azure_client, ws_id, subscription_id, resource_group,
            foundry_account=foundry_account or None,
            search_service=search_service or None,
        )
        if is_azure:
            error_msg = f"Azure error: {e.detail}"
        elif is_fabric:
            error_msg = str(e)
        else:
            error_msg = f"Unexpected error: {str(e)[:300]}"
        if cleanup_note:
            error_msg += "\n\n" + cleanup_note
        data: dict = {"message": error_msg, "workspaceId": ws_id if ws_remaining else ""}
        if ws_remaining and (foundry_account or search_service):
            data["azure"] = {
                "subscriptionId": subscription_id,
                "resourceGroup": resource_group,
                "foundryAccount": foundry_account,
                "searchService": search_service,
            }
        yield {"event": "error", "data": data}
