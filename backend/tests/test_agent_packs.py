import asyncio
import base64
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

    async def start_template_deployment(self, sub, rg, name, template, parameters):
        self.calls.append(("template", name, parameters))
        self.template_polls = 0

    async def get_template_deployment(self, sub, rg, name):
        self.template_polls += 1
        if self.template_state == "Succeeded" and self.template_polls == 1:
            return {"provisioningState": "Running"}
        return {"provisioningState": self.template_state, "outputs": {k: {"value": v} for k, v in INFRA_OUTPUTS.items()}}

    async def template_deployment_error(self, sub, rg, name):
        return "storage: RequestDisallowedByPolicy"

    template_state = "Succeeded"


INFRA_OUTPUTS = {
    "cmmsBaseUrl": "https://prod.logic.azure.com/workflows/abc/triggers/manual/paths/invoke",
    "cmmsApiVersion": "2016-10-01",
    "cmmsSp": "/triggers/manual/run",
    "cmmsSv": "1.0",
    "cmmsConnectionId": "/subscriptions/x/connections/plant-cmms",
    "cmmsWorkflowName": "logic-plant-cmms-1",
    "incidentWorkflowName": "logic-incident-response-1",
    "appInsightsName": "appi-fdg-1",
    "storageAccountName": "stfdg1",
}


class FakeProject:
    """Stand-in for FoundryProjectClient that records data-plane calls."""

    def __init__(self, endpoint, token, fail_on_agent=None):
        self.endpoint, self.token = endpoint, token
        self.uploads: list[str] = []
        self.stores: list[tuple[str, list[str]]] = []
        self.agents: list[dict] = []
        self.fail_on_agent = fail_on_agent
        self.warmed: list[str] = []
        self.evals: list[tuple] = []
        self.eval_runs: list[tuple] = []
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

    async def create_agent_evaluation(self, name, judge_model):
        if self.fail_on_agent == "evaluations":
            raise FoundryProjectError(400, "Evaluations are not available")
        self.evals.append((name, judge_model))
        return f"eval-{len(self.evals)}"

    async def start_agent_evaluation_run(self, eval_id, agent, queries):
        self.eval_runs.append((eval_id, agent, len(queries)))
        return f"run-{len(self.eval_runs)}"

    async def close(self):
        self.closed = True


async def collect(gen):
    return [event async for event in gen]


async def no_sleep(seconds):
    return None


def run_deploy(fake_az, agent_token="ai-token", fail_on_agent=None):
    pack = agent_packs.load_pack("manufacturing")
    recorded: list = []
    projects: list[FakeProject] = []

    def factory(endpoint, token):
        projects.append(FakeProject(endpoint, token, fail_on_agent))
        return projects[-1]

    plant = AsyncMock(return_value=httpx.Response(200, json={"work_orders": [], "quality_holds": []}))
    with patch.object(agent_packs, "call_plant_system", plant):
        events = asyncio.run(collect(agent_packs.deploy_pack(
            fake_az, pack, agent_token, SUB, "rg-fdg-agents-test", "swedencentral",
            on_resources=recorded.append, project_client_factory=factory, sleep=no_sleep,
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

    def test_actions_evaluations_and_incident_reference_real_things(self):
        pack = agent_packs.load_pack("manufacturing")
        spec = agent_packs._pack_json("manufacturing", pack["infra"]["openapi"])
        operations = {op["operationId"] for item in spec["paths"].values() for op in item.values()}
        agent_ids = {a["id"] for a in pack["agents"]}
        for agent in pack["agents"]:
            self.assertLessEqual(set(agent.get("actions", [])), operations, agent["id"])
        self.assertLessEqual(set(pack["evaluations"]), agent_ids)
        self.assertTrue(all(pack["evaluations"].values()))

        template = agent_packs._pack_json("manufacturing", pack["infra"]["template"])
        self.assertLessEqual({"foundryAccountName", "foundryProjectName", "modelDeploymentName"}, set(template["parameters"]))
        self.assertLessEqual(set(INFRA_OUTPUTS), set(template["outputs"]))

        # Every action the incident status reads exists in the generated workflow.
        workflow = json.loads(agent_packs.pack_file(pack, "infra/incident.workflow.json").read_text(encoding="utf-8"))
        names: set[str] = set()

        def walk(actions):
            for name, action in actions.items():
                names.add(name)
                walk(action.get("actions", {}))
                walk(action.get("else", {}).get("actions", {}))

        walk(workflow["actions"])
        incident = pack["incident"]
        for step in incident["steps"]:
            self.assertIn(step["agent"], agent_ids | {"supervisor"})
            for key in ("start", "done", "output", "data"):
                if step.get(key):
                    self.assertIn(step[key], names, f"{step['id']}.{key}")
            self.assertLessEqual(set(step["watch"]), names, step["id"])
        for key in ("approvalAction", "draftAction", "reportAction"):
            self.assertIn(incident[key], names)


def action(name, status, link=None):
    props = {"status": status}
    if link:
        props["outputsLink"] = {"uri": link}
    return {"name": name, "properties": props}


class FakeRunAzure:
    """ARM run/actions stand-in for the incident status view."""

    def __init__(self, run_status, actions, contents):
        self.run_status, self.actions, self.contents = run_status, actions, contents
        self.reads: list[str] = []

    async def get_workflow_run(self, sub, rg, workflow, run):
        return {"properties": {"status": self.run_status, "startTime": "2025-01-01T00:00:00Z"}}

    async def list_workflow_run_actions(self, sub, rg, workflow, run):
        return self.actions

    async def read_run_content(self, link):
        self.reads.append(link)
        return self.contents[link]


AZURE = {"subscriptionId": SUB, "resourceGroup": "rg", "incidentWorkflow": "wf", "cmmsWorkflow": "cmms"}


class IncidentStatusTests(unittest.TestCase):
    def setUp(self):
        agent_packs._finished_content.clear()
        self.pack = agent_packs.load_pack("manufacturing")

    def status(self, fake, run_id="RUN0000000001"):
        return asyncio.run(agent_packs.incident_status(fake, AZURE, self.pack, run_id))

    def test_waiting_for_approval_shows_the_draft(self):
        fake = FakeRunAzure("Running", [
            action("Start_Triage", "Succeeded"), action("Wait_Triage", "Succeeded"),
            action("Triage_report", "Succeeded", "l-triage"), action("Triage_fields", "Succeeded", "l-fields"),
            action("Start_Holds", "Succeeded"), action("Holds_report", "Succeeded"),
            action("Triage_summary", "Succeeded", "l-summary"),
            action("Start_Inspection", "Skipped"), action("Inspection_report", "Skipped"),
            action("Start_Diagnosis", "Succeeded"), action("Diagnosis_report", "Succeeded", "l-diag"),
            action("Work_order_draft", "Succeeded", "l-draft"),
            action("Request_approval", "Succeeded"), action("Wait_for_approval", "Running"),
        ], {
            "l-triage": {"body": "MCH-0046 drives the spike."},
            "l-summary": "MCH-0046 drives the spike.\n\nB-04049 - QH-1",
            "l-fields": {"machine_id": "MCH-0046", "machine_related": True},
            "l-diag": "Clean the nozzle.",
            "l-draft": {"body": {"machine_id": "MCH-0046", "priority": "P2", "title": "t", "description": "d"}},
        })
        result = self.status(fake)
        steps = {s["id"]: s for s in result["steps"]}
        self.assertEqual(steps["triage"]["status"], "completed")
        self.assertEqual(steps["triage"]["output"], "MCH-0046 drives the spike.\n\nB-04049 - QH-1")
        self.assertEqual(steps["triage"]["data"]["machine_id"], "MCH-0046")
        self.assertEqual(steps["inspection"]["status"], "skipped")
        self.assertEqual(steps["diagnosis"]["status"], "completed")
        self.assertEqual(steps["approval"]["status"], "waiting")
        self.assertEqual(steps["work-order"]["status"], "pending")
        self.assertTrue(result["awaitingApproval"])
        self.assertEqual(result["draft"]["priority"], "P2")
        self.assertNotIn("report", result)

        # Finished outputs are cached, so the next poll doesn't fetch them again.
        reads = len(fake.reads)
        self.status(fake)
        self.assertEqual(len(fake.reads), reads + 0)

    def test_finished_run_with_rejection_and_failure(self):
        fake = FakeRunAzure("Failed", [
            action("Start_Triage", "Succeeded"), action("Triage_fields", "Succeeded", "l-fields"),
            action("Start_Holds", "Skipped"), action("Triage_summary", "Succeeded", "l-summary"),
            action("Start_Inspection", "Skipped"), action("Inspection_report", "Skipped"),
            action("Wait_for_approval", "Succeeded"), action("Approval_decision", "Succeeded", "l-approval"),
            action("Start_Work_order", "Skipped"), action("Set_work_order_rejected", "Succeeded"),
            action("Start_Handover", "Succeeded"), action("Wait_Handover", "Failed"),
        ], {
            "l-fields": {"machine_id": "MCH-0046"},
            "l-summary": "No holds.",
            "l-approval": {"status": "rejected", "decided_by": "me"},
        })
        steps = {s["id"]: s for s in self.status(fake, "RUN0000000002")["steps"]}
        self.assertEqual(steps["inspection"]["status"], "skipped")
        self.assertEqual(steps["approval"]["status"], "completed")
        self.assertEqual(steps["approval"]["data"]["status"], "rejected")
        self.assertEqual(steps["work-order"]["status"], "skipped")
        self.assertEqual(steps["handover"]["status"], "failed")
        self.assertEqual(steps["handover"]["error"], "The step did not finish.")

    def test_decision_requires_a_waiting_run(self):
        fake = FakeRunAzure("Running", [action("Wait_for_approval", "Succeeded")], {})
        with self.assertRaises(agent_packs.AgentPackError):
            asyncio.run(agent_packs.record_decision(fake, AZURE, self.pack, "RUN0000000003", "approved", "me", ""))

    def test_old_deployments_without_workflows_are_rejected(self):
        with self.assertRaises(agent_packs.AgentPackError):
            asyncio.run(agent_packs.incident_status(FakeRunAzure("Running", [], {}), {"resourceGroup": "rg"}, self.pack, "RUN0000000004"))

    def test_evaluation_scores_use_each_evaluator_scale(self):
        client = AsyncMock()
        client.get_evaluation_run.return_value = {"status": "completed", "report_url": "https://ai.azure.com/r"}
        client.list_evaluation_items.return_value = [
            {"results": [{"name": "Task adherence", "score": 1, "passed": True},
                         {"name": "Intent resolution", "score": 4, "passed": True}]},
            {"results": [{"name": "Task adherence", "score": 0, "passed": False},
                         {"name": "Intent resolution", "score": 5, "passed": True}]},
        ]
        azure = {"evaluations": {"quality-analyst": {"evalId": "e1", "runId": "evalrun-scale-test"}}}
        [entry] = asyncio.run(agent_packs.evaluation_results(client, self.pack, azure))
        criteria = {c["name"]: c for c in entry["criteria"]}
        self.assertEqual(criteria["Task adherence"], {"name": "Task adherence", "average": 0.5, "scale": 1, "passed": 1, "scored": 2})
        self.assertEqual(criteria["Intent resolution"]["average"], 4.5)
        self.assertEqual(criteria["Intent resolution"]["scale"], 5)


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
            {"data": ["a.csv", "b.csv"]}, "vs-1", {"a.csv": "file-a", "b.csv": "file-b"}, None
        )
        self.assertEqual(tools[0], {"type": "file_search", "vector_store_ids": ["vs-1"]})
        self.assertEqual(tools[1]["container"], {"type": "auto", "file_ids": ["file-a", "file-b"]})
        self.assertEqual(agent_packs._agent_tools({"data": []}, None, {}, None), [])
        actions = agent_packs._agent_tools({"actions": ["getBoard"]}, None, {}, lambda ops: {"type": "openapi", "ops": ops})
        self.assertEqual(actions, [{"type": "openapi", "ops": ["getBoard"]}])

    def test_resource_group_name_and_portal_urls(self):
        self.assertRegex(agent_packs.new_resource_group_name("manufacturing"), r"^rg-fdg-agents-manufacturing-[0-9a-f]{6}$")
        url = agent_packs.foundry_portal_url(
            "11111111-2222-3333-4444-555555555555", "rg", "acct", "proj", "build/agents/a/build", "tenant-1",
        )
        self.assertEqual(url, "https://ai.azure.com/nextgen/r/ERERESIiMzNERFVVVVVVVQ,rg,,acct,proj/build/agents/a/build?tid=tenant-1")
        self.assertEqual(
            agent_packs.azure_portal_url("/subscriptions/s/resourceGroups/rg", "t"),
            "https://portal.azure.com/#@t/resource/subscriptions/s/resourceGroups/rg/overview",
        )

    def test_openapi_tool_is_limited_to_the_agents_operations(self):
        pack = agent_packs.load_pack("manufacturing")
        tool = agent_packs.openapi_tool(pack, INFRA_OUTPUTS, ["createWorkOrder", "getBoard"])
        spec = tool["openapi"]["spec"]
        self.assertEqual(set(spec["paths"]), {"/workorders", "/board"})
        self.assertEqual(spec["servers"], [{"url": INFRA_OUTPUTS["cmmsBaseUrl"]}])
        params = {p["name"]: p["schema"]["enum"] for p in spec["paths"]["/workorders"]["post"]["parameters"]}
        self.assertEqual(params, {"api-version": ["2016-10-01"], "sp": ["/triggers/manual/run"], "sv": ["1.0"]})
        self.assertEqual(spec["components"]["securitySchemes"]["sig"], {"type": "apiKey", "name": "sig", "in": "query"})
        self.assertEqual(tool["openapi"]["auth"]["security_scheme"]["project_connection_id"], INFRA_OUTPUTS["cmmsConnectionId"])
        self.assertNotIn("sig", json.dumps(spec["paths"]))
        # The cached template is not mutated between agents.
        again = agent_packs.openapi_tool(pack, INFRA_OUTPUTS, ["placeQualityHold"])
        self.assertEqual(set(again["openapi"]["spec"]["paths"]), {"/qualityholds"})


class DeployFlowTests(unittest.TestCase):
    def test_happy_path_creates_all_agents_with_grounding(self):
        fake = FakeAzure()
        events, recorded, project = run_deploy(fake)
        self.assertEqual(events[0]["event"], "plan")
        self.assertNotIn("error", [e["event"] for e in events])

        # 7 knowledge documents + 3 data files, each uploaded exactly once.
        self.assertEqual(len(project.uploads), 10)
        self.assertEqual(len(set(project.uploads)), 10)
        # Shift handover is data-only (no knowledge documents), so 3 indexes.
        self.assertEqual(len(project.stores), 3)
        self.assertEqual(project.token, "ai-token")
        self.assertEqual(project.warmed, ["gpt-5.4-mini"])
        self.assertTrue(project.closed)

        by_name = {a["name"]: a for a in project.agents}
        self.assertEqual(set(by_name), {"maintenance-assistant", "quality-analyst", "shift-handover", "visual-inspector"})
        tool_types = {name: [t["type"] for t in a["tools"]] for name, a in by_name.items()}
        self.assertEqual(tool_types["maintenance-assistant"], ["file_search", "code_interpreter", "openapi"])
        self.assertEqual(tool_types["shift-handover"], ["code_interpreter", "openapi"])
        self.assertEqual(tool_types["visual-inspector"], ["file_search"])
        self.assertEqual(len(by_name["quality-analyst"]["tools"][1]["container"]["file_ids"]), 3)
        self.assertEqual(set(by_name["shift-handover"]["tools"][1]["openapi"]["spec"]["paths"]), {"/board"})
        self.assertTrue(all(a["model"] == "gpt-5.4-mini" for a in project.agents))
        self.assertIn(("model", "gpt-5.4-mini", agent_packs.MODEL_CAPACITY), fake.calls)

        role = next(c for c in fake.calls if c[0] == "role")
        self.assertEqual(role[2:], (FOUNDRY_USER, "caller-oid", "User"))
        self.assertTrue(role[1].endswith("/providers/Microsoft.CognitiveServices/accounts/" + recorded[-1]["foundryAccount"]))

        # The infrastructure template starts after the model and gets its names.
        template = next(c for c in fake.calls if c[0] == "template")
        self.assertEqual(template[1], agent_packs.INFRA_DEPLOYMENT)
        self.assertEqual(template[2]["modelDeploymentName"], "gpt-5.4-mini")
        self.assertEqual(template[2]["foundryAccountName"], recorded[-1]["foundryAccount"])
        self.assertLess(fake.calls.index(next(c for c in fake.calls if c[0] == "model")), fake.calls.index(template))
        providers = next(c for c in fake.calls if c[0] == "providers")[1]
        self.assertIn("Microsoft.Logic", providers)

        # Evaluations run on demand, not during the deploy.
        self.assertEqual(project.eval_runs, [])

        done = json.loads(events[-1]["data"]["detail"])
        self.assertEqual(len(done["agents"]), 4)
        self.assertIn("/build/agents/visual-inspector/build", done["agents"][3]["portalUrl"])
        azure = done["azure"]
        self.assertEqual(azure["resourceGroup"], "rg-fdg-agents-test")
        self.assertTrue(azure["portalUrl"].startswith("https://ai.azure.com/nextgen/r/"))
        self.assertTrue(azure["portalUrl"].endswith("?tid=tenant-1"))
        self.assertEqual(azure["incidentWorkflow"], "logic-incident-response-1")
        self.assertEqual(azure["cmmsWorkflow"], "logic-plant-cmms-1")
        self.assertIn("/components/appi-fdg-1/", azure["tracingUrl"])
        self.assertNotIn("evaluations", azure)
        self.assertNotIn('"sig"', json.dumps(azure))
        self.assertNotIn("sig=", json.dumps(azure))
        self.assertEqual(recorded[-1]["portalUrl"], azure["portalUrl"])
        rg_call = next(c for c in fake.calls if c[0] == "rg")
        self.assertEqual(rg_call[2]["created-by"], agent_packs.RESOURCE_GROUP_TAG)
        self.assertEqual(rg_call[2]["SecurityControl"], "Ignore")

    def test_infrastructure_failure_tears_down_resource_group(self):
        fake = FakeAzure()
        fake.template_state = "Failed"
        events, _, project = run_deploy(fake)
        self.assertEqual(events[-1]["event"], "error")
        self.assertIn("RequestDisallowedByPolicy", events[-1]["data"]["message"])
        self.assertIn(("delete-rg", "rg-fdg-agents-test"), fake.calls)
        self.assertEqual(project.agents, [])
        failed = [e for e in events if e["event"] == "step" and e["data"]["status"] == "failed"]
        self.assertEqual(failed[0]["data"]["name"], "infra")

    def test_first_evaluation_run_creates_the_definitions(self):
        project = FakeProject("https://p", "ai")
        runs = asyncio.run(agent_packs.start_evaluations(project, agent_packs.load_pack("manufacturing"), "m"))
        self.assertEqual(set(runs), {"maintenance-assistant", "quality-analyst", "shift-handover"})
        self.assertEqual(len(project.evals), 3)
        self.assertTrue(all(model == "m" for _, model in project.evals))

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
        responses = iter([404, 403, 200, 403])

        def handler(request):
            self.assertEqual(request.headers["authorization"], "Bearer tok")
            status = next(responses)
            if status == 404:
                return httpx.Response(404, json={"error": {"message": "Project not found"}})
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

    def test_agent_evaluation_bodies(self):
        bodies: list[tuple[str, dict]] = []

        def handler(request):
            bodies.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={"id": f"id-{len(bodies)}"})

        async def go(client):
            eval_id = await client.create_agent_evaluation("qa quality", "gpt-5.4-mini")
            return await client.start_agent_evaluation_run(eval_id, "quality-analyst", ["q1", "q2"])

        run_id, _ = self.run_client(handler, go)
        self.assertEqual(run_id, "id-2")
        (path, definition), (run_path, run) = bodies
        self.assertTrue(path.endswith("/openai/v1/evals"))
        criteria = {c["evaluator_name"]: c for c in definition["testing_criteria"]}
        self.assertEqual(set(criteria), {"builtin.task_adherence", "builtin.intent_resolution", "builtin.tool_call_accuracy"})
        self.assertIn("tool_definitions", criteria["builtin.tool_call_accuracy"]["data_mapping"])
        self.assertNotIn("tool_definitions", criteria["builtin.task_adherence"]["data_mapping"])
        self.assertEqual(criteria["builtin.task_adherence"]["initialization_parameters"], {"deployment_name": "gpt-5.4-mini"})
        self.assertTrue(run_path.endswith("/openai/v1/evals/id-1/runs"))
        self.assertEqual(run["data_source"]["target"], {"type": "azure_ai_agent", "name": "quality-analyst"})
        self.assertEqual([c["item"]["query"] for c in run["data_source"]["source"]["content"]], ["q1", "q2"])


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

    def completed_job(self, azure=None):
        job = self.store.create_job(
            demo_id="manufacturing", workspace_name="rg-x", user_id="user-1", scenario_id=agent_packs.SCENARIO_ID,
        )
        self.store.set_azure_resources(job.job_id, azure if azure is not None else dict(AZURE, projectEndpoint="https://p", model="m"))
        self.store.set_status(job.job_id, "completed")
        return job.job_id

    def test_incident_endpoints(self):
        job_id = self.completed_job()
        photo = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jpeg").decode()
        body = {"line": "Line-B", "shift": "evening", "date": "2025-03-17", "photo": photo}
        with patch("app.routers.agent_packs.AzureClient") as client_cls, \
                patch("app.routers.agent_packs.start_incident", new=AsyncMock(return_value="RUN0000000009")) as start:
            client_cls.return_value.close = AsyncMock()
            r = self.client.post(f"/api/agent-packs/jobs/{job_id}/incidents", json=body)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json(), {"incidentId": "RUN0000000009"})
            self.assertEqual(start.call_args.args[2:], ("Line-B", "evening", "2025-03-17", photo))

            for bad in ({"photo": "data:image/gif;base64,R0lG"}, {"line": "Line-Z"}, {"shift": "late"}):
                self.assertEqual(self.client.post(f"/api/agent-packs/jobs/{job_id}/incidents", json=body | bad).status_code, 422, bad)

            with patch("app.routers.agent_packs.record_decision", new=AsyncMock()) as decide:
                r = self.client.post(
                    f"/api/agent-packs/jobs/{job_id}/incidents/RUN0000000009/decision", json={"decision": "approved"},
                )
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(decide.call_args.args[3:6], ("RUN0000000009", "approved", "presenter"))
            self.assertEqual(self.client.post(
                f"/api/agent-packs/jobs/{job_id}/incidents/RUN0000000009/decision", json={"decision": "maybe"},
            ).status_code, 422)
            self.assertEqual(self.client.get(f"/api/agent-packs/jobs/{job_id}/incidents/bad-id!").status_code, 400)

            with patch("app.routers.agent_packs.incident_status",
                       new=AsyncMock(side_effect=agent_packs.AgentPackError("This incident is not waiting"))):
                self.assertEqual(self.client.get(f"/api/agent-packs/jobs/{job_id}/incidents/RUN0000000009").status_code, 409)
            with patch("app.routers.agent_packs.plant_board", new=AsyncMock(side_effect=AzureError(403, "denied"))):
                self.assertEqual(self.client.get(f"/api/agent-packs/jobs/{job_id}/board").status_code, 403)

    def test_live_endpoints_require_an_owned_completed_job(self):
        job_id = self.completed_job()
        self.store.set_status(job_id, "failed")
        self.assertEqual(self.client.get(f"/api/agent-packs/jobs/{job_id}/board").status_code, 409)
        with patch("app.routers.agent_packs.get_user_id", lambda token: "someone-else"):
            self.assertEqual(self.client.get(f"/api/agent-packs/jobs/{job_id}/board").status_code, 404)
        self.assertEqual(self.client.get("/api/agent-packs/jobs/not-a-uuid/board").status_code, 400)

    def test_evaluations_rerun_reuses_definitions(self):
        job_id = self.completed_job(dict(AZURE, projectEndpoint="https://p", model="m",
                                         evaluations={"quality-analyst": {"evalId": "eval-1", "runId": "run-1"}}))
        project = FakeProject("https://p", "ai")
        with patch("app.routers.agent_packs.FoundryProjectClient", return_value=project):
            r = self.client.post(f"/api/agent-packs/jobs/{job_id}/evaluations")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["started"], 3)
        runs = self.store.get_job(job_id).azure_resources["evaluations"]
        self.assertEqual(runs["quality-analyst"]["evalId"], "eval-1")
        self.assertEqual(len(project.evals), 2)
        self.assertTrue(project.closed)


if __name__ == "__main__":
    unittest.main()
