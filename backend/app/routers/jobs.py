"""Jobs endpoint — persistent deployment jobs with SSE streaming."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from app.auth import get_user_token, get_storage_token, get_user_id
from app.fabric_client import FabricClient
from app.job_runner import run_job
from app.job_store import job_store
from app.models import DeployRequest, SAFE_ID, UUID_RE

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
limiter = Limiter(key_func=get_remote_address)


@router.post("")
@limiter.limit("20/hour")
async def create_job(
    body: DeployRequest,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Create a deployment job — runs in background, returns job_id immediately."""
    if not SAFE_ID.match(body.demo_id):
        raise HTTPException(status_code=400, detail="Invalid demo_id")

    storage_tok = request.headers.get("x-storage-token", "")
    if not storage_tok:
        storage_tok = await get_storage_token(request)

    user_id = get_user_id(token)
    client = FabricClient(token, storage_token=storage_tok)

    # Auto-discover capacity before launching task (fail fast)
    cap_id = body.capacity_id
    if not cap_id and not body.workspace_id:
        try:
            workspaces = await client.list_workspaces()
            for ws in workspaces:
                if ws.get("capacityId"):
                    cap_id = ws["capacityId"]
                    break
        except Exception:
            pass
        if not cap_id:
            await client.close()
            raise HTTPException(
                status_code=400,
                detail="No Fabric capacity found. You need at least one active capacity (F2+, Trial, or PPU).",
            )

    workspace_name = body.workspace_name or body.demo_id
    job = job_store.create_job(
        demo_id=body.demo_id,
        workspace_name=workspace_name,
        user_id=user_id,
    )

    asyncio.create_task(
        run_job(
            job_id=job.job_id,
            client=client,
            demo_id=body.demo_id,
            workspace_name=workspace_name,
            workspace_id=body.workspace_id,
            capacity_id=cap_id,
        )
    )

    return {"job_id": job.job_id}


@router.get("")
@limiter.limit("60/hour")
async def list_jobs(
    request: Request,
    token: str = Depends(get_user_token),
):
    """List all deployment jobs for the current user."""
    user_id = get_user_id(token)
    return job_store.list_jobs(user_id)


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    token: str = Depends(get_user_token),
):
    """Get full snapshot of a single job."""
    if not UUID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Verify user owns this job
    user_id = get_user_id(token)
    if job.user_id != user_id and job.user_id != "dev-user":
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_detail()


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: str,
    request: Request,
    token: str = Depends(get_user_token),
):
    """SSE stream — replays past events then tails live updates."""
    if not UUID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    user_id = get_user_id(token)
    if job.user_id != user_id and job.user_id != "dev-user":
        raise HTTPException(status_code=404, detail="Job not found")

    queue = job_store.subscribe(job_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        try:
            # Phase 1: Replay all past events
            past_events = job_store.get_events(job_id)
            for evt in past_events:
                yield {
                    "event": evt["event"],
                    "data": json.dumps(evt["data"]) if not isinstance(evt["data"], str) else evt["data"],
                }

            # If job is already terminal, we're done after replay
            current = job_store.get_job(job_id)
            if current and current.status in ("completed", "failed"):
                return

            # Phase 2: Tail live updates from queue
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield {"event": "ping", "data": ""}
                    continue

                if evt.get("event") == "_done":
                    break

                yield {
                    "event": evt["event"],
                    "data": json.dumps(evt["data"]) if not isinstance(evt["data"], str) else evt["data"],
                }
        except asyncio.CancelledError:
            pass
        finally:
            job_store.unsubscribe(job_id, queue)

    return EventSourceResponse(event_generator())


@router.delete("/{job_id}/workspace")
@limiter.limit("10/hour")
async def delete_job_workspace(
    job_id: str,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Delete the workspace created by a job."""
    if not UUID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    user_id = get_user_id(token)
    if job.user_id != user_id and job.user_id != "dev-user":
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.workspace_id:
        raise HTTPException(status_code=400, detail="No workspace to delete")
    if not UUID_RE.match(job.workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace_id")

    client = FabricClient(token)
    try:
        await client.delete_workspace(job.workspace_id)
        return {"status": "deleted", "workspaceId": job.workspace_id}
    except Exception as e:
        from app.fabric_client import FabricError
        if isinstance(e, FabricError):
            if e.status == 404:
                return {"status": "already_deleted", "workspaceId": job.workspace_id}
            elif e.status == 403:
                raise HTTPException(status_code=403, detail="Cannot delete workspace: you need Owner permissions.")
        raise HTTPException(status_code=500, detail=f"Failed to delete workspace: {str(e)[:200]}")
    finally:
        await client.close()
