"""Azure ARM + Blob Storage REST API client for ADLS Gen2 provisioning."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
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
# Microsoft Foundry / Cognitive Services (preview — used by the Fabric+Foundry scenario)
COG_API_VERSION = "2025-12-01"          # accounts, projects, deployments, connections
MODEL_CAPACITY_API_VERSION = "2024-10-01"  # modelCapacities quota pre-flight
# Azure AI Search (Foundry IQ retrieval engine for the Fabric data agent)
SEARCH_API_VERSION = "2023-11-01"
# Built-in role definition GUIDs (used for the Foundry IQ RBAC wiring)
STORAGE_BLOB_DATA_CONTRIBUTOR = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
SEARCH_INDEX_DATA_READER = "1407120a-92aa-4202-b7e9-c0e197c71c8f"
SEARCH_SERVICE_CONTRIBUTOR = "7ca78c08-252a-4471-8644-bb5ff32d4ba0"
COGNITIVE_SERVICES_USER = "a97b65f3-24c7-4388-baec-2e87135dc908"
AZURE_AI_DEVELOPER = "64702f94-c441-49e6-a78b-ef80e0188fee"
# "Foundry User" (formerly "Azure AI User") — the documented role for create/edit
# agents; its Microsoft.CognitiveServices/* dataAction grants the agents data-plane.
FOUNDRY_USER = "53ca6127-db72-4b80-b1b0-d745d6d5456d"


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

    async def assign_role(
        self,
        scope: str,
        role_def_guid: str,
        principal_id: str,
        principal_type: str = "ServicePrincipal",
    ) -> None:
        """Assign a built-in role to a principal at an ARM scope. ``scope`` is a full
        ARM resource id (starts with /subscriptions/...). 409 (already assigned) is
        treated as success. Used for the Foundry IQ managed-identity RBAC wiring."""
        # roleDefinitions live at subscription scope; derive the subscription id.
        sub_id = scope.split("/subscriptions/", 1)[1].split("/", 1)[0]
        role_def_id = (
            f"/subscriptions/{sub_id}/providers/Microsoft.Authorization"
            f"/roleDefinitions/{role_def_guid}"
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
                "principalType": principal_type,
            }
        }
        try:
            await self._arm_request("PUT", url, json=body)
        except AzureError as e:
            if e.status == 409:
                return  # already assigned
            # ARM sometimes 400s briefly while a just-created identity propagates.
            if e.status == 400 and "does not exist" in (e.detail or "").lower():
                raise AzureError(400, "Principal not yet replicated in Microsoft Entra; retry shortly.")
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

    async def list_locations(self, subscription_id: str) -> list[dict]:
        """List the physical Azure regions available to a subscription
        (parallels list_subscriptions / list_resource_groups for the region picker)."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/locations"
            f"?api-version={ARM_API_VERSION}"
        )
        resp = await self._arm_request("GET", url)
        out = []
        for loc in resp.json().get("value", []):
            meta = loc.get("metadata") or {}
            # Skip logical/edge regions — only offer real datacenter regions.
            if meta.get("regionType") and meta["regionType"] != "Physical":
                continue
            out.append(
                {"name": loc["name"], "displayName": loc.get("displayName", loc["name"])}
            )
        out.sort(key=lambda r: r["displayName"])
        return out

    async def create_resource_group(
        self, subscription_id: str, name: str, location: str
    ) -> dict:
        """Create the resource group if absent, else reuse the existing one.

        A resource group's location is only metadata — the resources inside it may
        live in any region — so an RG that already exists in a *different* region is
        still perfectly usable (e.g. an eastus RG from a Shortcuts demo reused by a
        westus2 Mirroring demo). ARM rejects a PUT that would change an existing
        RG's location ("Invalid resource group location ... already exists in
        location ..."), so GET-then-create instead of blindly PUT-ing.
        """
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{name}"
            f"?api-version={RG_API_VERSION}"
        )
        existing = await self._arm_client.get(url)
        if existing.status_code == 200:
            return existing.json()
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

    async def get_search_admin_key(
        self, subscription_id: str, resource_group: str, service_name: str
    ) -> str:
        """Primary admin key of an Azure AI Search service (via ARM). Lets the
        backend call the Search data-plane with api-key auth instead of a per-user
        delegated token — so the Foundry IQ steps work for EVERY user, not only
        ones who have consented to the search.azure.com scope."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Search/searchServices/{service_name}"
            f"/listAdminKeys?api-version={SEARCH_API_VERSION}"
        )
        resp = await self._arm_request("POST", url)
        key = resp.json().get("primaryKey")
        if not key:
            raise AzureError(500, f"No admin key returned for search service '{service_name}'")
        return key

    async def get_cognitive_account_key(
        self, subscription_id: str, resource_group: str, account_name: str
    ) -> str:
        """First API key of a Cognitive Services / Foundry account (via ARM)."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/listKeys?api-version={COG_API_VERSION}"
        )
        resp = await self._arm_request("POST", url)
        body = resp.json()
        key = body.get("key1") or body.get("key2")
        if not key:
            raise AzureError(500, f"No key returned for account '{account_name}'")
        return key

    async def get_managed_identity_token(self, resource: str) -> str:
        """Acquire an access token for `resource` using the App Service system-assigned
        managed identity (App Service MSI endpoint). Lets the backend call data-plane
        APIs (e.g. the Foundry Agent Service) without any per-user delegated token."""
        endpoint = os.environ.get("IDENTITY_ENDPOINT")
        header = os.environ.get("IDENTITY_HEADER")
        if not endpoint or not header:
            raise AzureError(500, "Backend managed identity is not available")
        async with httpx.AsyncClient(timeout=30.0) as c:
            resp = await c.get(
                endpoint,
                params={"resource": resource, "api-version": "2019-08-01"},
                headers={"X-IDENTITY-HEADER": header},
            )
        if resp.status_code >= 400:
            raise AzureError(resp.status_code, f"MI token request failed: {resp.text[:200]}")
        tok = resp.json().get("access_token", "")
        if not tok:
            raise AzureError(500, "MI token response had no access_token")
        return tok

    @staticmethod
    def oid_from_token(token: str) -> str:
        """Decode the `oid` (principal object id) claim from a JWT access token."""
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            return json.loads(base64.urlsafe_b64decode(payload)).get("oid", "")
        except Exception:
            return ""

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

    # ── Microsoft Foundry (preview) ─────────────────────────────────
    # Provision an Azure AI Foundry account + project + model deployment for the
    # "Fabric + Foundry AI agent" scenario. Everything here is PREVIEW; ARM shapes
    # may change. The deployer treats these as best-effort/skippable so a change
    # never breaks the (already-completed) Fabric half of the deploy.

    async def _poll_cog_provisioning(
        self, url: str, what: str, timeout: int = 600, absent_grace: int = 150
    ) -> dict:
        """Poll a Cognitive Services resource until provisioningState is terminal.

        Tolerates a brief initial 404 window (a freshly-accepted create may not be
        visible in ARM for a few seconds). If the resource never appears within
        ``absent_grace`` seconds it is treated as never-created, so a genuine failure
        surfaces quickly instead of waiting out the full timeout."""
        start = time.time()
        seen = False
        absent_since: float | None = None
        while time.time() - start < timeout:
            await asyncio.sleep(8)
            try:
                resp = await self._arm_request("GET", url)
            except httpx.TransportError as e:
                logger.debug("%s poll network error (retrying): %s", what, e)
                continue
            except AzureError as e:
                if e.status == 404:
                    if not seen:
                        absent_since = absent_since or time.time()
                        if time.time() - absent_since > absent_grace:
                            raise AzureError(
                                404,
                                f"{what} never appeared in ARM after the create was "
                                f"accepted — it was not provisioned.",
                            )
                    continue  # not yet visible in ARM
                raise
            seen = True
            absent_since = None
            state = (resp.json().get("properties", {}).get("provisioningState") or "").lower()
            logger.debug("%s provisioningState: %s", what, state)
            if state == "succeeded":
                return resp.json()
            if state in ("failed", "canceled", "cancelled"):
                raise AzureError(500, f"{what} provisioning ended in state '{state}'")
        raise AzureError(504, f"{what} provisioning timed out after {timeout}s")

    @staticmethod
    def _arm_error_detail(resp: httpx.Response) -> str:
        """Pull the most actionable message out of an ARM error response."""
        detail = resp.text[:500]
        try:
            detail = resp.json().get("error", {}).get("message", detail)[:500]
        except Exception:
            pass
        return detail

    async def _cog_put(self, url: str, body: dict, what: str, poll_timeout: int = 600) -> dict:
        """Idempotent PUT of a Cognitive Services resource, resilient to ARM gateway
        timeouts. A 502/503/504 on the PUT does NOT mean the create failed — the
        resource provider has very likely accepted the request and is provisioning in
        the background. On a transient gateway error we retry the PUT a few times,
        then fall back to polling the resource's own provisioningState rather than
        aborting the whole deploy."""
        transient = (502, 503, 504)
        last = ""
        for attempt in range(4):
            try:
                resp = await self._arm_client.put(url, json=body)
            except httpx.TransportError as e:
                last = f"network error: {e}"
                logger.warning("%s PUT network error (attempt %d/4): %s", what, attempt + 1, e)
                await asyncio.sleep(5 * (attempt + 1))
                continue
            if resp.status_code in transient:
                last = self._arm_error_detail(resp)
                logger.warning("%s PUT %d (transient gateway error, attempt %d/4): %s",
                               what, resp.status_code, attempt + 1, last)
                await asyncio.sleep(5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise AzureError(resp.status_code, self._arm_error_detail(resp))
            try:
                state = (resp.json().get("properties", {}).get("provisioningState") or "").lower()
            except Exception:
                state = ""
            if state == "succeeded":
                return resp.json()
            return await self._poll_cog_provisioning(url, what, timeout=poll_timeout)
        # Every PUT attempt hit a gateway timeout — the resource may still be coming up.
        logger.warning("%s: all PUT attempts hit a gateway timeout; polling in case the "
                       "provider accepted the create. Last error: %s", what, last)
        return await self._poll_cog_provisioning(url, what, timeout=poll_timeout)

    async def check_model_capacity(
        self, subscription_id: str, model_name: str, model_version: str, model_format: str = "OpenAI"
    ) -> list[dict]:
        """Return per-region available capacity for a model (advisory pre-flight).
        Returns a list of {location, availableCapacity}; empty on any failure so a
        listing hiccup never blocks an otherwise-valid deploy."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/providers/Microsoft.CognitiveServices"
            f"/modelCapacities?api-version={MODEL_CAPACITY_API_VERSION}"
            f"&modelFormat={model_format}&modelName={model_name}&modelVersion={model_version}"
        )
        try:
            resp = await self._arm_request("GET", url)
        except Exception as e:  # noqa: BLE001 - advisory only
            logger.warning("Model capacity check skipped: %s", e)
            return []
        out = []
        for entry in resp.json().get("value", []):
            props = entry.get("properties", {})
            out.append({
                "location": entry.get("location", ""),
                "availableCapacity": props.get("availableCapacity", 0),
            })
        return out

    async def create_foundry_account(
        self, subscription_id: str, resource_group: str, account_name: str, location: str
    ) -> dict:
        """Create an Azure AI Foundry account (Microsoft.CognitiveServices/accounts,
        kind=AIServices) with project management enabled and a system-assigned
        identity. Idempotent PUT; polls until provisioningState is Succeeded."""
        base = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        )
        url = f"{base}?api-version={COG_API_VERSION}"
        body = {
            "location": location,
            "kind": "AIServices",
            "sku": {"name": "S0"},
            "identity": {"type": "SystemAssigned"},
            "properties": {
                "allowProjectManagement": True,
                "customSubDomainName": account_name,
                "publicNetworkAccess": "Enabled",
            },
        }
        return await self._cog_put(url, body, f"Foundry account '{account_name}'")

    async def create_foundry_project(
        self, subscription_id: str, resource_group: str, account_name: str,
        project_name: str, location: str, display_name: str | None = None,
    ) -> dict:
        """Create a Foundry project under the account. Polls provisioningState."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/projects/{project_name}?api-version={COG_API_VERSION}"
        )
        body = {
            "location": location,
            "identity": {"type": "SystemAssigned"},
            "properties": {"displayName": display_name or project_name},
        }
        return await self._cog_put(url, body, f"Foundry project '{project_name}'")

    async def create_model_deployment(
        self, subscription_id: str, resource_group: str, account_name: str,
        deployment_name: str, model_name: str, model_version: str,
        sku_name: str = "GlobalStandard", capacity: int = 10,
    ) -> dict:
        """Deploy an OpenAI model on the Foundry account. Polls provisioningState."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/deployments/{deployment_name}?api-version={COG_API_VERSION}"
        )
        body = {
            "sku": {"name": sku_name, "capacity": capacity},
            "properties": {
                "model": {"format": "OpenAI", "name": model_name, "version": model_version},
            },
        }
        return await self._cog_put(url, body, f"Model deployment '{deployment_name}'")

    async def create_fabric_data_agent_connection(
        self, subscription_id: str, resource_group: str, account_name: str,
        project_name: str, connection_name: str, workspace_id: str, artifact_id: str,
    ) -> dict:
        """Create a project connection to a published Fabric data agent, carrying the
        Fabric workspace-id + artifact-id. PREVIEW and best-effort — the connection
        shape for Fabric data agents is evolving, so the deployer treats a failure
        here as a skippable step (the user can add the connection in the portal)."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/projects/{project_name}/connections/{connection_name}"
            f"?api-version={COG_API_VERSION}"
        )
        body = {
            "properties": {
                "category": "CustomKeys",
                "target": f"https://fabric.microsoft.com/groups/{workspace_id}/aiskills/{artifact_id}",
                "authType": "CustomKeys",
                "isSharedToAll": False,
                "credentials": {"keys": {"workspace-id": workspace_id, "artifact-id": artifact_id}},
                "metadata": {"type": "fabric_dataagent"},
            }
        }
        resp = await self._arm_client.put(url, json=body)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                detail = resp.json().get("error", {}).get("message", detail)[:500]
            except Exception:
                pass
            raise AzureError(resp.status_code, detail)
        return resp.json()

    async def delete_foundry_account(
        self, subscription_id: str, resource_group: str, account_name: str
    ) -> bool:
        """Delete the Foundry account. Model deployments cascade, but nested
        **projects do NOT** — ARM rejects the account delete with
        ``CannotDeleteResource`` while any project exists. So delete the
        projects first, then the account. 404-tolerant: returns False if the
        account was already gone."""
        base = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        )

        # 1. Delete nested projects first (the blocker).
        try:
            projects_resp = await self._arm_client.get(
                f"{base}/projects?api-version={COG_API_VERSION}"
            )
            if projects_resp.status_code < 400:
                for proj in projects_resp.json().get("value", []):
                    proj_name = proj.get("name", "").split("/")[-1]
                    if not proj_name:
                        continue
                    try:
                        await self._arm_client.delete(
                            f"{base}/projects/{proj_name}?api-version={COG_API_VERSION}"
                        )
                    except Exception as pe:  # noqa: BLE001 — best-effort per project
                        logger.warning("[foundry] project '%s' delete failed: %s", proj_name, pe)
        except Exception as le:  # noqa: BLE001 — listing is best-effort
            logger.warning("[foundry] could not list projects for '%s': %s", account_name, le)

        # 2. Delete the account.
        resp = await self._arm_client.delete(f"{base}?api-version={COG_API_VERSION}")
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise AzureError(resp.status_code, resp.text[:300])
        return True

    # ── Azure AI Search (Foundry IQ retrieval engine, preview) ───────────
    # The new Foundry grounds a Fabric data agent through Foundry IQ, which runs
    # on an Azure AI Search service. We provision the service (with a managed
    # identity so it can call the Foundry account back), then the caller wires the
    # 3-way RBAC. Standing-cost resource — teardown must always remove it.

    async def register_search_provider(self, subscription_id: str) -> None:
        """Register the Microsoft.Search resource provider on the subscription
        (idempotent). New subscriptions that never used AI Search fail creation
        with MissingSubscriptionRegistration until this runs."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/providers/Microsoft.Search"
            f"/register?api-version=2021-04-01"
        )
        try:
            await self._arm_request("POST", url)
        except AzureError as e:
            logger.warning("Microsoft.Search provider register returned: %s", e.detail[:120])

    async def create_search_service(
        self, subscription_id: str, resource_group: str, name: str, location: str,
        sku: str = "standard",
    ) -> dict:
        """Create an Azure AI Search service with a system-assigned managed identity
        (required so Foundry IQ can authenticate the search service back to the
        Foundry account). Idempotent PUT; polls until provisioningState succeeds.
        Returns the service resource (incl. identity.principalId)."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Search/searchServices/{name}"
            f"?api-version={SEARCH_API_VERSION}"
        )
        body = {
            "location": location,
            "sku": {"name": sku},
            "identity": {"type": "SystemAssigned"},
            "properties": {
                "replicaCount": 1,
                "partitionCount": 1,
                "hostingMode": "default",
                # Allow BOTH Entra-ID (RBAC — used by the project + Foundry IQ runtime)
                # AND admin api-keys, so the backend can create the Foundry IQ knowledge
                # source/base with the admin key (fetched via ARM) WITHOUT each user
                # consenting to the search.azure.com delegated scope. Keyless-only made
                # the knowledge-base step fail with 401 for non-consented users.
                "authOptions": {"aadOrApiKey": {"aadAuthFailureMode": "http403"}},
                "disableLocalAuth": False,
            },
        }
        transient = (502, 503, 504)
        for attempt in range(4):
            try:
                resp = await self._arm_client.put(url, json=body)
            except httpx.TransportError as e:
                logger.warning("Search service PUT network error (attempt %d/4): %s", attempt + 1, e)
                await asyncio.sleep(5 * (attempt + 1))
                continue
            if resp.status_code in transient:
                logger.warning("Search service PUT %d (transient gateway error, attempt %d/4): %s",
                               resp.status_code, attempt + 1, self._arm_error_detail(resp))
                await asyncio.sleep(5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise AzureError(resp.status_code, self._arm_error_detail(resp))
            break  # accepted — poll for the terminal state below
        # Even if every PUT attempt gateway-timed-out, the service may still be
        # provisioning; the poll below picks it up (or times out if it never appears).

        start = time.time()
        timeout = 600
        while time.time() - start < timeout:
            await asyncio.sleep(10)
            try:
                svc = (await self._arm_request("GET", url)).json()
            except httpx.TransportError as e:
                logger.debug("Search poll network error (retrying): %s", e)
                continue
            except AzureError as e:
                if e.status == 404:
                    continue
                raise
            state = (svc.get("properties", {}).get("provisioningState") or "").lower()
            logger.debug("Search service %s provisioningState: %s", name, state)
            if state == "succeeded":
                return svc
            if state == "failed":
                raise AzureError(500, f"Search service '{name}' provisioning failed")
        raise AzureError(504, f"Search service '{name}' provisioning timed out after {timeout}s")

    async def get_search_service(
        self, subscription_id: str, resource_group: str, name: str
    ) -> dict:
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Search/searchServices/{name}"
            f"?api-version={SEARCH_API_VERSION}"
        )
        return (await self._arm_request("GET", url)).json()

    async def delete_search_service(
        self, subscription_id: str, resource_group: str, name: str
    ) -> bool:
        """Delete an Azure AI Search service. 404-tolerant: returns False if gone."""
        url = (
            f"{ARM_API}/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Search/searchServices/{name}"
            f"?api-version={SEARCH_API_VERSION}"
        )
        resp = await self._arm_client.delete(url)
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise AzureError(resp.status_code, resp.text[:300])
        return True

    # ── Foundry project connection (RemoteTool MCP → knowledge base) ──────
    # The agent reaches the knowledge base through a project connection that
    # targets the KB's MCP endpoint, authenticating with the project's managed
    # identity. ARM control-plane (api-version 2025-10-01-preview).

    @staticmethod
    def _project_resource_id(
        subscription_id: str, resource_group: str, account: str, project: str
    ) -> str:
        return (
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account}/projects/{project}"
        )

    async def create_kb_connection(
        self, subscription_id: str, resource_group: str, account: str, project: str,
        connection_name: str, search_endpoint: str, knowledge_base: str,
    ) -> dict:
        """Create a RemoteTool project connection pointing at the knowledge base's
        MCP endpoint (project-managed-identity auth)."""
        mcp_target = f"{search_endpoint}/knowledgebases/{knowledge_base}/mcp?api-version=2026-05-01-preview"
        url = (
            f"{ARM_API}{self._project_resource_id(subscription_id, resource_group, account, project)}"
            f"/connections/{connection_name}?api-version=2025-10-01-preview"
        )
        body = {
            "name": connection_name,
            "type": "Microsoft.MachineLearningServices/workspaces/connections",
            "properties": {
                "authType": "ProjectManagedIdentity",
                "category": "RemoteTool",
                "target": mcp_target,
                "isSharedToAll": True,
                "audience": "https://search.azure.com/",
                "metadata": {"ApiType": "Azure"},
            },
        }
        resp = await self._arm_client.put(url, json=body)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                detail = resp.json().get("error", {}).get("message", detail)[:500]
            except Exception:
                pass
            raise AzureError(resp.status_code, detail)
        return resp.json() if resp.text else {}

    async def delete_kb_connection(
        self, subscription_id: str, resource_group: str, account: str, project: str,
        connection_name: str,
    ) -> bool:
        """Delete the project connection. 404-tolerant."""
        url = (
            f"{ARM_API}{self._project_resource_id(subscription_id, resource_group, account, project)}"
            f"/connections/{connection_name}?api-version=2025-10-01-preview"
        )
        resp = await self._arm_client.delete(url)
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise AzureError(resp.status_code, resp.text[:300])
        return True
