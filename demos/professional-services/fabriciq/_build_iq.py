"""Build the professional-services Fabric IQ ontology package.

Entities (5; Engagement, ProjectEvent, Timesheet span Lakehouse + Eventhouse):
  Client       PK client_id
  Consultant   PK consultant_id
  Engagement   PK engagement_id;  FK client_id, lead_consultant_id   (dual)
  ProjectEvent PK event_id;       FK engagement_id, consultant_id    (dual)
  Timesheet    PK timesheet_id;   FK consultant_id, engagement_id    (dual)
"""

from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_scenarios"))
from fabriciq_common import Entity, Prop, write_iq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "professional_services_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Client", "clients", [
        Prop("ClientId", "client_id", "String", ident=True, display=True),
        Prop("ClientName", "client_name"),
        Prop("Industry", "industry"),
        Prop("Region", "region"),
        Prop("Tier", "tier"),
        Prop("ContractValueGbp", "contract_value_gbp", "Double"),
        Prop("RelationshipYears", "relationship_years", "BigInt"),
        Prop("NpsScore", "nps_score", "BigInt"),
    ]),
    Entity("Consultant", "consultants", [
        Prop("ConsultantId", "consultant_id", "String", ident=True, display=True),
        Prop("Grade", "grade"),
        Prop("Practice", "practice"),
        Prop("Region", "region"),
        Prop("DailyRateGbp", "daily_rate_gbp", "Double"),
        Prop("YearsExperience", "years_experience", "BigInt"),
        Prop("IsBillable", "is_billable", "BigInt"),
    ]),
    Entity("Engagement", "engagements", [
        Prop("EngagementId", "engagement_id", "String", ident=True, display=True),
        Prop("ClientId", "client_id"),
        Prop("LeadConsultantId", "lead_consultant_id"),
        Prop("Practice", "practice"),
        Prop("Status", "status"),
        Prop("IsOverBudget", "is_over_budget", "BigInt"),
        Prop("BudgetGbp", "budget_gbp", "Double"),
        Prop("Headcount", "headcount", "BigInt"),
        Prop("ActualSpendGbp", "actual_spend_gbp", "Double", ts=True),
        Prop("MarginPct", "margin_pct", "Double", ts=True),
    ]),
    Entity("ProjectEvent", "project_events", [
        Prop("EventId", "event_id", "String", ident=True, display=True),
        Prop("EngagementId", "engagement_id"),
        Prop("ConsultantId", "consultant_id"),
        Prop("TaskType", "task_type"),
        Prop("HoursLogged", "hours_logged", "Double", ts=True),
        Prop("CostGbp", "cost_gbp", "Double", ts=True),
        Prop("BudgetRemainingPct", "budget_remaining_pct", "Double", ts=True),
    ]),
    Entity("Timesheet", "timesheets", [
        Prop("TimesheetId", "timesheet_id", "String", ident=True, display=True),
        Prop("ConsultantId", "consultant_id"),
        Prop("EngagementId", "engagement_id"),
        Prop("TaskType", "task_type"),
        Prop("IsBillable", "is_billable", "BigInt"),
        Prop("HoursLogged", "hours_logged", "Double", ts=True),
        Prop("BilledValueGbp", "billed_value_gbp", "Double", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("EngagementForClient", "Engagement", "Client"),
    ("EngagementLedBy", "Engagement", "Consultant"),
    ("EventForEngagement", "ProjectEvent", "Engagement"),
    ("EventByConsultant", "ProjectEvent", "Consultant"),
    ("TimesheetForEngagement", "Timesheet", "Engagement"),
    ("TimesheetByConsultant", "Timesheet", "Consultant"),
]
BINDING_RELATIONSHIP = [
    ("EngagementForClient", "Engagement", "Client", "engagement_id", "client_id", "engagements"),
    ("EngagementLedBy", "Engagement", "Consultant", "engagement_id", "lead_consultant_id", "engagements"),
    ("EventForEngagement", "ProjectEvent", "Engagement", "event_id", "engagement_id", "project_events"),
    ("EventByConsultant", "ProjectEvent", "Consultant", "event_id", "consultant_id", "project_events"),
    ("TimesheetForEngagement", "Timesheet", "Engagement", "timesheet_id", "engagement_id", "timesheets"),
    ("TimesheetByConsultant", "Timesheet", "Consultant", "timesheet_id", "consultant_id", "timesheets"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    clients = _read("clients.csv")
    consultants = _read("consultants.csv")
    engagements = _read("engagements.csv")
    events = _read("project_events.csv")
    timesheets = _read("timesheets.csv")

    eng_c = engagements[:EVENT_CAP]
    ev_c = events[:EVENT_CAP]
    ts_c = timesheets[:EVENT_CAP]

    instance_tables = {
        "clients": (["client_id", "client_name", "industry", "region", "tier", "contract_value_gbp", "relationship_years", "nps_score"],
                    [[r["client_id"], r["client_name"], r["industry"], r["region"], r["tier"], r["contract_value_gbp"], r["relationship_years"], r["nps_score"]] for r in clients]),
        "consultants": (["consultant_id", "grade", "practice", "region", "daily_rate_gbp", "years_experience", "is_billable"],
                        [[r["consultant_id"], r["grade"], r["practice"], r["region"], r["daily_rate_gbp"], r["years_experience"], r["is_billable"]] for r in consultants]),
        "engagements": (["engagement_id", "client_id", "lead_consultant_id", "practice", "status", "is_over_budget", "budget_gbp", "headcount"],
                        [[r["engagement_id"], r["client_id"], r["lead_consultant_id"], r["practice"], r["status"], r["is_over_budget"], r["budget_gbp"], r["headcount"]] for r in eng_c]),
        "project_events": (["event_id", "engagement_id", "consultant_id", "task_type"],
                           [[r["event_id"], r["engagement_id"], r["consultant_id"], r["task_type"]] for r in ev_c]),
        "timesheets": (["timesheet_id", "consultant_id", "engagement_id", "task_type", "is_billable"],
                       [[r["timesheet_id"], r["consultant_id"], r["engagement_id"], r["task_type"], r["is_billable"]] for r in ts_c]),
    }
    events_tables = {
        "engagements": (["engagement_id", "timestamp_utc", "actual_spend_gbp", "margin_pct"],
                        [[r["engagement_id"], r["start_date"], r["actual_spend_gbp"], r["margin_pct"]] for r in eng_c]),
        "project_events": (["event_id", "timestamp_utc", "hours_logged", "cost_gbp", "budget_remaining_pct"],
                           [[r["event_id"], r["event_date"], r["hours_logged"], r["cost_gbp"], r["budget_remaining_pct"]] for r in ev_c]),
        "timesheets": (["timesheet_id", "timestamp_utc", "hours_logged", "billed_value_gbp"],
                       [[r["timesheet_id"], r["week_starting"], r["hours_logged"], r["billed_value_gbp"]] for r in ts_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Clients: {len(clients)}  Consultants: {len(consultants)}  Engagements: {len(eng_c)}  Events: {len(ev_c)}  Timesheets: {len(ts_c)}")


if __name__ == "__main__":
    build()
