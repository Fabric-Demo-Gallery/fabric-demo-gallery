"""Build the construction Fabric IQ ontology package.

Entities (4; Task, CostEntry span Lakehouse + Eventhouse):
  Project        PK project_id;  FK lead_subcontractor_id
  Subcontractor  PK subcontractor_id
  Task           PK task_id;     FK project_id, assigned_subcontractor_id  (dual)
  CostEntry      PK cost_id;     FK project_id                             (dual)
"""

from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_scenarios"))
from fabriciq_common import Entity, Prop, write_iq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "construction_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Project", "projects", [
        Prop("ProjectId", "project_id", "String", ident=True, display=True),
        Prop("ProjectName", "project_name"),
        Prop("ProjectType", "project_type"),
        Prop("Region", "region"),
        Prop("Status", "status"),
        Prop("Budget", "budget", "Double"),
        Prop("LeadSubcontractorId", "lead_subcontractor_id"),
    ]),
    Entity("Subcontractor", "subcontractors", [
        Prop("SubcontractorId", "subcontractor_id", "String", ident=True, display=True),
        Prop("CompanyName", "company_name"),
        Prop("Trade", "trade"),
        Prop("Region", "region"),
        Prop("Rating", "rating", "Double"),
        Prop("YearsActive", "years_active", "BigInt"),
        Prop("Accredited", "accredited"),
    ]),
    Entity("Task", "tasks", [
        Prop("TaskId", "task_id", "String", ident=True, display=True),
        Prop("ProjectId", "project_id"),
        Prop("AssignedSubcontractorId", "assigned_subcontractor_id"),
        Prop("TaskName", "task_name"),
        Prop("Status", "status"),
        Prop("IsDelayed", "is_delayed", "BigInt"),
        Prop("PctComplete", "pct_complete", "Double", ts=True),
        Prop("ScheduleVarianceDays", "schedule_variance_days", "BigInt", ts=True),
    ]),
    Entity("CostEntry", "cost_ledger", [
        Prop("CostId", "cost_id", "String", ident=True, display=True),
        Prop("ProjectId", "project_id"),
        Prop("CostCategory", "cost_category"),
        Prop("Supplier", "supplier"),
        Prop("Approved", "approved"),
        Prop("PlannedCost", "planned_cost", "Double", ts=True),
        Prop("ActualCost", "actual_cost", "Double", ts=True),
        Prop("CostVariance", "cost_variance", "Double", ts=True),
        Prop("CostVariancePct", "cost_variance_pct", "Double", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("ProjectLedBy", "Project", "Subcontractor"),
    ("TaskInProject", "Task", "Project"),
    ("TaskAssignedTo", "Task", "Subcontractor"),
    ("CostForProject", "CostEntry", "Project"),
]
BINDING_RELATIONSHIP = [
    ("ProjectLedBy", "Project", "Subcontractor", "project_id", "lead_subcontractor_id", "projects"),
    ("TaskInProject", "Task", "Project", "task_id", "project_id", "tasks"),
    ("TaskAssignedTo", "Task", "Subcontractor", "task_id", "assigned_subcontractor_id", "tasks"),
    ("CostForProject", "CostEntry", "Project", "cost_id", "project_id", "cost_ledger"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    projects = _read("projects.csv")
    subs = _read("subcontractors.csv")
    tasks = _read("tasks.csv")
    costs = _read("cost_ledger.csv")

    tasks_c = tasks[:EVENT_CAP]
    costs_c = costs[:EVENT_CAP]

    def task_start(r):
        return r.get("actual_start_date") or r.get("planned_start_date")

    instance_tables = {
        "projects": (["project_id", "project_name", "project_type", "region", "status", "budget", "lead_subcontractor_id"],
                     [[r["project_id"], r["project_name"], r["project_type"], r["region"], r["status"], r["budget"], r["lead_subcontractor_id"]] for r in projects]),
        "subcontractors": (["subcontractor_id", "company_name", "trade", "region", "rating", "years_active", "accredited"],
                           [[r["subcontractor_id"], r["company_name"], r["trade"], r["region"], r["rating"], r["years_active"], r["accredited"]] for r in subs]),
        "tasks": (["task_id", "project_id", "assigned_subcontractor_id", "task_name", "status", "is_delayed"],
                  [[r["task_id"], r["project_id"], r["assigned_subcontractor_id"], r["task_name"], r["status"], r["is_delayed"]] for r in tasks_c]),
        "cost_ledger": (["cost_id", "project_id", "cost_category", "supplier", "approved"],
                        [[r["cost_id"], r["project_id"], r["cost_category"], r["supplier"], r["approved"]] for r in costs_c]),
    }
    events_tables = {
        "tasks": (["task_id", "timestamp_utc", "pct_complete", "schedule_variance_days"],
                  [[r["task_id"], task_start(r), r["pct_complete"], r["schedule_variance_days"]] for r in tasks_c]),
        "cost_ledger": (["cost_id", "timestamp_utc", "planned_cost", "actual_cost", "cost_variance", "cost_variance_pct"],
                        [[r["cost_id"], r["entry_date"], r["planned_cost"], r["actual_cost"], r["cost_variance"], r["cost_variance_pct"]] for r in costs_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Projects: {len(projects)}  Subcontractors: {len(subs)}  Tasks: {len(tasks_c)}  Costs: {len(costs_c)}")


if __name__ == "__main__":
    build()
