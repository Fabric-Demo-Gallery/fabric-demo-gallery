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
    ) -> dict:
        """Create a notebook, then update its definition with content and lakehouse binding."""
        # Step 1: Create empty notebook
        item = await self.create_item(workspace_id, "Notebook", name)
        nb_id = item["id"]
        logger.info("Created empty notebook '%s' (%s), updating definition...", name, nb_id)

        # Step 2: Build Fabric .py notebook format from .ipynb
        ipynb_content = Path(ipynb_path).read_text(encoding="utf-8")
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
