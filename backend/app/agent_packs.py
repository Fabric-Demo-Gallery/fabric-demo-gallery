"""AI agent packs - general Microsoft Foundry agents grounded on an industry's
demo data, deployed into the user's Azure subscription.

No containers or images: each deploy is ARM calls with the user's management
token plus Foundry data-plane calls with the user's delegated ``ai.azure.com``
token (both already requested by the gallery):

  pre-flight -> dedicated resource group -> provider -> Foundry account +
  project -> model (with fallbacks) -> caller gets "Azure AI User" ->
  upload knowledge docs + data files -> one vector store per agent ->
  prompt agents (File Search / Code Interpreter / vision).

The agents are used in the Foundry agent playground, which has its own
sign-in, so nothing is publicly exposed. Deleting the resource group removes
everything.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import secrets
from collections.abc import AsyncIterator, Callable
from functools import cache
from pathlib import Path

from app.azure_client import FOUNDRY_USER, AzureClient, AzureError
from app.deployer import DEMOS_DIR, DeploymentStep, _find_step
from app.foundry_project_client import FoundryProjectClient, FoundryProjectError

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
MODEL_CAPACITY = 150  # thousand tokens per minute (GlobalStandard is billed per token, not per capacity)
MIN_MODEL_CAPACITY = 20
MODEL_SKU = "GlobalStandard"
CONTENT_TYPES = {".csv": "text/csv", ".md": "text/markdown"}


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


def portal_url(subscription_id: str, resource_group: str, account: str, tenant_id: str = "") -> str:
    url = (
        f"https://ai.azure.com/build/agents?wsid=/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}/providers/Microsoft.CognitiveServices/accounts/{account}"
    )
    return f"{url}&tid={tenant_id}" if tenant_id else url


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


def _agent_tools(agent: dict, vector_store_id: str | None, file_ids: dict[str, str]) -> list[dict]:
    tools: list[dict] = []
    if vector_store_id:
        tools.append({"type": "file_search", "vector_store_ids": [vector_store_id]})
    if agent.get("data"):
        tools.append({
            "type": "code_interpreter",
            "container": {"type": "auto", "file_ids": [file_ids[name] for name in agent["data"]]},
        })
    return tools


async def deploy_pack(
    az: AzureClient,
    pack: dict,
    agent_token: str,
    subscription_id: str,
    resource_group: str,
    location: str,
    on_resources: Callable[[dict | None], None],
    project_client_factory: Callable[[str, str], FoundryProjectClient] = FoundryProjectClient,
) -> AsyncIterator[dict]:
    """Deploy an agent pack, yielding plan/step/error events."""
    steps = [
        DeploymentStep("preflight", "Check Azure permissions and model quota"),
        DeploymentStep("resource-group", "Create a dedicated resource group"),
        DeploymentStep("foundry", "Provision Microsoft Foundry account + project"),
        DeploymentStep("model", "Deploy the AI model"),
        DeploymentStep("access", "Grant you access to the Foundry project"),
        DeploymentStep("knowledge", "Upload knowledge documents and plant data"),
        DeploymentStep("agents", f"Create {len(pack['agents'])} agents"),
        DeploymentStep("verify", "Check the model responds"),
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
        await az.register_providers(subscription_id, REQUIRED_PROVIDERS)
        await az.create_tagged_resource_group(
            subscription_id, resource_group, location,
            {"created-by": RESOURCE_GROUP_TAG, "fdg-agent-pack": pack["id"]},
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

            # 7. Agents.
            yield {"event": "step", "data": start("agents")}
            created: list[dict] = []
            for agent in pack["agents"]:
                await client.create_agent(
                    agent["id"], model,
                    pack_file(pack, agent["instructions"]).read_text(encoding="utf-8"),
                    _agent_tools(agent, stores.get(agent["id"]), file_ids),
                    description=agent["title"],
                )
                created.append({"id": agent["id"], "name": agent["id"], "title": agent["title"]})
                current.detail = f"Created {len(created)} of {len(pack['agents'])}"
                yield {"event": "step", "data": current.to_dict()}
            yield {"event": "step", "data": finish(", ".join(a["title"] for a in created))}

            # 8. A fresh deployment can throttle its first requests; make sure the
            # presenter's first chat works instead of hitting a 429 in the playground.
            yield {"event": "step", "data": start("verify")}
            ready = await client.warm_up(model)
            yield {"event": "step", "data": finish(
                "Model answered" if ready else "Model still warming up - give it a minute before the first chat"
            )}
        finally:
            await client.close()

        _, _, tenant_id = az.get_caller_entra_admin()
        azure["portalUrl"] = portal_url(subscription_id, resource_group, account, tenant_id)
        azure["projectEndpoint"] = endpoint
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
