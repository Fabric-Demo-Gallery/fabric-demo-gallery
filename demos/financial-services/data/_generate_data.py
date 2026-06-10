"""Reproducible generator for the Financial Services demo source data.

Produces ``customers.csv``, ``accounts.csv`` and ``transactions.csv`` with a
*learnable* relationship between observable transaction / account / customer
features and the fraud label, so the fraud-detection classifier trains to a
credible AUC (~0.80-0.90) instead of behaving like a coin flip on uncorrelated
random data.

Signal model (per transaction):
  * Latent fraud propensity is a logistic function of observable drivers:
      base
      + amount_z          (larger amounts are riskier)
      + international      (country != UK)
      + night-time hour
      + channel risk      (Online / POS riskier than Branch / ATM)
      + merchant risk      (Wire Transfer / International / Online Shopping riskier)
      + customer risk_tier
      + account credit-utilisation
      + irreducible noise (keeps AUC < 1.0)
  * ``is_flagged_fraud = rng < sigmoid(fraud_logit)`` — tuned to ~10% prevalence
    so there are plenty of positives to learn from.

IDs are CONSISTENT across files (each transaction's account + customer exist in
the dimension tables) so the silver joins line up. The ML feature-engineering
notebook derives the target from ``is_flagged_fraud`` and EXCLUDES the leaky
silver columns ``risk_score`` / ``risk_band`` (which are computed from the fraud
flag) from the model features.

Run:  python demos/financial-services/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_CUSTOMERS = 2000
N_ACCOUNTS = 5000
N_TRANSACTIONS = 100_000
N_DAYS = 90
START_DATE = datetime(2025, 1, 1)

OUT_DIR = Path(__file__).resolve().parent

AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
SEGMENTS = ["Retail", "SME", "Corporate", "Private Banking"]
REGIONS = ["London", "South East", "North West", "Midlands", "Scotland",
           "Wales", "North East", "South West"]
RISK_TIERS = ["Low", "Medium", "High", "Very High"]
# Customer risk tier -> latent fraud offset.
RISK_TIER_OFFSET = {"Low": -0.70, "Medium": -0.15, "High": 0.55, "Very High": 1.15}

ACCOUNT_TYPES = ["Current", "Savings", "Business Current", "Mortgage", "Credit Card"]
ACCOUNT_STATUS = ["Active", "Active", "Active", "Active", "Dormant", "Closed"]

TXN_TYPES = ["Purchase", "Transfer", "Withdrawal", "Direct Debit", "Fee", "Refund"]
CHANNELS = ["Online", "POS", "Mobile", "ATM", "Branch"]
# Channel -> latent fraud offset (card-not-present channels riskier).
CHANNEL_RISK = {"Online": 0.85, "Mobile": 0.45, "POS": 0.20, "ATM": -0.25, "Branch": -0.80}

COUNTRIES = ["UK", "US", "DE", "FR", "CN", "NG", "UAE"]
# Non-UK countries get the international risk bump (applied separately too).
COUNTRY_WEIGHTS = [0.82, 0.05, 0.03, 0.03, 0.025, 0.025, 0.02]

MERCHANTS = ["Groceries", "Restaurants", "Retail", "Utilities", "Entertainment",
             "Healthcare", "Insurance", "Travel", "Electronics", "Online Shopping",
             "ATM Withdrawal", "International", "Wire Transfer"]
# Merchant category -> latent fraud offset.
MERCHANT_RISK = {
    "Groceries": -0.55, "Restaurants": -0.40, "Retail": -0.15, "Utilities": -0.60,
    "Entertainment": -0.10, "Healthcare": -0.30, "Insurance": -0.25, "Travel": 0.40,
    "Electronics": 0.55, "Online Shopping": 0.70, "ATM Withdrawal": 0.15,
    "International": 1.05, "Wire Transfer": 1.30,
}
# Typical amount scale (lognormal mean of log) per merchant category.
MERCHANT_AMOUNT = {
    "Groceries": 3.4, "Restaurants": 3.6, "Retail": 4.0, "Utilities": 4.2,
    "Entertainment": 3.7, "Healthcare": 4.4, "Insurance": 4.8, "Travel": 5.4,
    "Electronics": 5.2, "Online Shopping": 4.3, "ATM Withdrawal": 4.0,
    "International": 5.6, "Wire Transfer": 6.4,
}


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Customers ───────────────────────────────────────────────────────────
    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        risk = str(rng.choice(RISK_TIERS, p=[0.45, 0.30, 0.18, 0.07]))
        customers.append({
            "customer_id": f"CUST-{i:05d}",
            "age_group": str(rng.choice(AGE_GROUPS)),
            "segment": str(rng.choice(SEGMENTS, p=[0.55, 0.25, 0.12, 0.08])),
            "region": str(rng.choice(REGIONS)),
            "risk_tier": risk,
            "since_year": int(rng.integers(2005, 2025)),
        })

    with (OUT_DIR / "customers.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["customer_id", "age_group", "segment", "region", "risk_tier", "since_year"])
        for c in customers:
            w.writerow([c["customer_id"], c["age_group"], c["segment"],
                        c["region"], c["risk_tier"], c["since_year"]])
    print(f"Wrote {len(customers)} customers -> customers.csv")

    cust_by_id = {c["customer_id"]: c for c in customers}

    # ── Accounts (each linked to a customer) ────────────────────────────────
    accounts = []
    for i in range(1, N_ACCOUNTS + 1):
        cust = customers[int(rng.integers(0, N_CUSTOMERS))]
        acct_type = str(rng.choice(ACCOUNT_TYPES, p=[0.35, 0.30, 0.12, 0.13, 0.10]))
        if acct_type in ("Credit Card", "Current", "Business Current"):
            credit_limit = float(rng.choice([1000, 2500, 5000, 10000, 25000]))
            util = float(np.clip(rng.beta(2, 3) * 100, 0, 100))
        else:
            credit_limit = 0.0
            util = 0.0
        balance = float(np.clip(rng.lognormal(9.4, 1.0), 0, 500000))
        open_year = int(rng.integers(2008, 2025))
        open_date = datetime(open_year, int(rng.integers(1, 13)), int(rng.integers(1, 28)))
        accounts.append({
            "account_id": f"ACCT-{i:06d}",
            "customer_id": cust["customer_id"],
            "account_type": acct_type,
            "balance": round(balance, 2),
            "credit_limit": credit_limit,
            "credit_utilisation_pct": round(util, 2),
            "open_date": open_date.strftime("%Y-%m-%d"),
            "status": str(rng.choice(ACCOUNT_STATUS)),
            "util": util,
        })

    with (OUT_DIR / "accounts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "customer_id", "account_type", "balance",
                    "credit_limit", "credit_utilisation_pct", "open_date", "status"])
        for a in accounts:
            w.writerow([a["account_id"], a["customer_id"], a["account_type"],
                        a["balance"], a["credit_limit"], a["credit_utilisation_pct"],
                        a["open_date"], a["status"]])
    print(f"Wrote {len(accounts)} accounts -> accounts.csv")

    # ── Transactions with learnable fraud signal ────────────────────────────
    # Global amount stats for z-scoring (computed on a quick pre-sample of logs).
    log_amount_mean = 4.3
    log_amount_std = 1.1

    rows = []
    n_fraud = 0
    for t in range(1, N_TRANSACTIONS + 1):
        acct = accounts[int(rng.integers(0, N_ACCOUNTS))]
        cust = cust_by_id[acct["customer_id"]]
        merchant = str(rng.choice(MERCHANTS))
        txn_type = str(rng.choice(TXN_TYPES, p=[0.42, 0.16, 0.16, 0.12, 0.08, 0.06]))
        channel = str(rng.choice(CHANNELS, p=[0.34, 0.26, 0.20, 0.12, 0.08]))
        country = str(rng.choice(COUNTRIES, p=COUNTRY_WEIGHTS))

        # Amount from merchant-specific lognormal.
        log_amt = rng.normal(MERCHANT_AMOUNT[merchant], 0.7)
        amount = float(np.clip(math.exp(log_amt), 1.0, 250000.0))
        amount_z = (math.log(amount) - log_amount_mean) / log_amount_std

        day = START_DATE + timedelta(days=int(rng.integers(0, N_DAYS)))
        hour = int(rng.integers(0, 24))
        is_night = hour >= 22 or hour < 6
        is_intl = country != "UK"

        fraud_logit = (
            -3.30
            + 0.95 * amount_z
            + (1.15 if is_intl else 0.0)
            + (0.60 if is_night else 0.0)
            + CHANNEL_RISK[channel]
            + MERCHANT_RISK[merchant]
            + RISK_TIER_OFFSET[cust["risk_tier"]]
            + 0.015 * (acct["util"] - 40.0)
            + float(rng.normal(0, 0.38))
        )
        is_fraud = rng.random() < sigmoid(fraud_logit)
        if is_fraud:
            n_fraud += 1

        ts = (day + timedelta(hours=hour, minutes=int(rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S")
        rows.append([
            f"TXN-{t:07d}", acct["account_id"], acct["customer_id"], ts,
            txn_type, merchant, round(amount, 2), bool(is_fraud), channel, country,
        ])

    with (OUT_DIR / "transactions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["transaction_id", "account_id", "customer_id", "transaction_date",
                    "transaction_type", "merchant_category", "amount",
                    "is_flagged_fraud", "channel", "country"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} transactions -> transactions.csv "
          f"({n_fraud:,} fraud, {100 * n_fraud / len(rows):.1f}%)")


if __name__ == "__main__":
    main()
