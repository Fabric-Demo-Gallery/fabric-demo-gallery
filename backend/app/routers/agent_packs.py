"""AI agent pack endpoints - catalog, deploy, incident workflow, plant system
board, evaluations and resource cleanup."""

import asyncio
import base64
import binascii
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.agent_packs import (
    INCIDENT_PHOTO_MAX_BYTES,
    SCENARIO_ID,
    AgentPackError,
    evaluation_results,
    incident_status,
    list_packs,
    load_pack,
    new_resource_group_name,
    plant_board,
    record_decision,
    run_pack_job,
    start_evaluations,
    start_incident,
)
from app.auth import (
    get_agent_token,
    get_management_token,
    get_user_email,
    get_user_id,
    get_user_token,
)
from app.azure_client import AzureClient, AzureError
from app.foundry_project_client import FoundryProjectClient, FoundryProjectError
from app.job_store import job_store
from app.models import SAFE_ID, UUID_RE
from app.routers.jobs import _owns_job

router = APIRouter(prefix="/api/agent-packs", tags=["agent-packs"])
limiter = Limiter(key_func=get_remote_address)

RUN_ID_RE = re.compile(r"^[0-9A-Za-z]{10,80}$")
PHOTO_RE = re.compile(r"^data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)$")


class PackDeployRequest(BaseModel):
    subscription_id: str
    location: str

    @field_validator("subscription_id")
    @classmethod
    def validate_subscription(cls, v: str) -> str:
        if not UUID_RE.match(v):
            raise ValueError("Invalid subscription_id")
        return v


@router.get("")
async def get_packs():
    """List the deployable AI agent packs and their supported regions."""
    return list_packs()


@router.post("/{pack_id}/deploy")
@limiter.limit("10/hour")
async def deploy_pack(
    pack_id: str,
    body: PackDeployRequest,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Create a background job that deploys an agent pack to Azure."""
    if not SAFE_ID.match(pack_id):
        raise HTTPException(status_code=400, detail="Invalid pack id")
    try:
        pack = load_pack(pack_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent pack '{pack_id}' not found.") from None
    if body.location not in pack["regions"]:
        raise HTTPException(status_code=400, detail=f"Region '{body.location}' is not supported for these agents.")

    management_token = await get_management_token(request)
    agent_token = await get_agent_token(request)
    if not management_token:
        raise HTTPException(status_code=401, detail="Azure authorization is required to deploy the agents.")

    resource_group = new_resource_group_name(pack_id)
    job = job_store.create_job(
        demo_id=pack_id,
        workspace_name=resource_group,
        user_id=get_user_id(token),
        scenario_id=SCENARIO_ID,
        user_email=get_user_email(token),
    )
    task = asyncio.create_task(
        run_pack_job(
            job_id=job.job_id,
            management_token=management_token,
            agent_token=agent_token,
            pack=pack,
            subscription_id=body.subscription_id,
            resource_group=resource_group,
            location=body.location,
        )
    )
    job_store.set_task(job.job_id, task)
    return {"job_id": job.job_id, "resource_group": resource_group}


@router.delete("/jobs/{job_id}/resources")
@limiter.limit("10/hour")
async def delete_pack_resources(
    job_id: str,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Delete the resource group an agent pack deployment created."""
    if not UUID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    job = job_store.get_job(job_id)
    if not job or not _owns_job(job, get_user_id(token)) or job.scenario_id != SCENARIO_ID:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("pending", "running"):
        raise HTTPException(status_code=409, detail="Cancel the running deployment before deleting its resources.")
    az = job.azure_resources or {}
    subscription_id, resource_group = az.get("subscriptionId"), az.get("resourceGroup")
    if not (subscription_id and resource_group):
        raise HTTPException(status_code=400, detail="This deployment has no Azure resources to delete.")

    client = AzureClient(await get_management_token(request))
    try:
        deleted = await client.delete_resource_group(subscription_id, resource_group)
    except AzureError as e:
        if e.status == 403:
            raise HTTPException(status_code=403, detail="You don't have permission to delete this resource group.") from None
        raise HTTPException(status_code=502, detail=f"Failed to delete resource group: {e.detail[:200]}") from None
    finally:
        await client.close()
    job_store.set_azure_resources(job_id, None)
    return {"status": "deleting" if deleted else "already_deleted", "resourceGroup": resource_group}


# ── After the deploy: incident workflow, plant system, evaluations ──────────


class IncidentRequest(BaseModel):
    line: str = Field(pattern=r"^Line-[A-E]$")
    shift: Literal["night", "day", "evening"]
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    photo: str = ""

    @field_validator("photo")
    @classmethod
    def validate_photo(cls, v: str) -> str:
        if not v:
            return v
        match = PHOTO_RE.match(v)
        if not match:
            raise ValueError("The photo must be a PNG or JPEG data URL")
        try:
            size = len(base64.b64decode(match.group(2), validate=True))
        except (binascii.Error, ValueError):
            raise ValueError("The photo is not valid base64") from None
        if size > INCIDENT_PHOTO_MAX_BYTES:
            raise ValueError(f"The photo must be under {INCIDENT_PHOTO_MAX_BYTES // (1024 * 1024)} MB")
        return v


class DecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=500)


def _deployed_pack(job_id: str, token: str) -> tuple[dict, dict]:
    """The pack and Azure resources of a completed agent pack job the caller owns."""
    if not UUID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    job = job_store.get_job(job_id)
    if not job or not _owns_job(job, get_user_id(token)) or job.scenario_id != SCENARIO_ID:
        raise HTTPException(status_code=404, detail="Job not found")
    azure = job.azure_resources or {}
    if job.status != "completed" or not azure.get("resourceGroup"):
        raise HTTPException(status_code=409, detail="These agents are not deployed (anymore).")
    try:
        pack = load_pack(job.demo_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Agent pack not found.") from None
    return pack, azure


def _check_run_id(incident_id: str) -> None:
    if not RUN_ID_RE.match(incident_id):
        raise HTTPException(status_code=400, detail="Invalid incident id")


def _http_error(e: Exception) -> HTTPException:
    if isinstance(e, AgentPackError):
        return HTTPException(status_code=409, detail=str(e))
    status = getattr(e, "status", 502)
    detail = getattr(e, "detail", str(e))[:300]
    if status in (401, 403):
        return HTTPException(status_code=403, detail=f"Azure denied the request: {detail}")
    if status == 404:
        return HTTPException(status_code=404, detail="Not found - the resources may have been deleted.")
    return HTTPException(status_code=502, detail=detail)


@router.post("/jobs/{job_id}/incidents")
@limiter.limit("20/hour")
async def create_incident(job_id: str, body: IncidentRequest, request: Request, token: str = Depends(get_user_token)):
    """Start the multi-agent incident workflow (a Logic App in the user's resource group)."""
    _, azure = _deployed_pack(job_id, token)
    client = AzureClient(await get_management_token(request))
    try:
        incident_id = await start_incident(client, azure, body.line, body.shift, body.date, body.photo)
    except (AgentPackError, AzureError) as e:
        raise _http_error(e) from None
    finally:
        await client.close()
    return {"incidentId": incident_id}


@router.get("/jobs/{job_id}/incidents/{incident_id}")
async def get_incident(job_id: str, incident_id: str, request: Request, token: str = Depends(get_user_token)):
    """Live status of an incident run: steps, outputs, pending approval, final report."""
    pack, azure = _deployed_pack(job_id, token)
    _check_run_id(incident_id)
    client = AzureClient(await get_management_token(request))
    try:
        return await incident_status(client, azure, pack, incident_id)
    except (AgentPackError, AzureError) as e:
        raise _http_error(e) from None
    finally:
        await client.close()


@router.post("/jobs/{job_id}/incidents/{incident_id}/decision")
@limiter.limit("30/hour")
async def decide_incident(
    job_id: str, incident_id: str, body: DecisionRequest, request: Request, token: str = Depends(get_user_token)
):
    """Approve or reject the work order the incident workflow is waiting on."""
    pack, azure = _deployed_pack(job_id, token)
    _check_run_id(incident_id)
    client = AzureClient(await get_management_token(request))
    try:
        await record_decision(
            client, azure, pack, incident_id, body.decision, get_user_email(token) or "presenter", body.comment,
        )
    except (AgentPackError, AzureError) as e:
        raise _http_error(e) from None
    finally:
        await client.close()
    return {"status": body.decision}


@router.get("/jobs/{job_id}/board")
async def get_board(job_id: str, request: Request, token: str = Depends(get_user_token)):
    """Work orders and quality holds the agents created in the simulated plant system."""
    _, azure = _deployed_pack(job_id, token)
    client = AzureClient(await get_management_token(request))
    try:
        return await plant_board(client, azure)
    except (AgentPackError, AzureError) as e:
        raise _http_error(e) from None
    finally:
        await client.close()


@router.get("/jobs/{job_id}/evaluations")
async def get_evaluations(job_id: str, request: Request, token: str = Depends(get_user_token)):
    """Scores of the agents' latest evaluation runs (Foundry built-in evaluators)."""
    pack, azure = _deployed_pack(job_id, token)
    if not azure.get("evaluations"):
        return []
    client = FoundryProjectClient(azure["projectEndpoint"], await get_agent_token(request))
    try:
        return await evaluation_results(client, pack, azure)
    except FoundryProjectError as e:
        raise _http_error(e) from None
    finally:
        await client.close()


@router.post("/jobs/{job_id}/evaluations")
@limiter.limit("10/hour")
async def run_evaluations(job_id: str, request: Request, token: str = Depends(get_user_token)):
    """Run the agents' test sets (the first run creates the evaluation definitions)."""
    pack, azure = _deployed_pack(job_id, token)
    if not pack.get("evaluations"):
        raise HTTPException(status_code=400, detail="This agent pack has no evaluations.")
    client = FoundryProjectClient(azure["projectEndpoint"], await get_agent_token(request))
    try:
        runs = await start_evaluations(client, pack, azure["model"], azure.get("evaluations"))
    except FoundryProjectError as e:
        raise _http_error(e) from None
    finally:
        await client.close()
    job_store.set_azure_resources(job_id, {**azure, "evaluations": runs})
    return {"started": len(runs)}
