"""Reproducible generator for the Professional-Services demo source data.

Produces ``clients.csv``, ``consultants.csv``, ``engagements.csv`` and
``timesheets.csv`` with a *learnable* relationship between observable
engagement / client / consultant features and the **project-overrun** label
(``is_over_budget``), so the outcome classifier trains to a credible AUC
(~0.80-0.88).

Use case: Project Outcome Prediction — predict whether an engagement will run
*over budget* (actual spend exceeds planned budget).

Signal model (per engagement):
  * Overrun propensity is a logistic function of drivers:
      base
      + practice risk      (Technology / Data harder to estimate)
      + planned duration    (longer projects drift more)
      + headcount           (bigger teams overrun more)
      - lead seniority       (senior leads deliver on budget)
      - lead experience
      + client tier risk     (Strategic engagements are more ambitious)
      + industry risk        (Government / Healthcare overrun more)
      + budget size
      + irreducible noise (keeps AUC < 1.0)
  * actual_spend_gbp, margin_pct, status are DERIVED from the label
    (post-project leakage); the FE notebook EXCLUDES them.
  * Target prevalence ~38%.

IDs are CONSISTENT: every engagement references an existing client + lead
consultant, and timesheets reference existing consultants + engagements.

Run:  python demos/professional-services/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_CLIENTS = 120
N_CONSULTANTS = 300
N_ENGAGEMENTS = 8000
N_TIMESHEETS = 60000
START_DATE = datetime(2024, 1, 1)

OUT_DIR = Path(__file__).resolve().parent

INDUSTRIES = ["Energy", "Finance", "Government", "Healthcare",
              "Manufacturing", "Retail", "Technology"]
INDUSTRY_RISK = {"Energy": 0.10, "Finance": -0.15, "Government": 0.65, "Healthcare": 0.45,
                 "Manufacturing": 0.05, "Retail": -0.20, "Technology": 0.25}
REGIONS = ["Dubai", "Frankfurt", "London", "New York", "Paris", "Singapore", "Sydney"]
TIERS = ["Standard", "Key", "Strategic"]
TIER_RISK = {"Standard": -0.20, "Key": 0.15, "Strategic": 0.55}
PRACTICES = ["Change Management", "Data & Analytics", "Finance", "HR",
             "Operations", "Strategy", "Technology"]
PRACTICE_RISK = {"Change Management": 0.10, "Data & Analytics": 0.55, "Finance": -0.20,
                 "HR": -0.30, "Operations": 0.00, "Strategy": 0.20, "Technology": 0.65}
GRADES = ["Analyst", "Consultant", "Senior Consultant", "Manager",
          "Principal", "Director", "Partner"]
# Higher grade -> lower overrun risk (more seniority).
GRADE_SENIORITY = {"Analyst": 0, "Consultant": 1, "Senior Consultant": 2, "Manager": 3,
                   "Principal": 4, "Director": 5, "Partner": 6}
GRADE_RATE = {"Analyst": 450, "Consultant": 620, "Senior Consultant": 820, "Manager": 1050,
              "Principal": 1350, "Director": 1700, "Partner": 2200}
TASK_TYPES = ["Delivery", "Business Development", "Research", "Client Workshop",
              "Internal", "Project Management"]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Clients ─────────────────────────────────────────────────────────────
    clients = []
    for i in range(1, N_CLIENTS + 1):
        clients.append({
            "client_id": f"CLI-{i:04d}",
            "client_name": f"Client {i} {str(rng.choice(['Group', 'Holdings', 'Partners', 'Industries']))}",
            "industry": str(rng.choice(INDUSTRIES)),
            "region": str(rng.choice(REGIONS)),
            "tier": str(rng.choice(TIERS, p=[0.55, 0.30, 0.15])),
            "contract_value_gbp": round(float(rng.uniform(50000, 800000)), 2),
            "relationship_years": int(rng.integers(1, 16)),
            "nps_score": int(rng.integers(-20, 81)),
        })
    with (OUT_DIR / "clients.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["client_id", "client_name", "industry", "region", "tier",
                    "contract_value_gbp", "relationship_years", "nps_score"])
        for c in clients:
            w.writerow([c["client_id"], c["client_name"], c["industry"], c["region"], c["tier"],
                        c["contract_value_gbp"], c["relationship_years"], c["nps_score"]])
    print(f"Wrote {len(clients)} clients -> clients.csv")

    # ── Consultants ─────────────────────────────────────────────────────────
    consultants = []
    for i in range(1, N_CONSULTANTS + 1):
        grade = str(rng.choice(GRADES, p=[0.18, 0.22, 0.20, 0.16, 0.12, 0.08, 0.04]))
        yrs = int(np.clip(GRADE_SENIORITY[grade] * 2 + rng.integers(0, 5), 0, 35))
        consultants.append({
            "consultant_id": f"CON-{i:04d}",
            "grade": grade,
            "practice": str(rng.choice(PRACTICES)),
            "region": str(rng.choice(REGIONS)),
            "daily_rate_gbp": int(GRADE_RATE[grade] * float(rng.uniform(0.9, 1.15))),
            "years_experience": yrs,
            "is_billable": int(rng.random() < 0.85),
            "hire_date": (START_DATE - timedelta(days=int(rng.integers(180, 6000)))).strftime("%Y-%m-%d"),
        })
    with (OUT_DIR / "consultants.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["consultant_id", "grade", "practice", "region", "daily_rate_gbp",
                    "years_experience", "is_billable", "hire_date"])
        for c in consultants:
            w.writerow([c["consultant_id"], c["grade"], c["practice"], c["region"],
                        c["daily_rate_gbp"], c["years_experience"], c["is_billable"],
                        c["hire_date"]])
    print(f"Wrote {len(consultants)} consultants -> consultants.csv")

    # ── Engagements with learnable overrun signal ───────────────────────────
    client_by_id = {c["client_id"]: c for c in clients}
    rows = []
    n_over = 0
    for e in range(1, N_ENGAGEMENTS + 1):
        client = clients[int(rng.integers(0, N_CLIENTS))]
        lead = consultants[int(rng.integers(0, N_CONSULTANTS))]
        practice = str(rng.choice(PRACTICES))
        budget = round(float(rng.uniform(80000, 1200000)), 2)
        planned_days = int(np.clip(rng.normal(180, 70), 30, 540))
        headcount = int(np.clip(rng.poisson(8) + 2, 2, 40))
        start = START_DATE + timedelta(days=int(rng.integers(0, 600)))
        planned_end = start + timedelta(days=planned_days)

        overrun_logit = (
            -1.95
            + 1.55 * PRACTICE_RISK[practice]
            + 0.0040 * (planned_days - 180)
            + 0.075 * (headcount - 8)
            - 0.42 * (GRADE_SENIORITY[lead["grade"]] - 3)
            - 0.035 * (lead["years_experience"] - 10)
            + 1.50 * TIER_RISK[client["tier"]]
            + 1.50 * INDUSTRY_RISK[client["industry"]]
            + 0.00000110 * (budget - 400000)
            + float(rng.normal(0, 0.28))
        )
        is_over = int(rng.random() < sigmoid(overrun_logit))
        if is_over:
            n_over += 1
            spend = round(budget * float(rng.uniform(1.02, 1.45)), 2)
            status = str(rng.choice(["Delayed", "At Risk", "Cancelled"], p=[0.45, 0.35, 0.20]))
        else:
            spend = round(budget * float(rng.uniform(0.70, 0.99)), 2)
            status = str(rng.choice(["Completed", "On Track"], p=[0.55, 0.45]))
        margin = round((budget - spend) / budget * 100, 2)

        rows.append([
            f"ENG-{e:05d}", client["client_id"], lead["consultant_id"], practice,
            start.strftime("%Y-%m-%d"), planned_end.strftime("%Y-%m-%d"),
            budget, spend, margin, status, headcount,
            planned_days, is_over,
        ])

    with (OUT_DIR / "engagements.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["engagement_id", "client_id", "lead_consultant_id", "practice",
                    "start_date", "planned_end_date", "budget_gbp", "actual_spend_gbp",
                    "margin_pct", "status", "headcount", "planned_duration_days", "is_over_budget"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} engagements -> engagements.csv "
          f"({n_over:,} over budget, {100*n_over/len(rows):.1f}%)")

    # ── Timesheets (reference existing consultants + engagements) ───────────
    eng_ids = [r[0] for r in rows]
    trows = []
    for t in range(1, N_TIMESHEETS + 1):
        con = consultants[int(rng.integers(0, N_CONSULTANTS))]
        eng = eng_ids[int(rng.integers(0, len(eng_ids)))]
        task = str(rng.choice(TASK_TYPES, p=[0.45, 0.10, 0.10, 0.12, 0.10, 0.13]))
        billable = int(con["is_billable"] and task in ("Delivery", "Client Workshop", "Project Management"))
        hours = round(float(rng.uniform(0.5, 12.0)), 2)
        rate = con["daily_rate_gbp"]
        billed = round(hours / 8.0 * rate, 2) if billable else 0.0
        trows.append([
            f"TS-{t:07d}", con["consultant_id"], eng,
            (START_DATE + timedelta(days=int(rng.integers(0, 700)))).strftime("%Y-%m-%d"),
            task, hours, billable, rate, billed,
        ])
    with (OUT_DIR / "timesheets.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timesheet_id", "consultant_id", "engagement_id", "week_starting",
                    "task_type", "hours_logged", "is_billable", "daily_rate_gbp", "billed_value_gbp"])
        w.writerows(trows)
    print(f"Wrote {len(trows):,} timesheets -> timesheets.csv")


if __name__ == "__main__":
    main()
