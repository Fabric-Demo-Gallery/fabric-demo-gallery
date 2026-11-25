"""Foundry project data-plane client for the AI agent packs.

Uses the signed-in user's delegated ``ai.azure.com`` token (the same scope the
Fabric & Foundry scenario already requests). Account-key auth is deliberately
not offered: many tenants enforce ``disableLocalAuth`` on AI Services accounts.

Endpoints (verified end to end):
  POST {project}/openai/v1/files                    multipart, purpose=assistants
  POST {project}/openai/v1/vector_stores            {name, file_ids}
  GET  {project}/openai/v1/vector_stores/{id}       poll until completed
  POST {project}/agents?api-version=v1              prompt agent definition
  POST {project}/openai/v1/evals                    agent evaluation (built-in evaluators)
  POST {project}/openai/v1/evals/{id}/runs          run it against an agent with inline queries
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

AGENT_API_VERSION = "v1"
# A role assignment made just before the first call can take a few minutes to
# reach the data plane, and a new project can briefly answer "Project not
# found"; keep retrying 401/403/404 until the first call succeeds.
AUTH_PROPAGATION_TIMEOUT_S = 300
AUTH_RETRY_DELAY_S = 15
VECTOR_STORE_TIMEOUT_S = 180
WARM_UP_TIMEOUT_S = 240
WARM_UP_RETRY_DELAY_S = 15
# Built-in Foundry evaluators for agents. Task adherence is pass/fail (0 or 1);
# the others are scored 1-5 by the judge model.
AGENT_EVALUATORS = {
    "builtin.task_adherence": "Task adherence",
    "builtin.intent_resolution": "Intent resolution",
    "builtin.tool_call_accuracy": "Tool call accuracy",
}
EVALUATOR_SCALES = {"Task adherence": 1}


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

    @staticmethod
    def _is_propagating(resp: httpx.Response) -> bool:
        if resp.status_code in (401, 403):
            return True
        return resp.status_code == 404 and "project not found" in _error_detail(resp).lower()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        deadline = time.monotonic() + AUTH_PROPAGATION_TIMEOUT_S
        while True:
            resp = await self._client.request(method, f"{self._endpoint}{path}", **kwargs)
            if self._is_propagating(resp) and not self._authorized and time.monotonic() < deadline:
                logger.info("[agents] %s %s -> %s; waiting for propagation", method, path, resp.status_code)
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

    async def create_agent_evaluation(self, name: str, judge_model: str) -> str:
        """An evaluation definition that scores an agent's answers and tool calls."""
        response = {"query": "{{item.query}}", "response": "{{sample.output_items}}"}
        criteria = [
            {
                "type": "azure_ai_evaluator",
                "name": label,
                "evaluator_name": evaluator,
                "initialization_parameters": {"deployment_name": judge_model},
                "data_mapping": (
                    response | {"tool_definitions": "{{sample.tool_definitions}}"}
                    if evaluator == "builtin.tool_call_accuracy" else response
                ),
            }
            for evaluator, label in AGENT_EVALUATORS.items()
        ]
        body = await self._request("POST", "/openai/v1/evals", json={
            "name": name,
            "data_source_config": {
                "type": "custom",
                "item_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                "include_sample_schema": True,
            },
            "testing_criteria": criteria,
        })
        return body["id"]

    async def start_agent_evaluation_run(self, eval_id: str, agent: str, queries: list[str]) -> str:
        """Run the evaluation against an agent: Foundry sends each query to the
        agent, then the judge model scores the answers. Returns the run id."""
        body = await self._request("POST", f"/openai/v1/evals/{eval_id}/runs", json={
            "name": f"{agent} test set",
            "data_source": {
                "type": "azure_ai_target_completions",
                "source": {"type": "file_content", "content": [{"item": {"query": q}} for q in queries]},
                "input_messages": {"type": "template", "template": [
                    {"type": "message", "role": "user", "content": {"type": "input_text", "text": "{{item.query}}"}},
                ]},
                "target": {"type": "azure_ai_agent", "name": agent},
            },
        })
        return body["id"]

    async def get_evaluation_run(self, eval_id: str, run_id: str) -> dict:
        return await self._request("GET", f"/openai/v1/evals/{eval_id}/runs/{run_id}")

    async def list_evaluation_items(self, eval_id: str, run_id: str) -> list[dict]:
        body = await self._request("GET", f"/openai/v1/evals/{eval_id}/runs/{run_id}/output_items")
        return body.get("data", [])

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
