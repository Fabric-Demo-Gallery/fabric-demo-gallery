"""Fabric REST API client — wraps workspace, item, and job operations."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FABRIC_API = "https://api.fabric.microsoft.com/v1"
ONELAKE_API = "https://onelake.dfs.fabric.microsoft.com"


class FabricError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Fabric API {status}: {detail}")


class FabricClient:
    """Async client for Fabric REST APIs using a delegated user token."""

    def __init__(self, token: str, storage_token: str | None = None):
        self._token = token
        self._storage_token = storage_token or token
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        self._storage_client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self._storage_token}",
            },
            timeout=120.0,
        )

    async def close(self):
        await self._client.aclose()
        await self._storage_client.aclose()

    # ── helpers ──────────────────────────────────────────────────────────

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        resp = await self._client.request(method, url, **kwargs)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning("Rate limited, retrying after %ds", retry_after)
            await asyncio.sleep(retry_after)
            resp = await self._client.request(method, url, **kwargs)
            if resp.status_code == 429:
                raise FabricError(429, "Fabric API rate-limited after retry. Wait a minute and try again.")
        if resp.status_code >= 400:
            detail = resp.text[:500]
            # Try to extract a human-readable message from JSON error
            try:
                err = resp.json()
                msg = err.get("error", {}).get("message") or err.get("message") or detail
                detail = msg[:500]
            except Exception:
                pass
            raise FabricError(resp.status_code, detail)
        return resp

    async def _poll_lro(self, location: str, timeout: int = 300) -> dict | None:
        """Poll a long-running operation until completion."""
        start = time.time()
        while time.time() - start < timeout:
            resp = await self._client.get(location)
            if resp.status_code == 200:
                body = resp.json()
                status = body.get("status", "").lower()
                if status in ("succeeded", "completed"):
                    return body
                if status in ("failed", "cancelled", "deduped"):
                    # Extract human-readable error from LRO result
                    err = body.get("error", {})
                    err_msg = err.get("message", json.dumps(body)[:300])
                    raise FabricError(500, f"Operation {status}: {err_msg}")
                logger.debug("LRO status: %s", status)
            elif resp.status_code == 401:
                raise FabricError(401, "Authentication expired during operation. Sign out, sign back in, and retry.")
            elif resp.status_code == 404:
                raise FabricError(404, "Operation tracking lost. The item may have been created — check the workspace.")
            await asyncio.sleep(5)
        raise FabricError(504, f"Operation timed out after {timeout}s. The item may still be provisioning — check the workspace in Fabric portal.")

    # ── workspaces ───────────────────────────────────────────────────────

    async def list_workspaces(self) -> list[dict]:
        items = []
        url = f"{FABRIC_API}/workspaces"
        while url:
            resp = await self._request("GET", url)
            body = resp.json()
            items.extend(body.get("value", []))
            url = body.get("continuationUri")
        return items

    async def create_workspace(self, name: str, capacity_id: str | None = None) -> dict:
        body: dict[str, Any] = {"displayName": name}
        if capacity_id:
            body["capacityId"] = capacity_id
        resp = await self._request("POST", f"{FABRIC_API}/workspaces", json=body)
        return resp.json()

    async def list_capacities(self) -> list[dict]:
        """List available Fabric capacities, with Trial capacities first."""
        resp = await self._request("GET", f"{FABRIC_API}/capacities")
        body = resp.json()
        caps = body.get("value", [])
        result = []
        for c in caps:
            if c.get("state", "").lower() != "active":
                continue
            sku = c.get("sku", "")
            is_trial = sku.startswith("FT") or "trial" in c.get("displayName", "").lower()
            result.append({
                "id": c["id"],
                "displayName": c.get("displayName", ""),
                "sku": sku,
                "state": c.get("state", ""),
                "isTrial": is_trial,
            })
        # Sort: paid capacities first, then Trial
        result.sort(key=lambda x: (1 if x["isTrial"] else 0, x["displayName"]))
        return result

    async def get_workspace(self, workspace_id: str) -> dict:
        resp = await self._request("GET", f"{FABRIC_API}/workspaces/{workspace_id}")
        return resp.json()

    async def delete_workspace(self, workspace_id: str) -> None:
        await self._request("DELETE", f"{FABRIC_API}/workspaces/{workspace_id}")

    # ── items (generic) ──────────────────────────────────────────────────

    async def create_item(
        self,
        workspace_id: str,
        item_type: str,
        display_name: str,
        definition: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {"displayName": display_name, "type": item_type}
        if definition:
            body["definition"] = definition
        resp = await self._request(
            "POST", f"{FABRIC_API}/workspaces/{workspace_id}/items", json=body
        )
        # Handle 201 (created) or 202 (LRO)
        if resp.status_code == 202:
            location = resp.headers.get("Location")
            if location:
                await self._poll_lro(location)
            # LRO result doesn't always contain item details — find the item by name
            # Try with type filter first, then without
            for attempt in range(3):
                if attempt > 0:
                    await asyncio.sleep(2)
                items = await self.list_items(workspace_id, item_type)
                for item in items:
                    if item.get("displayName") == display_name:
                        logger.info("Found item '%s' (id=%s) on attempt %d", display_name, item.get("id"), attempt + 1)
                        return item
            # Try listing ALL items without type filter
            items = await self.list_items(workspace_id)
            for item in items:
                if item.get("displayName") == display_name:
                    logger.info("Found item '%s' via unfiltered listing", display_name)
                    return item
            logger.warning("Created item '%s' but couldn't find it in listing", display_name)
            raise FabricError(500, f"'{display_name}' was created but could not be located in the workspace. This is a Fabric API timing issue — retry the deployment.")
        return resp.json()

    async def delete_item(self, workspace_id: str, item_id: str) -> None:
        await self._request(
            "DELETE", f"{FABRIC_API}/workspaces/{workspace_id}/items/{item_id}"
        )

    async def list_items(self, workspace_id: str, item_type: str | None = None) -> list[dict]:
        url = f"{FABRIC_API}/workspaces/{workspace_id}/items"
        if item_type:
            url += f"?type={item_type}"
        items = []
        while url:
            resp = await self._request("GET", url)
            body = resp.json()
            items.extend(body.get("value", []))
            url = body.get("continuationUri")
        return items

    async def update_item_definition(
        self, workspace_id: str, item_id: str, definition: dict
    ) -> None:
        resp = await self._request(
            "POST",
            f"{FABRIC_API}/workspaces/{workspace_id}/items/{item_id}/updateDefinition",
            json={"definition": definition},
        )
        if resp.status_code == 202:
            location = resp.headers.get("Location")
            if location:
                await self._poll_lro(location)

    # ── lakehouses ───────────────────────────────────────────────────────

    async def create_lakehouse(self, workspace_id: str, name: str) -> dict:
        return await self.create_item(workspace_id, "Lakehouse", name)

    async def get_lakehouse(self, workspace_id: str, lakehouse_id: str) -> dict:
        resp = await self._request(
            "GET", f"{FABRIC_API}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
        )
        return resp.json()

    async def wait_for_sql_endpoint(
        self, workspace_id: str, lakehouse_id: str, timeout: int = 300
    ) -> str:
        """Wait until the SQL endpoint is provisioned and return the connection string."""
        start = time.time()
        while time.time() - start < timeout:
            lh = await self.get_lakehouse(workspace_id, lakehouse_id)
            props = lh.get("properties", {}).get("sqlEndpointProperties", {})
            if props.get("provisioningStatus", "").lower() == "success":
                return props["connectionString"]
            await asyncio.sleep(5)
        raise FabricError(504, "SQL endpoint provisioning timed out")

    # ── notebooks ────────────────────────────────────────────────────────

    async def create_notebook(
        self,
        workspace_id: str,
        name: str,
        ipynb_path: str | Path,
        lakehouse_id: str,
        lakehouse_name: str,
        variables: dict[str, str] | None = None,
    ) -> dict:
        """Create a notebook, then update its definition with content and lakehouse binding."""
        # Step 1: Create empty notebook
        item = await self.create_item(workspace_id, "Notebook", name)
        nb_id = item["id"]
        logger.info("Created empty notebook '%s' (%s), updating definition...", name, nb_id)

        # Step 2: Build Fabric .py notebook format from .ipynb
        ipynb_content = Path(ipynb_path).read_text(encoding="utf-8")
        # Substitute variables (e.g. {{EVENTHOUSE_URI}}, {{KQL_DATABASE_NAME}})
        if variables:
            for key, value in variables.items():
                ipynb_content = ipynb_content.replace(f"{{{{{key}}}}}", value)
        ipynb = json.loads(ipynb_content)

        py_lines = ["# Fabric notebook source", ""]

        # Add metadata with lakehouse binding
        metadata = {
            "dependencies": {
                "lakehouse": {
                    "default_lakehouse": lakehouse_id,
                    "default_lakehouse_name": lakehouse_name,
                    "default_lakehouse_workspace_id": workspace_id,
                    "known_lakehouses": [{"id": lakehouse_id}],
                }
            }
        }
        py_lines.append("# METADATA ********************")
        py_lines.append("")
        for line in json.dumps(metadata, indent=2).splitlines():
            py_lines.append(f"# META {line}")
        py_lines.append("")

        # Convert cells
        for cell in ipynb.get("cells", []):
            cell_type = cell.get("cell_type", "code")
            source = cell.get("source", [])
            if isinstance(source, list):
                source_text = "".join(source)
            else:
                source_text = source

            if cell_type == "markdown":
                py_lines.append("# MARKDOWN ********************")
                py_lines.append("")
                for line in source_text.splitlines():
                    py_lines.append(f"# {line}" if line.strip() else "#")
                py_lines.append("")
            else:
                py_lines.append("# CELL ********************")
                py_lines.append("")
                py_lines.append(source_text.rstrip())
                py_lines.append("")

        py_content = "\r\n".join(py_lines)
        encoded = base64.b64encode(py_content.encode()).decode()

        # Step 3: Update definition
        definition = {
            "parts": [
                {
                    "path": "notebook-content.py",
                    "payload": encoded,
                    "payloadType": "InlineBase64",
                }
            ]
        }
        await self.update_item_definition(workspace_id, nb_id, definition)
        return item

    async def run_notebook(
        self,
        workspace_id: str,
        notebook_id: str,
        lakehouse_id: str,
        lakehouse_name: str,
        timeout: int = 600,
    ) -> dict:
        """Execute a notebook and wait for completion."""
        body = {
            "executionData": {
                "configuration": {
                    "defaultLakehouse": {
                        "id": lakehouse_id,
                        "name": lakehouse_name,
                    }
                }
            }
        }
        resp = await self._request(
            "POST",
            f"{FABRIC_API}/workspaces/{workspace_id}/items/{notebook_id}/jobs/instances?jobType=RunNotebook",
            json=body,
        )
        location = resp.headers.get("Location")
        if not location:
            raise FabricError(500, "No Location header for notebook job")
        result = await self._poll_lro(location, timeout=timeout)
        return result or {}

    # ── OneLake file upload ──────────────────────────────────────────────

    async def upload_file_to_lakehouse(
        self,
        workspace_id: str,
        lakehouse_id: str,
        remote_path: str,
        local_path: str | Path,
    ) -> None:
        """Upload a file to lakehouse Files/ via OneLake DFS API (uses storage token)."""
        file_name = Path(local_path).name
        data = Path(local_path).read_bytes()
        base = f"{ONELAKE_API}/{workspace_id}/{lakehouse_id}/Files/{remote_path}"

        def _check(r, step):
            if r.status_code >= 400:
                if r.status_code == 403:
                    raise FabricError(403, f"Cannot upload '{file_name}': storage access denied. Ensure your account has OneLake write permissions.")
                elif r.status_code == 401:
                    raise FabricError(401, f"Cannot upload '{file_name}': storage token expired or invalid. Sign out and sign back in.")
                else:
                    raise FabricError(r.status_code, f"Upload '{file_name}' failed at {step}: {r.text[:200]}")

        r = await self._storage_client.put(f"{base}?resource=file", content=b"")
        _check(r, "create")
        r = await self._storage_client.patch(f"{base}?action=append&position=0", content=data)
        _check(r, "append")
        r = await self._storage_client.patch(f"{base}?action=flush&position={len(data)}")
        _check(r, "flush")

    # ── semantic model ───────────────────────────────────────────────────

    async def create_semantic_model(
        self, workspace_id: str, name: str, tmdl_definition: dict
    ) -> dict:
        return await self.create_item(workspace_id, "SemanticModel", name, tmdl_definition)

    async def refresh_semantic_model(
        self, workspace_id: str, model_id: str, timeout: int = 300
    ) -> None:
        """Trigger a semantic model refresh and wait for completion."""
        resp = await self._request(
            "POST",
            f"{FABRIC_API}/workspaces/{workspace_id}/semanticModels/{model_id}/refresh",
            json={"type": "full"},
        )
        if resp.status_code == 202:
            location = resp.headers.get("Location")
            if location:
                await self._poll_lro(location, timeout=timeout)

    # ── pipelines ────────────────────────────────────────────────────────

    async def create_pipeline(
        self, workspace_id: str, name: str, definition: dict | None = None
    ) -> dict:
        return await self.create_item(workspace_id, "DataPipeline", name, definition)

    # ── Eventhouse & KQL Database ────────────────────────────────────────

    async def create_eventhouse(self, workspace_id: str, name: str) -> dict:
        """Create an Eventhouse in the workspace."""
        url = f"{FABRIC_API}/workspaces/{workspace_id}/eventhouses"
        resp = await self._request("POST", url, json={"displayName": name})
        if resp.status_code == 201:
            return resp.json()
        if resp.status_code == 202:
            location = resp.headers.get("Location", "")
            if location:
                await self._poll_lro(location)
            # Eventhouse may take a moment — list to find it
            items = await self.list_items(workspace_id, "Eventhouse")
            for item in items:
                if item["displayName"] == name:
                    return item
            raise FabricError(404, f"Eventhouse '{name}' not found after creation")
        raise FabricError(resp.status_code, resp.text[:300])

    async def get_eventhouse(self, workspace_id: str, eventhouse_id: str) -> dict:
        """Get Eventhouse details including queryServiceUri and ingestionServiceUri."""
        url = f"{FABRIC_API}/workspaces/{workspace_id}/eventhouses/{eventhouse_id}"
        resp = await self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        raise FabricError(resp.status_code, resp.text[:300])

    async def create_kql_database(
        self, workspace_id: str, name: str, eventhouse_id: str
    ) -> dict:
        """Create a KQL Database within an Eventhouse."""
        url = f"{FABRIC_API}/workspaces/{workspace_id}/kqlDatabases"
        body = {
            "displayName": name,
            "creationPayload": {
                "databaseType": "ReadWrite",
                "parentEventhouseItemId": eventhouse_id,
            },
        }
        resp = await self._request("POST", url, json=body)
        if resp.status_code == 201:
            return resp.json()
        if resp.status_code == 202:
            location = resp.headers.get("Location", "")
            if location:
                await self._poll_lro(location)
            items = await self.list_items(workspace_id, "KQLDatabase")
            for item in items:
                if item["displayName"] == name:
                    return item
            raise FabricError(404, f"KQL Database '{name}' not found after creation")
        raise FabricError(resp.status_code, resp.text[:300])

    async def create_kql_dashboard(
        self, workspace_id: str, name: str, kql_database_id: str, eventhouse_uri: str, kql_database_name: str
    ) -> dict:
        """Create a Real-Time Dashboard (KQL Dashboard) with pre-built tiles."""
        import uuid

        ds_id = str(uuid.uuid4())
        page1_id = str(uuid.uuid4())
        page2_id = str(uuid.uuid4())
        page3_id = str(uuid.uuid4())

        def _tile(title, query, page_id, vis_type, x, y, w, h):
            t = {
                "id": str(uuid.uuid4()),
                "title": title,
                "query": query,
                "dataSourceId": ds_id,
                "pageId": page_id,
                "visualType": vis_type,
                "layout": {"x": x, "y": y, "width": w, "height": h},
                "usedParamVariables": [],
                "visualOptions": {},
            }
            if vis_type in ("bar", "line"):
                t["visualOptions"] = {
                    "xColumn": {"type": "infer"},
                    "yColumns": {"type": "infer"},
                    "seriesColumns": {"type": "infer"},
                    "hideLegend": False,
                    "xColumnTitle": "",
                    "yColumnTitle": "",
                    "xAxisScale": "linear",
                    "yAxisScale": "linear",
                    "crossFilterDisabled": False,
                    "hideTileTitle": False,
                    "multipleYAxes": {"base": {"id": "-1", "columns": [], "label": "", "yAxisMinimumValue": None, "yAxisMaximumValue": None, "yAxisScale": "linear", "horizontalLines": []}, "additional": []},
                }
            return t

        dashboard_def = {
            "$schema": "https://dataexplorer.azure.com/static/d/schema/20/dashboard.json",
            "schema_version": "20",
            "title": name,
            "autoRefresh": {"enabled": True, "defaultInterval": "5m", "minInterval": "1m"},
            "dataSources": [
                {
                    "id": ds_id,
                    "name": kql_database_name,
                    "clusterUri": eventhouse_uri,
                    "database": kql_database_id,
                    "kind": "kusto-trident",
                    "scopeId": "kusto",
                    "workspace": workspace_id,
                }
            ],
            "pages": [
                {"name": "Grid Health", "id": page1_id},
                {"name": "Outages & Events", "id": page2_id},
                {"name": "Renewable Generation", "id": page3_id},
            ],
            "parameters": [],
            "tiles": [
                _tile("Avg Voltage by Substation",
                      "GridSensors\n| summarize AvgVoltage=round(avg(voltage_v),1) by substation_id\n| order by AvgVoltage asc",
                      page1_id, "bar", 0, 0, 8, 6),
                _tile("Voltage Anomalies by Substation",
                      "GridSensors\n| where voltage_v < 220 or voltage_v > 240\n| summarize AnomalyCount=count() by substation_id, region\n| order by AnomalyCount desc\n| take 15",
                      page1_id, "table", 8, 0, 4, 6),
                _tile("Hourly Load Pattern (MW)",
                      "GridSensors\n| extend Hour=datetime_part('hour', todatetime(timestamp))\n| summarize AvgLoad=round(avg(load_mw),1) by Hour\n| order by Hour asc",
                      page1_id, "line", 0, 6, 6, 5),
                _tile("Avg Frequency by Region",
                      "GridSensors\n| summarize AvgFreq=round(avg(frequency_hz),3), AvgVoltage=round(avg(voltage_v),1), Readings=count() by region\n| order by Readings desc",
                      page1_id, "table", 6, 6, 6, 5),

                _tile("Events by Type and Region",
                      "PowerEvents\n| summarize Count=count() by event_type, region\n| order by Count desc",
                      page2_id, "bar", 0, 0, 6, 6),
                _tile("Outages by Region",
                      "PowerEvents\n| where event_type == 'outage'\n| summarize Outages=count(), AffectedCustomers=sum(affected_customers), AvgDurationMin=round(avg(duration_sec)/60.0,1) by region\n| order by Outages desc",
                      page2_id, "table", 6, 0, 6, 6),
                _tile("Critical Events Timeline",
                      "PowerEvents\n| where severity == 'critical'\n| extend Day=format_datetime(todatetime(timestamp), 'yyyy-MM-dd')\n| summarize CriticalCount=count() by Day\n| order by Day asc",
                      page2_id, "line", 0, 6, 12, 5),

                _tile("Generation by Plant Type",
                      "RenewableGeneration\n| summarize TotalGen=round(sum(generation_mw),0), AvgCapacityFactor=round(avg(capacity_factor),2) by plant_type",
                      page3_id, "bar", 0, 0, 6, 6),
                _tile("Daily Renewable Output by Type",
                      "RenewableGeneration\n| extend Day=format_datetime(todatetime(timestamp), 'yyyy-MM-dd')\n| summarize DailyGen=round(sum(generation_mw),0) by Day, plant_type\n| order by Day asc",
                      page3_id, "line", 6, 0, 6, 6),
                _tile("Capacity Factor by Plant and Weather",
                      "RenewableGeneration\n| summarize AvgCF=round(avg(capacity_factor),3), Readings=count() by plant_type, weather\n| order by AvgCF desc",
                      page3_id, "table", 0, 6, 12, 5),
            ],
        }

        dashboard_json = json.dumps(dashboard_def)
        payload = base64.b64encode(dashboard_json.encode()).decode()

        definition = {
            "parts": [
                {
                    "path": "RealTimeDashboard.json",
                    "payload": payload,
                    "payloadType": "InlineBase64",
                }
            ]
        }

        return await self.create_item(workspace_id, "KQLDashboard", name, definition)

    async def create_item_schedule(
        self, workspace_id: str, item_id: str, interval_minutes: int = 10, job_type: str = "Pipeline"
    ) -> dict | None:
        """Create a Cron schedule for an item (e.g. pipeline) to run every N minutes."""
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        start = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (now + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")

        url = f"{FABRIC_API}/workspaces/{workspace_id}/items/{item_id}/jobs/{job_type}/schedules"
        body = {
            "enabled": True,
            "configuration": {
                "type": "Cron",
                "startDateTime": start,
                "endDateTime": end,
                "localTimeZoneId": "UTC",
                "interval": interval_minutes,
            },
        }
        try:
            resp = await self._request("POST", url, json=body)
            if resp.status_code == 201:
                return resp.json()
            logger.warning("Schedule creation returned %s: %s", resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            logger.warning("Failed to create schedule: %s", str(e)[:200])
            return None

    # ── connections ──────────────────────────────────────────────────────

    async def upload_blob_oauth(
        self,
        account_name: str,
        container: str,
        blob_name: str,
        data: bytes,
    ) -> None:
        """
        Upload bytes to Azure Blob Storage using OAuth Bearer token.
        Uses the storage-scoped token already held by this client.
        Requires the caller to have Storage Blob Data Contributor (or Owner) on the account.
        """
        url = f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}"
        content_type = "text/csv" if blob_name.endswith(".csv") else "application/octet-stream"
        headers = {
            "x-ms-version": "2020-04-08",
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": content_type,
        }
        # Retry up to 5 times — RBAC propagation after role assignment can take ~60s
        for attempt in range(5):
            resp = await self._storage_client.put(url, content=data, headers=headers)
            if resp.status_code in (200, 201):
                return
            if resp.status_code == 403 and attempt < 4:
                wait = 20 + attempt * 5
                logger.info("Blob upload 403 (RBAC propagation), retry %d/4 in %ds", attempt + 1, wait)
                await asyncio.sleep(wait)
                continue
            raise FabricError(resp.status_code, f"Blob upload failed: {resp.text[:300]}")

    async def create_connection(
        self,
        display_name: str,
        adls_account_url: str,
        account_key: str,
    ) -> dict:
        """
        Create a shareable cloud connection using account key.
        NOTE: blocked when allowSharedKeyAccess=false — use create_connection_oauth() instead.
        """
        body = {
            "connectivityType": "ShareableCloud",
            "displayName": display_name,
            "connectionDetails": {
                "type": "AzureDataLakeStorage",
                "parameters": [
                    {"name": "account", "value": adls_account_url}
                ],
            },
            "credentialDetails": {
                "singleSignOn": False,
                "connectionEncryption": "NotEncrypted",
                "skipTestConnection": False,
                "credentials": {
                    "credentialType": "Key",
                    "key": account_key,
                },
            },
        }
        resp = await self._request("POST", f"{FABRIC_API}/connections", json=body)
        return resp.json()

    async def _generate_user_delegation_sas(self, account_name: str, container: str) -> str:
        """
        Generate a read-only User Delegation SAS for an ADLS Gen2 container.
        Uses the storage OAuth2 token — works even when allowSharedKeyAccess=false.
        """
        import hmac as _hmac
        import hashlib
        import base64
        import urllib.parse
        from datetime import datetime, timezone, timedelta
        from xml.etree import ElementTree as ET

        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        expiry = (now + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        version = "2020-12-06"

        # 1. Get User Delegation Key
        xml_body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<KeyInfo><Start>{start}</Start><Expiry>{expiry}</Expiry></KeyInfo>'
        )
        async with httpx.AsyncClient(timeout=30.0) as c:
            resp = await c.post(
                f"https://{account_name}.blob.core.windows.net/?restype=service&comp=userdelegationkey",
                content=xml_body.encode(),
                headers={
                    "Authorization": f"Bearer {self._storage_token}",
                    "x-ms-version": version,
                    "Content-Type": "application/xml",
                },
            )
        if resp.status_code >= 400:
            raise FabricError(resp.status_code, f"UserDelegationKey failed: {resp.text[:200]}")

        root = ET.fromstring(resp.text)
        def _get(tag: str) -> str:
            el = root.find(tag)
            return el.text if el is not None else ""

        signed_oid = _get("SignedOid")
        signed_tid = _get("SignedTid")
        signed_start = _get("SignedStart")
        signed_expiry = _get("SignedExpiry")
        signed_service = _get("SignedService")
        signed_version = _get("SignedVersion")
        key_value = _get("Value")

        # 2. Build string-to-sign (container SAS, version 2020-12-06)
        string_to_sign = "\n".join([
            "rl",                                   # signedPermissions
            start,                                  # signedStart
            expiry,                                 # signedExpiry
            f"/blob/{account_name}/{container}",    # canonicalizedResource
            signed_oid,                             # signedKeyObjectId
            signed_tid,                             # signedKeyTenantId
            signed_start,                           # signedKeyStart
            signed_expiry,                          # signedKeyExpiry
            signed_service,                         # signedKeyService
            signed_version,                         # signedKeyVersion
            "", "", "",                             # authorizedOid, unauthorizedOid, correlationId
            "", "",                                 # IP, protocol
            version,                                # signedVersion
            "c",                                    # signedResource (container)
            "", "",                                 # snapshotTime, encryptionScope
            "", "", "", "", "",                     # rscc, rscd, rsce, rscl, rsct
        ])

        key_bytes = base64.b64decode(key_value)
        sig = base64.b64encode(
            _hmac.new(key_bytes, string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        ).decode()

        # 3. Build SAS query string
        q = urllib.parse.quote
        return "&".join([
            f"sv={version}",
            f"st={q(start, safe='')}",
            f"se={q(expiry, safe='')}",
            "sr=c",
            "sp=rl",
            f"skoid={signed_oid}",
            f"sktid={signed_tid}",
            f"skt={q(signed_start, safe='')}",
            f"ske={q(signed_expiry, safe='')}",
            f"sks={signed_service}",
            f"skv={signed_version}",
            f"sig={q(sig, safe='')}",
        ])

    async def create_connection_oauth(
        self,
        display_name: str,
        adls_account_url: str,
        container: str = "",
    ) -> dict:
        """
        Create a shareable cloud connection to ADLS Gen2 using a User Delegation SAS.
        Requires the fabric token to include Connection.ReadWrite.All scope.
        """
        # Generate User Delegation SAS for the container (OAuth2-based, no account key needed)
        account_name = adls_account_url.replace("https://", "").rstrip("/").split(".")[0]
        sas_token = ""
        if container:
            try:
                sas_token = await self._generate_user_delegation_sas(account_name, container)
                logger.info("[connection] user delegation SAS generated for container: %s", container)
            except Exception as sas_err:
                logger.warning("[connection] SAS generation failed: %s", sas_err)

        conn_path = f"/{container}" if container else "/"
        body = {
            "connectivityType": "ShareableCloud",
            "displayName": display_name,
            "connectionDetails": {
                "type": "AzureDataLakeStorage",
                # creationMethod is required by the Fabric Connections API
                "creationMethod": "AzureDataLakeStorage",
                # API requires "server" (hostname only, no scheme) and "path"
                "parameters": [
                    {
                        "dataType": "Text",
                        "name": "server",
                        "value": adls_account_url.replace("https://", "").rstrip("/"),
                    },
                    {
                        "dataType": "Text",
                        "name": "path",
                        "value": conn_path,
                    },
                ],
            },
            "credentialDetails": {
                # SharedAccessSignature using a User Delegation SAS (OAuth2-based).
                # Works even when allowSharedKeyAccess=false (MSIT tenant policy).
                # SAS is generated below and scoped to the specific container.
                "singleSignOnType": "None",
                "connectionEncryption": "NotEncrypted",
                "skipTestConnection": False,
                "credentials": {
                    "credentialType": "SharedAccessSignature",
                    "token": sas_token,
                },
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as c:
            resp = await c.post(
                f"{FABRIC_API}/connections",
                json=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 409:
                # Connection with this display name already exists — find and reuse it.
                logger.info("[connection] 409 DuplicateConnectionName — looking up existing connection '%s'", display_name)
                list_resp = await c.get(
                    f"{FABRIC_API}/connections",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                if list_resp.status_code == 200:
                    for conn in list_resp.json().get("value", []):
                        if conn.get("displayName") == display_name:
                            logger.info("[connection] reusing existing connection id=%s", conn.get("id"))
                            return conn
                raise FabricError(resp.status_code, resp.text[:500])
        if resp.status_code >= 400:
            raise FabricError(resp.status_code, resp.text[:500])
        return resp.json()

    # ── shortcuts ────────────────────────────────────────────────────────

    async def create_shortcut(
        self,
        workspace_id: str,
        lakehouse_id: str,
        name: str,
        parent_path: str,
        adls_location: str,
        adls_subpath: str,
        connection_id: str,
        onelake_token: str | None = None,
    ) -> dict:
        """
        Create an ADLS Gen2 shortcut in a lakehouse.
        Requires the fabric token to include OneLake.ReadWrite.All scope.

        Args:
            parent_path:  e.g. "Files"
            adls_location: e.g. "https://myaccount.dfs.core.windows.net"
            adls_subpath: e.g. "/containername"  (leading slash, no trailing)
            connection_id: Fabric connection ID returned by create_connection()
            onelake_token: Optional dedicated token with OneLake.ReadWrite.All scope.
                           If provided, used instead of the main Fabric token.
        """
        url = (
            f"{FABRIC_API}/workspaces/{workspace_id}"
            f"/items/{lakehouse_id}/shortcuts"
        )
        body = {
            "name": name,
            "path": parent_path,
            "target": {
                "adlsGen2": {
                    "location": adls_location,
                    "subpath": adls_subpath,
                    "connectionId": connection_id,
                },
            },
        }
        # Always use the main Fabric token (self._request) — it includes both
        # Item.ReadWrite.All and OneLake.ReadWrite.All which the Shortcuts REST API requires.
        # The onelake_token (OneLake.ReadWrite.All only) is for OneLake DFS file uploads, not REST.
        resp = await self._request("POST", url, json=body)
        return resp.json()
