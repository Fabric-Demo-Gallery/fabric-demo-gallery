"""Deployment orchestrator — reads a demo manifest and provisions all Fabric items."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncIterator

from app.fabric_client import FabricClient, FabricError
from app.report_builder import build_manufacturing_report_definition, build_retail_report_definition

logger = logging.getLogger(__name__)

DEMOS_DIR = Path(__file__).resolve().parent.parent.parent / "demos"


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


async def deploy_demo(
    client: FabricClient,
    demo_id: str,
    workspace_name: str | None = None,
    workspace_id: str | None = None,
    capacity_id: str | None = None,
) -> AsyncIterator[dict]:
    """
    Deploy a demo end-to-end, yielding progress events as SSE-compatible dicts.

    Steps:
    1. Create or reuse workspace
    2. Create lakehouse
    3. Upload sample data
    4. Create & deploy notebooks
    5. Execute notebooks (Bronze → Silver → Gold)
    6. Wait for SQL endpoint
    7. Create semantic model
    8. Create pipeline
    """
    manifest = load_manifest(demo_id)
    demo_dir = DEMOS_DIR / demo_id
    items = manifest["fabricItems"]

    steps: list[DeploymentStep] = []
    created_ids: dict[str, str] = {}  # logical name → Fabric item ID

    # ── Plan steps ───────────────────────────────────────────────────────
    if not workspace_id:
        steps.append(DeploymentStep("workspace", f"Create workspace '{workspace_name}'"))

    lakehouses = [i for i in items if i["type"] == "Lakehouse"]
    for lh in lakehouses:
        steps.append(DeploymentStep(f"lakehouse:{lh['name']}", f"Create lakehouse '{lh['name']}'"))

    data_files = list((demo_dir / "data").glob("*")) if (demo_dir / "data").exists() else []
    if data_files:
        steps.append(DeploymentStep("upload-data", f"Upload {len(data_files)} sample data file(s)"))

    notebooks = [i for i in items if i["type"] == "Notebook"]
    for nb in notebooks:
        steps.append(DeploymentStep(f"notebook:{nb['name']}", f"Create notebook '{nb['name']}'"))
    for nb in notebooks:
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
            ws = await client.create_workspace(workspace_name or manifest["title"], capacity_id)
            ws_id = ws["id"]
            step.status = "completed"
            step.item_id = ws_id
            yield {"event": "step", "data": step.to_dict()}

        # 2. Lakehouses
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

        # 3. Upload sample data
        if data_files and lakehouse_id:
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

        # 4. Create notebooks
        notebook_ids: dict[str, str] = {}
        for nb in notebooks:
            step = _find_step(steps, f"notebook:{nb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            ipynb_path = demo_dir / nb.get("definitionPath", f"notebooks/{nb['name']}.ipynb")
            result = await client.create_notebook(
                ws_id, nb["name"], ipynb_path, lakehouse_id, lakehouse_name
            )
            nb_id = result["id"]
            notebook_ids[nb["name"]] = nb_id
            created_ids[nb["name"]] = nb_id
            step.status = "completed"
            step.item_id = nb_id
            yield {"event": "step", "data": step.to_dict()}

        # 5. Execute notebooks sequentially (with delay to avoid capacity throttling)
        for i, nb in enumerate(notebooks):
            step = _find_step(steps, f"run:{nb['name']}")
            step.status = "running"
            yield {"event": "step", "data": step.to_dict()}
            nb_id = notebook_ids[nb["name"]]

            # Wait between notebook runs to avoid Spark rate limits
            if i > 0:
                logger.info("Waiting 30s before next notebook to avoid capacity throttling...")
                await asyncio.sleep(30)

            # Retry once on throttling errors
            try:
                result = await client.run_notebook(ws_id, nb_id, lakehouse_id, lakehouse_name)
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
                    await client.run_notebook(ws_id, nb_id, lakehouse_id, lakehouse_name)
                elif "Session_Statements_Failed" in e.detail or "Cancelled" in e.detail:
                    step.detail = f"Notebook code error — retrying in 30s..."
                    yield {"event": "step", "data": step.to_dict()}
                    await asyncio.sleep(30)
                    try:
                        await client.run_notebook(ws_id, nb_id, lakehouse_id, lakehouse_name)
                    except FabricError:
                        raise FabricError(500, f"Notebook '{nb['name']}' failed twice. Check the notebook code in Fabric portal for errors.")
                else:
                    raise

            step.status = "completed"
            yield {"event": "step", "data": step.to_dict()}

        # 6. Wait for SQL endpoint
        step = _find_step(steps, "sql-endpoint")
        step.status = "running"
        yield {"event": "step", "data": step.to_dict()}
        conn_string = await client.wait_for_sql_endpoint(ws_id, lakehouse_id)
        step.status = "completed"
        step.detail = conn_string
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
                    "LAKEHOUSE_NAME": lakehouse_name,
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
                    step.status = "completed"
                    step.detail = f"⚠ Refresh failed: {e.detail[:150]}. Refresh manually in Fabric portal."
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
                    report_def = _build_report_definition(demo_id, sm_id)
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


def _build_report_definition(demo_id: str, semantic_model_id: str) -> dict:
    """Build a Power BI report definition for the given demo."""
    if demo_id == "manufacturing-qc":
        return build_manufacturing_report_definition(semantic_model_id)
    elif demo_id == "retail-sales":
        return build_retail_report_definition(semantic_model_id)
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
