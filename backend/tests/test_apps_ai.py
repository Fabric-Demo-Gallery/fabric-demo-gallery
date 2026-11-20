import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import apps_ai
from app import job_store as job_store_module
from app.auth import get_user_token
from app.azure_client import AzureError


class FakeAzure:
    """Minimal async stand-in for AzureClient covering the Apps & AI flow."""

    def __init__(self, template_state: str = "Succeeded", permissions=None):
        self.template_state = template_state
        self.permissions = permissions if permissions is not None else [{"actions": ["*"], "notActions": []}]
        self.calls: list[tuple] = []
        self.deployed_params: dict = {}

    async def list_caller_permissions(self, sub):
        return self.permissions

    async def check_model_capacity(self, sub, name, version):
        return [{"location": "swedencentral", "availableCapacity": 200}]

    async def resource_group_exists(self, sub, name):
        return False

    async def create_tagged_resource_group(self, sub, name, location, tags):
        self.calls.append(("rg", name, tags))

    async def register_providers(self, sub, namespaces):
        self.calls.append(("providers", tuple(namespaces)))

    async def create_foundry_account(self, sub, rg, account, location):
        self.calls.append(("account", account))

    async def create_foundry_project(self, sub, rg, account, project, location, display_name=None):
        self.calls.append(("project", project))

    async def create_model_deployment(self, sub, rg, account, deployment, name, version, sku_name, capacity):
        self.calls.append(("model", name, capacity))

    async def deploy_template(self, sub, rg, name, template, parameters):
        self.deployed_params = parameters

    async def get_deployment(self, sub, rg, name):
        props = {"provisioningState": self.template_state}
        if self.template_state == "Succeeded":
            props["outputs"] = {
                "frontendUrl": {"value": "https://web.example.io"},
                "frontendAppName": {"value": "tdraw-web-x"},
                "backendAppName": {"value": "tdraw-api-x"},
            }
        return {"properties": props}

    async def deployment_failure_detail(self, sub, rg, name):
        return "backend: image not found"

    async def get_container_app_revision_state(self, sub, rg, name):
        return "Running", "Healthy"

    async def delete_resource_group(self, sub, name):
        self.calls.append(("delete-rg", name))
        return True


async def collect(gen):
    return [event async for event in gen]


def run_deploy(fake, ranges=("20.30.40.50/32",)):
    app = apps_ai.get_app("technical-drawing-analysis")
    recorded: list = []
    with patch("app.apps_ai.asyncio.sleep", new=AsyncMock()):
        events = asyncio.run(collect(apps_ai.deploy_app(
            fake, app, "00000000-0000-0000-0000-000000000000", "rg-fdg-test", "swedencentral",
            list(ranges), on_resources=recorded.append,
        )))
    return events, recorded


class HelperTests(unittest.TestCase):
    def test_normalize_ip_ranges(self):
        self.assertEqual(
            apps_ai.normalize_ip_ranges(["20.30.40.50", "20.30.40.0/24", "20.30.40.50/32"]),
            ["20.30.40.50/32", "20.30.40.0/24"],
        )
        for bad in ("10.0.0.1", "2001:db8::1", "not-an-ip"):
            with self.assertRaises(ValueError):
                apps_ai.normalize_ip_ranges([bad])
        with self.assertRaises(ValueError):
            apps_ai.normalize_ip_ranges([f"20.30.40.{i}" for i in range(11)])

    def test_client_ip_from_headers_prefers_public_ipv4(self):
        self.assertEqual(
            apps_ai.client_ip_from_headers({"x-forwarded-for": "20.30.40.50:51234, 10.0.0.4"}),
            "20.30.40.50",
        )
        self.assertEqual(apps_ai.client_ip_from_headers({"x-client-ip": "52.1.2.3"}), "52.1.2.3")
        self.assertIsNone(apps_ai.client_ip_from_headers({"x-forwarded-for": "10.0.0.4"}))
        self.assertIsNone(apps_ai.client_ip_from_headers({}))

    def test_action_allowed_honours_not_actions(self):
        owner = [{"actions": ["*"], "notActions": []}]
        contributor = [{"actions": ["*"], "notActions": ["Microsoft.Authorization/*/Write"]}]
        action = "Microsoft.Authorization/roleAssignments/write"
        self.assertTrue(apps_ai._action_allowed(owner, action))
        self.assertFalse(apps_ai._action_allowed(contributor, action))
        uaa = [{"actions": ["Microsoft.Authorization/*"], "notActions": []}]
        self.assertTrue(apps_ai._action_allowed(contributor + uaa, action))

    def test_catalog_matches_template(self):
        template = apps_ai.load_template()
        params = set(template["parameters"])
        required = {k for k, v in template["parameters"].items() if "defaultValue" not in v}
        passed = {
            "appId", "namePrefix", "location", "foundryAccountName", "foundryProjectName",
            "modelDeploymentName", "backendImage", "frontendImage", "backendPort",
            "backendEnv", "allowedIpRanges",
        }
        self.assertTrue(required <= passed, required - passed)
        self.assertTrue(passed <= params, passed - params)
        catalog = apps_ai.load_catalog()
        self.assertIn(catalog["defaultRegion"], catalog["regions"])
        for app in catalog["apps"]:
            self.assertLessEqual(len(app["namePrefix"]), 8)
            self.assertTrue(app["modelCandidates"])
            self.assertTrue((Path(apps_ai.APPS_DIR).parents[1] / "apps-ai" / app["id"]).is_dir())
            self.assertRegex(apps_ai.image_ref(app["id"], "backend"), r"^ghcr\.io/.+/" + app["id"] + r"-backend:")


class DeployFlowTests(unittest.TestCase):
    def test_happy_path_completes_and_records_resources(self):
        fake = FakeAzure()
        events, recorded = run_deploy(fake)
        self.assertEqual(events[0]["event"], "plan")
        self.assertNotIn("error", [e["event"] for e in events])
        done = json.loads(events[-1]["data"]["detail"])
        self.assertEqual(done["appUrl"], "https://web.example.io")
        self.assertEqual(done["azure"]["resourceGroup"], "rg-fdg-test")
        self.assertEqual(done["azure"]["model"], "gpt-5.4")
        self.assertEqual(fake.deployed_params["allowedIpRanges"], ["20.30.40.50/32"])
        self.assertEqual(fake.deployed_params["backendPort"], 8000)
        self.assertIn(("model", "gpt-5.4", apps_ai.MODEL_CAPACITY), fake.calls)
        self.assertEqual(recorded[0]["resourceGroup"], "rg-fdg-test")
        self.assertEqual(fake.calls[0][2]["created-by"], apps_ai.RESOURCE_GROUP_TAG)

    def test_model_falls_back_to_next_candidate(self):
        fake = FakeAzure()

        async def flaky(sub, rg, account, deployment, name, version, sku_name, capacity):
            if name == "gpt-5.4":
                raise AzureError(400, "InsufficientQuota")
            fake.calls.append(("model", name, capacity))

        fake.create_model_deployment = flaky
        events, _ = run_deploy(fake)
        done = json.loads(events[-1]["data"]["detail"])
        self.assertEqual(done["azure"]["model"], "gpt-5.4-mini")

    def test_template_failure_tears_down_resource_group(self):
        fake = FakeAzure(template_state="Failed")
        events, recorded = run_deploy(fake)
        self.assertEqual(events[-1]["event"], "error")
        self.assertIn("image not found", events[-1]["data"]["message"])
        self.assertIn(("delete-rg", "rg-fdg-test"), fake.calls)
        self.assertIsNone(recorded[-1])
        failed = [e for e in events if e["event"] == "step" and e["data"]["status"] == "failed"]
        self.assertEqual(failed[0]["data"]["name"], "apps")

    def test_missing_role_assignment_permission_fails_before_creating_anything(self):
        fake = FakeAzure(permissions=[{"actions": ["*"], "notActions": ["Microsoft.Authorization/*/Write"]}])
        events, recorded = run_deploy(fake)
        self.assertEqual(events[-1]["event"], "error")
        self.assertIn("roleAssignments/write", events[-1]["data"]["message"])
        self.assertEqual(fake.calls, [])
        self.assertEqual(recorded, [])


class RouterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(job_store_module, "PERSIST_PATH", Path(temp.name) / "jobs.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = job_store_module.JobStore()
        for target in ("app.routers.apps.job_store", "app.job_store.job_store"):
            p = patch(target, self.store)
            p.start()
            self.addCleanup(p.stop)
        p = patch("app.analytics.record_deployment_event")
        p.start()
        self.addCleanup(p.stop)

        from app.routers import apps
        self.apps_router = apps
        api = FastAPI()
        api.state.limiter = apps.limiter
        api.include_router(apps.router)
        api.dependency_overrides[get_user_token] = lambda: "token"
        self.client = TestClient(api)
        for target, value in (
            ("app.routers.apps.get_user_id", lambda token: "user-1"),
            ("app.routers.apps.get_user_email", lambda token: None),
            ("app.routers.apps.get_management_token", AsyncMock(return_value="mgmt")),
        ):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def body(self, **overrides):
        return {
            "subscription_id": "00000000-0000-0000-0000-000000000000",
            "location": "swedencentral",
            "allowed_ip_ranges": ["20.30.40.50"],
            **overrides,
        }

    def test_rejects_unsupported_region_and_missing_allowlist(self):
        r = self.client.post("/api/apps/technical-drawing-analysis/deploy", json=self.body(location="brazilsouth"))
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/apps/technical-drawing-analysis/deploy", json=self.body(allowed_ip_ranges=[]))
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/apps/unknown-app/deploy", json=self.body())
        self.assertEqual(r.status_code, 404)

    def test_deploy_creates_job_and_delete_requires_finished_job(self):
        with patch("app.routers.apps.run_app_job", new=AsyncMock()) as runner:
            r = self.client.post("/api/apps/technical-drawing-analysis/deploy", json=self.body())
        self.assertEqual(r.status_code, 200, r.text)
        job_id = r.json()["job_id"]
        self.assertEqual(runner.call_args.kwargs["allowed_ip_ranges"], ["20.30.40.50/32"])
        job = self.store.get_job(job_id)
        self.assertEqual(job.scenario_id, apps_ai.SCENARIO_ID)
        self.assertTrue(job.workspace_name.startswith("rg-fdg-technical-drawing-analysis-"))

        self.store.set_azure_resources(job_id, {"subscriptionId": "00000000-0000-0000-0000-000000000000", "resourceGroup": job.workspace_name})
        r = self.client.delete(f"/api/apps/jobs/{job_id}/resources")
        self.assertEqual(r.status_code, 409)

        self.store.set_status(job_id, "completed")
        with patch("app.routers.apps.AzureClient") as client_cls:
            client = client_cls.return_value
            client.delete_resource_group = AsyncMock(return_value=True)
            client.close = AsyncMock()
            r = self.client.delete(f"/api/apps/jobs/{job_id}/resources")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "deleting")
        self.assertIsNone(self.store.get_job(job_id).azure_resources)

    def test_public_access_skips_allowlist(self):
        with patch("app.routers.apps.run_app_job", new=AsyncMock()) as runner:
            r = self.client.post(
                "/api/apps/demand-portfolio-planning/deploy",
                json=self.body(public_access=True, allowed_ip_ranges=[]),
            )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(runner.call_args.kwargs["allowed_ip_ranges"], [])


if __name__ == "__main__":
    unittest.main()
