"""Deployment endpoint — streams progress via SSE."""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from app.auth import get_user_token, get_storage_token
from app.deployer import deploy_demo
from app.fabric_client import FabricClient

router = APIRouter(prefix="/api/deploy", tags=["deploy"])
limiter = Limiter(key_func=get_remote_address)

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9 &_\-().]{1,100}$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class DeployRequest(BaseModel):
    demo_id: str
    workspace_name: str | None = None
    workspace_id: str | None = None
    capacity_id: str | None = None

    @field_validator("demo_id")
    @classmethod
    def validate_demo_id(cls, v: str) -> str:
        if not _SAFE_ID.match(v):
            raise ValueError("Invalid demo_id")
        return v

    @field_validator("workspace_name")
    @classmethod
    def validate_workspace_name(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_NAME.match(v):
            raise ValueError("Workspace name contains invalid characters")
        return v

    @field_validator("workspace_id", "capacity_id")
    @classmethod
    def validate_uuids(cls, v: str | None) -> str | None:
        if v is not None and not _UUID.match(v):
            raise ValueError("Invalid UUID format")
        return v


@router.post("/{demo_id}")
@limiter.limit("5/hour")
async def start_deployment(
    demo_id: str,
    body: DeployRequest,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Start deploying a demo — returns an SSE stream with progress updates."""
    if not _SAFE_ID.match(demo_id):
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

            async for event in deploy_demo(
                client=client,
                demo_id=demo_id,
                workspace_name=body.workspace_name,
                workspace_id=body.workspace_id,
                capacity_id=cap_id,
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

    return EventSourceResponse(event_generator())


@router.delete("/{workspace_id}")
@limiter.limit("10/hour")
async def teardown_deployment(
    workspace_id: str,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Delete a workspace and all its items (teardown a deployed demo)."""
    if not _UUID.match(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace_id")
    client = FabricClient(token)
    try:
        await client.delete_workspace(workspace_id)
        return {"status": "deleted", "workspaceId": workspace_id}
    except Exception as e:
        from app.fabric_client import FabricError
        if isinstance(e, FabricError):
            if e.status == 404:
                return {"status": "already_deleted", "workspaceId": workspace_id, "message": "Workspace was already deleted or not found."}
            elif e.status == 403:
                raise HTTPException(status_code=403, detail="Cannot delete workspace: you need Owner permissions on this workspace.")
        raise HTTPException(status_code=500, detail=f"Failed to delete workspace: {str(e)[:200]}")
    finally:
        await client.close()
