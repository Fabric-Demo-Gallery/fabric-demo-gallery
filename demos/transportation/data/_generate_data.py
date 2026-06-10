"""Reproducible generator for the Transportation demo source data.

Produces ``vehicles.csv``, ``routes.csv``, ``deliveries.csv`` and
``fuel_logs.csv`` with a *learnable* relationship between observable delivery /
route / vehicle features and the ``is_late`` label, so the delivery-delay
classifier trains to a credible AUC (~0.85-0.92).

Signal model (per delivery):
  * A latent congestion/risk multiplier drives the actual duration relative to
    the planned duration. Drivers (all OBSERVABLE before arrival):
      - route_type        (Express tightest SLA, most likely late)
      - distance_km        (longer trips accumulate more variance)
      - load_utilisation   (heavier loads run slower)
      - vehicle_age        (older vehicles slower / breakdown-prone)
      - departure rush hour (07-09 / 16-19) and weekend
      - irreducible noise (keeps AUC < 1.0)
  * actual_duration = planned_duration * congestion; delay = actual - planned.
  * ``is_late = actual_duration > sla_hours`` (route SLA) -> ~30% prevalence.

LEAKAGE: ``actual_arrival``, ``actual_duration_hrs``, ``delay_hrs`` and
``status`` are known only AFTER the trip. The ML feature-engineering notebook
EXCLUDES them and uses only pre-departure features.

IDs are CONSISTENT: every delivery references an existing vehicle + route.

Run:  python demos/transportation/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_VEHICLES = 100
N_ROUTES = 500
N_DELIVERIES = 50000
N_FUEL_LOGS = 20000
N_DAYS = 90
START_DATE = datetime(2025, 1, 1)

OUT_DIR = Path(__file__).resolve().parent

CITIES = ["London", "Manchester", "Birmingham", "Bristol", "Leeds", "Glasgow",
          "Edinburgh", "Cardiff", "Liverpool", "Newcastle", "Sheffield", "Nottingham"]
DEPOTS = ["London", "Manchester", "Birmingham", "Bristol", "Leeds", "Glasgow"]
VEHICLE_TYPES = ["Van", "Rigid", "HGV", "Refrigerated"]
VEHICLE_CAP = {"Van": 2, "Rigid": 8, "HGV": 20, "Refrigerated": 12}
VEHICLE_RISK = {"Van": -0.20, "Rigid": 0.05, "HGV": 0.30, "Refrigerated": 0.20}
ROUTE_TYPES = ["Express", "Standard", "Economy"]
# SLA is a uniform generosity factor on base drive time (NOT coupled to route
# type), so lateness is driven by the continuous congestion model rather than a
# route-type lookup. route_type still affects risk via ROUTE_RISK below.
SLA_FACTOR = 1.42
ROUTE_RISK = {"Express": 0.40, "Standard": 0.0, "Economy": -0.35}
FUEL_TYPES = ["Diesel", "Electric", "HVO"]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Vehicles ────────────────────────────────────────────────────────────
    vehicles = []
    for i in range(1, N_VEHICLES + 1):
        vtype = str(rng.choice(VEHICLE_TYPES, p=[0.30, 0.28, 0.27, 0.15]))
        year = int(rng.integers(2012, 2025))
        vehicles.append({
            "vehicle_id": f"VEH-{i:04d}",
            "vehicle_type": vtype,
            "depot": str(rng.choice(DEPOTS)),
            "capacity_tonnes": VEHICLE_CAP[vtype],
            "year_registered": year,
            "status": str(rng.choice(["Active", "Active", "Active", "Maintenance", "Decommissioned"])),
            "driver_id": f"DRV-{int(rng.integers(1, 80)):04d}",
            "age": 2025 - year,
        })
    with (OUT_DIR / "vehicles.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["vehicle_id", "vehicle_type", "depot", "capacity_tonnes",
                    "year_registered", "status", "driver_id"])
        for v in vehicles:
            w.writerow([v["vehicle_id"], v["vehicle_type"], v["depot"], v["capacity_tonnes"],
                        v["year_registered"], v["status"], v["driver_id"]])
    print(f"Wrote {len(vehicles)} vehicles -> vehicles.csv")

    # ── Routes ──────────────────────────────────────────────────────────────
    routes = []
    for i in range(1, N_ROUTES + 1):
        origin = str(rng.choice(CITIES))
        dest = str(rng.choice([c for c in CITIES if c != origin]))
        distance = float(np.clip(rng.normal(280, 150), 20, 720))
        rtype = str(rng.choice(ROUTE_TYPES, p=[0.30, 0.45, 0.25]))
        # Expected hours at ~62 km/h; uniform SLA generosity factor.
        base_hours = distance / 62.0
        sla = round(base_hours * SLA_FACTOR, 1)
        routes.append({
            "route_id": f"RT-{i:04d}",
            "origin": origin,
            "destination": dest,
            "distance_km": round(distance, 1),
            "route_type": rtype,
            "sla_hours": sla,
            "toll_cost_gbp": round(distance * float(rng.uniform(0.02, 0.06)), 2),
            "base_hours": base_hours,
        })
    with (OUT_DIR / "routes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["route_id", "origin", "destination", "distance_km",
                    "route_type", "sla_hours", "toll_cost_gbp"])
        for r in routes:
            w.writerow([r["route_id"], r["origin"], r["destination"], r["distance_km"],
                        r["route_type"], r["sla_hours"], r["toll_cost_gbp"]])
    print(f"Wrote {len(routes)} routes -> routes.csv")

    veh_by_id = {v["vehicle_id"]: v for v in vehicles}

    # ── Deliveries with learnable lateness signal ───────────────────────────
    rows = []
    n_late = 0
    for d in range(1, N_DELIVERIES + 1):
        veh = vehicles[int(rng.integers(0, N_VEHICLES))]
        route = routes[int(rng.integers(0, N_ROUTES))]
        load = float(np.clip(rng.uniform(0.2, 1.05) * veh["capacity_tonnes"], 0.1, veh["capacity_tonnes"]))
        load_util = load / veh["capacity_tonnes"]

        day = START_DATE + timedelta(days=int(rng.integers(0, N_DAYS)))
        hour = int(rng.integers(0, 24))
        dep = day + timedelta(hours=hour, minutes=int(rng.integers(0, 60)))
        is_rush = hour in (7, 8, 9, 16, 17, 18, 19)
        is_weekend = dep.weekday() >= 5

        planned = route["base_hours"]

        # Congestion multiplier (>1 means slower than planned).
        congestion_logit = (
            -0.10
            + ROUTE_RISK[route["route_type"]]
            + 0.0011 * (route["distance_km"] - 280)
            + 0.95 * (load_util - 0.6)
            + 0.050 * (veh["age"] - 6)
            + (0.55 if is_rush else 0.0)
            - (0.30 if is_weekend else 0.0)
            + float(rng.normal(0, 0.52))
        )
        congestion = 0.80 + 0.95 * sigmoid(congestion_logit)  # ~0.80..1.75
        actual = planned * congestion
        delay = max(0.0, actual - planned)
        is_late = int(actual > route["sla_hours"])
        if is_late:
            n_late += 1
        arrival = dep + timedelta(hours=actual)
        status = "Delivered" if rng.random() > 0.02 else "Returned"

        rows.append([
            f"DEL-{d:07d}", veh["vehicle_id"], route["route_id"],
            dep.strftime("%Y-%m-%d %H:%M:%S"), arrival.strftime("%Y-%m-%d %H:%M:%S"),
            round(planned, 2), round(actual, 2), round(delay, 2),
            route["distance_km"], round(load, 1), status, is_late,
        ])
    with (OUT_DIR / "deliveries.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["delivery_id", "vehicle_id", "route_id", "planned_departure",
                    "actual_arrival", "planned_duration_hrs", "actual_duration_hrs",
                    "delay_hrs", "distance_km", "load_tonnes", "status", "is_late"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} deliveries -> deliveries.csv ({n_late:,} late, {100*n_late/len(rows):.1f}%)")

    # ── Fuel logs ───────────────────────────────────────────────────────────
    frows = []
    for i in range(1, N_FUEL_LOGS + 1):
        veh = vehicles[int(rng.integers(0, N_VEHICLES))]
        day = START_DATE + timedelta(days=int(rng.integers(0, N_DAYS)))
        litres = float(np.clip(rng.normal(110, 35), 20, 240))
        cpl = round(float(rng.uniform(1.45, 1.85)), 3)
        frows.append([
            f"FL-{i:07d}", veh["vehicle_id"], day.strftime("%Y-%m-%d"),
            veh["depot"], int(rng.integers(50000, 300000)),
            round(litres, 1), cpl, round(litres * cpl, 2),
            str(rng.choice(FUEL_TYPES, p=[0.75, 0.15, 0.10])),
        ])
    with (OUT_DIR / "fuel_logs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["log_id", "vehicle_id", "log_date", "depot", "odometer_km",
                    "litres_filled", "cost_per_litre", "total_cost_gbp", "fuel_type"])
        w.writerows(frows)
    print(f"Wrote {len(frows):,} fuel logs -> fuel_logs.csv")


if __name__ == "__main__":
    main()
