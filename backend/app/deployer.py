"""Deployment orchestrator — reads a demo manifest and provisions all Fabric items."""

from __future__ import annotations

import asyncio
import base64
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
ENABLED_SCENARIOS: set[str] = {
    "data-virtualization-batch",
    "ai-ml",
    "anomaly-detection-alerts",
    "external-data-integration",
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
                step.status = "skipped"
                step.detail = f"Dashboard not created: {str(e)[:150]}. You can add it manually in Fabric."
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
        # Co-locate the Azure SQL server with the Fabric capacity's region. Many
        # governed subscriptions (e.g. MCAPS) restrict SQL provisioning to certain
        # regions; the capacity's region is always one where the user has quota.
        # Azure region codes are the display name lowercased with spaces removed
        # ("West US 3" -> "westus3").
        cap_region = (ws_info.get("capacityRegion") or "").strip()
        sql_location = cap_region.lower().replace(" ", "") if cap_region else azure_location
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

        sql_server = sql_server_name or (
            f"fdg-{demo_id.replace('-', '')[:8]}-"
            + "".join(random.choices(_string.ascii_lowercase + _string.digits, k=6))
        )
        sql_database = f"{demo_id.replace('-', '')[:12]}ops"
        sami_principal_id = ""
        try:
            if create_resource_group:
                await azure_client.create_resource_group(subscription_id, resource_group, sql_location)
            srv = await azure_client.create_sql_server(
                subscription_id, resource_group, sql_server, sql_location,
                entra_login, entra_oid, entra_tenant,
            )
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
        step.detail = f"{sql_server}.database.windows.net / {sql_database} (S3 tier, {sql_location})"
        yield {"event": "step", "data": step.to_dict()}

        sql_fqdn = f"{sql_server}.database.windows.net"
        nb_variables = {
            "SQL_SERVER": sql_fqdn,
            "SQL_DATABASE": sql_database,
            "WORKSPACE_IDENTITY_NAME": ws_identity_name,
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
            yield {"event": "step", "data": step.to_dict()}
            try:
                result = await client.run_notebook(
                    ws_id, notebook_ids[nb["name"]], lakehouse_id, lakehouse_name, timeout=1800
                )
                job_status = result.get("status", "").lower() if isinstance(result, dict) else ""
                if job_status == "failed":
                    failure = result.get("failureReason", {})
                    raise FabricError(500, f"Seed notebook failed: {failure.get('message', '')[:200]}")
            except FabricError as e:
                if "Livy" in e.detail:
                    step.detail = "Spark cold-start — retrying in 60s..."
                    yield {"event": "step", "data": step.to_dict()}
                    await asyncio.sleep(60)
                    await client.run_notebook(
                        ws_id, notebook_ids[nb["name"]], lakehouse_id, lakehouse_name, timeout=1800
                    )
                else:
                    raise
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
