"""Reproducible generator for the Construction demo source data.

Produces ``subcontractors.csv``, ``projects.csv``, ``tasks.csv`` and
``cost_ledger.csv`` with a *learnable* relationship between observable
task / project / subcontractor features and the **task-delay** label
(``is_delayed``), so the delay classifier trains to a credible AUC
(~0.80-0.88).

Use case: Project Delay Prediction — predict whether a construction task will
finish *late* (schedule variance exceeds a threshold of materiality).

Signal model (per task):
  * Delay propensity is a logistic function of drivers:
      base
      + task-type risk      (MEP / Roofing harder to schedule than Site Prep)
      + planned duration     (longer tasks drift more)
      - subcontractor rating (better subs deliver on time)
      - accredited?          (accredited subs deliver on time)
      + trade risk           (Structural Steel / MEP riskier)
      + project-type risk     (Infrastructure overruns more)
      + irreducible noise (keeps AUC < 1.0)
  * actual_start_date, forecast_end_date, schedule_variance_days, status,
    pct_complete are DERIVED from the label (post-task leakage); the FE
    notebook EXCLUDES them.
  * Target prevalence ~38%.

IDs are CONSISTENT: every task references an existing project + assigned
subcontractor, and cost-ledger rows reference existing projects.

Run:  python demos/construction/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_SUBCONTRACTORS = 100
N_PROJECTS = 200
N_TASKS = 15000
N_COST = 50000
START_DATE = datetime(2024, 1, 1)

OUT_DIR = Path(__file__).resolve().parent

TRADES = ["Civil Engineering", "Electrical", "Fit-Out", "Glazing", "Groundworks",
          "Landscaping", "MEP", "Plumbing", "Roofing", "Structural Steel"]
TRADE_RISK = {"Civil Engineering": 0.15, "Electrical": 0.10, "Fit-Out": -0.10, "Glazing": 0.05,
              "Groundworks": 0.25, "Landscaping": -0.25, "MEP": 0.55, "Plumbing": 0.00,
              "Roofing": 0.40, "Structural Steel": 0.50}
REGIONS = ["London", "Midlands", "North West", "Scotland", "South East", "South West", "Wales"]
PROJECT_TYPES = ["Commercial", "Industrial", "Infrastructure", "Renovation", "Residential"]
PROJECT_TYPE_RISK = {"Commercial": 0.05, "Industrial": 0.20, "Infrastructure": 0.55,
                     "Renovation": 0.30, "Residential": -0.15}
TASK_NAMES = ["Site Preparation", "Foundation", "Framing", "Roofing", "MEP Rough-In",
              "Plumbing Fit-Out", "Electrical Fit-Out", "Insulation", "Drywall",
              "Finishing", "Inspection", "Commissioning", "Handover"]
TASK_RISK = {"Site Preparation": -0.30, "Foundation": 0.10, "Framing": 0.05, "Roofing": 0.40,
             "MEP Rough-In": 0.55, "Plumbing Fit-Out": 0.10, "Electrical Fit-Out": 0.15,
             "Insulation": -0.10, "Drywall": -0.05, "Finishing": 0.20, "Inspection": -0.20,
             "Commissioning": 0.35, "Handover": -0.25}
COST_CATEGORIES = ["Labour", "Materials", "Plant & Equipment", "Subcontractor", "Overheads"]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Subcontractors ──────────────────────────────────────────────────────
    subs = []
    for i in range(1, N_SUBCONTRACTORS + 1):
        rating = round(float(np.clip(rng.normal(3.8, 0.6), 1.0, 5.0)), 1)
        subs.append({
            "subcontractor_id": f"SUB-{i:04d}",
            "company_name": f"Sub-Contractor {i} Ltd",
            "trade": str(rng.choice(TRADES)),
            "region": str(rng.choice(REGIONS)),
            "rating": rating,
            "years_active": int(rng.integers(1, 31)),
            "accredited": "Y" if rng.random() < 0.6 else "N",
        })
    with (OUT_DIR / "subcontractors.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subcontractor_id", "company_name", "trade", "region",
                    "rating", "years_active", "accredited"])
        for s in subs:
            w.writerow([s["subcontractor_id"], s["company_name"], s["trade"], s["region"],
                        s["rating"], s["years_active"], s["accredited"]])
    print(f"Wrote {len(subs)} subcontractors -> subcontractors.csv")

    # ── Projects ────────────────────────────────────────────────────────────
    projects = []
    for i in range(1, N_PROJECTS + 1):
        ptype = str(rng.choice(PROJECT_TYPES))
        lead = subs[int(rng.integers(0, N_SUBCONTRACTORS))]
        p_start = START_DATE + timedelta(days=int(rng.integers(0, 400)))
        p_dur = int(rng.integers(120, 720))
        p_end = p_start + timedelta(days=p_dur)
        projects.append({
            "project_id": f"PRJ-{i:04d}",
            "project_name": f"Project {i} - {ptype}",
            "project_type": ptype,
            "region": str(rng.choice(REGIONS)),
            "status": str(rng.choice(["Planning", "In Progress", "Completed", "On Hold", "Cancelled"],
                                     p=[0.12, 0.42, 0.30, 0.10, 0.06])),
            "budget": round(float(rng.uniform(500000, 50000000)), 2),
            "planned_start_date": p_start.strftime("%Y-%m-%d"),
            "planned_end_date": p_end.strftime("%Y-%m-%d"),
            "lead_subcontractor_id": lead["subcontractor_id"],
        })
    with (OUT_DIR / "projects.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["project_id", "project_name", "project_type", "region", "status",
                    "budget", "planned_start_date", "planned_end_date", "lead_subcontractor_id"])
        for p in projects:
            w.writerow([p["project_id"], p["project_name"], p["project_type"], p["region"],
                        p["status"], p["budget"], p["planned_start_date"], p["planned_end_date"],
                        p["lead_subcontractor_id"]])
    print(f"Wrote {len(projects)} projects -> projects.csv")

    # ── Tasks with learnable delay signal ───────────────────────────────────
    sub_by_id = {s["subcontractor_id"]: s for s in subs}
    proj_by_id = {p["project_id"]: p for p in projects}
    rows = []
    n_delayed = 0
    for t in range(1, N_TASKS + 1):
        proj = projects[int(rng.integers(0, N_PROJECTS))]
        sub = subs[int(rng.integers(0, N_SUBCONTRACTORS))]
        task_name = str(rng.choice(TASK_NAMES))
        planned_days = int(np.clip(rng.normal(30, 14), 3, 120))
        p_start = datetime.strptime(proj["planned_start_date"], "%Y-%m-%d") + timedelta(days=int(rng.integers(0, 200)))
        p_end = p_start + timedelta(days=planned_days)

        delay_logit = (
            -1.05
            + 2.40 * TASK_RISK[task_name]
            + 0.026 * (planned_days - 30)
            - 1.05 * (sub["rating"] - 3.8)
            - 0.75 * (1 if sub["accredited"] == "Y" else 0)
            + 2.40 * TRADE_RISK[sub["trade"]]
            + 2.40 * PROJECT_TYPE_RISK[proj["project_type"]]
            + float(rng.normal(0, 0.24))
        )
        is_delayed = int(rng.random() < sigmoid(delay_logit))
        if is_delayed:
            n_delayed += 1
            sched_var = int(np.clip(round(rng.uniform(6, 45)), 6, 90))
            status = str(rng.choice(["Delayed", "Blocked"], p=[0.7, 0.3]))
            pct = round(float(rng.uniform(20, 95)), 1)
        else:
            sched_var = int(round(rng.uniform(-3, 5)))
            status = str(rng.choice(["Completed", "In Progress", "Not Started"], p=[0.5, 0.35, 0.15]))
            pct = round(float(rng.uniform(40, 100)), 1) if status != "Not Started" else 0.0
        a_start = p_start + timedelta(days=int(np.clip(round(rng.normal(sched_var * 0.4, 2)), -5, 60)))
        f_end = p_end + timedelta(days=sched_var)

        rows.append([
            f"TSK-{t:06d}", proj["project_id"], task_name, sub["subcontractor_id"],
            p_start.strftime("%Y-%m-%d"), p_end.strftime("%Y-%m-%d"),
            a_start.strftime("%Y-%m-%d"), f_end.strftime("%Y-%m-%d"),
            sched_var, status, pct, planned_days, is_delayed,
        ])

    with (OUT_DIR / "tasks.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["task_id", "project_id", "task_name", "assigned_subcontractor_id",
                    "planned_start_date", "planned_end_date", "actual_start_date",
                    "forecast_end_date", "schedule_variance_days", "status", "pct_complete",
                    "planned_duration_days", "is_delayed"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} tasks -> tasks.csv "
          f"({n_delayed:,} delayed, {100*n_delayed/len(rows):.1f}%)")

    # ── Cost ledger (reference existing projects) ───────────────────────────
    crows = []
    for c in range(1, N_COST + 1):
        proj = projects[int(rng.integers(0, N_PROJECTS))]
        category = str(rng.choice(COST_CATEGORIES, p=[0.28, 0.30, 0.14, 0.20, 0.08]))
        planned = round(float(rng.uniform(5000, 500000)), 2)
        variance_pct = round(float(rng.normal(2.0, 8.0)), 2)
        actual = round(planned * (1 + variance_pct / 100.0), 2)
        crows.append([
            f"CST-{c:07d}", proj["project_id"],
            (START_DATE + timedelta(days=int(rng.integers(0, 700)))).strftime("%Y-%m-%d"),
            category, f"Supplier-{int(rng.integers(1, 300)):03d}",
            planned, actual, round(actual - planned, 2), variance_pct,
            "Y" if rng.random() < 0.85 else "N",
        ])
    with (OUT_DIR / "cost_ledger.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cost_id", "project_id", "entry_date", "cost_category", "supplier",
                    "planned_cost", "actual_cost", "cost_variance", "cost_variance_pct", "approved"])
        w.writerows(crows)
    print(f"Wrote {len(crows):,} cost-ledger rows -> cost_ledger.csv")


if __name__ == "__main__":
    main()
