"""AI agent pack endpoints - catalog, deploy, and resource cleanup."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.agent_packs import (
    SCENARIO_ID,
    list_packs,
    load_pack,
    new_resource_group_name,
    run_pack_job,
)
from app.auth import (
    get_agent_token,
    get_management_token,
    get_user_email,
    get_user_id,
    get_user_token,
)
from app.azure_client import AzureClient, AzureError
from app.job_store import job_store
from app.models import SAFE_ID, UUID_RE
from app.routers.jobs import _owns_job

router = APIRouter(prefix="/api/agent-packs", tags=["agent-packs"])
limiter = Limiter(key_func=get_remote_address)


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
