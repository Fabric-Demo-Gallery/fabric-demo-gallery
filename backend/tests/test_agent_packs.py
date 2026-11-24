import asyncio
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import agent_packs
from app import job_store as job_store_module
from app.auth import get_user_token
from app.azure_client import FOUNDRY_USER, AzureError
from app.foundry_project_client import FoundryProjectClient, FoundryProjectError

SUB = "00000000-0000-0000-0000-000000000000"


class FakeAzure:
    """Async stand-in for AzureClient covering the agent pack ARM calls."""

    def __init__(self, permissions=None):
        self.permissions = permissions if permissions is not None else [{"actions": ["*"], "notActions": []}]
        self.calls: list[tuple] = []

    async def list_caller_permissions(self, sub):
        return self.permissions

    async def check_model_capacity(self, sub, name, version):
        # A different SKU listed first must not be mistaken for GlobalStandard quota.
        return [
            {"location": "swedencentral", "availableCapacity": 0, "skuName": "Standard"},
            {"location": "swedencentral", "availableCapacity": 1790, "skuName": "GlobalStandard"},
        ]

    async def resource_group_exists(self, sub, name):
        return False

    async def register_providers(self, sub, namespaces):
        self.calls.append(("providers", tuple(namespaces)))

    async def create_tagged_resource_group(self, sub, name, location, tags):
        self.calls.append(("rg", name, tags))

    async def create_foundry_account(self, sub, rg, account, location):
        self.calls.append(("account", account))

    async def create_foundry_project(self, sub, rg, account, project, location, display_name=None):
        self.calls.append(("project", project))

    async def create_model_deployment(self, sub, rg, account, deployment, name, version, sku_name, capacity):
        self.calls.append(("model", name, capacity))

    def get_caller_oid(self):
        return "caller-oid"

    def get_caller_entra_admin(self):
        return "user@contoso.com", "caller-oid", "tenant-1"

    async def assign_role(self, scope, role, principal_id, principal_type):
        self.calls.append(("role", scope, role, principal_id, principal_type))

    async def delete_resource_group(self, sub, name):
        self.calls.append(("delete-rg", name))
        return True


class FakeProject:
    """Stand-in for FoundryProjectClient that records data-plane calls."""

    def __init__(self, endpoint, token, fail_on_agent=None):
        self.endpoint, self.token = endpoint, token
        self.uploads: list[str] = []
        self.stores: list[tuple[str, list[str]]] = []
        self.agents: list[dict] = []
        self.fail_on_agent = fail_on_agent
        self.warmed: list[str] = []
        self.closed = False

    async def warm_up(self, model):
        self.warmed.append(model)
        return True

    async def upload_file(self, filename, content, content_type):
        assert content, filename
        self.uploads.append(filename)
        return f"file-{len(self.uploads)}"

    async def create_vector_store(self, name, file_ids):
        self.stores.append((name, file_ids))
        return f"vs-{len(self.stores)}"

    async def create_agent(self, name, model, instructions, tools, description=""):
        if name == self.fail_on_agent:
            raise FoundryProjectError(400, "Tool not supported in this region")
        self.agents.append({"name": name, "model": model, "instructions": instructions, "tools": tools})
        return {"name": name}

    async def close(self):
        self.closed = True


async def collect(gen):
    return [event async for event in gen]


def run_deploy(fake_az, agent_token="ai-token", fail_on_agent=None):
    pack = agent_packs.load_pack("manufacturing")
    recorded: list = []
    projects: list[FakeProject] = []

    def factory(endpoint, token):
        projects.append(FakeProject(endpoint, token, fail_on_agent))
        return projects[-1]

    events = asyncio.run(collect(agent_packs.deploy_pack(
        fake_az, pack, agent_token, SUB, "rg-fdg-agents-test", "swedencentral",
        on_resources=recorded.append, project_client_factory=factory,
    )))
    return events, recorded, (projects[0] if projects else None)


class PackContentTests(unittest.TestCase):
    def test_manufacturing_pack_files_resolve(self):
        pack = agent_packs.load_pack("manufacturing")
        self.assertIn(pack["defaultRegion"], pack["regions"])
        self.assertTrue(pack["modelCandidates"])
        for agent in pack["agents"]:
            # Foundry agent names: letters, digits and hyphens.
            self.assertRegex(agent["id"], r"^[a-z0-9][a-z0-9-]{0,62}$")
            self.assertTrue(agent_packs.pack_file(pack, agent["instructions"]).read_text(encoding="utf-8").strip())
            for rel in agent["knowledge"]:
                path = agent_packs.pack_file(pack, rel)
                self.assertTrue(path.is_file(), rel)
                self.assertIn(path.suffix, agent_packs.CONTENT_TYPES)
            for name in agent["data"]:
                path = agent_packs.data_file(pack, name)
                self.assertTrue(path.is_file(), name)
                self.assertIn(path.suffix, agent_packs.CONTENT_TYPES)

    def test_instructions_reference_every_attached_data_file(self):
        pack = agent_packs.load_pack("manufacturing")
        for agent in pack["agents"]:
            text = agent_packs.pack_file(pack, agent["instructions"]).read_text(encoding="utf-8")
            for name in agent["data"]:
                self.assertIn(name, text, f"{agent['id']} instructions don't mention {name}")

    def test_pack_paths_cannot_escape(self):
        pack = agent_packs.load_pack("manufacturing")
        with self.assertRaises(agent_packs.AgentPackError):
            agent_packs.pack_file(pack, "../../backend/app/auth.py")

    def test_list_packs(self):
        packs = agent_packs.list_packs()
        manufacturing = next(p for p in packs if p["id"] == "manufacturing")
        self.assertEqual(len(manufacturing["agents"]), 4)


class HelperTests(unittest.TestCase):
    def test_action_allowed_honours_not_actions(self):
        action = "Microsoft.Authorization/roleAssignments/write"
        contributor = [{"actions": ["*"], "notActions": ["Microsoft.Authorization/*/Write"]}]
        uaa = [{"actions": ["Microsoft.Authorization/*"], "notActions": []}]
        self.assertTrue(agent_packs._action_allowed([{"actions": ["*"], "notActions": []}], action))
        self.assertFalse(agent_packs._action_allowed(contributor, action))
        self.assertTrue(agent_packs._action_allowed(contributor + uaa, action))

    def test_agent_tools(self):
        tools = agent_packs._agent_tools(
            {"data": ["a.csv", "b.csv"]}, "vs-1", {"a.csv": "file-a", "b.csv": "file-b"}
        )
        self.assertEqual(tools[0], {"type": "file_search", "vector_store_ids": ["vs-1"]})
        self.assertEqual(tools[1]["container"], {"type": "auto", "file_ids": ["file-a", "file-b"]})
        self.assertEqual(agent_packs._agent_tools({"data": []}, None, {}), [])

    def test_resource_group_name_and_portal_url(self):
        self.assertRegex(agent_packs.new_resource_group_name("manufacturing"), r"^rg-fdg-agents-manufacturing-[0-9a-f]{6}$")
        url = agent_packs.portal_url(SUB, "rg", "acct", "tenant-1")
        self.assertIn(f"/subscriptions/{SUB}/resourceGroups/rg/", url)
        self.assertTrue(url.endswith("&tid=tenant-1"))


class DeployFlowTests(unittest.TestCase):
    def test_happy_path_creates_all_agents_with_grounding(self):
        fake = FakeAzure()
        events, recorded, project = run_deploy(fake)
        self.assertEqual(events[0]["event"], "plan")
        self.assertNotIn("error", [e["event"] for e in events])

        # 5 knowledge documents + 3 data files, each uploaded exactly once.
        self.assertEqual(len(project.uploads), 8)
        self.assertEqual(len(set(project.uploads)), 8)
        # Shift handover is data-only (no knowledge documents), so 3 indexes.
        self.assertEqual(len(project.stores), 3)
        self.assertEqual(project.token, "ai-token")
        self.assertEqual(project.warmed, ["gpt-5.4-mini"])
        self.assertTrue(project.closed)

        by_name = {a["name"]: a for a in project.agents}
        self.assertEqual(set(by_name), {"maintenance-assistant", "quality-analyst", "shift-handover", "visual-inspector"})
        tool_types = {name: [t["type"] for t in a["tools"]] for name, a in by_name.items()}
        self.assertEqual(tool_types["maintenance-assistant"], ["file_search", "code_interpreter"])
        self.assertEqual(tool_types["shift-handover"], ["code_interpreter"])
        self.assertEqual(tool_types["visual-inspector"], ["file_search"])
        self.assertEqual(len(by_name["quality-analyst"]["tools"][1]["container"]["file_ids"]), 3)
        self.assertTrue(all(a["model"] == "gpt-5.4-mini" for a in project.agents))
        self.assertIn(("model", "gpt-5.4-mini", agent_packs.MODEL_CAPACITY), fake.calls)

        role = next(c for c in fake.calls if c[0] == "role")
        self.assertEqual(role[2:], (FOUNDRY_USER, "caller-oid", "User"))
        self.assertTrue(role[1].endswith("/providers/Microsoft.CognitiveServices/accounts/" + recorded[-1]["foundryAccount"]))

        done = json.loads(events[-1]["data"]["detail"])
        self.assertEqual(len(done["agents"]), 4)
        self.assertEqual(done["azure"]["resourceGroup"], "rg-fdg-agents-test")
        self.assertIn("&tid=tenant-1", done["azure"]["portalUrl"])
        self.assertEqual(recorded[-1]["portalUrl"], done["azure"]["portalUrl"])
        rg_call = next(c for c in fake.calls if c[0] == "rg")
        self.assertEqual(rg_call[2]["created-by"], agent_packs.RESOURCE_GROUP_TAG)

    def test_missing_agent_token_fails_before_creating_anything(self):
        fake = FakeAzure()
        events, recorded, project = run_deploy(fake, agent_token="")
        self.assertEqual(events[-1]["event"], "error")
        self.assertIn("Foundry", events[-1]["data"]["message"])
        self.assertEqual(fake.calls, [])
        self.assertEqual(recorded, [])
        self.assertIsNone(project)

    def test_missing_role_assignment_permission_fails_before_creating_anything(self):
        fake = FakeAzure(permissions=[{"actions": ["*"], "notActions": ["Microsoft.Authorization/*/Write"]}])
        events, recorded, _ = run_deploy(fake)
        self.assertEqual(events[-1]["event"], "error")
        self.assertIn("roleAssignments/write", events[-1]["data"]["message"])
        self.assertEqual(fake.calls, [])
        self.assertEqual(recorded, [])

    def test_model_falls_back_to_next_candidate(self):
        fake = FakeAzure()

        async def flaky(sub, rg, account, deployment, name, version, sku_name, capacity):
            if name == "gpt-5.4-mini":
                raise AzureError(400, "InsufficientQuota")
            fake.calls.append(("model", name, capacity))

        fake.create_model_deployment = flaky
        events, _, project = run_deploy(fake)
        done = json.loads(events[-1]["data"]["detail"])
        self.assertEqual(done["azure"]["model"], "gpt-5.4")
        self.assertTrue(all(a["model"] == "gpt-5.4" for a in project.agents))

    def test_agent_failure_tears_down_resource_group(self):
        fake = FakeAzure()
        events, recorded, project = run_deploy(fake, fail_on_agent="shift-handover")
        self.assertEqual(events[-1]["event"], "error")
        self.assertIn("Tool not supported", events[-1]["data"]["message"])
        self.assertIn(("delete-rg", "rg-fdg-agents-test"), fake.calls)
        self.assertIsNone(recorded[-1])
        self.assertTrue(project.closed)
        failed = [e for e in events if e["event"] == "step" and e["data"]["status"] == "failed"]
        self.assertEqual(failed[0]["data"]["name"], "agents")


class ProjectClientTests(unittest.TestCase):
    def run_client(self, handler, coro_fn):
        sleeps: list[float] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        async def go():
            client = FoundryProjectClient(
                "https://acct.services.ai.azure.com/api/projects/p", "tok",
                sleep=fake_sleep, transport=httpx.MockTransport(handler),
            )
            try:
                return await coro_fn(client)
            finally:
                await client.close()

        return asyncio.run(go()), sleeps

    def test_retries_auth_errors_until_first_success_then_fails_fast(self):
        responses = iter([403, 403, 200, 403])

        def handler(request):
            self.assertEqual(request.headers["authorization"], "Bearer tok")
            status = next(responses)
            return httpx.Response(status, json={"id": "file-1"} if status == 200 else {"error": {"message": "denied"}})

        async def go(client):
            file_id = await client.upload_file("a.csv", b"x", "text/csv")
            with self.assertRaises(FoundryProjectError) as ctx:
                await client.upload_file("b.csv", b"y", "text/csv")
            return file_id, ctx.exception

        (file_id, err), sleeps = self.run_client(handler, go)
        self.assertEqual(file_id, "file-1")
        self.assertEqual(err.status, 403)
        self.assertEqual(err.detail, "denied")
        self.assertEqual(len(sleeps), 2)

    def test_vector_store_waits_until_indexed(self):
        states = iter([
            {"id": "vs-1", "status": "in_progress", "file_counts": {"in_progress": 2}},
            {"id": "vs-1", "status": "in_progress", "file_counts": {"in_progress": 1}},
            {"id": "vs-1", "status": "completed", "file_counts": {"in_progress": 0, "completed": 2}},
        ])
        seen: list[str] = []

        def handler(request):
            seen.append(f"{request.method} {request.url.path}")
            return httpx.Response(200, json=next(states))

        store_id, sleeps = self.run_client(handler, lambda c: c.create_vector_store("kb", ["f1", "f2"]))
        self.assertEqual(store_id, "vs-1")
        self.assertEqual(seen[0], "POST /api/projects/p/openai/v1/vector_stores")
        self.assertEqual(seen[-1], "GET /api/projects/p/openai/v1/vector_stores/vs-1")
        self.assertEqual(len(sleeps), 2)

    def test_vector_store_reports_failed_files(self):
        def handler(request):
            return httpx.Response(200, json={"id": "vs-1", "status": "completed", "file_counts": {"failed": 1}})

        with self.assertRaises(FoundryProjectError):
            self.run_client(handler, lambda c: c.create_vector_store("kb", ["f1"]))

    def test_warm_up_retries_throttling_then_succeeds(self):
        statuses = iter([429, 429, 200])
        bodies: list[dict] = []

        def handler(request):
            bodies.append(json.loads(request.content))
            status = next(statuses)
            return httpx.Response(status, json={"output": []} if status == 200 else {"error": {"message": "rate limit"}})

        ready, sleeps = self.run_client(handler, lambda c: c.warm_up("gpt-5.4-mini"))
        self.assertTrue(ready)
        self.assertEqual(len(sleeps), 2)
        self.assertEqual(bodies[0]["model"], "gpt-5.4-mini")

    def test_warm_up_gives_up_after_timeout_but_raises_other_errors(self):
        throttled, _ = self.run_client(
            lambda request: httpx.Response(429, json={"error": {"message": "rate limit"}}),
            lambda c: c.warm_up("m", timeout=0),
        )
        self.assertFalse(throttled)
        with self.assertRaises(FoundryProjectError):
            self.run_client(lambda request: httpx.Response(404, json={"error": {"message": "no deployment"}}),
                            lambda c: c.warm_up("m"))

    def test_create_agent_body(self):
        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"name": "a"})

        tools = [{"type": "file_search", "vector_store_ids": ["vs-1"]}]
        self.run_client(handler, lambda c: c.create_agent("a", "gpt-5.4-mini", "Be brief.", tools, "A"))
        self.assertTrue(captured["url"].endswith("/api/projects/p/agents?api-version=v1"))
        self.assertEqual(captured["body"]["definition"], {
            "kind": "prompt", "model": "gpt-5.4-mini", "instructions": "Be brief.", "tools": tools,
        })
        self.assertEqual(captured["body"]["description"], "A")


class RouterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(job_store_module, "PERSIST_PATH", Path(temp.name) / "jobs.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = job_store_module.JobStore()
        for target, value in (
            ("app.routers.agent_packs.job_store", self.store),
            ("app.analytics.record_deployment_event", lambda *a, **k: None),
            ("app.routers.agent_packs.get_user_id", lambda token: "user-1"),
            ("app.routers.agent_packs.get_user_email", lambda token: None),
            ("app.routers.agent_packs.get_management_token", AsyncMock(return_value="mgmt")),
            ("app.routers.agent_packs.get_agent_token", AsyncMock(return_value="ai")),
        ):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

        from app.routers import agent_packs as router_module
        api = FastAPI()
        api.state.limiter = router_module.limiter
        api.include_router(router_module.router)
        api.dependency_overrides[get_user_token] = lambda: "token"
        self.client = TestClient(api)

    def test_catalog(self):
        r = self.client.get("/api/agent-packs")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["id"], "manufacturing")

    def test_rejects_unknown_pack_and_region(self):
        body = {"subscription_id": SUB, "location": "brazilsouth"}
        self.assertEqual(self.client.post("/api/agent-packs/manufacturing/deploy", json=body).status_code, 400)
        body["location"] = "swedencentral"
        self.assertEqual(self.client.post("/api/agent-packs/unknown/deploy", json=body).status_code, 404)
        body["subscription_id"] = "not-a-guid"
        self.assertEqual(self.client.post("/api/agent-packs/manufacturing/deploy", json=body).status_code, 422)

    def test_deploy_creates_job_and_delete_requires_finished_job(self):
        with patch("app.routers.agent_packs.run_pack_job", new=AsyncMock()) as runner:
            r = self.client.post(
                "/api/agent-packs/manufacturing/deploy",
                json={"subscription_id": SUB, "location": "swedencentral"},
            )
        self.assertEqual(r.status_code, 200, r.text)
        job_id = r.json()["job_id"]
        self.assertEqual(runner.call_args.kwargs["agent_token"], "ai")
        job = self.store.get_job(job_id)
        self.assertEqual(job.scenario_id, agent_packs.SCENARIO_ID)
        self.assertTrue(re.match(r"^rg-fdg-agents-manufacturing-", job.workspace_name))

        self.store.set_azure_resources(job_id, {"subscriptionId": SUB, "resourceGroup": job.workspace_name})
        self.assertEqual(self.client.delete(f"/api/agent-packs/jobs/{job_id}/resources").status_code, 409)

        self.store.set_status(job_id, "completed")
        with patch("app.routers.agent_packs.AzureClient") as client_cls:
            client_cls.return_value.delete_resource_group = AsyncMock(return_value=True)
            client_cls.return_value.close = AsyncMock()
            r = self.client.delete(f"/api/agent-packs/jobs/{job_id}/resources")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "deleting")
        self.assertIsNone(self.store.get_job(job_id).azure_resources)


if __name__ == "__main__":
    unittest.main()
