"""Apps & AI endpoints - catalog, client IP, deploy, and resource cleanup."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.apps_ai import (
    SCENARIO_ID,
    client_ip_from_headers,
    get_app,
    list_apps,
    load_catalog,
    new_resource_group_name,
    normalize_ip_ranges,
    run_app_job,
)
from app.auth import get_management_token, get_user_email, get_user_id, get_user_token
from app.azure_client import AzureClient, AzureError
from app.job_store import job_store
from app.models import SAFE_ID, UUID_RE
from app.routers.jobs import _owns_job

router = APIRouter(prefix="/api/apps", tags=["apps"])
limiter = Limiter(key_func=get_remote_address)


class AppDeployRequest(BaseModel):
    subscription_id: str
    location: str
    public_access: bool = False
    allowed_ip_ranges: list[str] = []

    @field_validator("subscription_id")
    @classmethod
    def validate_subscription(cls, v: str) -> str:
        if not UUID_RE.match(v):
            raise ValueError("Invalid subscription_id")
        return v


@router.get("")
async def get_apps():
    """List the deployable Apps & AI demos and supported regions."""
    return list_apps()


@router.get("/client-ip")
async def get_client_ip(request: Request):
    """The caller's public IPv4 (as seen by the gallery), to pre-fill the allowlist."""
    return {"ip": client_ip_from_headers(request.headers)}


@router.post("/{app_id}/deploy")
@limiter.limit("10/hour")
async def deploy_app(
    app_id: str,
    body: AppDeployRequest,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Create a background job that deploys an Apps & AI demo to Azure."""
    if not SAFE_ID.match(app_id):
        raise HTTPException(status_code=400, detail="Invalid app id")
    app = get_app(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"App '{app_id}' not found.")
    if body.location not in load_catalog()["regions"]:
        raise HTTPException(status_code=400, detail=f"Region '{body.location}' is not supported for this app.")
    if body.public_access:
        ranges: list[str] = []
    else:
        try:
            ranges = normalize_ip_ranges(body.allowed_ip_ranges)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        if not ranges:
            raise HTTPException(
                status_code=400,
                detail="Add at least one public IPv4 address that may open the app, or choose public access.",
            )

    management_token = await get_management_token(request)
    if not management_token:
        raise HTTPException(status_code=401, detail="Azure authorization is required to deploy this app.")

    resource_group = new_resource_group_name(app_id)
    job = job_store.create_job(
        demo_id=app_id,
        workspace_name=resource_group,
        user_id=get_user_id(token),
        scenario_id=SCENARIO_ID,
        user_email=get_user_email(token),
    )

    task = asyncio.create_task(
        run_app_job(
            job_id=job.job_id,
            management_token=management_token,
            app=app,
            subscription_id=body.subscription_id,
            resource_group=resource_group,
            location=body.location,
            allowed_ip_ranges=ranges,
        )
    )
    job_store.set_task(job.job_id, task)
    return {"job_id": job.job_id, "resource_group": resource_group}


@router.delete("/jobs/{job_id}/resources")
@limiter.limit("10/hour")
async def delete_app_resources(
    job_id: str,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Delete the resource group an Apps & AI deployment created."""
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
