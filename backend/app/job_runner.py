"""Background job runner — wraps deploy_demo() and updates JobStore."""

from __future__ import annotations

import json
import logging

from app.deployer import deploy_demo
from app.fabric_client import FabricClient
from app.job_store import job_store

logger = logging.getLogger(__name__)


async def run_job(
    job_id: str,
    client: FabricClient,
    demo_id: str,
    workspace_name: str | None,
    workspace_id: str | None,
    capacity_id: str | None,
) -> None:
    """Run a deployment job in the background, updating the job store with events."""
    try:
        async for event in deploy_demo(
            client=client,
            demo_id=demo_id,
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            capacity_id=capacity_id,
        ):
            job_store.emit_event(job_id, event)

        # Generator exhausted — mark completed or failed based on whether an error was emitted
        job = job_store.get_job(job_id)
        if job:
            if job.error:
                job_store.set_status(job_id, "failed")
            elif job.status != "failed":
                job_store.set_status(job_id, "completed")

    except Exception as e:
        logger.exception("Job %s failed with unexpected error", job_id)
        error_event = {
            "event": "error",
            "data": {
                "message": f"Server error: {type(e).__name__}: {str(e)[:300]}",
            },
        }
        job_store.emit_event(job_id, error_event)
        job_store.set_status(job_id, "failed")
    finally:
        await client.close()

        # Push a sentinel so stream subscribers know the job is done
        job = job_store.get_job(job_id)
        if job:
            sentinel = {"event": "_done", "data": {}}
            for queue in list(job._subscribers):
                try:
                    queue.put_nowait(sentinel)
                except Exception:
                    pass
