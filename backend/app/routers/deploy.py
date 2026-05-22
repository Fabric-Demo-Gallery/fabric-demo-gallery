"""Deployment endpoint — streams progress via SSE (legacy, kept for backward compatibility)."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from app.auth import get_user_token, get_storage_token
from app.deployer import deploy_demo
from app.fabric_client import FabricClient
from app.models import DeployRequest, SAFE_ID, UUID_RE

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
    if not UUID_RE.match(workspace_id):
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
