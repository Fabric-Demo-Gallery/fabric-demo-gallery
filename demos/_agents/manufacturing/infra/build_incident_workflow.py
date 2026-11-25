"""Generates incident.workflow.json - the Logic Apps definition for the
manufacturing incident response. Kept as a generator because every agent step
repeats the same start -> poll -> extract pattern; run it after editing:

    python demos/_agents/manufacturing/infra/build_incident_workflow.py
"""

import json
from pathlib import Path

AI_AUTH = {"type": "ManagedServiceIdentity", "audience": "https://ai.azure.com"}
TABLE_AUTH = {"type": "ManagedServiceIdentity", "audience": "https://storage.azure.com/"}
TABLE_HEADERS = {
    "Accept": "application/json;odata=nometadata",
    "Content-Type": "application/json",
    "x-ms-version": "2020-12-06",
}
RESPONSES = "@{parameters('projectEndpoint')}/openai/v1/responses"
APPROVAL_URI = (
    "https://@{parameters('storageAccount')}.table.core.windows.net/approvals"
    "(PartitionKey='incident',RowKey='@{workflow()?['run']?['name']}')"
)
INCIDENT = "@{workflow()?['run']?['name']}"
WHERE = "@{triggerBody()?['line']}, @{triggerBody()?['shift']} shift of @{triggerBody()?['date']}"


AGENT_ATTEMPTS = 3
STEP_KEYS: list[str] = []


def agent_step(
    key: str, agent: str, agent_input, run_after: dict, require_call: str = "", previous: str = ""
) -> dict:
    """Run an agent in the background, poll until done, extract the text.
    A failed run (for example a token rate limit while other agents are busy)
    is retried with a growing delay. With ``require_call`` the agent must use a
    tool and the run is retried when it did not call that tool operation.
    ``previous`` continues the conversation of an earlier step.
    Produces Run_<key> (Count_, Backoff_, Start_, Wait_, Save_<key>),
    <key>_messages and <key>_report; the result lives in the variable <key>Result."""
    STEP_KEYS.append(key)
    result = f"variables('{key}Result')"
    retry = f"equals({result}?['status'], 'failed')"
    if require_call:
        retry = f"or({retry}, not(contains(string(coalesce({result}?['output'], '')), '{require_call}')))"
    body = {
        "agent_reference": {"type": "agent_reference", "name": agent},
        "input": agent_input,
        "background": True,
    }
    if require_call:
        body["tool_choice"] = "required"
    if previous:
        body["previous_response_id"] = f"@{{variables('{previous}Result')?['id']}}"
    return {
        f"Run_{key}": {
            "type": "Until",
            "runAfter": run_after,
            "expression": f"@or(not({retry}), greaterOrEquals(variables('{key}Attempt'), {AGENT_ATTEMPTS}))",
            "limit": {"count": AGENT_ATTEMPTS, "timeout": "PT30M"},
            "actions": {
                f"Count_{key}": {"type": "IncrementVariable", "inputs": {"name": f"{key}Attempt", "value": 1}},
                f"Backoff_{key}": {
                    "type": "Wait",
                    "runAfter": {f"Count_{key}": ["Succeeded"]},
                    "inputs": {"interval": {"count": f"@add(mul(sub(variables('{key}Attempt'), 1), 30), 1)", "unit": "Second"}},
                },
                f"Start_{key}": {
                    "type": "Http",
                    "runAfter": {f"Backoff_{key}": ["Succeeded"]},
                    "inputs": {
                        "method": "POST",
                        "uri": RESPONSES,
                        "headers": {"Content-Type": "application/json"},
                        "body": body,
                        "authentication": AI_AUTH,
                    },
                },
                f"Wait_{key}": {
                    "type": "Until",
                    "runAfter": {f"Start_{key}": ["Succeeded"]},
                    "expression": f"@not(contains(createArray('queued', 'in_progress'), body('Poll_{key}')?['status']))",
                    "limit": {"count": 200, "timeout": "PT15M"},
                    "actions": {
                        f"Delay_{key}": {"type": "Wait", "inputs": {"interval": {"count": 4, "unit": "Second"}}},
                        f"Poll_{key}": {
                            "type": "Http",
                            "runAfter": {f"Delay_{key}": ["Succeeded"]},
                            "inputs": {
                                "method": "GET",
                                "uri": f"{RESPONSES}/@{{body('Start_{key}')?['id']}}",
                                "authentication": AI_AUTH,
                            },
                        },
                    },
                },
                f"Save_{key}": {
                    "type": "SetVariable",
                    "runAfter": {f"Wait_{key}": ["Succeeded"]},
                    "inputs": {"name": f"{key}Result", "value": f"@body('Poll_{key}')"},
                },
            },
        },
        f"{key}_messages": {
            "type": "Query",
            "runAfter": {f"Run_{key}": ["Succeeded"]},
            "inputs": {"from": f"@coalesce({result}?['output'], json('[]'))", "where": "@equals(item()?['type'], 'message')"},
        },
        f"{key}_report": {
            "type": "Compose",
            "runAfter": {f"{key}_messages": ["Succeeded"]},
            "inputs": (
                f"@coalesce(last(body('{key}_messages'))?['content']?[0]?['text'], "
                f"concat('The agent did not finish (status: ', string({result}?['status']), ').'))"
            ),
        },
    }


def extract_step(key: str, source: str, instruction: str, schema: dict, run_after: dict) -> dict:
    """Turn an agent's free-text answer into JSON with a direct model call
    (structured output is not allowed together with agent_reference)."""
    return {
        f"Extract_{key}": {
            "type": "Http",
            "runAfter": run_after,
            "inputs": {
                "method": "POST",
                "uri": RESPONSES,
                "headers": {"Content-Type": "application/json"},
                "body": {
                    "model": "@{parameters('model')}",
                    "input": f"{instruction}\n\n@{{outputs('{source}')}}",
                    "text": {"format": {"type": "json_schema", "name": key, "strict": True, "schema": schema}},
                },
                "authentication": AI_AUTH,
            },
        },
        f"{key}_json_messages": {
            "type": "Query",
            "runAfter": {f"Extract_{key}": ["Succeeded"]},
            "inputs": {"from": f"@body('Extract_{key}')?['output']", "where": "@equals(item()?['type'], 'message')"},
        },
        key: {
            "type": "Compose",
            "runAfter": {f"{key}_json_messages": ["Succeeded"]},
            "inputs": f"@json(last(body('{key}_json_messages'))?['content']?[0]?['text'])",
        },
    }


def set_var(name: str, value: str, run_after: dict) -> dict:
    return {"type": "SetVariable", "runAfter": run_after, "inputs": {"name": name, "value": value}}


TRIAGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "root_cause", "machine_id", "machine_related", "defect_rate_pct", "hold_batches"],
    "properties": {
        "summary": {"type": "string", "description": "Two sentences: what happened and why."},
        "root_cause": {"type": "string"},
        "machine_id": {"type": "string", "description": "Most likely machine, e.g. MCH-0046, or empty."},
        "machine_related": {"type": "boolean"},
        "defect_rate_pct": {"type": "number"},
        "hold_batches": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Batch IDs classified as hold (not watch or normal), e.g. B-04049; empty if none.",
        },
    },
}
WORK_ORDER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["machine_id", "priority", "title", "description"],
    "properties": {
        "machine_id": {"type": "string"},
        "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
        "title": {"type": "string"},
        "description": {"type": "string", "description": "Diagnosis and ordered tasks, plain text."},
    },
}

actions: dict = {
    "Init_diagnosis": {
        "type": "InitializeVariable",
        "inputs": {"variables": [{"name": "diagnosis", "type": "string", "value": "No machine-related cause was found, so no maintenance diagnosis was needed."}]},
    },
    "Init_work_order": {
        "type": "InitializeVariable",
        "runAfter": {"Init_diagnosis": ["Succeeded"]},
        "inputs": {"variables": [{"name": "workOrder", "type": "string", "value": "No work order was requested."}]},
    },
    "Init_inspection": {
        "type": "InitializeVariable",
        "runAfter": {"Init_work_order": ["Succeeded"]},
        "inputs": {"variables": [{"name": "inspection", "type": "string", "value": "No part photo was provided."}]},
    },
    "Init_holds": {
        "type": "InitializeVariable",
        "runAfter": {"Init_inspection": ["Succeeded"]},
        "inputs": {"variables": [{"name": "holds", "type": "string", "value": "No batch was above the hold threshold, so no hold was placed."}]},
    },
}

# 1. Quality triage: the analysis classifies the batches, then a separate turn places the holds,
#    so the hold is placed reliably (tool call required) and only for hold-level batches.
actions |= agent_step(
    "Triage", "quality-analyst",
    (
        f"Incident {INCIDENT}: production reports a defect spike on {WHERE}. "
        "Investigate it with the data: compare the shift's defect rate with the line's normal level, "
        "find which machine, product or batches drive it, and name the single most likely machine. "
        "Then classify every batch of the shift with the Quality Hold Procedure (batch defect rate above 10 % = hold, "
        "above 8 % up to 10 % = watch, otherwise normal) and list the batches per class with their defect rates. "
        "Do not place any holds in this step - that is done next. Keep the answer under 200 words."
    ),
    {"Init_holds": ["Succeeded"]},
)
actions |= extract_step(
    "Triage_fields", "Triage_report",
    "Extract the incident triage fields from this analysis. Use an empty string when a value is not stated.",
    TRIAGE_SCHEMA, {"Triage_report": ["Succeeded"]},
)
holds = agent_step(
    "Holds", "quality-analyst",
    (
        "Place the quality holds now: call the placeQualityHold operation of the plant_maintenance_system tool "
        "(a direct tool call - it is not available in Code Interpreter) once for each of these batches: "
        "@{join(outputs('Triage_fields')?['hold_batches'], ', ')}. Put the defect numbers from your analysis in the "
        "reason. Do not place any other holds. Reply with one line per hold: batch ID - the hold ID the tool returned."
    ),
    {},
    require_call="plant_maintenance_system_placeQualityHold",
    previous="Triage",
)
holds["Set_holds"] = set_var("holds", "@{outputs('Holds_report')}", {"Holds_report": ["Succeeded"]})
actions["If_holds"] = {
    "type": "If",
    "runAfter": {"Triage_fields": ["Succeeded"]},
    "expression": {"and": [{"greater": ["@length(coalesce(outputs('Triage_fields')?['hold_batches'], json('[]')))", 0]}]},
    "actions": holds,
    "else": {"actions": {}},
}
actions["Triage_summary"] = {
    "type": "Compose",
    "runAfter": {"If_holds": ["Succeeded", "Failed", "Skipped"]},
    "inputs": "@{outputs('Triage_report')}\n\n**Quality holds placed:**\n\n@{variables('holds')}",
}

# 2a. Visual inspection of the part photo (parallel with maintenance).
inspection = agent_step(
    "Inspection", "visual-inspector",
    [{
        "role": "user",
        "content": [
            {"type": "input_text", "text": (
                f"Incident {INCIDENT}: this photo shows a part taken from {WHERE}. "
                "Inspect it against the quality inspection standard: list the defects with severity class, "
                "give a verdict and the likely process cause. Keep it under 150 words."
            )},
            {"type": "input_image", "image_url": "@{triggerBody()?['photo']}"},
        ],
    }],
    {},
)
actions["If_photo"] = {
    "type": "If",
    "runAfter": {"Triage_summary": ["Succeeded"]},
    "expression": {"and": [{"not": {"equals": ["@coalesce(triggerBody()?['photo'], '')", ""]}}]},
    "actions": inspection | {"Set_inspection": set_var("inspection", "@{outputs('Inspection_report')}", {"Inspection_report": ["Succeeded"]})},
    "else": {"actions": {}},
}

# 2b. Maintenance: diagnose, draft a work order, wait for approval, then let the agent create it.
maintenance = agent_step(
    "Diagnosis", "maintenance-assistant",
    (
        f"Incident {INCIDENT} on {WHERE}: quality found that machine @{{outputs('Triage_fields')?['machine_id']}} "
        "is the most likely cause of the defect spike. Triage: @{outputs('Triage_fields')?['summary']} "
        "Visual inspection of a part from the shift: @{variables('inspection')} "
        "Diagnose the machine from its sensor history, age and failure events, and connect it with the defects found "
        "in the inspection. Look up the applicable alarm and maintenance procedures. Then propose ONE work order "
        "following the work order procedure: priority, title and ordered tasks. Do NOT create the work order yet - "
        "it needs approval first. Keep it under 250 words."
    ),
    {},
)
maintenance |= extract_step(
    "Work_order_draft", "Diagnosis_report",
    "Extract the proposed work order from this maintenance diagnosis. Put the diagnosis summary and the ordered tasks in description.",
    WORK_ORDER_SCHEMA, {"Diagnosis_report": ["Succeeded"]},
)
maintenance["Set_diagnosis"] = set_var("diagnosis", "@{outputs('Diagnosis_report')}", {"Work_order_draft": ["Succeeded"]})
maintenance["Request_approval"] = {
    "type": "Http",
    "runAfter": {"Set_diagnosis": ["Succeeded"]},
    "inputs": {
        "method": "PUT",
        "uri": APPROVAL_URI,
        "headers": TABLE_HEADERS,
        "body": {
            "status": "pending",
            "machine_id": "@{outputs('Work_order_draft')?['machine_id']}",
            "priority": "@{outputs('Work_order_draft')?['priority']}",
            "title": "@{outputs('Work_order_draft')?['title']}",
            "requested_at": "@{utcNow()}",
        },
        "authentication": TABLE_AUTH,
    },
}
maintenance["Wait_for_approval"] = {
    "type": "Until",
    "runAfter": {"Request_approval": ["Succeeded"]},
    "expression": "@not(equals(body('Get_approval')?['status'], 'pending'))",
    "limit": {"count": 400, "timeout": "PT30M"},
    "actions": {
        "Delay_approval": {"type": "Wait", "inputs": {"interval": {"count": 5, "unit": "Second"}}},
        "Get_approval": {
            "type": "Http",
            "runAfter": {"Delay_approval": ["Succeeded"]},
            "inputs": {"method": "GET", "uri": APPROVAL_URI, "headers": TABLE_HEADERS, "authentication": TABLE_AUTH},
        },
    },
}
maintenance["Approval_decision"] = {
    "type": "Compose",
    "runAfter": {"Wait_for_approval": ["Succeeded", "TimedOut", "Failed"]},
    # Outside the loop, so the gallery can read the decision from the run history.
    "inputs": "@coalesce(body('Get_approval'), json('{\"status\": \"no decision\"}'))",
}
approved = agent_step(
    "Work_order", "maintenance-assistant",
    (
        f"Incident {INCIDENT}: your proposed work order was approved by @{{outputs('Approval_decision')?['decided_by']}}. "
        "This is an approved action, not a question: call the createWorkOrder operation of the plant_maintenance_system tool now "
        "(a direct tool call - it is not available in Code Interpreter), "
        "without any analysis first, with exactly these fields - machine_id: @{outputs('Work_order_draft')?['machine_id']}, "
        "priority: @{outputs('Work_order_draft')?['priority']}, "
        "title: @{outputs('Work_order_draft')?['title']}, "
        "requested_by: maintenance-assistant (approved by @{outputs('Approval_decision')?['decided_by']}), "
        "description: @{outputs('Work_order_draft')?['description']} "
        "Then reply in one sentence with the work order ID the tool returned."
    ),
    {},
    require_call="plant_maintenance_system_createWorkOrder",
)
approved["Set_work_order"] = set_var("workOrder", "@{outputs('Work_order_report')}", {"Work_order_report": ["Succeeded"]})
maintenance["If_approved"] = {
    "type": "If",
    "runAfter": {"Approval_decision": ["Succeeded"]},
    "expression": {"and": [{"equals": ["@outputs('Approval_decision')?['status']", "approved"]}]},
    "actions": approved,
    "else": {
        "actions": {
            "Set_work_order_rejected": set_var(
                "workOrder",
                "The proposed work order (@{outputs('Work_order_draft')?['priority']}: @{outputs('Work_order_draft')?['title']}) "
                "was not approved: @{coalesce(outputs('Approval_decision')?['comment'], outputs('Approval_decision')?['status'], 'no decision in time')}.",
                {},
            )
        }
    },
}
actions["If_machine_related"] = {
    "type": "If",
    "runAfter": {"If_photo": ["Succeeded", "Failed", "Skipped"]},
    "expression": {"and": [
        {"equals": ["@outputs('Triage_fields')?['machine_related']", True]},
        {"not": {"equals": ["@outputs('Triage_fields')?['machine_id']", ""]}},
    ]},
    "actions": maintenance,
    "else": {"actions": {}},
}

# 3. Shift handover with an incident section.
actions |= agent_step(
    "Handover", "shift-handover",
    (
        "First call the getBoard operation of the plant_maintenance_system tool (a direct tool call - it is not available "
        "in Code Interpreter) to read the open work orders and quality holds. "
        f"Then write the handover for {WHERE} and add a section 'Incident {INCIDENT}' that summarises what was done:\n"
        "- Quality triage: @{outputs('Triage_fields')?['summary']} Root cause: @{outputs('Triage_fields')?['root_cause']} "
        "Quality holds: @{variables('holds')}\n"
        "- Maintenance diagnosis: @{variables('diagnosis')}\n"
        "- Visual inspection: @{variables('inspection')}\n"
        "- Work order: @{variables('workOrder')}\n"
        "In 'Open work orders & quality holds', list the records returned by getBoard. "
        "Keep the whole handover under 400 words."
    ),
    {"If_machine_related": ["Succeeded", "Failed", "Skipped"], "If_photo": ["Succeeded", "Failed", "Skipped"]},
)
actions["Incident_report"] = {
    "type": "Compose",
    "runAfter": {"Handover_report": ["Succeeded"]},
    "inputs": {
        "incident_id": INCIDENT,
        "triage": "@outputs('Triage_fields')",
        "quality_holds": "@variables('holds')",
        "diagnosis": "@variables('diagnosis')",
        "inspection": "@variables('inspection')",
        "work_order": "@variables('workOrder')",
        "handover": "@outputs('Handover_report')",
    },
}

# Variables must be initialized at the top level, before the first agent step.
previous = "Init_holds"
for step_key in STEP_KEYS:
    for var, var_type, value in ((f"{step_key}Result", "object", {}), (f"{step_key}Attempt", "integer", 0)):
        actions[f"Init_{var}"] = {
            "type": "InitializeVariable",
            "runAfter": {previous: ["Succeeded"]},
            "inputs": {"variables": [{"name": var, "type": var_type, "value": value}]},
        }
        previous = f"Init_{var}"
actions["Run_Triage"]["runAfter"] = {previous: ["Succeeded"]}

definition = {
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {
        "projectEndpoint": {"type": "String"},
        "model": {"type": "String"},
        "storageAccount": {"type": "String"},
    },
    "triggers": {
        "manual": {
            "type": "Request",
            "kind": "Http",
            "inputs": {
                "method": "POST",
                "schema": {
                    "type": "object",
                    "properties": {
                        "line": {"type": "string"},
                        "shift": {"type": "string"},
                        "date": {"type": "string"},
                        "photo": {"type": "string"},
                    },
                },
            },
        }
    },
    "actions": actions,
    "outputs": {},
}

out = Path(__file__).with_name("incident.workflow.json")
out.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(actions)} top-level actions)")
