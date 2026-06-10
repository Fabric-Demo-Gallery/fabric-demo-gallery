"""Reproducible generator for the Media demo source data.

Produces ``content_catalog.csv``, ``subscribers.csv``, ``viewing_history.csv``
and ``ad_impressions.csv`` with a *learnable* relationship between observable
content / subscriber / context features and the **content-completion** label
(``is_completed``), so the completion classifier trains to a credible AUC
(~0.80-0.88).

Use case: Content Recommendation — predict whether a viewing session will be
*completed* (watched to the end), a proxy for content-recommendation quality.

Signal model (per viewing session):
  * Completion propensity is a logistic function of drivers:
      base
      - duration            (longer content is less likely to be finished)
      + genre affinity       (Kids / Comedy / Action finish most; News / Docs least)
      + content_type         (Series / Movie finish more than Live)
      + device               (TV finishes most, Mobile least)
      + plan tier            (Premium subscribers engage more)
      + latent subscriber engagement + latent content quality
      + irreducible noise (keeps AUC < 1.0)
  * watch_duration_mins is DERIVED from completion (post-view leakage).
  * rating is DERIVED from completion + quality (post-view leakage).
  * Target prevalence ~38%.

IDs are CONSISTENT: every view references an existing subscriber + content, and
ad impressions reference existing content. The ML feature-engineering notebook
EXCLUDES post-view leakage (watch_duration_mins, rating) and uses pre-view
context features only.

Run:  python demos/media/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_CONTENT = 2000
N_SUBSCRIBERS = 10000
N_VIEWS = 200000
N_ADS = 100000
N_DAYS = 120
START_DATE = datetime(2025, 1, 1)

OUT_DIR = Path(__file__).resolve().parent

GENRES = ["Action", "Comedy", "Documentary", "Drama", "Kids",
          "News", "Romance", "Sci-Fi", "Sports", "Thriller"]
# Genre -> completion affinity offset.
GENRE_AFFINITY = {
    "Action": 0.40, "Comedy": 0.55, "Documentary": -0.45, "Drama": 0.00,
    "Kids": 0.85, "News": -0.55, "Romance": 0.15, "Sci-Fi": 0.20,
    "Sports": -0.30, "Thriller": 0.10,
}
CONTENT_TYPES = ["Movie", "Series", "Live", "Documentary"]
CONTENT_TYPE_OFFSET = {"Movie": 0.20, "Series": 0.45, "Live": -0.45, "Documentary": -0.20}
# Duration range (minutes) by content type.
DURATION_RANGE = {"Movie": (80, 180), "Series": (20, 55), "Live": (30, 150), "Documentary": (40, 95)}
COST_BUCKETS = ["Low (<$1M)", "Medium ($1M-$10M)", "High ($10M-$50M)", "Blockbuster (>$50M)"]
LANGUAGES = ["English", "French", "German", "Japanese", "Korean", "Spanish"]

PLAN_TYPES = ["Basic", "Standard", "Premium"]
PLAN_OFFSET = {"Basic": -0.25, "Standard": 0.00, "Premium": 0.30}
PLAN_FEE = {"Basic": 7.99, "Standard": 13.99, "Premium": 19.99}
REGIONS = ["Asia Pacific", "Europe", "Latin America", "Middle East", "North America"]
AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55+"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "PayPal", "Apple Pay", "Google Pay"]

DEVICES = ["TV", "Gaming Console", "Tablet", "Web", "Mobile"]
DEVICE_OFFSET = {"TV": 0.60, "Gaming Console": 0.30, "Tablet": 0.00, "Web": -0.30, "Mobile": -0.50}
AD_TYPES = ["Pre-roll", "Mid-roll", "Post-roll", "Banner"]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Content catalog (latent quality) ────────────────────────────────────
    content = []
    for i in range(1, N_CONTENT + 1):
        genre = str(rng.choice(GENRES))
        ctype = str(rng.choice(CONTENT_TYPES, p=[0.34, 0.40, 0.12, 0.14]))
        lo, hi = DURATION_RANGE[ctype]
        duration = int(rng.integers(lo, hi + 1))
        content.append({
            "content_id": f"CNT-{i:05d}",
            "title": f"{genre} {ctype} {i}",
            "genre": genre,
            "content_type": ctype,
            "release_year": int(rng.integers(2010, 2026)),
            "duration_mins": duration,
            "production_cost_bucket": str(rng.choice(COST_BUCKETS, p=[0.30, 0.34, 0.24, 0.12])),
            "language": str(rng.choice(LANGUAGES, p=[0.55, 0.10, 0.08, 0.10, 0.07, 0.10])),
            "quality": float(rng.normal(0, 1)),  # latent, not written
        })
    with (OUT_DIR / "content_catalog.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["content_id", "title", "genre", "content_type", "release_year",
                    "duration_mins", "production_cost_bucket", "language"])
        for c in content:
            w.writerow([c["content_id"], c["title"], c["genre"], c["content_type"],
                        c["release_year"], c["duration_mins"], c["production_cost_bucket"],
                        c["language"]])
    print(f"Wrote {len(content)} content -> content_catalog.csv")

    # ── Subscribers (latent engagement) ─────────────────────────────────────
    subscribers = []
    for i in range(1, N_SUBSCRIBERS + 1):
        plan = str(rng.choice(PLAN_TYPES, p=[0.34, 0.40, 0.26]))
        signup = START_DATE - timedelta(days=int(rng.integers(30, 1500)))
        is_churned = int(rng.random() < 0.22)
        churn_date = ""
        if is_churned:
            churn_date = (signup + timedelta(days=int(rng.integers(60, 900)))).strftime("%Y-%m-%d")
        subscribers.append({
            "subscriber_id": f"SUB-{i:06d}",
            "plan_type": plan,
            "region": str(rng.choice(REGIONS)),
            "age_group": str(rng.choice(AGE_GROUPS)),
            "payment_method": str(rng.choice(PAYMENT_METHODS)),
            "monthly_fee": PLAN_FEE[plan],
            "signup_date": signup.strftime("%Y-%m-%d"),
            "churn_date": churn_date,
            "is_churned": is_churned,
            "engagement": float(rng.normal(0, 1)),  # latent, not written
        })
    with (OUT_DIR / "subscribers.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subscriber_id", "plan_type", "region", "age_group", "payment_method",
                    "monthly_fee", "signup_date", "churn_date", "is_churned"])
        for s in subscribers:
            w.writerow([s["subscriber_id"], s["plan_type"], s["region"], s["age_group"],
                        s["payment_method"], s["monthly_fee"], s["signup_date"],
                        s["churn_date"], s["is_churned"]])
    print(f"Wrote {len(subscribers)} subscribers -> subscribers.csv")

    # ── Viewing history with learnable completion signal ────────────────────
    rows = []
    n_complete = 0
    for v in range(1, N_VIEWS + 1):
        sub = subscribers[int(rng.integers(0, N_SUBSCRIBERS))]
        cnt = content[int(rng.integers(0, N_CONTENT))]
        device = str(rng.choice(DEVICES, p=[0.30, 0.10, 0.18, 0.17, 0.25]))
        view_dt = START_DATE + timedelta(days=int(rng.integers(0, N_DAYS)))
        view_hour = int(rng.integers(0, 24))
        duration = cnt["duration_mins"]

        complete_logit = (
            -0.55
            - 0.017 * (duration - 60)
            + 1.30 * GENRE_AFFINITY[cnt["genre"]]
            + 1.30 * CONTENT_TYPE_OFFSET[cnt["content_type"]]
            + 1.20 * DEVICE_OFFSET[device]
            + PLAN_OFFSET[sub["plan_type"]]
            + 0.35 * sub["engagement"]
            + 0.35 * cnt["quality"]
            + float(rng.normal(0, 0.40))
        )
        is_completed = int(rng.random() < sigmoid(complete_logit))
        if is_completed:
            n_complete += 1
            watch = round(duration * float(rng.uniform(0.90, 1.0)), 1)
            rating = int(np.clip(round(rng.normal(4.2, 0.8)), 1, 5))
        else:
            watch = round(duration * float(rng.uniform(0.02, 0.70)), 1)
            rating = int(np.clip(round(rng.normal(2.6, 1.1)), 1, 5))

        rows.append([
            f"VW-{v:08d}", sub["subscriber_id"], cnt["content_id"],
            view_dt.strftime("%Y-%m-%d"), view_hour, watch, is_completed, device, rating,
        ])

    with (OUT_DIR / "viewing_history.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["view_id", "subscriber_id", "content_id", "view_date", "view_hour",
                    "watch_duration_mins", "is_completed", "device_type", "rating"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} views -> viewing_history.csv "
          f"({n_complete:,} completed, {100*n_complete/len(rows):.1f}%)")

    # ── Ad impressions (reference existing content) ─────────────────────────
    arows = []
    for a in range(1, N_ADS + 1):
        cnt = content[int(rng.integers(0, N_CONTENT))]
        ad_type = str(rng.choice(AD_TYPES, p=[0.30, 0.40, 0.15, 0.15]))
        impressions = int(rng.integers(500, 12000))
        ctr = float(rng.uniform(0.01, 0.08))
        clicks = int(impressions * ctr)
        cpm = round(float(rng.uniform(3.0, 14.0)), 2)
        revenue = round(impressions / 1000.0 * cpm, 4)
        arows.append([
            f"AD-{a:08d}", cnt["content_id"],
            (START_DATE + timedelta(days=int(rng.integers(0, N_DAYS)))).strftime("%Y-%m-%d"),
            ad_type, impressions, clicks, revenue, cpm,
        ])
    with (OUT_DIR / "ad_impressions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["impression_id", "content_id", "ad_date", "ad_type",
                    "impressions", "clicks", "revenue_usd", "cpm"])
        w.writerows(arows)
    print(f"Wrote {len(arows):,} ad impressions -> ad_impressions.csv")


if __name__ == "__main__":
    main()
