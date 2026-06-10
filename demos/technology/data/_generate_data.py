"""Reproducible generator for the Technology (SaaS) demo source data.

Produces ``accounts.csv``, ``users.csv``, ``events.csv`` and
``support_tickets.csv`` with a *learnable* relationship between observable
account / usage / support features and the churn label, so the churn-prediction
classifier trains to a credible AUC (~0.85-0.92).

Signal model (per account):
  * Latent churn propensity is a logistic function of drivers:
      base
      - plan tier        (Enterprise/Professional churn less)
      - log(mrr)         (bigger accounts churn less)
      - log(seat_count)
      + young tenure      (newer accounts churn more)
      + industry/region small effects
      + irreducible noise (keeps AUC < 1.0)
  * ``is_churned = rng < sigmoid(logit)`` — tuned to ~22% prevalence.
  * Downstream signals are generated to CORRELATE with the latent churn risk so
    they become genuine predictors after aggregation:
      - health_score (0-100): high for healthy accounts, low for churn risk.
      - users' logins_last_30_days: lower for churn-risk accounts.
      - event volume per account: lower for churn-risk accounts.
      - support tickets: more SLA breaches + lower CSAT for churn-risk accounts.

IDs are CONSISTENT across files. The ML feature-engineering notebook derives the
target from ``is_churned`` and EXCLUDES leaky columns (``churn_date`` and any
churn-derived flag) from the model.

Run:  python demos/technology/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_ACCOUNTS = 2000
N_USERS = 10000
N_EVENTS = 200000
N_TICKETS = 20000
START_DATE = datetime(2025, 1, 1)
WINDOW_DAYS = 90

OUT_DIR = Path(__file__).resolve().parent

PLANS = ["Starter", "Growth", "Professional", "Enterprise"]
PLAN_MRR = {"Starter": 99, "Growth": 499, "Professional": 1499, "Enterprise": 4999}
PLAN_TIER = {"Starter": 1, "Growth": 2, "Professional": 3, "Enterprise": 4}
PLAN_CHURN = {"Starter": 0.90, "Growth": 0.25, "Professional": -0.45, "Enterprise": -1.10}

INDUSTRIES = ["Manufacturing", "Professional Services", "Retail", "Healthcare",
              "Finance", "Technology", "Education", "Media"]
REGIONS = ["North America", "Europe", "APAC", "LATAM"]

ROLES = ["Admin", "Analyst", "Viewer", "Developer", "Manager"]
FEATURES = ["Dashboard", "Reports", "Data Export", "API", "Integrations",
            "Automation", "Alerts", "ML Insights", "Admin Console", "Billing"]
ACTIONS = ["view", "create", "export", "share", "configure", "delete"]
TICKET_CATEGORIES = ["Bug", "Feature Request", "How-To", "Billing", "Outage"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Accounts with latent churn signal ───────────────────────────────────
    accounts = []
    n_churn = 0
    for i in range(1, N_ACCOUNTS + 1):
        plan = str(rng.choice(PLANS, p=[0.34, 0.36, 0.20, 0.10]))
        mrr = float(PLAN_MRR[plan] * float(rng.uniform(0.85, 1.4)))
        seats = int(np.clip(rng.lognormal(2.0 + 0.5 * PLAN_TIER[plan], 0.6), 1, 500))
        industry = str(rng.choice(INDUSTRIES))
        region = str(rng.choice(REGIONS, p=[0.45, 0.30, 0.15, 0.10]))
        tenure_days = int(rng.integers(30, 1500))
        signup = START_DATE - timedelta(days=tenure_days)

        churn_logit = (
            -1.05
            + PLAN_CHURN[plan]
            - 0.70 * (math.log(mrr) - 6.2)
            - 0.45 * (math.log(seats) - 2.0)
            + (0.95 if tenure_days < 180 else 0.0)
            + 0.15 * (REGIONS.index(region) - 1)
            + float(rng.normal(0, 0.30))
        )
        latent = sigmoid(churn_logit)
        is_churned = rng.random() < latent
        if is_churned:
            n_churn += 1
            churn_date = (START_DATE + timedelta(days=int(rng.integers(0, WINDOW_DAYS)))).strftime("%Y-%m-%d")
        else:
            churn_date = ""

        # health_score anti-correlated with churn risk (strong, wide spread).
        health = float(np.clip(95.0 - 80.0 * latent + rng.normal(0, 6), 1, 100))

        accounts.append({
            "account_id": f"ACC-{i:05d}",
            "plan": plan,
            "mrr_usd": round(mrr, 0),
            "industry": industry,
            "region": region,
            "signup_date": signup.strftime("%Y-%m-%d"),
            "churn_date": churn_date,
            "is_churned": int(is_churned),
            "seat_count": seats,
            "health_score": round(health, 1),
            "latent": latent,
        })

    with (OUT_DIR / "accounts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "plan", "mrr_usd", "industry", "region",
                    "signup_date", "churn_date", "is_churned", "seat_count", "health_score"])
        for a in accounts:
            w.writerow([a["account_id"], a["plan"], a["mrr_usd"], a["industry"], a["region"],
                        a["signup_date"], a["churn_date"], a["is_churned"], a["seat_count"], a["health_score"]])
    print(f"Wrote {len(accounts)} accounts -> accounts.csv ({n_churn} churned, {100*n_churn/len(accounts):.1f}%)")

    acc_by_id = {a["account_id"]: a for a in accounts}

    # ── Users (activity inversely correlated with account churn risk) ───────
    users = []
    for i in range(1, N_USERS + 1):
        acc = accounts[int(rng.integers(0, N_ACCOUNTS))]
        latent = acc["latent"]
        # Healthy accounts -> more logins; churn-risk -> fewer / dormant.
        mean_logins = max(0.0, 30.0 * (1.0 - latent) - 3.0)
        logins = int(np.clip(rng.poisson(max(0.2, mean_logins)), 0, 60))
        is_active = int(logins > 0 and rng.random() > 0.3 * latent)
        last_login = (START_DATE + timedelta(days=int(rng.integers(0, WINDOW_DAYS)))) if logins > 0 \
            else (START_DATE - timedelta(days=int(rng.integers(30, 200))))
        signup = datetime.strptime(acc["signup_date"], "%Y-%m-%d") + timedelta(days=int(rng.integers(0, 120)))
        users.append({
            "user_id": f"USR-{i:07d}",
            "account_id": acc["account_id"],
            "role": str(rng.choice(ROLES)),
            "is_active": is_active,
            "last_login_date": last_login.strftime("%Y-%m-%d"),
            "signup_date": signup.strftime("%Y-%m-%d"),
            "logins_last_30_days": logins,
        })

    with (OUT_DIR / "users.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "account_id", "role", "is_active",
                    "last_login_date", "signup_date", "logins_last_30_days"])
        for u in users:
            w.writerow([u["user_id"], u["account_id"], u["role"], u["is_active"],
                        u["last_login_date"], u["signup_date"], u["logins_last_30_days"]])
    print(f"Wrote {len(users)} users -> users.csv")

    users_by_acc: dict[str, list[dict]] = {}
    for u in users:
        users_by_acc.setdefault(u["account_id"], []).append(u)

    # ── Events (volume inversely correlated with churn risk) ────────────────
    # Build an account sampling weight so churn-risk accounts emit fewer events.
    acc_weight = np.array([max(0.05, 1.0 - a["latent"]) for a in accounts], dtype=float)
    acc_weight /= acc_weight.sum()
    rows = []
    for e in range(1, N_EVENTS + 1):
        ai = int(rng.choice(N_ACCOUNTS, p=acc_weight))
        acc = accounts[ai]
        acc_users = users_by_acc.get(acc["account_id"])
        if not acc_users:
            continue
        u = acc_users[int(rng.integers(0, len(acc_users)))]
        day = START_DATE + timedelta(days=int(rng.integers(0, WINDOW_DAYS)))
        rows.append([
            f"EVT-{e:08d}", u["user_id"], acc["account_id"], day.strftime("%Y-%m-%d"),
            str(rng.choice(FEATURES)), str(rng.choice(ACTIONS)),
            f"SES-{int(rng.integers(1, 999999)):08d}", int(np.clip(rng.exponential(120), 1, 3600)),
        ])
    with (OUT_DIR / "events.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["event_id", "user_id", "account_id", "event_date",
                    "feature", "action", "session_id", "duration_secs"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} events -> events.csv")

    # ── Support tickets (more breaches + lower CSAT for churn-risk accounts) ─
    trows = []
    for t in range(1, N_TICKETS + 1):
        acc = accounts[int(rng.integers(0, N_ACCOUNTS))]
        latent = acc["latent"]
        category = str(rng.choice(TICKET_CATEGORIES))
        priority = str(rng.choice(PRIORITIES, p=[0.35, 0.35, 0.22, 0.08]))
        sla_target = {"Low": 72, "Medium": 24, "High": 8, "Critical": 4}[priority]
        # churn-risk accounts get slower resolutions.
        res_mean = sla_target * (0.6 + 1.4 * latent)
        resolution = float(np.clip(rng.normal(res_mean, sla_target * 0.4), 0.2, sla_target * 4))
        breached = int(resolution > sla_target)
        # CSAT lower for churn-risk + breaches.
        csat = int(np.clip(round(rng.normal(4.7 - 3.2 * latent - 0.6 * breached, 0.6)), 1, 5))
        created = START_DATE + timedelta(days=int(rng.integers(0, WINDOW_DAYS)), hours=int(rng.integers(0, 24)))
        resolved = created + timedelta(hours=resolution)
        trows.append([
            f"TKT-{t:07d}", acc["account_id"], created.strftime("%Y-%m-%d %H:%M:%S"),
            resolved.strftime("%Y-%m-%d %H:%M:%S"), category, priority,
            round(resolution, 2), sla_target, breached, csat,
        ])
    with (OUT_DIR / "support_tickets.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticket_id", "account_id", "created_at", "resolved_at", "category",
                    "priority", "resolution_hrs", "sla_target_hrs", "is_sla_breached", "csat_score"])
        w.writerows(trows)
    print(f"Wrote {len(trows):,} support tickets -> support_tickets.csv")


if __name__ == "__main__":
    main()
