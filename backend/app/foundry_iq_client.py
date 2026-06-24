"""Foundry IQ (Azure AI Search) data-plane client — knowledge sources + bases.

The new Microsoft Foundry grounds a Fabric data agent through Foundry IQ, which
runs on an Azure AI Search service. Grounding requires two data-plane objects on
the search service:

  * a *knowledge source* of kind ``fabricDataAgent`` (carries the Fabric
    workspace + data-agent ids), and
  * a *knowledge base* that references the source and a chat model (the Foundry
    ``gpt-4o-mini`` deployment).

These use the Azure AI Search REST API (host ``{service}.search.windows.net``),
which has a DIFFERENT token audience (``https://search.azure.com``) than ARM, so
it gets its own small client. Shapes verified against a working live setup.

All of this is PREVIEW (api-version 2026-05-01-preview) and may change.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

SEARCH_DATAPLANE_API_VERSION = "2026-05-01-preview"
SEARCH_TOKEN_AUDIENCE = "https://search.azure.com"


class FoundryIQError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Foundry IQ (Search) API {status}: {detail}")


class FoundryIQClient:
    """Async client for the Azure AI Search data-plane (Foundry IQ KB/KS)."""

    def __init__(self, service_name: str, *, token: str | None = None, api_key: str | None = None):
        self._endpoint = f"https://{service_name}.search.windows.net"
        headers = {"Content-Type": "application/json"}
        # Prefer the service admin key (works for everyone); fall back to a
        # delegated search.azure.com bearer token when only that is available.
        if api_key:
            headers["api-key"] = api_key
        elif token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(headers=headers, timeout=60.0)

    async def close(self):
        await self._client.aclose()

    async def _put(self, path: str, body: dict) -> dict:
        url = f"{self._endpoint}/{path}?api-version={SEARCH_DATAPLANE_API_VERSION}"
        resp = await self._client.put(url, json=body)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                err = resp.json()
                detail = (err.get("error", {}).get("message") or detail)[:500]
            except Exception:
                pass
            raise FoundryIQError(resp.status_code, detail)
        return resp.json() if resp.text else {}

    async def create_fabric_knowledge_source(
        self, name: str, workspace_id: str, data_agent_id: str
    ) -> dict:
        """Create/update a Fabric-data-agent knowledge source (live data, no index)."""
        body = {
            "name": name,
            "kind": "fabricDataAgent",
            "fabricDataAgentParameters": {
                "fabricEndpoint": None,
                "workspaceId": workspace_id,
                "dataAgentId": data_agent_id,
            },
        }
        return await self._put(f"knowledgeSources/{name}", body)

    async def create_knowledge_base(
        self,
        name: str,
        knowledge_source_name: str,
        foundry_account: str,
        model_deployment: str,
        model_name: str = "gpt-4o-mini",
    ) -> dict:
        """Create/update a knowledge base that grounds on the knowledge source and
        uses the Foundry ``gpt-4o-mini`` deployment for retrieval reasoning."""
        body = {
            "name": name,
            "description": "",
            "retrievalInstructions": "",
            "answerInstructions": "",
            "outputMode": "extractiveData",
            "knowledgeSources": [{"name": knowledge_source_name}],
            "models": [
                {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": f"https://{foundry_account}.openai.azure.com",
                        "deploymentId": model_deployment,
                        "modelName": model_name,
                        "apiKey": None,
                        "authIdentity": None,
                    },
                }
            ],
            "retrievalReasoningEffort": {"kind": "low"},
        }
        return await self._put(f"knowledgeBases/{name}", body)


# ── Foundry Agent Service (create an agent that calls the KB via MCP) ─────────

DEFAULT_AGENT_INSTRUCTIONS = (
    "You are a helpful assistant that answers questions using the knowledge base.\n"
    "Use the knowledge base tool to answer the user's questions. If the knowledge "
    "base doesn't contain the answer, respond with \"I don't know\".\n"
    "When you use information from the knowledge base, include citations to the "
    "retrieved sources."
)


class FoundryAgentError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"Foundry Agent API {status}: {detail}")


class FoundryAgentClient:
    """Async client for Foundry Agent Service (project data-plane, ``ai.azure.com``
    token). Creates a 'prompt' agent that calls a Foundry IQ knowledge base via an
    MCP tool. ``project_endpoint`` looks like
    ``https://<acct>.services.ai.azure.com/api/projects/<proj>``."""

    AGENT_API_VERSION = "v1"

    def __init__(self, project_endpoint: str, *, token: str | None = None, api_key: str | None = None):
        self._endpoint = project_endpoint.rstrip("/")
        headers = {"Content-Type": "application/json"}
        # Prefer the delegated ai.azure.com bearer token (known-good path); fall
        # back to the Foundry account key for users who haven't consented.
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif api_key:
            headers["api-key"] = api_key
        self._client = httpx.AsyncClient(headers=headers, timeout=60.0)

    async def close(self):
        await self._client.aclose()

    async def create_agent(
        self, name: str, model_deployment: str, search_endpoint: str,
        knowledge_base: str, connection_name: str, instructions: str = "",
    ) -> dict:
        """Create a prompt agent wired to the knowledge base's MCP tool."""
        mcp_url = f"{search_endpoint}/knowledgebases/{knowledge_base}/mcp?api-version=2026-05-01-preview"
        body = {
            "name": name,
            "definition": {
                "model": model_deployment,
                "instructions": instructions or DEFAULT_AGENT_INSTRUCTIONS,
                "tools": [
                    {
                        "server_label": "knowledge-base",
                        "server_url": mcp_url,
                        "require_approval": "never",
                        "allowed_tools": ["knowledge_base_retrieve"],
                        "project_connection_id": connection_name,
                        "type": "mcp",
                    }
                ],
                "kind": "prompt",
            },
        }
        url = f"{self._endpoint}/agents?api-version={self.AGENT_API_VERSION}"
        resp = await self._client.post(url, json=body)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                err = resp.json()
                detail = (err.get("error", {}).get("message") or detail)[:500]
            except Exception:
                pass
            raise FoundryAgentError(resp.status_code, detail)
        return resp.json() if resp.text else {}

    async def delete_agent(self, name: str) -> bool:
        url = f"{self._endpoint}/agents/{name}?api-version={self.AGENT_API_VERSION}"
        resp = await self._client.delete(url)
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise FoundryAgentError(resp.status_code, resp.text[:300])
        return True
