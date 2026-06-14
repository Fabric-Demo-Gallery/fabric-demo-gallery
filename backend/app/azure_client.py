"""Azure ARM + Blob Storage REST API client for ADLS Gen2 provisioning."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ARM_API = "https://management.azure.com"
STORAGE_API_VERSION = "2023-01-01"
ARM_API_VERSION = "2022-12-01"
RG_API_VERSION = "2021-04-01"
RBAC_API_VERSION = "2022-04-01"
SQL_API_VERSION = "2021-11-01"
# Built-in role: Storage Blob Data Contributor
STORAGE_BLOB_DATA_CONTRIBUTOR = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"


class AzureError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Azure API {status}: {detail}")


def _extract_arm_error(body: dict) -> str:
    """Pull the most actionable message out of an ARM operation-status failure
    body. The useful reason is usually nested in error.details[]; fall back to
    error.message, then the raw body."""
    err = body.get("error") or {}
    details = err.get("details") or []
    msgs = [d.get("message") for d in details if isinstance(d, dict) and d.get("message")]
    if msgs:
        return " ".join(msgs)[:500]
    if err.get("message"):
        return err["message"][:500]
    return json.dumps(body)[:500]



class AzureClient:
    """Async client for Azure ARM and Blob Storage REST APIs."""

    def __init__(self, management_token: str):
        self._management_token = management_token
        self._arm_client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {management_token}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def close(self):
        await self._arm_client.aclose()

    # ── helpers ──────────────────────────────────────────────────────────

    async def _arm_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        resp = await self._arm_client.request(method, url, **kwargs)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                err = resp.json()
                msg = (
                    err.get("error", {}).get("message")
                    or err.get("message")
                    or detail
                )
                detail = msg[:500]
            except Exception:
                pass
            raise AzureError(resp.status_code, detail)
        return resp

    async def _poll_arm_lro(self, async_operation_url: str, timeout: int = 180) -> dict:
        """Poll an ARM long-running operation until it succeeds or times out."""
        start = time.time()
        while time.time() - start < timeout:
            resp = await self._arm_client.get(async_operation_url)
            if resp.status_code >= 400:
                raise AzureError(resp.status_code, resp.text[:300])

            # 202 = still in progress (body may be empty)
            if resp.status_code == 202:
                await asyncio.sleep(6)
                continue

            # Try to parse JSON body; empty / non-JSON body = still in progress
            try:
                body = resp.json()
            except Exception:
                await asyncio.sleep(6)
                continue

            # ARM ops use "status"; some use "provisioningState" at the root level
            status = (
                body.get("status")
                or body.get("provisioningState")
                or ""
            ).lower()

            if status == "succeeded":
                return body
            if status in ("failed", "canceled"):
                err = body.get("error", {})
                raise AzureError(
                    500,
                    f"ARM operation {status}: {err.get('message', str(body)[:200])}",
                )
            # "inprogress", "running", "accepted", or unknown — keep polling
            logger.debug("ARM LRO status: %s", status)
            await asyncio.sleep(6)
        raise AzureError(504, f"ARM operation timed out after {timeout}s")

    # ── subscriptions ────────────────────────────────────────────────────

    def get_caller_oid(self) -> str:
        """Extract the caller's object ID from the management token (JWT)."""
        try:
            parts = self._management_token.split(".")
            if len(parts) < 2:
                return ""
            padding = 4 - len(parts[1]) % 4
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * padding))
            return claims.get("oid") or claims.get("sub", "")
        except Exception:
            return ""

    def get_caller_entra_admin(self) -> tuple[str, str, str]:
        """Extract (login, object_id, tenant_id) of the caller from the
        management token (JWT), for use as the Azure SQL Entra ID administrator.

        login is the user principal name; falls back across the usual claim
        names. Returns empty strings on failure (caller validates).
        """
        try:
            parts = self._management_token.split(".")
            if len(parts) < 2:
                return "", "", ""
            padding = 4 - len(parts[1]) % 4
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * padding))
            oid = claims.get("oid") or claims.get("sub", "")
            tid = claims.get("tid", "")
            login = (
                claims.get("upn")
                or claims.get("preferred_username")
                or claims.get("unique_name")
                or claims.get("email")
                or oid
            )
            return login, oid, tid
        except Exception:
            return "", "", ""

    async def assign_blob_data_contributor(
        self,
        subscription_id: str,
        resource_group: str,
        account_name: str,
        principal_id: str,
    ) -> None:
        """Assign Storage Blob Data Contributor to a principal on a storage account."""
        scope = (
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{account_name}"
        )
        role_def_id = (
            f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization"
            f"/roleDefinitions/{STORAGE_BLOB_DATA_CONTRIBUTOR}"
        )
        assignment_id = str(uuid.uuid4())
        url = (
            f"{ARM_API}{scope}/providers/Microsoft.Authorization"
            f"/roleAssignments/{assignment_id}?api-version={RBAC_API_VERSION}"
        )
        body = {
            "properties": {
                "roleDefinitionId": role_def_id,
                "principalId": principal_id,
                "principalType": "User",
            }
        }
        try:
            await self._arm_request("PUT", url, json=body)
        except AzureError as e:
            if e.status == 409:
                return  # already assigned — not an error
            raise

    async def list_subscriptions(self) -> list[dict]:
        """List all Azure subscriptions visible to the current user."""
        resp = await self._arm_request(
            "GET", f"{ARM_API}/subscriptions?api-version={ARM_API_VERSION}"
        )
        return [
            {"id": s["subscriptionId"], "displayName": s.get("displayName", "")}
            for s in resp.json().get("value", [])
            if s.get("state", "").lower() == "enabled"
        ]

    # ── resource groups ──────────────────────────────────────────────────

    async def list_resource_groups(self, subscription_id: str) -> list[dict]:
        """List resource groups in a subscription."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourcegroups"
            f"?api-version={RG_API_VERSION}"
        )
        resp = await self._arm_request("GET", url)
        return [
            {"name": rg["name"], "location": rg.get("location", "")}
            for rg in resp.json().get("value", [])
        ]

    async def create_resource_group(
        self, subscription_id: str, name: str, location: str
    ) -> dict:
        """Create (or update) a resource group."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{name}"
            f"?api-version={RG_API_VERSION}"
        )
        resp = await self._arm_request("PUT", url, json={"location": location})
        return resp.json()

    # ── storage accounts ─────────────────────────────────────────────────

    async def create_storage_account(
        self,
        subscription_id: str,
        resource_group: str,
        name: str,
        location: str,
    ) -> dict:
        """
        Create an ADLS Gen2-enabled storage account (StorageV2 + HNS).
        Handles ARM LRO — polls until provisioned. Returns the account object.
        """
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{name}"
            f"?api-version={STORAGE_API_VERSION}"
        )
        body = {
            "sku": {"name": "Standard_LRS"},
            "kind": "StorageV2",
            "location": location,
            "properties": {
                "isHnsEnabled": True,          # ADLS Gen2 hierarchical namespace
                "minimumTlsVersion": "TLS1_2",
                "allowBlobPublicAccess": False,
                "supportsHttpsTrafficOnly": True,
            },
        }
        resp = await self._arm_client.put(url, json=body)
        if resp.status_code == 409:
            # Account already exists — check if it's ours
            detail = resp.text[:300]
            try:
                err_code = resp.json().get("error", {}).get("code", "")
                if err_code == "StorageAccountAlreadyTaken":
                    raise AzureError(409, f"Storage account name '{name}' is already taken globally. Choose a different name.")
            except AzureError:
                raise
            except Exception:
                pass
            raise AzureError(409, detail)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                msg = resp.json().get("error", {}).get("message", detail)
                detail = msg[:500]
            except Exception:
                pass
            raise AzureError(resp.status_code, detail)

        if resp.status_code == 202:
            # Poll the resource's own provisioningState directly — the Azure-AsyncOperation
            # URL can lag behind reality (still "InProgress" after the account is live).
            _poll_start = time.time()
            _poll_timeout = 600
            while time.time() - _poll_start < _poll_timeout:
                await asyncio.sleep(8)
                try:
                    acct = await self.get_storage_account(subscription_id, resource_group, name)
                    pstate = (acct.get("properties", {}).get("provisioningState") or "").lower()
                    logger.debug("Storage account %s provisioningState: %s", name, pstate)
                    if pstate == "succeeded":
                        return acct
                    if pstate in ("failed", "canceled"):
                        raise AzureError(500, f"Storage account provisioning {pstate}")
                    # "creating" / "resolvingdns" / etc. — keep polling
                except AzureError as e:
                    if e.status == 404:
                        continue  # Not yet visible in ARM — keep waiting
                    raise
            raise AzureError(
                504,
                f"Storage account provisioning timed out after {_poll_timeout}s. "
                "Check the Azure portal — if it succeeded, you can retry.",
            )
        elif resp.status_code in (200, 201):
            # Synchronous create — verify provisioningState before returning
            try:
                pstate = (
                    resp.json().get("properties", {}).get("provisioningState") or "succeeded"
                ).lower()
                if pstate not in ("succeeded", ""):
                    # Already-exists but still provisioning (rare) — do one GET poll
                    await asyncio.sleep(5)
            except Exception:
                pass
        # Return the full account details
        return await self.get_storage_account(subscription_id, resource_group, name)

    async def get_storage_account(
        self,
        subscription_id: str,
        resource_group: str,
        name: str,
    ) -> dict:
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{name}"
            f"?api-version={STORAGE_API_VERSION}"
        )
        resp = await self._arm_request("GET", url)
        return resp.json()

    async def create_blob_container(
        self,
        subscription_id: str,
        resource_group: str,
        account_name: str,
        container_name: str,
    ) -> dict:
        """Create a blob container in the storage account."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{account_name}"
            f"/blobServices/default/containers/{container_name}"
            f"?api-version={STORAGE_API_VERSION}"
        )
        resp = await self._arm_request("PUT", url, json={})
        return resp.json()

    async def get_storage_account_key(
        self,
        subscription_id: str,
        resource_group: str,
        account_name: str,
    ) -> str:
        """Retrieve the first storage account access key."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{account_name}"
            f"/listKeys?api-version={STORAGE_API_VERSION}"
        )
        resp = await self._arm_request("POST", url)
        keys = resp.json().get("keys", [])
        if not keys:
            raise AzureError(500, f"No keys returned for storage account '{account_name}'")
        return keys[0]["value"]

    # ── blob upload (SharedKeyLite auth) ─────────────────────────────────

    async def upload_blob(
        self,
        account_name: str,
        container: str,
        blob_name: str,
        data: bytes,
        account_key: str,
    ) -> None:
        """
        Upload bytes to Azure Blob Storage using SharedKey authentication.
        Uses the REST API directly — no extra SDK required.
        """
        url = f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}"
        now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        content_length = str(len(data))
        content_type = "text/csv" if blob_name.endswith(".csv") else "application/octet-stream"

        # Build SharedKey signature
        # https://docs.microsoft.com/en-us/rest/api/storageservices/authorize-with-shared-key
        canonicalized_headers = f"x-ms-blob-type:BlockBlob\nx-ms-date:{now}\nx-ms-version:2020-04-08"
        canonicalized_resource = f"/{account_name}/{container}/{blob_name}"
        string_to_sign = (
            f"PUT\n"          # HTTP method
            f"\n"             # Content-Encoding
            f"\n"             # Content-Language
            f"{content_length}\n"  # Content-Length
            f"\n"             # Content-MD5
            f"{content_type}\n"    # Content-Type
            f"\n"             # Date
            f"\n"             # If-Modified-Since
            f"\n"             # If-Match
            f"\n"             # If-None-Match
            f"\n"             # If-Unmodified-Since
            f"\n"             # Range
            f"{canonicalized_headers}\n"
            f"{canonicalized_resource}"
        )
        key_bytes = base64.b64decode(account_key)
        sig = base64.b64encode(
            hmac.new(key_bytes, string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        ).decode()

        headers = {
            "Authorization": f"SharedKey {account_name}:{sig}",
            "x-ms-date": now,
            "x-ms-version": "2020-04-08",
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": content_type,
            "Content-Length": content_length,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.put(url, content=data, headers=headers)
        if resp.status_code not in (200, 201):
            raise AzureError(resp.status_code, f"Blob upload failed: {resp.text[:300]}")

    # ── Azure SQL (for Fabric Mirroring) ─────────────────────────────────

    async def create_sql_server(
        self,
        subscription_id: str,
        resource_group: str,
        server_name: str,
        location: str,
        entra_admin_login: str,
        entra_admin_object_id: str,
        entra_admin_tenant_id: str,
    ) -> dict:
        """Create a logical Azure SQL server with a system-assigned managed
        identity (SAMI) — a hard prerequisite for Fabric Database Mirroring —
        configured for **Microsoft Entra-only authentication** (no SQL login/
        password). The deploying user is set as the Entra ID administrator.

        Entra-only auth is mandatory in MCAPS/MSIT-governed tenants (the
        AzureSQL_WithoutAzureADOnlyAuthentication_Deny policy blocks any server
        that permits SQL authentication).

        Idempotent: if the server already exists the PUT updates it in place.
        Polls until the server state is 'Ready'.
        """
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Sql/servers/{server_name}"
            f"?api-version={SQL_API_VERSION}"
        )
        body = {
            "location": location,
            "identity": {"type": "SystemAssigned"},  # SAMI required by mirroring
            "properties": {
                # Microsoft Entra-only authentication — no administratorLogin/password.
                "administrators": {
                    "administratorType": "ActiveDirectory",
                    "principalType": "User",
                    "login": entra_admin_login,
                    "sid": entra_admin_object_id,
                    "tenantId": entra_admin_tenant_id,
                    "azureADOnlyAuthentication": True,
                },
                "version": "12.0",
                "minimalTlsVersion": "1.2",
                "publicNetworkAccess": "Enabled",
            },
        }
        resp = await self._arm_client.put(url, json=body)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                msg = resp.json().get("error", {}).get("message", detail)
                detail = msg[:500]
            except Exception:
                pass
            if resp.status_code == 409 and "already" in detail.lower():
                raise AzureError(
                    409,
                    f"SQL server name '{server_name}' is already taken globally. "
                    "Choose a different name.",
                )
            raise AzureError(resp.status_code, detail)

        # Follow the async operation (Azure-AsyncOperation header) so that async
        # provisioning failures — e.g. 'ProvisioningDisabled: region restricted' in
        # governed subscriptions — surface immediately with the real message,
        # instead of silently 404ing the resource GET until the 600s timeout.
        async_url = resp.headers.get("Azure-AsyncOperation") or resp.headers.get("Location")
        if async_url:
            start = time.time()
            timeout = 600
            while time.time() - start < timeout:
                await asyncio.sleep(6)
                try:
                    op = await self._arm_client.get(async_url)
                except httpx.TransportError as e:
                    # Transient network blip (ConnectTimeout/ConnectError/ReadTimeout)
                    # while polling — keep waiting rather than failing the deploy.
                    logger.debug("SQL provisioning poll network error (retrying): %s", e)
                    continue
                if op.status_code >= 400:
                    continue  # operation status not queryable yet
                ob = op.json()
                status = (ob.get("status") or "").lower()
                if status in ("succeeded", "completed"):
                    return await self.get_sql_server(subscription_id, resource_group, server_name)
                if status in ("failed", "canceled", "cancelled"):
                    raise AzureError(500, f"SQL server provisioning failed: {_extract_arm_error(ob)}")
                # InProgress / Accepted / Running — keep polling
            raise AzureError(504, f"SQL server provisioning timed out after {timeout}s")

        # Fallback: no async header — poll the resource's own provisioningState.
        start = time.time()
        timeout = 600
        while time.time() - start < timeout:
            await asyncio.sleep(8)
            try:
                srv = await self.get_sql_server(subscription_id, resource_group, server_name)
                state = (srv.get("properties", {}).get("state") or "").lower()
                logger.debug("SQL server %s state: %s", server_name, state)
                if state == "ready":
                    return srv
                if state in ("disabled",):
                    raise AzureError(500, f"SQL server provisioning ended in state '{state}'")
            except httpx.TransportError as e:
                # Transient network blip while polling — keep waiting.
                logger.debug("SQL provisioning poll network error (retrying): %s", e)
                continue
            except AzureError as e:
                if e.status == 404:
                    continue  # not yet visible in ARM
                raise
        raise AzureError(504, f"SQL server provisioning timed out after {timeout}s")

    async def get_sql_server(
        self, subscription_id: str, resource_group: str, server_name: str
    ) -> dict:
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Sql/servers/{server_name}"
            f"?api-version={SQL_API_VERSION}"
        )
        resp = await self._arm_request("GET", url)
        return resp.json()

    async def create_sql_firewall_rule(
        self,
        subscription_id: str,
        resource_group: str,
        server_name: str,
        rule_name: str,
        start_ip: str,
        end_ip: str,
    ) -> None:
        """Create/update a server firewall rule. 0.0.0.0–0.0.0.0 is the special
        'Allow Azure services and resources to access this server' rule, which
        both Fabric Spark (seeding) and the mirroring service require."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Sql/servers/{server_name}/firewallRules/{rule_name}"
            f"?api-version={SQL_API_VERSION}"
        )
        body = {"properties": {"startIpAddress": start_ip, "endIpAddress": end_ip}}
        await self._arm_request("PUT", url, json=body)

    async def create_sql_database(
        self,
        subscription_id: str,
        resource_group: str,
        server_name: str,
        database_name: str,
        location: str,
    ) -> dict:
        """Create a Standard S3 database (100 DTU — the minimum DTU tier that
        Fabric Mirroring supports; Free/Basic/<100 DTU tiers are rejected).
        Handles the 202 LRO by polling the database status."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Sql/servers/{server_name}/databases/{database_name}"
            f"?api-version={SQL_API_VERSION}"
        )
        body = {
            "location": location,
            "sku": {"name": "S3", "tier": "Standard"},
            "properties": {"maxSizeBytes": 2147483648},  # 2 GB
        }
        resp = await self._arm_client.put(url, json=body)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                msg = resp.json().get("error", {}).get("message", detail)
                detail = msg[:500]
            except Exception:
                pass
            raise AzureError(resp.status_code, detail)

        start = time.time()
        timeout = 600
        while time.time() - start < timeout:
            await asyncio.sleep(8)
            try:
                gurl = url
                gresp = await self._arm_request("GET", gurl)
                db = gresp.json()
                status = (db.get("properties", {}).get("status") or "").lower()
                logger.debug("SQL database %s status: %s", database_name, status)
                if status == "online":
                    return db
                if status in ("failed", "disabled"):
                    raise AzureError(500, f"SQL database creation ended in status '{status}'")
            except AzureError as e:
                if e.status == 404:
                    continue
                raise
        raise AzureError(504, f"SQL database creation timed out after {timeout}s")

    async def delete_sql_server(
        self, subscription_id: str, resource_group: str, server_name: str
    ) -> bool:
        """Delete the logical SQL server (cascades all databases).
        404-tolerant: returns False if the server was already gone."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Sql/servers/{server_name}"
            f"?api-version={SQL_API_VERSION}"
        )
        resp = await self._arm_client.delete(url)
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise AzureError(resp.status_code, resp.text[:300])
        return True

    async def delete_storage_account(
        self, subscription_id: str, resource_group: str, name: str
    ) -> bool:
        """Delete a storage account (and its containers/blobs).
        404-tolerant: returns False if the account was already gone."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{name}"
            f"?api-version={STORAGE_API_VERSION}"
        )
        resp = await self._arm_client.delete(url)
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise AzureError(resp.status_code, resp.text[:300])
        return True
