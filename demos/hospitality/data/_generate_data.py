"""Reproducible generator for the Hospitality demo source data.

Produces ``properties.csv``, ``guests.csv``, ``bookings.csv`` and
``reviews.csv`` with a *learnable* relationship between observable booking /
guest / property features and the booking-cancellation label, so the
cancellation classifier trains to a credible AUC (~0.85-0.92).

Signal model (per booking):
  * Latent cancellation propensity is a logistic function of drivers:
      base
      + lead_time         (booking far in advance -> more likely to cancel)
      + channel risk       (OTA cancels most, Direct least)
      + room_rate / nights (pricier, longer stays cancel a bit more)
      - loyalty tier       (loyal guests cancel less)
      + non-refundable?    (refundable bookings cancel more)
      + irreducible noise (keeps AUC < 1.0)
  * status = 'cancelled' if cancelled; otherwise 'completed'/'no_show'.
  * is_cancelled = 1 for cancelled bookings. Target prevalence ~28%.

IDs are CONSISTENT: every booking references an existing guest + property, and
reviews reference completed bookings. The ML feature-engineering notebook
EXCLUDES post-stay leakage (status, total_amount realised) and uses pre-stay
features only.

Run:  python demos/hospitality/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_PROPERTIES = 50
N_GUESTS = 5000
N_BOOKINGS = 50000
N_REVIEWS = 20000
N_DAYS = 120
START_DATE = datetime(2025, 1, 1)

OUT_DIR = Path(__file__).resolve().parent

CITIES = [("London", "UK"), ("Manchester", "UK"), ("Edinburgh", "UK"),
          ("Paris", "France"), ("Amsterdam", "Netherlands"), ("Barcelona", "Spain"),
          ("Rome", "Italy"), ("Berlin", "Germany")]
PROPERTY_TYPES = ["Hotel", "Resort", "Boutique", "Apartment"]
ROOM_TYPES = ["Standard", "Deluxe", "Executive", "Junior Suite", "Suite"]
ROOM_RATE_BASE = {"Standard": 95, "Deluxe": 150, "Executive": 230, "Junior Suite": 320, "Suite": 480}
CHANNELS = ["Direct", "OTA", "Corporate", "Group"]
# Channel -> cancellation risk offset.
CHANNEL_RISK = {"Direct": -0.85, "OTA": 1.15, "Corporate": -0.30, "Group": 0.45}
MEAL_PLANS = ["Room Only", "Bed & Breakfast", "Half Board", "Full Board"]
LOYALTY_TIERS = ["None", "Bronze", "Silver", "Gold", "Platinum"]
LOYALTY_RISK = {"None": 0.70, "Bronze": 0.25, "Silver": -0.15, "Gold": -0.70, "Platinum": -1.25}
REGIONS = ["Europe", "North America", "APAC", "Middle East"]
AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
NATIONALITIES = ["UK", "US", "DE", "FR", "ES", "IT", "NL", "CN", "AE"]
SENTIMENTS = ["Positive", "Neutral", "Negative"]
PLATFORMS = ["Google", "TripAdvisor", "Booking.com", "Direct"]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Properties ──────────────────────────────────────────────────────────
    properties = []
    for i in range(1, N_PROPERTIES + 1):
        city, country = CITIES[i % len(CITIES)]
        properties.append({
            "property_id": f"PROP-{i:03d}",
            "property_name": f"{city} {PROPERTY_TYPES[i % len(PROPERTY_TYPES)]} {i}",
            "city": city, "country": country,
            "property_type": str(rng.choice(PROPERTY_TYPES)),
            "star_rating": int(rng.integers(3, 6)),
            "room_count": int(rng.integers(40, 300)),
        })
    with (OUT_DIR / "properties.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["property_id", "property_name", "city", "country",
                    "property_type", "star_rating", "room_count"])
        for p in properties:
            w.writerow([p["property_id"], p["property_name"], p["city"], p["country"],
                        p["property_type"], p["star_rating"], p["room_count"]])
    print(f"Wrote {len(properties)} properties -> properties.csv")

    # ── Guests ──────────────────────────────────────────────────────────────
    guests = []
    for i in range(1, N_GUESTS + 1):
        tier = str(rng.choice(LOYALTY_TIERS, p=[0.35, 0.27, 0.20, 0.12, 0.06]))
        stays = int(np.clip(rng.poisson({"None": 1, "Bronze": 3, "Silver": 6,
                                          "Gold": 12, "Platinum": 25}[tier]), 0, 80))
        guests.append({
            "guest_id": f"GST-{i:05d}",
            "loyalty_tier": tier,
            "region": str(rng.choice(REGIONS)),
            "age_group": str(rng.choice(AGE_GROUPS)),
            "nationality": str(rng.choice(NATIONALITIES)),
            "total_stays": stays,
            "total_spend": round(stays * float(rng.uniform(180, 650)), 2),
            "preferred_channel": str(rng.choice(CHANNELS)),
            "signup_date": (START_DATE - timedelta(days=int(rng.integers(120, 2200)))).strftime("%Y-%m-%d"),
        })
    with (OUT_DIR / "guests.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["guest_id", "loyalty_tier", "region", "age_group", "nationality",
                    "total_stays", "total_spend", "preferred_channel", "signup_date"])
        for g in guests:
            w.writerow([g["guest_id"], g["loyalty_tier"], g["region"], g["age_group"],
                        g["nationality"], g["total_stays"], g["total_spend"],
                        g["preferred_channel"], g["signup_date"]])
    print(f"Wrote {len(guests)} guests -> guests.csv")

    # ── Bookings with learnable cancellation signal ─────────────────────────
    rows = []
    completed_bookings = []
    n_cancel = 0
    for b in range(1, N_BOOKINGS + 1):
        prop = properties[int(rng.integers(0, N_PROPERTIES))]
        guest = guests[int(rng.integers(0, N_GUESTS))]
        room_type = str(rng.choice(ROOM_TYPES, p=[0.34, 0.28, 0.20, 0.10, 0.08]))
        channel = str(rng.choice(CHANNELS, p=[0.34, 0.40, 0.14, 0.12]))
        meal = str(rng.choice(MEAL_PLANS, p=[0.40, 0.35, 0.17, 0.08]))
        nights = int(np.clip(rng.poisson(3) + 1, 1, 21))
        lead_time = int(np.clip(rng.exponential(35), 0, 330))
        rate = round(ROOM_RATE_BASE[room_type] * float(rng.uniform(0.85, 1.4)), 2)
        is_refundable = int(rng.random() < 0.6)

        check_in = START_DATE + timedelta(days=int(rng.integers(0, N_DAYS)))
        check_out = check_in + timedelta(days=nights)

        cancel_logit = (
            -1.95
            + 0.020 * (lead_time - 30)
            + CHANNEL_RISK[channel]
            + LOYALTY_RISK[guest["loyalty_tier"]]
            + 0.28 * (nights - 3) / 3.0
            + 0.0014 * (rate - 200)
            + (0.75 if is_refundable else -0.55)
            + float(rng.normal(0, 0.30))
        )
        is_cancelled = int(rng.random() < sigmoid(cancel_logit))
        if is_cancelled:
            n_cancel += 1
            status = "cancelled"
            total = 0.0
        else:
            status = "completed" if rng.random() > 0.05 else "no_show"
            total = round(rate * nights, 2)

        rows.append([
            f"BK-{b:07d}", prop["property_id"], guest["guest_id"],
            check_in.strftime("%Y-%m-%d"), check_out.strftime("%Y-%m-%d"),
            nights, room_type, channel, meal, rate, total, status,
            lead_time, is_refundable, is_cancelled,
            guest["loyalty_tier"],
        ])
        if status == "completed":
            completed_bookings.append((f"BK-{b:07d}", prop["property_id"], guest["guest_id"], check_out))

    with (OUT_DIR / "bookings.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["booking_id", "property_id", "guest_id", "check_in_date", "check_out_date",
                    "nights", "room_type", "channel", "meal_plan", "room_rate", "total_amount",
                    "status", "lead_time_days", "is_refundable", "is_cancelled", "loyalty_tier"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} bookings -> bookings.csv ({n_cancel:,} cancelled, {100*n_cancel/len(rows):.1f}%)")

    # ── Reviews (only for completed bookings) ───────────────────────────────
    rng.shuffle(completed_bookings)
    review_src = completed_bookings[:N_REVIEWS]
    frows = []
    for i, (bk, prop_id, gst, co) in enumerate(review_src, start=1):
        overall = int(np.clip(round(rng.normal(8.2, 1.6)), 1, 10))
        sentiment = "Positive" if overall >= 8 else ("Neutral" if overall >= 6 else "Negative")
        frows.append([
            f"REV-{i:06d}", bk, prop_id, gst,
            (co + timedelta(days=int(rng.integers(0, 10)))).strftime("%Y-%m-%d"),
            overall,
            int(np.clip(round(rng.normal(overall, 1)), 1, 10)),
            int(np.clip(round(rng.normal(overall, 1)), 1, 10)),
            int(np.clip(round(rng.normal(overall, 1)), 1, 10)),
            int(np.clip(round(rng.normal(overall, 1)), 1, 10)),
            sentiment, str(rng.choice(PLATFORMS)),
        ])
    with (OUT_DIR / "reviews.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "booking_id", "property_id", "guest_id", "review_date",
                    "overall_score", "cleanliness_score", "service_score", "value_score",
                    "food_score", "sentiment", "platform"])
        w.writerows(frows)
    print(f"Wrote {len(frows):,} reviews -> reviews.csv")


if __name__ == "__main__":
    main()
