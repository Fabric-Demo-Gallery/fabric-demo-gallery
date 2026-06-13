"""Deployment endpoint — streams progress via SSE."""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from app.auth import get_user_token, get_storage_token, get_management_token
from app.azure_client import AzureClient
from app.deployer import deploy_demo, load_scenario
from app.fabric_client import FabricClient
from app.models import DeployRequest, SAFE_ID, UUID_RE

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9 &_\-().]{1,100}$")
_SAFE_RG = re.compile(r"^[a-zA-Z0-9._\-()]{1,90}$")
_SAFE_STORAGE_ACCT = re.compile(r"^[a-z0-9]{3,24}$")

router = APIRouter(prefix="/api/deploy", tags=["deploy"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/{demo_id}")
@limiter.limit("20/hour")
async def start_deployment(
    demo_id: str,
    body: DeployRequest,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Start deploying a demo — returns an SSE stream with progress updates."""
    if not SAFE_ID.match(demo_id):
        raise HTTPException(status_code=400, detail="Invalid demo_id")
    # Get storage token from header or az CLI fallback
    storage_tok = request.headers.get("x-storage-token", "")
    if not storage_tok:
        storage_tok = await get_storage_token(request)
    client = FabricClient(token, storage_token=storage_tok)

    async def event_generator():
        try:
            # Auto-discover capacity if not provided
            cap_id = body.capacity_id
            if not cap_id and not body.workspace_id:
                workspaces = await client.list_workspaces()
                for ws in workspaces:
                    if ws.get("capacityId"):
                        cap_id = ws["capacityId"]
                        break
                if not cap_id:
                    yield {"event": "error", "data": json.dumps({"message": "No Fabric capacity found. You need at least one active capacity (F2+, Trial, or PPU) to deploy a demo."})}
                    return

            # Build AzureClient if management token + subscription provided
            mgmt_tok = request.headers.get("x-management-token", "")
            az_client: AzureClient | None = None
            if mgmt_tok and body.subscription_id:
                az_client = AzureClient(mgmt_tok)

            # Load scenario template if provided
            scenario_manifest: dict | None = None
            if body.scenario_id:
                try:
                    sc = load_scenario(body.scenario_id)
                    scenario_manifest = {
                        "id": body.scenario_id,
                        "title": sc.get("title", body.scenario_id),
                        "fabricItems": sc.get("fabricItemTemplate", []),
                    }
                except FileNotFoundError:
                    yield {"event": "error", "data": json.dumps({"message": f"Scenario '{body.scenario_id}' not found"})}
                    return

            async for event in deploy_demo(
                client=client,
                demo_id=demo_id,
                workspace_name=body.workspace_name,
                workspace_id=body.workspace_id,
                capacity_id=cap_id,
                manifest_override=scenario_manifest,
                azure_client=az_client,
                subscription_id=body.subscription_id,
                resource_group=body.resource_group,
                storage_account_name=body.storage_account_name,
                azure_location=body.azure_location or "eastus",
                create_resource_group=body.create_resource_group,
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }
        except Exception as e:
            # Catch any unhandled exception and send it as an SSE error event
            yield {"event": "error", "data": json.dumps({"message": f"Server error: {type(e).__name__}: {str(e)[:300]}"})}
        finally:
            await client.close()
            if az_client:
                await az_client.close()

    return EventSourceResponse(event_generator())


class CustomDeployRequest(BaseModel):
    """Deploy an inline manifest (custom deployment wizard)."""
    manifest: dict
    workspace_name: str | None = None
    workspace_id: str | None = None
    capacity_id: str | None = None
    subscription_id: str | None = None
    resource_group: str | None = None
    storage_account_name: str | None = None
    azure_location: str | None = None
    create_resource_group: bool = False

    @field_validator("workspace_name")
    @classmethod
    def validate_ws_name(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_NAME.match(v):
            raise ValueError("Workspace name contains invalid characters")
        return v

    @field_validator("workspace_id", "capacity_id", "subscription_id")
    @classmethod
    def validate_uuids(cls, v: str | None) -> str | None:
        if v is not None and not UUID_RE.match(v):
            raise ValueError("Invalid UUID format")
        return v

    @field_validator("resource_group")
    @classmethod
    def validate_rg(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_RG.match(v):
            raise ValueError("Invalid resource group name")
        return v

    @field_validator("storage_account_name")
    @classmethod
    def validate_acct(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_STORAGE_ACCT.match(v):
            raise ValueError("Storage account name must be 3-24 lowercase alphanumeric characters")
        return v


@router.post("/custom")
@limiter.limit("5/hour")
async def start_custom_deployment(
    body: CustomDeployRequest,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Deploy an inline manifest (generated by the custom deployment wizard)."""
    storage_tok = request.headers.get("x-storage-token", "")
    if not storage_tok:
        storage_tok = await get_storage_token(request)
    client = FabricClient(token, storage_token=storage_tok)

    async def event_generator():
        az_client: AzureClient | None = None
        try:
            cap_id = body.capacity_id
            if not cap_id and not body.workspace_id:
                workspaces = await client.list_workspaces()
                for ws in workspaces:
                    if ws.get("capacityId"):
                        cap_id = ws["capacityId"]
                        break
                if not cap_id:
                    yield {"event": "error", "data": json.dumps({"message": "No Fabric capacity found."})}
                    return

            mgmt_tok = request.headers.get("x-management-token", "")
            if mgmt_tok and body.subscription_id:
                az_client = AzureClient(mgmt_tok)

            # Use a synthetic demo_id from the manifest
            demo_id = body.manifest.get("id", "custom")

            async for event in deploy_demo(
                client=client,
                demo_id=demo_id,
                workspace_name=body.workspace_name,
                workspace_id=body.workspace_id,
                capacity_id=cap_id,
                manifest_override=body.manifest,
                azure_client=az_client,
                subscription_id=body.subscription_id,
                resource_group=body.resource_group,
                storage_account_name=body.storage_account_name,
                azure_location=body.azure_location or "eastus",
                create_resource_group=body.create_resource_group,
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": f"Server error: {type(e).__name__}: {str(e)[:300]}"})}
        finally:
            await client.close()
            if az_client:
                await az_client.close()

    return EventSourceResponse(event_generator())


@router.delete("/{workspace_id}")
@limiter.limit("10/hour")
async def teardown_deployment(
    workspace_id: str,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Delete a workspace and all its items (teardown a deployed demo).

    If the deployment also provisioned an Azure SQL server (mirroring scenario)
    and the request carries an x-management-token header, the server is
    deleted too — the job store is searched by workspace_id for the metadata.
    """
    if not UUID_RE.match(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace_id")
    client = FabricClient(token)
    try:
        await client.delete_workspace(workspace_id)
        result: dict = {"status": "deleted", "workspaceId": workspace_id}
    except Exception as e:
        from app.fabric_client import FabricError
        if isinstance(e, FabricError):
            if e.status == 404:
                result = {"status": "already_deleted", "workspaceId": workspace_id, "message": "Workspace was already deleted or not found."}
            elif e.status == 403:
                raise HTTPException(status_code=403, detail="Cannot delete workspace: you need Owner permissions on this workspace.")
            else:
                raise HTTPException(status_code=500, detail=f"Failed to delete workspace: {str(e)[:200]}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to delete workspace: {str(e)[:200]}")
    finally:
        await client.close()

    # Mirroring deployments: also remove the provisioned Azure SQL server.
    from app.job_store import job_store
    az = None
    for job in job_store._jobs.values():
        if job.workspace_id == workspace_id and job.azure_resources:
            az = job.azure_resources
            break
    if az and az.get("sqlServer") and az.get("subscriptionId") and az.get("resourceGroup"):
        mgmt_token = request.headers.get("x-management-token", "")
        if mgmt_token:
            from app.azure_client import AzureClient, AzureError
            az_client = AzureClient(mgmt_token)
            try:
                deleted = await az_client.delete_sql_server(
                    az["subscriptionId"], az["resourceGroup"], az["sqlServer"]
                )
                result["sqlServer"] = "deleted" if deleted else "already_deleted"
            except AzureError as e:
                result["sqlServer"] = f"delete_failed: {e.detail[:150]}"
            finally:
                await az_client.close()
        else:
            result["sqlServer"] = "skipped_no_management_token"

    return result
