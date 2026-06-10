"""Deployment orchestrator — reads a demo manifest and provisions all Fabric items."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncIterator

from app.fabric_client import FabricClient, FabricError
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
from app.azure_client import AzureClient, AzureError

logger = logging.getLogger(__name__)

# In dev: backend/app/deployer.py → ../../demos
# On Azure: /home/site/wwwroot/app/deployer.py → ../demos (demos/ is sibling of app/)
_APP_DIR = Path(__file__).resolve().parent.parent  # backend/ or wwwroot/
DEMOS_DIR = _APP_DIR.parent / "demos" if (_APP_DIR.parent / "demos").exists() else _APP_DIR / "demos"


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
ENABLED_SCENARIOS: set[str] = {"data-virtualization-batch", "ai-ml", "anomaly-detection-alerts"}


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

    steps: list[DeploymentStep] = []
    created_ids: dict[str, str] = {}  # logical name → Fabric item ID

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
    elif data_files:
        steps.append(DeploymentStep("upload-data", f"Upload {len(data_files)} sample data file(s)"))

    notebooks = [i for i in items if i["type"] == "Notebook"]
    notebooks_to_run = [nb for nb in notebooks if nb.get("order") is not None]
    for nb in notebooks:
        steps.append(DeploymentStep(f"notebook:{nb['name']}", f"Create notebook '{nb['name']}'"))
    for nb in notebooks_to_run:
        steps.append(DeploymentStep(f"run:{nb['name']}", f"Execute notebook '{nb['name']}'"))

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
    for kd in kql_dashboards:
        steps.append(DeploymentStep(f"kqldash:{kd['name']}", f"Create real-time dashboard '{kd['name']}'"))

    pipelines = [i for i in items if i["type"] == "DataPipeline"]
    for pl in pipelines:
        steps.append(DeploymentStep(f"pipeline:{pl['name']}", f"Create pipeline '{pl['name']}'"))

    steps.append(DeploymentStep("done", "Deployment complete"))

    # Emit initial plan
    yield {"event": "plan", "data": [s.to_dict() for s in steps]}

    # ── Execute steps ────────────────────────────────────────────────────
    try:
        ws_id = workspace_id

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
                    step.detail = "You don't have permission to create workspaces. Contact your Fabric admin."
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

        # 2b. KQL Databases
        kql_db_name = ""
        for kdb in kql_databases:
            step = _find_step(steps, f"kqldb:{kdb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            parent_eh = kdb.get("parentEventhouse", "")
            parent_id = created_ids.get(parent_eh, "")
            if not parent_id:
                # Fall back to first eventhouse
                for eh in eventhouses:
                    parent_id = created_ids.get(eh["name"], "")
                    if parent_id:
                        break
            result = await client.create_kql_database(ws_id, kdb["name"], parent_id)
            kdb_id = result["id"]
            created_ids[kdb["name"]] = kdb_id
            kql_db_name = kdb["name"]
            step.status = "completed"
            step.item_id = kdb_id
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
                conn_result = await client.create_connection_oauth(
                    display_name=f"{demo_id}-{acct_name}-conn",
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
            ipynb_path = demo_dir / nb.get("definitionPath", f"notebooks/{nb['name']}.ipynb")
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

        # 5. Execute notebooks sequentially (with delay to avoid capacity throttling)
        notebook_timeout = 1800
        for i, nb in enumerate(notebooks_to_run):
            step = _find_step(steps, f"run:{nb['name']}")
            nb_id = notebook_ids.get(nb["name"])
            if not nb_id:
                step.status = "failed"
                step.detail = "Notebook was not created — skipping execution"
                yield {"event": "step", "data": step.to_dict()}
                continue
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}

            # Wait between notebook runs to avoid Spark rate limits
            if i > 0:
                logger.info("Waiting 45s before next notebook to avoid capacity throttling...")
                await asyncio.sleep(45)

            # Retry once on throttling errors
            try:
                result = await client.run_notebook(
                    ws_id,
                    nb_id,
                    lakehouse_id,
                    lakehouse_name,
                    timeout=notebook_timeout,
                )
                job_status = result.get("status", "").lower() if isinstance(result, dict) else ""
                if job_status == "failed":
                    failure = result.get("failureReason", {})
                    err_msg = failure.get("message", "Notebook execution failed")
                    raise FabricError(500, f"Notebook '{nb['name']}' failed: {err_msg[:200]}")
            except FabricError as e:
                if "TooManyRequests" in e.detail or "430" in e.detail or "throttl" in e.detail.lower():
                    step.detail = "Rate limited — retrying in 60s..."
                    yield {"event": "step", "data": step.to_dict()}
                    await asyncio.sleep(60)
                    await client.run_notebook(
                        ws_id,
                        nb_id,
                        lakehouse_id,
                        lakehouse_name,
                        timeout=notebook_timeout,
                    )
                elif "Livy" in e.detail or "Failed to create Livy session" in e.detail:
                    # Transient Spark cold-start — retry a few times on a longer backoff
                    last_err = e
                    succeeded = False
                    for attempt in range(3):
                        step.detail = f"Spark session cold-start — retrying ({attempt + 1}/3) in 60s..."
                        yield {"event": "step", "data": step.to_dict()}
                        await asyncio.sleep(60)
                        try:
                            await client.run_notebook(
                                ws_id,
                                nb_id,
                                lakehouse_id,
                                lakehouse_name,
                                timeout=notebook_timeout,
                            )
                            succeeded = True
                            break
                        except FabricError as retry_err:
                            last_err = retry_err
                            if not ("Livy" in retry_err.detail or "Failed to create Livy session" in retry_err.detail):
                                raise
                    if not succeeded:
                        raise FabricError(500, f"Notebook '{nb['name']}' failed: Spark session could not start after retries. {last_err.detail[:150]}")
                elif "Session_Statements_Failed" in e.detail or "Cancelled" in e.detail:
                    step.detail = f"Notebook code error — retrying in 45s..."
                    yield {"event": "step", "data": step.to_dict()}
                    await asyncio.sleep(45)
                    try:
                        await client.run_notebook(
                            ws_id,
                            nb_id,
                            lakehouse_id,
                            lakehouse_name,
                            timeout=notebook_timeout,
                        )
                    except FabricError:
                        raise FabricError(500, f"Notebook '{nb['name']}' failed twice. Check the notebook code in Fabric portal for errors.")
                else:
                    raise

            step.status = "completed"
            yield {"event": "step", "data": step.to_dict()}

        # 6. Wait for SQL endpoint (only relevant for lakehouse-based demos)
        conn_string = ""
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
                step.status = "completed"
                step.detail = "Skipped — no definition (create manually in Fabric)"
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
                    logger.warning("Semantic model refresh failed: %s", e.detail)
                    step.status = "failed"
                    step.detail = f"Refresh failed: {e.detail[:200]}"
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
            for sm in semantic_models:
                sm_id = created_ids.get(sm["name"])
                if sm_id:
                    break
            if sm_id:
                try:
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
                step.status = "completed"
                step.detail = "Skipped — no semantic model available"
            yield {"event": "step", "data": step.to_dict()}

        # 8b. KQL Dashboards (Real-Time Dashboards)
        for kd in kql_dashboards:
            step = _find_step(steps, f"kqldash:{kd['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            try:
                kdb_id = ""
                kdb_name_resolved = kql_db_name
                for kdb in kql_databases:
                    kdb_id = created_ids.get(kdb["name"], "")
                    if kdb_id:
                        break
                result = await client.create_kql_dashboard(
                    ws_id, kd["name"], kdb_id, eventhouse_uri, kdb_name_resolved
                )
                created_ids[kd["name"]] = result.get("id", "")
                step.item_id = result.get("id")
                step.status = "completed"
                step.detail = "10 tiles across 3 pages"
            except (FabricError, Exception) as e:
                logger.warning("KQL Dashboard creation failed: %s", str(e)[:300])
                step.status = "completed"
                step.detail = f"⚠ Dashboard failed: {str(e)[:150]}. Create manually."
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
                step.status = "completed"
                step.detail = f"⚠ Pipeline failed: {e.detail[:150]}. Create manually in Fabric."
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

        # Offer cleanup option
        error_msg = str(e)
        if ws_id:
            error_msg += f"\n\nWorkspace '{workspace_name}' was partially created. You can delete it from the Fabric portal or use the cleanup button."
        yield {"event": "error", "data": {"message": error_msg, "workspaceId": ws_id or ""}}

    except AzureError as e:
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = e.detail[:300]
                yield {"event": "step", "data": s.to_dict()}
                break
        error_msg = f"Azure provisioning error: {e.detail}"
        if ws_id:
            error_msg += f"\n\nFabric workspace was partially created (ID: {ws_id})."
        yield {"event": "error", "data": {"message": error_msg, "workspaceId": ws_id or ""}}

    except Exception as e:
        logger.exception("Unexpected deployment error")
        for s in steps:
            if s.status == "running":
                s.status = "failed"
                s.detail = str(e)[:300]
                yield {"event": "step", "data": s.to_dict()}
                break

        error_msg = f"Unexpected error: {type(e).__name__}: {e}"
        if ws_id:
            error_msg += f"\n\nWorkspace was partially created (ID: {ws_id})."
        yield {"event": "error", "data": {"message": error_msg, "workspaceId": ws_id or ""}}


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
