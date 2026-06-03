"""Background job runner — wraps deploy_demo() and updates JobStore."""

from __future__ import annotations

import json
import logging

from app.deployer import deploy_demo, load_manifest, load_scenario
from app.azure_client import AzureClient
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
    scenario_id: str | None = None,
    management_token: str | None = None,
    onelake_token: str | None = None,
    subscription_id: str | None = None,
    resource_group: str | None = None,
    storage_account_name: str | None = None,
    azure_location: str = "eastus",
    create_resource_group: bool = False,
) -> None:
    """Run a deployment job in the background, updating the job store with events."""
    try:
        # Build optional AzureClient
        az_client: AzureClient | None = None
        if management_token and subscription_id:
            az_client = AzureClient(management_token)

        # Resolve scenario manifest override
        manifest_override: dict | None = None
        if scenario_id:
            try:
                sc = load_scenario(scenario_id)
                demo_manifest = load_manifest(demo_id)
                # Check if scenario has structural additions (e.g. Shortcuts for data-virtualization)
                scenario_shortcut_items = [
                    i for i in sc.get("fabricItemTemplate", []) if i["type"] == "Shortcut"
                ]
                if scenario_shortcut_items:
                    # Shortcut scenario: add shortcuts before demo's standard items
                    manifest_override = {
                        "id": demo_id,
                        "title": sc.get("title", scenario_id),
                        "fabricItems": scenario_shortcut_items + demo_manifest.get("fabricItems", []),
                    }
                else:
                    # ML/other scenario: use scenario's own fabricItemTemplate
                    # (has correct notebook paths like notebooks/ml/...)
                    manifest_override = {
                        "id": demo_id,
                        "title": sc.get("title", scenario_id),
                        "fabricItems": sc.get("fabricItemTemplate", []),
                    }
            except FileNotFoundError:
                job_store.emit_event(job_id, {
                    "event": "error",
                    "data": {"message": f"Scenario '{scenario_id}' not found"},
                })
                job_store.set_status(job_id, "failed")
                return

        async for event in deploy_demo(
            client=client,
            demo_id=demo_id,
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            capacity_id=capacity_id,
            manifest_override=manifest_override,
            scenario_id=scenario_id,
            azure_client=az_client,
            onelake_token=onelake_token,
            subscription_id=subscription_id,
            resource_group=resource_group,
            storage_account_name=storage_account_name,
            azure_location=azure_location,
            create_resource_group=create_resource_group,
        ):
            job_store.emit_event(job_id, event)

        # Generator exhausted — mark completed or failed based on whether an error was emitted
        job = job_store.get_job(job_id)
        if job:
            if job.error:
                job_store.set_status(job_id, "failed")
            elif job.status not in ("failed", "cancelled"):
                job_store.set_status(job_id, "completed")

    except asyncio.CancelledError:
        logger.info("Job %s was cancelled", job_id)
        job_store.emit_event(job_id, {
            "event": "error",
            "data": {"message": "Deployment cancelled by user."},
        })
        job_store.set_status(job_id, "cancelled")

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
