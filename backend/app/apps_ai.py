"""Apps & AI demos - Azure-hosted apps deployed into the user's subscription.

Unlike the Fabric demos, these provision no Fabric items. Each app is a public
frontend Container App that proxies /api to an internal backend Container App,
which calls a Foundry model through its managed identity. Images are prebuilt
and public (see .github/workflows/apps-ai-images.yml), so a deploy is nothing
but ARM calls made with the signed-in user's own management token:

  resource group -> providers -> Foundry account + project -> model (with
  fallbacks) -> ARM template (Container Apps, monitoring, role assignments)
  -> wait until both revisions are running.

Every deploy gets its own new resource group, so cleanup is a single
resource-group delete.
"""

from __future__ import annotations

import asyncio
import fnmatch
import ipaddress
import json
import logging
import os
import secrets
import time
from collections.abc import AsyncIterator, Callable, Mapping
from functools import lru_cache
from pathlib import Path

from app.azure_client import AzureClient, AzureError
from app.deployer import DEMOS_DIR, DeploymentStep, _find_step

logger = logging.getLogger(__name__)

APPS_DIR: Path = DEMOS_DIR / "_apps"
SCENARIO_ID = "apps-ai"
RESOURCE_GROUP_TAG = "fabric-demo-gallery"
REQUIRED_PROVIDERS = [
    "Microsoft.App",
    "Microsoft.CognitiveServices",
    "Microsoft.OperationalInsights",
    "Microsoft.Insights",
]
# Creating the dedicated resource group and the backend's Foundry role
# assignments are the two actions plain Contributor lacks or that a custom
# role commonly omits - check them before anything billable is created.
REQUIRED_ACTIONS = [
    "Microsoft.Resources/subscriptions/resourceGroups/write",
    "Microsoft.Resources/deployments/write",
    "Microsoft.Authorization/roleAssignments/write",
]
MODEL_CAPACITY = 50  # thousand tokens per minute (GlobalStandard)
MIN_MODEL_CAPACITY = 10
MAX_IP_RANGES = 10
TEMPLATE_TIMEOUT_S = 25 * 60
READY_TIMEOUT_S = 6 * 60
RUNNING_STATES = {"running", "runningatmaxscale"}
FAILED_STATES = {"failed", "degraded"}


class AppsAiError(Exception):
    """A user-actionable deploy failure."""


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    return json.loads((APPS_DIR / "apps.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_template() -> dict:
    return json.loads((APPS_DIR / load_catalog()["template"]).read_text(encoding="utf-8"))


def get_app(app_id: str) -> dict | None:
    return next((a for a in load_catalog()["apps"] if a["id"] == app_id), None)


def list_apps() -> dict:
    catalog = load_catalog()
    return {
        "regions": catalog["regions"],
        "defaultRegion": catalog["defaultRegion"],
        "apps": [
            {"id": a["id"], "title": a["title"], "industry": a["industry"]}
            for a in catalog["apps"]
        ],
    }


def image_ref(app_id: str, component: str) -> str:
    """Public image for an app component. APPS_AI_IMAGE_REGISTRY / _TAG let a
    test environment point at a different registry without editing the catalog."""
    catalog = load_catalog()
    registry = os.getenv("APPS_AI_IMAGE_REGISTRY") or catalog["imageRegistry"]
    tag = os.getenv("APPS_AI_IMAGE_TAG") or catalog["imageTag"]
    return f"{registry.rstrip('/')}/{app_id}-{component}:{tag}"


def client_ip_from_headers(headers: Mapping[str, str]) -> str | None:
    """Best-effort public IPv4 of the browser, as seen through App Service's
    front end (X-Forwarded-For may carry 'ip:port'). Only used to pre-fill the
    user's own allowlist, so a spoofed header can only restrict their own app."""
    candidates = [headers.get("x-client-ip") or ""] + (headers.get("x-forwarded-for") or "").split(",")
    for raw in candidates:
        value = raw.strip()
        if not value:
            continue
        if value.count(":") == 1:  # IPv4 with port
            value = value.split(":", 1)[0]
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            continue
        if ip.version == 4 and ip.is_global:
            return str(ip)
    return None


def normalize_ip_ranges(ranges: list[str]) -> list[str]:
    """Validate an allowlist: public IPv4 addresses or CIDR ranges only
    (Container Apps ingress restrictions are IPv4)."""
    if len(ranges) > MAX_IP_RANGES:
        raise ValueError(f"At most {MAX_IP_RANGES} IP ranges are allowed.")
    out: list[str] = []
    for raw in ranges:
        value = (raw or "").strip()
        try:
            net = ipaddress.ip_network(value, strict=False)
        except ValueError:
            raise ValueError(f"'{value}' is not a valid IPv4 address or CIDR range.") from None
        if net.version != 4:
            raise ValueError(f"'{value}' is IPv6 - Container Apps access restrictions accept IPv4 only.")
        if not net.network_address.is_global:
            raise ValueError(f"'{value}' is not a public address - use your internet-facing IP.")
        if str(net) not in out:
            out.append(str(net))
    return out


def new_resource_group_name(app_id: str) -> str:
    return f"rg-fdg-{app_id}-{secrets.token_hex(3)}"


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
    except Exception as e:  # noqa: BLE001 - advisory pre-flight
        logger.warning("[apps-ai] permission pre-flight skipped: %s", e)
        return None
    return [a for a in REQUIRED_ACTIONS if not _action_allowed(perms, a)]


async def _rank_models(
    az: AzureClient, subscription_id: str, location: str, candidates: list[list[str]]
) -> list[tuple[str, str, int]]:
    """Order model candidates by available GlobalStandard quota in the region.
    Returns (name, version, capacity). Unknown quota keeps catalog order."""
    ranked: list[tuple[str, str, int]] = []
    unknown: list[tuple[str, str, int]] = []
    for name, version in candidates:
        regions = await az.check_model_capacity(subscription_id, name, version)
        if not regions:
            unknown.append((name, version, MODEL_CAPACITY))
            continue
        here = next((r for r in regions if r["location"].lower() == location.lower()), None)
        available = int(here["availableCapacity"]) if here else 0
        if available >= MIN_MODEL_CAPACITY:
            ranked.append((name, version, min(available, MODEL_CAPACITY)))
    return ranked + unknown


async def deploy_app(
    az: AzureClient,
    app: dict,
    subscription_id: str,
    resource_group: str,
    location: str,
    allowed_ip_ranges: list[str],
    on_resources: Callable[[dict | None], None],
) -> AsyncIterator[dict]:
    """Deploy one Apps & AI demo, yielding plan/step/error events."""
    steps = [
        DeploymentStep("preflight", "Check Azure permissions and model quota"),
        DeploymentStep("resource-group", "Create a dedicated resource group"),
        DeploymentStep("providers", "Register Azure resource providers"),
        DeploymentStep("foundry", "Provision Microsoft Foundry account + project"),
        DeploymentStep("model", "Deploy the AI model"),
        DeploymentStep("apps", "Deploy the Container Apps (frontend + backend)"),
        DeploymentStep("verify", "Wait for the app to start"),
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
        missing = await _missing_permissions(az, subscription_id)
        if missing:
            raise AppsAiError(
                "Your account can't deploy this app in the selected subscription - it is missing "
                f"{', '.join(missing)}. You need Owner, or Contributor + User Access Administrator "
                "(role assignments let the app's managed identity call the model)."
            )
        models = await _rank_models(az, subscription_id, location, app["modelCandidates"])
        if not models:
            names = ", ".join(n for n, _ in app["modelCandidates"])
            raise AppsAiError(
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
            raise AppsAiError(f"Resource group '{resource_group}' already exists - retry the deploy.")
        await az.create_tagged_resource_group(
            subscription_id, resource_group, location,
            {"created-by": RESOURCE_GROUP_TAG, "fdg-app": app["id"]},
        )
        rg_created = True
        on_resources(azure)
        yield {"event": "step", "data": finish(resource_group)}

        # 3. Providers.
        yield {"event": "step", "data": start("providers")}
        await az.register_providers(subscription_id, REQUIRED_PROVIDERS)
        yield {"event": "step", "data": finish("Registered")}

        # 4. Foundry account + project.
        yield {"event": "step", "data": start("foundry")}
        account = f"fdg-{app['namePrefix']}-{secrets.token_hex(3)}"
        project = f"{app['namePrefix']}-project"
        await az.create_foundry_account(subscription_id, resource_group, account, location)
        await az.create_foundry_project(
            subscription_id, resource_group, account, project, location,
            display_name=app["title"],
        )
        azure["foundryAccount"] = account
        azure["foundryProject"] = project
        on_resources(azure)
        yield {"event": "step", "data": finish(f"{account} / {project}")}

        # 5. Model, falling back across candidates on quota/availability errors.
        yield {"event": "step", "data": start("model")}
        deployment = ""
        errors: list[str] = []
        for name, version, capacity in models:
            try:
                await az.create_model_deployment(
                    subscription_id, resource_group, account, name, name, version,
                    sku_name="GlobalStandard", capacity=capacity,
                )
                deployment = name
                break
            except AzureError as e:
                logger.warning("[apps-ai] model %s failed, trying next: %s", name, e.detail)
                errors.append(f"{name}: {e.detail[:160]}")
        if not deployment:
            raise AppsAiError("No model could be deployed. " + " | ".join(errors))
        azure["model"] = deployment
        yield {"event": "step", "data": finish(deployment)}

        # 6. Container Apps via the compiled ARM template.
        yield {"event": "step", "data": start("apps")}
        deployment_name = f"fdg-{app['id']}"[:64]
        await az.deploy_template(
            subscription_id, resource_group, deployment_name, load_template(),
            {
                "appId": app["id"],
                "namePrefix": app["namePrefix"],
                "location": location,
                "foundryAccountName": account,
                "foundryProjectName": project,
                "modelDeploymentName": deployment,
                "backendImage": image_ref(app["id"], "backend"),
                "frontendImage": image_ref(app["id"], "frontend"),
                "backendPort": app["backendPort"],
                "backendEnv": app.get("backendEnv", []),
                "allowedIpRanges": allowed_ip_ranges,
            },
        )
        started = time.time()
        outputs: dict = {}
        while True:
            await asyncio.sleep(10)
            body = await az.get_deployment(subscription_id, resource_group, deployment_name)
            props = body.get("properties", {})
            state = (props.get("provisioningState") or "").lower()
            if state == "succeeded":
                outputs = {k: v.get("value") for k, v in (props.get("outputs") or {}).items()}
                break
            if state in ("failed", "canceled"):
                detail = await az.deployment_failure_detail(subscription_id, resource_group, deployment_name)
                raise AppsAiError(f"Container Apps deployment {state}: {detail or props.get('error')}")
            if time.time() - started > TEMPLATE_TIMEOUT_S:
                raise AppsAiError("Container Apps deployment timed out. Check the resource group's Deployments blade.")
            current.detail = f"Deploying... {int(time.time() - started)}s"
            yield {"event": "step", "data": current.to_dict()}
        app_url = outputs.get("frontendUrl", "")
        azure["appUrl"] = app_url
        azure["frontendApp"] = outputs.get("frontendAppName", "")
        azure["backendApp"] = outputs.get("backendAppName", "")
        on_resources(azure)
        yield {"event": "step", "data": finish(app_url)}

        # 7. Wait for both revisions via ARM - works even when the frontend is
        # IP-restricted and the gallery backend can't reach it over HTTP.
        yield {"event": "step", "data": start("verify")}
        started = time.time()
        pending = {azure["backendApp"], azure["frontendApp"]} - {""}
        note = "Running"
        while pending:
            for name in list(pending):
                running, health = await az.get_container_app_revision_state(subscription_id, resource_group, name)
                if running.lower() in FAILED_STATES or health.lower() == "unhealthy":
                    raise AppsAiError(
                        f"Container App '{name}' failed to start ({running or health}). "
                        "Open it in the Azure portal and check Log stream for details."
                    )
                if running.lower() in RUNNING_STATES:
                    pending.discard(name)
            if not pending:
                break
            if time.time() - started > READY_TIMEOUT_S:
                note = "Still starting - give it a minute before opening the app"
                break
            await asyncio.sleep(10)
        yield {"event": "step", "data": finish(note)}

        step = _find_step(steps, "done")
        step.status = "completed"
        step.detail = json.dumps({"appUrl": app_url, "azure": azure})
        yield {"event": "step", "data": step.to_dict()}

    except (AppsAiError, AzureError) as e:
        message = e.detail if isinstance(e, AzureError) else str(e)
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
            except Exception as te:  # noqa: BLE001
                logger.warning("[apps-ai] teardown of %s failed: %s", resource_group, te)
                data["message"] += f" Delete the resource group '{resource_group}' to remove partial resources."
                data["azure"] = azure
        yield {"event": "error", "data": data}


async def run_app_job(
    job_id: str,
    management_token: str,
    app: dict,
    subscription_id: str,
    resource_group: str,
    location: str,
    allowed_ip_ranges: list[str],
) -> None:
    """Background task: stream deploy_app events into the job store."""
    from app.job_store import job_store

    az = AzureClient(management_token)
    try:
        async for event in deploy_app(
            az, app, subscription_id, resource_group, location, allowed_ip_ranges,
            on_resources=lambda res: job_store.set_azure_resources(job_id, res),
        ):
            job_store.emit_event(job_id, event)
        job = job_store.get_job(job_id)
        if job:
            job_store.set_status(job_id, "failed" if job.error else "completed")
    except asyncio.CancelledError:
        logger.info("Apps & AI job %s was cancelled", job_id)
        job_store.emit_event(job_id, {
            "event": "error",
            "data": {"message": "Deployment cancelled. Anything already created is kept - delete it from the Monitoring page."},
        })
        job_store.set_status(job_id, "cancelled")
    except Exception as e:
        logger.exception("Apps & AI job %s failed with unexpected error", job_id)
        job_store.emit_event(job_id, {
            "event": "error",
            "data": {"message": f"Server error: {type(e).__name__}: {str(e)[:300]}"},
        })
        job_store.set_status(job_id, "failed")
    finally:
        try:
            await az.close()
        except Exception as e:  # noqa: BLE001 - closing must never mask the job outcome
            logger.debug("Apps & AI job %s: closing the ARM client failed: %s", job_id, e)
        job = job_store.get_job(job_id)
        if job:
            for queue in list(job._subscribers):
                try:
                    queue.put_nowait({"event": "_done", "data": {}})
                except asyncio.QueueFull:
                    logger.debug("Apps & AI job %s: subscriber queue full at completion", job_id)
