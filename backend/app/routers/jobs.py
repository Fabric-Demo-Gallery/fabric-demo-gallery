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

    # Validate the demo + scenario actually exist (and that a mirroring scenario
    # ships its spec) BEFORE creating a job, so a typo or missing file returns a
    # clear 4xx now instead of a cryptic failure partway through the deploy.
    from app.deployer import load_manifest, load_scenario, DEMOS_DIR
    try:
        manifest = load_manifest(body.demo_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Demo '{body.demo_id}' not found.")

    resolved_items = manifest.get("fabricItems", [])
    if body.scenario_id:
        try:
            scenario = load_scenario(body.scenario_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Scenario '{body.scenario_id}' not found.")
        scenario_items = scenario.get("fabricItemTemplate", [])
        if scenario_items:
            resolved_items = scenario_items

    # The mirroring path is selected when the resolved manifest has a
    # MirroredDatabase item — it requires a per-sector mirroring.json spec.
    if any(i.get("type") == "MirroredDatabase" for i in resolved_items):
        if not (DEMOS_DIR / body.demo_id / "mirroring.json").exists():
            raise HTTPException(
                status_code=400,
                detail=f"Demo '{body.demo_id}' is missing the mirroring.json spec required for this scenario.",
            )

    # The Fabric + Foundry scenario provisions a Microsoft Foundry resource, so it
    # requires an Azure subscription + resource group (plus the management token).
    if body.scenario_id == "fabric-foundry-agent":
        if not (body.subscription_id and body.resource_group):
            raise HTTPException(
                status_code=400,
                detail="The Fabric + Foundry scenario requires an Azure subscription and resource group.",
            )

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
        except Exception as e:
            await client.close()
            detail = str(e)[:200]
            if "401" in detail or "Unauthorized" in detail:
                raise HTTPException(status_code=401, detail="Authentication expired. Please sign out and sign in again.")
            elif "403" in detail or "Forbidden" in detail:
                raise HTTPException(status_code=403, detail="You don't have permission to list workspaces. Contact your Fabric admin.")
            raise HTTPException(status_code=502, detail=f"Failed to connect to Fabric API: {detail}")
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
        scenario_id=body.scenario_id,
    )

    management_tok = request.headers.get("x-management-token", "")
    onelake_tok = request.headers.get("x-onelake-token", "")
    search_tok = request.headers.get("x-search-token", "")
    agent_tok = request.headers.get("x-agent-token", "")

    task = asyncio.create_task(
        run_job(
            job_id=job.job_id,
            client=client,
            demo_id=body.demo_id,
            workspace_name=workspace_name,
            workspace_id=body.workspace_id,
            capacity_id=cap_id,
            scenario_id=body.scenario_id,
            management_token=management_tok or None,
            onelake_token=onelake_tok or None,
            subscription_id=body.subscription_id,
            resource_group=body.resource_group,
            storage_account_name=body.storage_account_name,
            azure_location=body.azure_location or "eastus",
            create_resource_group=body.create_resource_group,
            sql_server_name=body.sql_server_name,
            search_token=search_tok or None,
            agent_token=agent_tok or None,
        )
    )
    job_store.set_task(job.job_id, task)

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


@router.delete("/{job_id}")
@limiter.limit("30/hour")
async def cancel_job(
    job_id: str,
    request: Request,
    token: str = Depends(get_user_token),
):
    """Cancel a running deployment job."""
    if not UUID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    user_id = get_user_id(token)
    if job.user_id != user_id and job.user_id != "dev-user":
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("completed", "failed", "cancelled"):
        return {"status": job.status, "message": "Job already finished"}
    cancelled = job_store.cancel_job(job_id)
    job_store.set_status(job_id, "cancelled")
    return {"status": "cancelled", "cancelled": cancelled}


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
        result: dict = {"status": "deleted", "workspaceId": job.workspace_id}
    except Exception as e:
        from app.fabric_client import FabricError
        if isinstance(e, FabricError):
            if e.status == 404:
                result = {"status": "already_deleted", "workspaceId": job.workspace_id}
            elif e.status == 403:
                raise HTTPException(status_code=403, detail="Cannot delete workspace: you need Owner permissions.")
            else:
                raise HTTPException(status_code=500, detail=f"Failed to delete workspace: {str(e)[:200]}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to delete workspace: {str(e)[:200]}")
    finally:
        await client.close()

    # Mirroring jobs also provisioned an Azure SQL server — clean it up too.
    az = job.azure_resources or {}
    if az.get("sqlServer") and az.get("subscriptionId") and az.get("resourceGroup"):
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
