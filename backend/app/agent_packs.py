"""AI agent packs - general Microsoft Foundry agents grounded on an industry's
demo data, deployed into the user's Azure subscription.

No containers or images: each deploy is ARM calls with the user's management
token plus Foundry data-plane calls with the user's delegated ``ai.azure.com``
token (both already requested by the gallery):

  pre-flight -> dedicated resource group -> providers -> Foundry account +
  project -> model (with fallbacks) -> caller gets "Azure AI User" ->
  upload knowledge docs + data files -> one vector store per agent ->
  pack infrastructure (ARM template, started right after the model) ->
  prompt agents (File Search / Code Interpreter / vision / OpenAPI actions) ->
  warm-up. Agent evaluations run on demand from the agents page (they would
  compete with a live demo for the model's token rate limit).

A pack's optional ``infra`` template adds a simulated plant system the agents
act on (an OpenAPI tool backed by a Logic App), a multi-agent incident workflow
(Logic App) with a human approval step, and Application Insights tracing. All
of it is pay-per-use and lives in the same resource group, so deleting the
resource group removes everything.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import fnmatch
import json
import logging
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import cache
from pathlib import Path

import httpx

from app.azure_client import FOUNDRY_USER, AzureClient, AzureError
from app.deployer import DEMOS_DIR, DeploymentStep, _find_step
from app.foundry_project_client import (
    AGENT_EVALUATORS,
    EVALUATOR_SCALES,
    FoundryProjectClient,
    FoundryProjectError,
)

logger = logging.getLogger(__name__)

PACKS_DIR: Path = DEMOS_DIR / "_agents"
SCENARIO_ID = "ai-agents"
RESOURCE_GROUP_TAG = "fabric-demo-gallery"
REQUIRED_PROVIDERS = ["Microsoft.CognitiveServices"]
# The caller must create the resource group and give themself the Foundry
# data-plane role ("Azure AI User") on the new account.
REQUIRED_ACTIONS = [
    "Microsoft.Resources/subscriptions/resourceGroups/write",
    "Microsoft.Authorization/roleAssignments/write",
]
MODEL_CAPACITY = 300  # thousand tokens per minute (GlobalStandard is billed per token, not per capacity)
MIN_MODEL_CAPACITY = 20
MODEL_SKU = "GlobalStandard"
CONTENT_TYPES = {".csv": "text/csv", ".md": "text/markdown"}
INFRA_DEPLOYMENT = "fdg-agent-pack-infra"
INFRA_TIMEOUT_S = 900
INFRA_POLL_S = 10
# The plant system's managed identity needs its storage role to propagate.
SYSTEM_READY_TIMEOUT_S = 240
SYSTEM_READY_POLL_S = 15


class AgentPackError(Exception):
    """A user-actionable deploy failure."""


@cache
def load_pack(pack_id: str) -> dict:
    path = PACKS_DIR / pack_id / "pack.json"
    if not path.is_file():
        raise FileNotFoundError(f"Agent pack '{pack_id}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


def list_packs() -> list[dict]:
    packs = []
    for d in sorted(PACKS_DIR.iterdir()) if PACKS_DIR.is_dir() else []:
        if (d / "pack.json").is_file():
            pack = load_pack(d.name)
            packs.append({
                "id": pack["id"],
                "industry": pack["industry"],
                "title": pack["title"],
                "regions": pack["regions"],
                "defaultRegion": pack["defaultRegion"],
                "agents": [{"id": a["id"], "title": a["title"]} for a in pack["agents"]],
            })
    return packs


def pack_file(pack: dict, relative: str) -> Path:
    """Resolve a pack-relative path (instructions, knowledge) inside the pack folder."""
    base = (PACKS_DIR / pack["id"]).resolve()
    path = (base / relative).resolve()
    if base not in path.parents:
        raise AgentPackError(f"Pack file '{relative}' is outside the pack folder.")
    return path


def data_file(pack: dict, name: str) -> Path:
    """Resolve a shared data file (``dataFiles`` maps it into demos/)."""
    base = DEMOS_DIR.resolve()
    path = (base / pack["dataFiles"][name]).resolve()
    if base not in path.parents:
        raise AgentPackError(f"Data file '{name}' is outside the demos folder.")
    return path


def new_resource_group_name(pack_id: str) -> str:
    return f"rg-fdg-agents-{pack_id}-{secrets.token_hex(3)}"


def foundry_portal_url(
    subscription_id: str, resource_group: str, account: str, project: str, page: str = "build/agents",
    tenant_id: str = "",
) -> str:
    """Deep link into the Foundry portal for a project. The route encodes the
    subscription id as unpadded base64url of its 16 UUID bytes."""
    sub = base64.urlsafe_b64encode(uuid.UUID(subscription_id).bytes).decode().rstrip("=")
    url = f"https://ai.azure.com/nextgen/r/{sub},{resource_group},,{account},{project}/{page}"
    return f"{url}?tid={tenant_id}" if tenant_id else url


def azure_portal_url(resource_id: str, tenant_id: str = "", blade: str = "overview") -> str:
    tenant = f"@{tenant_id}" if tenant_id else ""
    return f"https://portal.azure.com/#{tenant}/resource{resource_id}/{blade}"


@cache
def _pack_json(pack_id: str, relative: str) -> dict:
    return json.loads(pack_file(load_pack(pack_id), relative).read_text(encoding="utf-8"))


def openapi_tool(pack: dict, outputs: dict, operations: list[str]) -> dict:
    """The pack's plant-system OpenAPI tool, limited to ``operations``.

    The Logic App behind it takes its routing parameters in the query string;
    they are fixed per deployment, so each one is declared as a required
    single-value enum. The signature (``sig``) comes from the project
    connection the template created, so it never appears in the agent."""
    infra = pack["infra"]
    spec = copy.deepcopy(_pack_json(pack["id"], infra["openapi"]))
    fixed = {"api-version": outputs["cmmsApiVersion"], "sp": outputs["cmmsSp"], "sv": outputs["cmmsSv"]}
    paths: dict = {}
    for path, item in spec["paths"].items():
        kept = {m: op for m, op in item.items() if op.get("operationId") in operations}
        for op in kept.values():
            op["parameters"] = [
                {"name": k, "in": "query", "required": True, "schema": {"type": "string", "enum": [v]}}
                for k, v in fixed.items()
            ]
        if kept:
            paths[path] = kept
    spec["paths"] = paths
    spec["servers"] = [{"url": outputs["cmmsBaseUrl"]}]
    spec["components"] = {"securitySchemes": {"sig": {"type": "apiKey", "name": "sig", "in": "query"}}}
    spec["security"] = [{"sig": []}]
    return {
        "type": "openapi",
        "openapi": {
            "name": infra["toolName"],
            "description": infra["toolDescription"],
            "spec": spec,
            "auth": {
                "type": "project_connection",
                "security_scheme": {"project_connection_id": outputs["cmmsConnectionId"]},
            },
        },
    }


def _action_allowed(permissions: list[dict], action: str) -> bool:
    """True if any role grants the action without that same role excluding it
    (notActions only subtract within their own role definition)."""
    action = action.lower()
    for perm in permissions:
        granted = any(fnmatch.fnmatchcase(action, a.lower()) for a in perm.get("actions", []))
        excluded = any(fnmatch.fnmatchcase(action, a.lower()) for a in perm.get("notActions", []))
        if granted and not excluded:
            return True
    return False


async def _missing_permissions(az: AzureClient, subscription_id: str) -> list[str] | None:
    """Actions the caller lacks at subscription scope, or None if unknown."""
    try:
        perms = await az.list_caller_permissions(subscription_id)
    except AzureError as e:
        logger.warning("[agents] permission pre-flight skipped: %s", e.detail)
        return None
    return [a for a in REQUIRED_ACTIONS if not _action_allowed(perms, a)]


async def _rank_models(
    az: AzureClient, subscription_id: str, location: str, candidates: list[list[str]]
) -> list[tuple[str, str, int]]:
    """Order model candidates by available GlobalStandard quota in the region.
    Returns (name, version, capacity); unknown quota keeps catalog order."""
    ranked: list[tuple[str, str, int]] = []
    unknown: list[tuple[str, str, int]] = []
    for name, version in candidates:
        regions = await az.check_model_capacity(subscription_id, name, version)
        if not regions:
            unknown.append((name, version, MODEL_CAPACITY))
            continue
        # One entry per SKU; only GlobalStandard quota matters for this deploy.
        here = next(
            (r for r in regions
             if r["location"].lower() == location.lower() and r.get("skuName", MODEL_SKU) == MODEL_SKU),
            None,
        )
        available = int(here["availableCapacity"]) if here else 0
        if available >= MIN_MODEL_CAPACITY:
            ranked.append((name, version, min(available, MODEL_CAPACITY)))
    return ranked + unknown


def _agent_tools(
    agent: dict, vector_store_id: str | None, file_ids: dict[str, str], actions_tool: Callable[[list[str]], dict] | None
) -> list[dict]:
    tools: list[dict] = []
    if vector_store_id:
        tools.append({"type": "file_search", "vector_store_ids": [vector_store_id]})
    if agent.get("data"):
        tools.append({
            "type": "code_interpreter",
            "container": {"type": "auto", "file_ids": [file_ids[name] for name in agent["data"]]},
        })
    if agent.get("actions") and actions_tool:
        tools.append(actions_tool(agent["actions"]))
    return tools


async def call_plant_system(az: AzureClient, azure: dict, path: str, body: dict, timeout: float = 60.0) -> httpx.Response:
    """POST to the simulated plant system (the CMMS Logic App) through its signed
    trigger URL, fetched fresh from ARM with the caller's token."""
    callback = await az.get_workflow_callback_url(azure["subscriptionId"], azure["resourceGroup"], azure["cmmsWorkflow"])
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(f"{callback['basePath']}/{path}", params=callback["queries"], json=body)


async def _wait_for_template(
    az: AzureClient, subscription_id: str, resource_group: str, sleep: Callable[[float], Awaitable[None]]
) -> dict:
    deadline = time.monotonic() + INFRA_TIMEOUT_S
    while True:
        props = await az.get_template_deployment(subscription_id, resource_group, INFRA_DEPLOYMENT)
        state = props.get("provisioningState", "")
        if state == "Succeeded":
            return {k: v.get("value") for k, v in (props.get("outputs") or {}).items()}
        if state in ("Failed", "Canceled"):
            detail = await az.template_deployment_error(subscription_id, resource_group, INFRA_DEPLOYMENT)
            raise AgentPackError(f"The workflow and tracing resources failed to deploy: {detail}")
        if time.monotonic() > deadline:
            raise AgentPackError(f"The workflow and tracing resources did not finish within {INFRA_TIMEOUT_S // 60} minutes.")
        await sleep(INFRA_POLL_S)


async def _wait_for_plant_system(az: AzureClient, azure: dict, sleep: Callable[[float], Awaitable[None]]) -> bool:
    """True once the plant system answers. Its storage role can take minutes to
    propagate, and until then the agents' tool calls would fail."""
    deadline = time.monotonic() + SYSTEM_READY_TIMEOUT_S
    while True:
        try:
            resp = await call_plant_system(az, azure, "board", {})
            if resp.status_code == 200:
                return True
            logger.info("[agents] plant system not ready yet: %s", resp.status_code)
        except (AzureError, httpx.HTTPError) as e:
            logger.info("[agents] plant system not ready yet: %s", e)
        if time.monotonic() > deadline:
            return False
        await sleep(SYSTEM_READY_POLL_S)


async def start_evaluations(client: FoundryProjectClient, pack: dict, model: str, existing: dict | None = None) -> dict:
    """Start one evaluation run per agent with a test set. Reuses the evaluation
    definitions in ``existing`` ({agent: {evalId, runId}}) when re-running."""
    runs: dict = {}
    for agent_id, queries in pack.get("evaluations", {}).items():
        eval_id = (existing or {}).get(agent_id, {}).get("evalId") or await client.create_agent_evaluation(
            f"{agent_id} quality", model,
        )
        runs[agent_id] = {"evalId": eval_id, "runId": await client.start_agent_evaluation_run(eval_id, agent_id, queries)}
    return runs


async def deploy_pack(
    az: AzureClient,
    pack: dict,
    agent_token: str,
    subscription_id: str,
    resource_group: str,
    location: str,
    on_resources: Callable[[dict | None], None],
    project_client_factory: Callable[[str, str], FoundryProjectClient] = FoundryProjectClient,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[dict]:
    """Deploy an agent pack, yielding plan/step/error events."""
    infra = pack.get("infra")
    steps = [
        DeploymentStep("preflight", "Check Azure permissions and model quota"),
        DeploymentStep("resource-group", "Create a dedicated resource group"),
        DeploymentStep("foundry", "Provision Microsoft Foundry account + project"),
        DeploymentStep("model", "Deploy the AI model"),
        DeploymentStep("access", "Grant you access to the Foundry project"),
        DeploymentStep("knowledge", "Upload knowledge documents and plant data"),
    ]
    if infra:
        steps.append(DeploymentStep("infra", "Deploy the plant system, incident workflow and tracing"))
    steps += [
        DeploymentStep("agents", f"Create {len(pack['agents'])} agents"),
        DeploymentStep("verify", "Check the model and plant system respond"),
        DeploymentStep("done", "Ready"),
    ]
    yield {"event": "plan", "data": [s.to_dict() for s in steps]}

    azure: dict = {
        "kind": SCENARIO_ID,
        "subscriptionId": subscription_id,
        "resourceGroup": resource_group,
        "location": location,
    }
    rg_created = False
    current: DeploymentStep | None = None

    def start(name: str) -> dict:
        nonlocal current
        current = _find_step(steps, name)
        current.status = "running"
        return current.to_dict()

    def finish(detail: str = "") -> dict:
        assert current is not None
        current.status = "completed"
        current.detail = detail
        return current.to_dict()

    try:
        # 1. Pre-flight - fail before anything billable exists.
        yield {"event": "step", "data": start("preflight")}
        if not agent_token:
            raise AgentPackError(
                "Sign-in for Microsoft Foundry is missing. Allow the Foundry Agent Service "
                "permission when prompted, then deploy again."
            )
        missing = await _missing_permissions(az, subscription_id)
        if missing:
            raise AgentPackError(
                "Your account can't deploy the agents in this subscription - it is missing "
                f"{', '.join(missing)}. You need Owner, or Contributor + User Access Administrator "
                "(you get the 'Azure AI User' role on the new Foundry account so you can chat with the agents)."
            )
        models = await _rank_models(az, subscription_id, location, pack["modelCandidates"])
        if not models:
            names = ", ".join(n for n, _ in pack["modelCandidates"])
            raise AgentPackError(
                f"No GlobalStandard quota in {location} for any supported model ({names}). "
                "Pick another region or request quota in the Microsoft Foundry portal."
            )
        yield {"event": "step", "data": finish(
            "Permissions OK" if missing == [] else "Permission check unavailable - continuing"
        )}

        # 2. Dedicated resource group - recorded right away so the user can
        # always delete it, even if the job is cancelled from here on.
        yield {"event": "step", "data": start("resource-group")}
        if await az.resource_group_exists(subscription_id, resource_group):
            raise AgentPackError(f"Resource group '{resource_group}' already exists - retry the deploy.")
        await az.register_providers(subscription_id, REQUIRED_PROVIDERS + (infra or {}).get("providers", []))
        await az.create_tagged_resource_group(
            subscription_id, resource_group, location,
            # SecurityControl=Ignore keeps tenant auto-remediation policies from
            # disabling the storage account's public endpoint the Logic Apps use.
            {"created-by": RESOURCE_GROUP_TAG, "fdg-agent-pack": pack["id"], "SecurityControl": "Ignore"},
        )
        rg_created = True
        on_resources(azure)
        yield {"event": "step", "data": finish(resource_group)}

        # 3. Foundry account + project.
        yield {"event": "step", "data": start("foundry")}
        account = f"fdg-agents-{secrets.token_hex(4)}"
        project = f"{pack['id']}-agents"
        await az.create_foundry_account(subscription_id, resource_group, account, location)
        await az.create_foundry_project(
            subscription_id, resource_group, account, project, location, display_name=pack["title"],
        )
        azure["foundryAccount"] = account
        azure["foundryProject"] = project
        on_resources(azure)
        yield {"event": "step", "data": finish(f"{account} / {project}")}

        # 4. Model, falling back across candidates on quota/availability errors.
        yield {"event": "step", "data": start("model")}
        model = ""
        errors: list[str] = []
        for name, version, capacity in models:
            try:
                await az.create_model_deployment(
                    subscription_id, resource_group, account, name, name, version,
                    sku_name=MODEL_SKU, capacity=capacity,
                )
                model = name
                break
            except AzureError as e:
                logger.warning("[agents] model %s failed, trying next: %s", name, e.detail)
                errors.append(f"{name}: {e.detail[:160]}")
        if not model:
            raise AgentPackError("No model could be deployed. " + " | ".join(errors))
        azure["model"] = model
        if infra:
            # Runs on ARM while the knowledge is uploaded; awaited before the agents.
            await az.start_template_deployment(
                subscription_id, resource_group, INFRA_DEPLOYMENT,
                _pack_json(pack["id"], infra["template"]),
                {"foundryAccountName": account, "foundryProjectName": project, "modelDeploymentName": model},
            )
        yield {"event": "step", "data": finish(model)}

        # 5. The caller needs the data-plane role to create and chat with agents.
        yield {"event": "step", "data": start("access")}
        caller = az.get_caller_oid()
        if not caller:
            raise AgentPackError("Couldn't read your user id from the Azure sign-in. Sign out and sign in again.")
        account_scope = (
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account}"
        )
        await az.assign_role(account_scope, FOUNDRY_USER, caller, "User")
        yield {"event": "step", "data": finish("Azure AI User on the Foundry account")}

        endpoint = f"https://{account}.services.ai.azure.com/api/projects/{project}"
        client = project_client_factory(endpoint, agent_token)
        try:
            # 6. Upload each document and data file once, then one vector store per agent.
            yield {"event": "step", "data": start("knowledge")}
            file_ids: dict[str, str] = {}
            for agent in pack["agents"]:
                for rel in agent.get("knowledge", []):
                    if rel not in file_ids:
                        path = pack_file(pack, rel)
                        file_ids[rel] = await client.upload_file(path.name, path.read_bytes(), CONTENT_TYPES[path.suffix])
                for name in agent.get("data", []):
                    if name not in file_ids:
                        path = data_file(pack, name)
                        file_ids[name] = await client.upload_file(path.name, path.read_bytes(), CONTENT_TYPES[path.suffix])
                current.detail = f"Uploaded {len(file_ids)} files"
                yield {"event": "step", "data": current.to_dict()}
            stores: dict[str, str] = {}
            for agent in pack["agents"]:
                if agent.get("knowledge"):
                    stores[agent["id"]] = await client.create_vector_store(
                        f"{agent['id']}-knowledge", [file_ids[rel] for rel in agent["knowledge"]],
                    )
            yield {"event": "step", "data": finish(f"{len(file_ids)} files, {len(stores)} knowledge indexes")}

            # 7. Plant system, incident workflow and tracing (started after the model).
            actions_tool: Callable[[list[str]], dict] | None = None
            if infra:
                yield {"event": "step", "data": start("infra")}
                outputs = await _wait_for_template(az, subscription_id, resource_group, sleep)
                azure.update({
                    "cmmsWorkflow": outputs["cmmsWorkflowName"],
                    "incidentWorkflow": outputs["incidentWorkflowName"],
                    "appInsights": outputs["appInsightsName"],
                })
                on_resources(azure)

                def actions_tool(operations: list[str]) -> dict:
                    return openapi_tool(pack, outputs, operations)

                yield {"event": "step", "data": finish("Plant maintenance system, incident workflow, Application Insights")}

            # 8. Agents.
            yield {"event": "step", "data": start("agents")}
            created: list[dict] = []
            for agent in pack["agents"]:
                await client.create_agent(
                    agent["id"], model,
                    pack_file(pack, agent["instructions"]).read_text(encoding="utf-8"),
                    _agent_tools(agent, stores.get(agent["id"]), file_ids, actions_tool),
                    description=agent["title"],
                )
                created.append({"id": agent["id"], "name": agent["id"], "title": agent["title"]})
                current.detail = f"Created {len(created)} of {len(pack['agents'])}"
                yield {"event": "step", "data": current.to_dict()}
            yield {"event": "step", "data": finish(", ".join(a["title"] for a in created))}

            # 9. A fresh deployment can throttle its first requests; make sure the
            # presenter's first chat works instead of hitting a 429 in the playground.
            yield {"event": "step", "data": start("verify")}
            ready = await client.warm_up(model)
            notes = ["Model answered" if ready else "Model still warming up - give it a minute before the first chat"]
            if infra:
                notes.append(
                    "plant system answered" if await _wait_for_plant_system(az, azure, sleep)
                    else "plant system still getting its permissions - give it a few minutes"
                )
            yield {"event": "step", "data": finish(", ".join(notes))}
        finally:
            await client.close()

        _, _, tenant_id = az.get_caller_entra_admin()
        azure["portalUrl"] = foundry_portal_url(subscription_id, resource_group, account, project, tenant_id=tenant_id)
        for a in created:
            a["portalUrl"] = foundry_portal_url(
                subscription_id, resource_group, account, project, f"build/agents/{a['name']}/build", tenant_id,
            )
        azure["projectEndpoint"] = endpoint
        if infra:
            rg_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            azure["tracingUrl"] = azure_portal_url(
                f"{rg_id}/providers/Microsoft.Insights/components/{azure['appInsights']}", tenant_id,
            )
            azure["workflowUrl"] = azure_portal_url(
                f"{rg_id}/providers/Microsoft.Logic/workflows/{azure['incidentWorkflow']}", tenant_id, "logicApp",
            )
        on_resources(azure)
        step = _find_step(steps, "done")
        step.status = "completed"
        step.detail = json.dumps({"agents": created, "azure": azure})
        yield {"event": "step", "data": step.to_dict()}

    except (AgentPackError, AzureError, FoundryProjectError) as e:
        message = e.detail if isinstance(e, (AzureError, FoundryProjectError)) else str(e)
        if current is not None and current.status == "running":
            current.status = "failed"
            current.detail = message[:300]
            yield {"event": "step", "data": current.to_dict()}
        data: dict = {"message": message, "workspaceId": ""}
        if rg_created:
            # Auto-teardown like the Fabric scenarios: the resource group is
            # dedicated to this deploy, so deleting it removes everything.
            try:
                await az.delete_resource_group(subscription_id, resource_group)
                data["message"] += f" The resource group '{resource_group}' is being deleted, so nothing is left behind."
                on_resources(None)
            except AzureError as te:
                logger.warning("[agents] teardown of %s failed: %s", resource_group, te.detail)
                data["message"] += f" Delete the resource group '{resource_group}' to remove partial resources."
                data["azure"] = azure
        yield {"event": "error", "data": data}


async def run_pack_job(
    job_id: str,
    management_token: str,
    agent_token: str,
    pack: dict,
    subscription_id: str,
    resource_group: str,
    location: str,
) -> None:
    """Background task: stream deploy_pack events into the job store."""
    from app.job_store import job_store

    az = AzureClient(management_token)
    try:
        async for event in deploy_pack(
            az, pack, agent_token, subscription_id, resource_group, location,
            on_resources=lambda res: job_store.set_azure_resources(job_id, res),
        ):
            job_store.emit_event(job_id, event)
        job = job_store.get_job(job_id)
        if job:
            job_store.set_status(job_id, "failed" if job.error else "completed")
    except asyncio.CancelledError:
        logger.info("Agent pack job %s was cancelled", job_id)
        job_store.emit_event(job_id, {
            "event": "error",
            "data": {"message": "Deployment cancelled. Anything already created is kept - delete it from the Monitoring page."},
        })
        job_store.set_status(job_id, "cancelled")
    except Exception as e:
        logger.exception("Agent pack job %s failed with unexpected error", job_id)
        job_store.emit_event(job_id, {
            "event": "error",
            "data": {"message": f"Server error: {type(e).__name__}: {str(e)[:300]}"},
        })
        job_store.set_status(job_id, "failed")
    finally:
        try:
            await az.close()
        except Exception as e:  # noqa: BLE001 - closing must never mask the job outcome
            logger.debug("Agent pack job %s: closing the ARM client failed: %s", job_id, e)
        job = job_store.get_job(job_id)
        if job:
            for queue in list(job._subscribers):
                try:
                    queue.put_nowait({"event": "_done", "data": {}})
                except asyncio.QueueFull:
                    logger.debug("Agent pack job %s: subscriber queue full at completion", job_id)


# ── Incident workflow, plant system board and evaluations (after deploy) ──

RUN_ACTIVE = {"Running", "Waiting", "Paused"}
ACTION_FAILED = {"Failed", "TimedOut", "Cancelled", "Aborted"}
INCIDENT_PHOTO_MAX_BYTES = 4 * 1024 * 1024
# Outputs of finished actions and completed evaluation runs never change.
_finished_content: dict[str, object] = {}
_finished_evaluations: dict[str, dict] = {}


def _remember(cache: dict, key: str, value) -> None:
    if len(cache) > 2000:
        cache.clear()
    cache[key] = value


async def _action_content(az: AzureClient, run_id: str, action: dict | None) -> object:
    """An action's output: a Compose value, or an HTTP action's response body."""
    if not action or action.get("properties", {}).get("status") != "Succeeded":
        return None
    key = f"{run_id}/{action['name']}"
    if key in _finished_content:
        return _finished_content[key]
    link = (action["properties"].get("outputsLink") or {}).get("uri")
    if not link:
        return None
    content = await az.read_run_content(link)
    if isinstance(content, dict) and "body" in content and (set(content) == {"body"} or "statusCode" in content):
        content = content["body"]
    _remember(_finished_content, key, content)
    return content


def _step_status(step: dict, actions: dict[str, dict], approval_action: str, run_active: bool) -> str:
    states = {n: actions[n]["properties"].get("status", "") for n in step["watch"] if n in actions}
    done = states.get(step["done"])
    if done == "Succeeded":
        return "completed"
    if any(s in ACTION_FAILED for s in states.values()):
        return "failed"
    if states.get(approval_action) in RUN_ACTIVE:
        return "waiting"
    if any(s in RUN_ACTIVE or s == "Succeeded" for s in states.values()):
        return "running" if run_active else "failed"
    if states and all(s == "Skipped" for s in states.values()):
        return "skipped"
    return "pending" if run_active else "skipped"


def _require_workflows(azure: dict) -> None:
    if not (azure.get("incidentWorkflow") and azure.get("cmmsWorkflow")):
        raise AgentPackError("This deployment has no incident workflow - redeploy the agents to get it.")


async def start_incident(az: AzureClient, azure: dict, line: str, shift: str, date: str, photo: str) -> str:
    """Start the incident workflow; its run name is the incident id."""
    _require_workflows(azure)
    callback = await az.get_workflow_callback_url(azure["subscriptionId"], azure["resourceGroup"], azure["incidentWorkflow"])
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(callback["value"], json={"line": line, "shift": shift, "date": date, "photo": photo})
    run_id = resp.headers.get("x-ms-workflow-run-id", "")
    if resp.status_code >= 400 or not run_id:
        raise AgentPackError(f"The incident workflow did not start ({resp.status_code}): {resp.text[:200]}")
    return run_id


async def incident_status(az: AzureClient, azure: dict, pack: dict, run_id: str) -> dict:
    """Live view of an incident run: one entry per agent step, with each
    finished step's output, the work order draft while approval is pending,
    and the final report."""
    _require_workflows(azure)
    config = pack["incident"]
    sub, rg, workflow = azure["subscriptionId"], azure["resourceGroup"], azure["incidentWorkflow"]
    run = (await az.get_workflow_run(sub, rg, workflow, run_id)).get("properties", {})
    actions = {a["name"]: a for a in await az.list_workflow_run_actions(sub, rg, workflow, run_id)}
    run_status = run.get("status", "Running")
    run_active = run_status in RUN_ACTIVE

    steps: list[dict] = []
    for step in config["steps"]:
        status = _step_status(step, actions, config["approvalAction"], run_active)
        item: dict = {"id": step["id"], "title": step["title"], "agent": step["agent"], "status": status}
        if status == "completed":
            if step.get("output"):
                item["output"] = await _action_content(az, run_id, actions.get(step["output"]))
            if step.get("data"):
                item["data"] = await _action_content(az, run_id, actions.get(step["data"]))
        elif status == "failed":
            failed = next(
                (actions[n] for n in step["watch"] if n in actions and actions[n]["properties"].get("status") in ACTION_FAILED),
                None,
            )
            error = (failed or {}).get("properties", {}).get("error") or {}
            item["error"] = error.get("message") or (failed or {}).get("properties", {}).get("code") or "The step did not finish."
        steps.append(item)

    result: dict = {
        "incidentId": run_id,
        "status": run_status,
        "startedAt": run.get("startTime"),
        "endedAt": run.get("endTime"),
        "steps": steps,
        "awaitingApproval": any(s["status"] == "waiting" for s in steps),
    }
    if result["awaitingApproval"]:
        result["draft"] = await _action_content(az, run_id, actions.get(config["draftAction"]))
    if run_status == "Succeeded":
        result["report"] = await _action_content(az, run_id, actions.get(config["reportAction"]))
    return result


async def record_decision(
    az: AzureClient, azure: dict, pack: dict, run_id: str, decision: str, decided_by: str, comment: str
) -> None:
    """Approve or reject the work order an incident run is waiting on."""
    _require_workflows(azure)
    actions = await az.list_workflow_run_actions(azure["subscriptionId"], azure["resourceGroup"], azure["incidentWorkflow"], run_id)
    waiting = next((a for a in actions if a["name"] == pack["incident"]["approvalAction"]), None)
    if not waiting or waiting["properties"].get("status") not in RUN_ACTIVE:
        raise AgentPackError("This incident is not waiting for an approval.")
    resp = await call_plant_system(az, azure, "approvals", {
        "incident_id": run_id, "decision": decision, "decided_by": decided_by, "comment": comment,
    })
    if resp.status_code >= 400:
        raise AgentPackError(f"The plant system did not record the decision ({resp.status_code}).")


async def plant_board(az: AzureClient, azure: dict) -> dict:
    """Work orders and quality holds in the simulated plant system, newest first."""
    _require_workflows(azure)
    resp = await call_plant_system(az, azure, "board", {})
    if resp.status_code >= 400:
        raise AgentPackError(f"The plant system did not answer ({resp.status_code}). It can take a few minutes after the deploy.")
    body = resp.json()

    def rows(key: str, id_field: str, fields: tuple[str, ...]) -> list[dict]:
        items = [{id_field: r.get("RowKey", ""), **{f: r.get(f, "") for f in fields}} for r in body.get(key) or []]
        return sorted(items, key=lambda r: r.get("created_at", ""), reverse=True)

    return {
        "workOrders": rows("work_orders", "id", ("machine_id", "priority", "title", "description", "status", "requested_by", "created_at")),
        "qualityHolds": rows("quality_holds", "id", ("batch_id", "machine_id", "production_line", "product", "reason", "status", "requested_by", "created_at")),
    }


async def evaluation_results(client: FoundryProjectClient, pack: dict, azure: dict) -> list[dict]:
    """Status and average scores of each agent's latest evaluation run."""
    titles = {a["id"]: a["title"] for a in pack["agents"]}
    labels = list(AGENT_EVALUATORS.values())
    results: list[dict] = []
    for agent_id, ids in (azure.get("evaluations") or {}).items():
        run_id = ids["runId"]
        if run_id in _finished_evaluations:
            results.append(_finished_evaluations[run_id])
            continue
        run = await client.get_evaluation_run(ids["evalId"], run_id)
        entry: dict = {
            "agent": agent_id,
            "title": titles.get(agent_id, agent_id),
            "status": run.get("status", ""),
            "reportUrl": run.get("report_url") or "",
            "queries": len(pack.get("evaluations", {}).get(agent_id, [])),
            "criteria": [],
        }
        if entry["status"] == "completed":
            scores: dict[str, list[float]] = {}
            passed: dict[str, int] = {}
            for item in await client.list_evaluation_items(ids["evalId"], run_id):
                for res in item.get("results") or []:
                    name = res.get("name", "")
                    if isinstance(res.get("score"), (int, float)):
                        scores.setdefault(name, []).append(float(res["score"]))
                    passed[name] = passed.get(name, 0) + (1 if res.get("passed") else 0)
            for name in labels + sorted(set(scores) - set(labels)):
                if name in scores or name in passed:
                    values = scores.get(name, [])
                    entry["criteria"].append({
                        "name": name,
                        "average": round(sum(values) / len(values), 2) if values else None,
                        "scale": EVALUATOR_SCALES.get(name, 5),
                        "passed": passed.get(name, 0),
                        "scored": len(values),
                    })
            _remember(_finished_evaluations, run_id, entry)
        elif entry["status"] in ("failed", "canceled"):
            entry["error"] = ((run.get("error") or {}).get("message") or "The evaluation run failed.")[:300]
        results.append(entry)
    return results
