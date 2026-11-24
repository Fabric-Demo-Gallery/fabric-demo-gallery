"""Foundry project data-plane client for the AI agent packs.

Uses the signed-in user's delegated ``ai.azure.com`` token (the same scope the
Fabric & Foundry scenario already requests). Account-key auth is deliberately
not offered: many tenants enforce ``disableLocalAuth`` on AI Services accounts.

Endpoints (verified end to end):
  POST {project}/openai/v1/files                    multipart, purpose=assistants
  POST {project}/openai/v1/vector_stores            {name, file_ids}
  GET  {project}/openai/v1/vector_stores/{id}       poll until completed
  POST {project}/agents?api-version=v1              prompt agent definition
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

AGENT_API_VERSION = "v1"
# A role assignment made just before the first call can take a few minutes to
# reach the data plane; keep retrying 401/403 until the first call succeeds.
AUTH_PROPAGATION_TIMEOUT_S = 300
AUTH_RETRY_DELAY_S = 15
VECTOR_STORE_TIMEOUT_S = 180
WARM_UP_TIMEOUT_S = 240
WARM_UP_RETRY_DELAY_S = 15


class FoundryProjectError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Foundry project API {status}: {detail}")


def _error_detail(resp: httpx.Response) -> str:
    detail = resp.text[:500]
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict) and err.get("message"):
            detail = str(err["message"])[:500]
    except ValueError:
        pass
    return detail


class FoundryProjectClient:
    def __init__(
        self,
        project_endpoint: str,
        token: str,
        *,
        sleep=asyncio.sleep,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._endpoint = project_endpoint.rstrip("/")
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, timeout=180.0, transport=transport
        )
        self._authorized = False
        self._sleep = sleep

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        deadline = time.monotonic() + AUTH_PROPAGATION_TIMEOUT_S
        while True:
            resp = await self._client.request(method, f"{self._endpoint}{path}", **kwargs)
            if resp.status_code in (401, 403) and not self._authorized and time.monotonic() < deadline:
                logger.info("[agents] %s %s -> %s; waiting for role propagation", method, path, resp.status_code)
                await self._sleep(AUTH_RETRY_DELAY_S)
                continue
            if resp.status_code >= 400:
                raise FoundryProjectError(resp.status_code, _error_detail(resp))
            self._authorized = True
            return resp.json() if resp.content else {}

    async def upload_file(self, filename: str, content: bytes, content_type: str) -> str:
        body = await self._request(
            "POST", "/openai/v1/files",
            data={"purpose": "assistants"},
            files={"file": (filename, content, content_type)},
        )
        return body["id"]

    async def create_vector_store(self, name: str, file_ids: list[str]) -> str:
        """Create a vector store and wait until every file is indexed."""
        store = await self._request("POST", "/openai/v1/vector_stores", json={"name": name, "file_ids": file_ids})
        store_id = store["id"]
        deadline = time.monotonic() + VECTOR_STORE_TIMEOUT_S
        while True:
            counts = store.get("file_counts") or {}
            if counts.get("failed"):
                raise FoundryProjectError(500, f"Vector store '{name}': {counts['failed']} file(s) failed to index.")
            if store.get("status") == "completed" and not counts.get("in_progress"):
                return store_id
            if time.monotonic() > deadline:
                raise FoundryProjectError(504, f"Vector store '{name}' was not ready after {VECTOR_STORE_TIMEOUT_S}s.")
            await self._sleep(3)
            store = await self._request("GET", f"/openai/v1/vector_stores/{store_id}")

    async def create_agent(
        self, name: str, model: str, instructions: str, tools: list[dict], description: str = ""
    ) -> dict:
        body: dict = {
            "name": name,
            "definition": {
                "kind": "prompt",
                "model": model,
                "instructions": instructions,
                "tools": tools,
            },
        }
        if description:
            body["description"] = description
        return await self._request("POST", f"/agents?api-version={AGENT_API_VERSION}", json=body)

    async def warm_up(self, model: str, timeout: float = WARM_UP_TIMEOUT_S) -> bool:
        """Send a tiny request to the model until it stops throttling (429).
        Returns False if it still throttles after ``timeout``; other errors raise."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                await self._request(
                    "POST", "/openai/v1/responses",
                    json={"model": model, "input": "Reply with OK.", "max_output_tokens": 32},
                )
                return True
            except FoundryProjectError as e:
                if e.status != 429:
                    raise
                if time.monotonic() > deadline:
                    return False
                await self._sleep(WARM_UP_RETRY_DELAY_S)
