"""Background job runner — wraps deploy_demo() and updates JobStore."""

from __future__ import annotations

import json
import logging

from app.deployer import deploy_demo, load_manifest, load_scenario, DEMOS_DIR
from app.azure_client import AzureClient
from app.fabric_client import FabricClient
from app.job_store import job_store

logger = logging.getLogger(__name__)


def _resolve_placeholders(items: list[dict], demo_id: str) -> list[dict]:
    """Replace {industry} placeholder in item names/references with demo_id.
    Hyphens in demo_id are converted to underscores so names are valid Fabric identifiers.
    """
    safe_id = demo_id.replace("-", "_")
    resolved = []
    for item in items:
        new_item = dict(item)
        for key in ("name", "parentEventhouse", "parentLakehouse"):
            if key in new_item and isinstance(new_item[key], str):
                new_item[key] = new_item[key].replace("{industry}", safe_id)
        resolved.append(new_item)
    return resolved


def _find_rti_csv(demo_id: str, table_name: str) -> str:
    """Return the most relevant CSV filename for RTI ingestion.

    Preference order:
    1. A CSV whose name matches the snake_case of the kqlConfig tableName
    2. The largest CSV in the demo's data/ folder (most rows)
    3. Empty string if no CSVs found
    """
    data_dir = DEMOS_DIR / demo_id / "data"
    if not data_dir.exists():
        return ""
    csvs = list(data_dir.glob("*.csv"))
    if not csvs:
        return ""
    # Try snake_case match of tableName (e.g. "SensorReadings" → "sensor_readings.csv")
    if table_name:
        snake = "".join(
            f"_{c.lower()}" if c.isupper() and i > 0 else c.lower()
            for i, c in enumerate(table_name)
        ) + ".csv"
        for csv in csvs:
            if csv.name == snake:
                return csv.name
    # Fall back to largest file
    return max(csvs, key=lambda f: f.stat().st_size).name


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
    sql_server_name: str | None = None,
    search_token: str | None = None,
    agent_token: str | None = None,
    kusto_token: str | None = None,
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
                scenario_template_items = sc.get("fabricItemTemplate", [])
                non_shortcut_items = [i for i in scenario_template_items if i["type"] != "Shortcut"]

                if non_shortcut_items:
                    # Scenario defines its own full item set (e.g. Real-Time Intelligence
                    # or the ML scenarios). Use the scenario items directly — do NOT merge
                    # with the demo's lakehouse manifest. Read per-demo kqlConfig from
                    # manifest.custom.json and inject as extra variables (empty/no-op for
                    # non-RTI scenarios).
                    kql_config: dict = {}
                    custom_path = DEMOS_DIR / demo_id / "manifest.custom.json"
                    if custom_path.exists():
                        try:
                            custom_data = json.loads(custom_path.read_text(encoding="utf-8"))
                            for sc_entry in custom_data.get("scenarios", []):
                                if sc_entry.get("id") == scenario_id:
                                    kql_config = sc_entry.get("kqlConfig", {})
                                    break
                        except Exception:
                            pass
                    manifest_override = {
                        "id": demo_id,
                        "title": sc.get("title", scenario_id),
                        "fabricItems": _resolve_placeholders(scenario_template_items, demo_id),
                        "extraNbVars": {
                            "RTI_TABLE_NAME": kql_config.get("tableName", ""),
                            "RTI_CSV_FILENAME": _find_rti_csv(demo_id, kql_config.get("tableName", "")),
                            "RTI_TIMESTAMP_COLUMN": kql_config.get("timestampColumn", ""),
                            "RTI_SIGNAL_COLUMN": kql_config.get("signalColumn", ""),
                            "RTI_GROUPBY_COLUMN": kql_config.get("groupByColumn", ""),
                        },
                    }
                else:
                    # Scenario only injects Shortcuts (e.g. data-virtualization-batch).
                    # Merge shortcut additions in front of the demo's existing item list so
                    # the ADLS connection is ready before notebooks run.
                    demo_manifest = load_manifest(demo_id)
                    manifest_override = {
                        "id": demo_id,
                        "title": sc.get("title", scenario_id),
                        "fabricItems": _resolve_placeholders(scenario_template_items, demo_id) + demo_manifest.get("fabricItems", []),
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
            sql_server_name=sql_server_name,
            search_token=search_token,
            agent_token=agent_token,
            kusto_token=kusto_token,
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
