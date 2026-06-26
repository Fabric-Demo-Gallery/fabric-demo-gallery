"""Build the technology (SaaS) Fabric IQ ontology package.

Entities (4; UsageEvent, SupportTicket span Lakehouse + Eventhouse):
  Account       PK account_id
  User          PK user_id;     FK account_id
  UsageEvent    PK event_id;    FK user_id, account_id   (dual)
  SupportTicket PK ticket_id;   FK account_id            (dual)
"""

from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_scenarios"))
from fabriciq_common import Entity, Prop, write_iq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "technology_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Account", "accounts", [
        Prop("AccountId", "account_id", "String", ident=True, display=True),
        Prop("Plan", "plan"),
        Prop("MrrUsd", "mrr_usd", "Double"),
        Prop("Industry", "industry"),
        Prop("Region", "region"),
        Prop("IsChurned", "is_churned", "BigInt"),
        Prop("SeatCount", "seat_count", "BigInt"),
        Prop("HealthScore", "health_score", "Double"),
    ]),
    Entity("User", "users", [
        Prop("UserId", "user_id", "String", ident=True, display=True),
        Prop("AccountId", "account_id"),
        Prop("Role", "role"),
        Prop("IsActive", "is_active", "BigInt"),
        Prop("LoginsLast30Days", "logins_last_30_days", "BigInt"),
    ]),
    Entity("UsageEvent", "events", [
        Prop("EventId", "event_id", "String", ident=True, display=True),
        Prop("UserId", "user_id"),
        Prop("AccountId", "account_id"),
        Prop("Feature", "feature"),
        Prop("Action", "action"),
        Prop("DurationSecs", "duration_secs", "BigInt", ts=True),
    ]),
    Entity("SupportTicket", "support_tickets", [
        Prop("TicketId", "ticket_id", "String", ident=True, display=True),
        Prop("AccountId", "account_id"),
        Prop("Category", "category"),
        Prop("Priority", "priority"),
        Prop("IsSlaBreached", "is_sla_breached", "BigInt"),
        Prop("ResolutionHrs", "resolution_hrs", "Double", ts=True),
        Prop("CsatScore", "csat_score", "BigInt", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("UserInAccount", "User", "Account"),
    ("EventByUser", "UsageEvent", "User"),
    ("EventForAccount", "UsageEvent", "Account"),
    ("TicketForAccount", "SupportTicket", "Account"),
]
BINDING_RELATIONSHIP = [
    ("UserInAccount", "User", "Account", "user_id", "account_id", "users"),
    ("EventByUser", "UsageEvent", "User", "event_id", "user_id", "events"),
    ("EventForAccount", "UsageEvent", "Account", "event_id", "account_id", "events"),
    ("TicketForAccount", "SupportTicket", "Account", "ticket_id", "account_id", "support_tickets"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    accounts = _read("accounts.csv")
    users = _read("users.csv")
    events = _read("events.csv")
    tickets = _read("support_tickets.csv")

    events_c = events[:EVENT_CAP]
    tickets_c = tickets[:EVENT_CAP]

    instance_tables = {
        "accounts": (["account_id", "plan", "mrr_usd", "industry", "region", "is_churned", "seat_count", "health_score"],
                     [[r["account_id"], r["plan"], r["mrr_usd"], r["industry"], r["region"], r["is_churned"], r["seat_count"], r["health_score"]] for r in accounts]),
        "users": (["user_id", "account_id", "role", "is_active", "logins_last_30_days"],
                  [[r["user_id"], r["account_id"], r["role"], r["is_active"], r["logins_last_30_days"]] for r in users]),
        "events": (["event_id", "user_id", "account_id", "feature", "action"],
                   [[r["event_id"], r["user_id"], r["account_id"], r["feature"], r["action"]] for r in events_c]),
        "support_tickets": (["ticket_id", "account_id", "category", "priority", "is_sla_breached"],
                            [[r["ticket_id"], r["account_id"], r["category"], r["priority"], r["is_sla_breached"]] for r in tickets_c]),
    }
    events_tables = {
        "events": (["event_id", "timestamp_utc", "duration_secs"],
                   [[r["event_id"], r["event_date"], r["duration_secs"]] for r in events_c]),
        "support_tickets": (["ticket_id", "timestamp_utc", "resolution_hrs", "csat_score"],
                            [[r["ticket_id"], r["created_at"], r["resolution_hrs"], r["csat_score"]] for r in tickets_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Accounts: {len(accounts)}  Users: {len(users)}  Events: {len(events_c)}  Tickets: {len(tickets_c)}")


if __name__ == "__main__":
    build()
