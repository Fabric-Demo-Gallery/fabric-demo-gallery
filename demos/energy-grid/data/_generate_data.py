"""Reproducible generator for the Energy Grid demo source data.

Produces ``grid_sensors.csv`` and ``power_events.csv`` with a *physically
plausible, learnable* relationship between grid sensor stress and failure
events, so the outage-prediction model trains to a credible AUC (~0.85-0.92)
instead of behaving like a coin flip on uncorrelated noise.

Signal model (per substation-day):
  * Hot days drive higher load (air-conditioning) -> overload.
  * Overload + heat drive voltage deviation, frequency deviation, and a
    drop in power factor.
  * Failure probability is a logistic function of those daily drivers plus a
    per-substation weakness and irreducible noise (so AUC stays < 1.0).
  * Failure-type events (outage / voltage_sag / surge / overload /
    equipment_fault) are emitted only on failed substation-days, with the
    dominant type chosen by which driver was most extreme. A matching
    ``restoration`` event follows. Benign ``restoration`` events are also
    scattered on healthy days for realism (they are not part of the label).

Run:  python demos/energy-grid/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

SEED = 42
N_SENSOR_ROWS = 100_000
START_DATE = datetime(2025, 3, 1, tzinfo=timezone.utc)
N_DAYS = 60
SUBSTATIONS = [f"SUB-{i:03d}" for i in range(1, 26)]
REGIONS = ["North", "South", "East", "West", "Central"]
# Region -> baseline temperature offset (deg C)
REGION_TEMP = {"North": -3.0, "South": 4.0, "East": 0.0, "West": 1.0, "Central": 2.0}

OUT_DIR = Path(__file__).resolve().parent


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # Stable region + weakness per substation.
    sub_region = {s: REGIONS[i % len(REGIONS)] for i, s in enumerate(SUBSTATIONS)}
    sub_weakness = {s: float(rng.normal(0, 1)) for s in SUBSTATIONS}

    # A single latent "stress" S in [0, 1] per substation-day drives BOTH the
    # observable sensor daily means AND (steeply) the failure probability, so a
    # model can recover S from the sensor features and predict failures well.
    sub_days = []  # one record per (substation, day) holding the daily drivers
    for d in range(N_DAYS):
        day = START_DATE + timedelta(days=d)
        # Seasonal warming from early March to late April + weekly cycle.
        seasonal = 8.0 + (22.0 - 8.0) * (d / max(N_DAYS - 1, 1))
        weekday = day.weekday()  # 0=Mon
        weekday_load = 3.0 if weekday < 5 else -2.0
        for s in SUBSTATIONS:
            region = sub_region[s]
            heatwave = float(rng.uniform(6, 14)) if rng.random() < 0.12 else 0.0
            temp_day = seasonal + REGION_TEMP[region] + heatwave + float(rng.normal(0, 2))

            # Latent stress: weak substation + heat + a modest irreducible part.
            stress_z = (
                -0.55
                + 0.55 * sub_weakness[s]
                + 0.075 * (temp_day - 18.0)
                + 0.05 * weekday_load
                + float(rng.normal(0, 0.45))
            )
            stress = sigmoid(stress_z)  # in (0, 1)

            # Observable daily means are near-monotonic in stress (+ light noise).
            load_day = float(np.clip(22.0 + 30.0 * stress + rng.normal(0, 2.0), 10.0, 65.0))
            overload = max(0.0, load_day - 45.0)
            volt_dev = float(max(0.2, 1.0 + 10.0 * stress + abs(rng.normal(0, 1.0))))
            freq_dev = float(max(0.005, 0.010 + 0.180 * stress + abs(rng.normal(0, 0.010))))
            power_factor = float(np.clip(0.980 - 0.140 * stress + rng.normal(0, 0.008), 0.80, 0.99))

            # Steep failure probability in stress -> calm days rarely fail,
            # stressed days usually do; the noise above keeps AUC below 1.
            failed = rng.random() < sigmoid(6.0 * (stress - 0.58))

            sub_days.append(
                {
                    "sub": s,
                    "region": region,
                    "day": day,
                    "temp": temp_day,
                    "load": load_day,
                    "overload": overload,
                    "volt_dev": volt_dev,
                    "volt_sign": 1.0 if rng.random() < 0.5 else -1.0,
                    "freq_dev": freq_dev,
                    "freq_sign": 1.0 if rng.random() < 0.5 else -1.0,
                    "pf": power_factor,
                    "failed": bool(failed),
                }
            )

    n_failed = sum(1 for r in sub_days if r["failed"])
    print(f"Substation-days: {len(sub_days):,} | failed: {n_failed:,} "
          f"({100 * n_failed / len(sub_days):.1f}%)")

    # ---- Sensor readings: spread N_SENSOR_ROWS across the substation-days ----
    per_day = N_SENSOR_ROWS // len(sub_days)
    remainder = N_SENSOR_ROWS - per_day * len(sub_days)
    sensor_path = OUT_DIR / "grid_sensors.csv"
    rid = 0
    with sensor_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["reading_id", "timestamp", "substation_id", "region",
                    "voltage_v", "frequency_hz", "power_factor", "load_mw", "temperature_c"])
        for idx, r in enumerate(sub_days):
            n = per_day + (1 if idx < remainder else 0)
            volt_mean = 230.0 + r["volt_sign"] * r["volt_dev"]
            volt_noise = 0.8 + 0.3 * r["volt_dev"]
            freq_mean = 50.0 + r["freq_sign"] * r["freq_dev"]
            freq_noise = 0.01 + 0.02 * r["freq_dev"]
            for _ in range(n):
                rid += 1
                secs = int(rng.integers(0, 86400))
                ts = (r["day"] + timedelta(seconds=secs)).strftime("%Y-%m-%dT%H:%M:%SZ")
                voltage = volt_mean + float(rng.normal(0, volt_noise))
                frequency = freq_mean + float(rng.normal(0, freq_noise))
                pf = float(np.clip(r["pf"] + rng.normal(0, 0.005), 0.5, 1.0))
                load = max(0.0, r["load"] + float(rng.normal(0, 1.5)))
                temp = r["temp"] + float(rng.normal(0, 1.0))
                w.writerow([
                    f"GS-{rid:07d}", ts, r["sub"], r["region"],
                    round(voltage, 2), round(frequency, 3), round(pf, 3),
                    round(load, 2), round(temp, 1),
                ])
    print(f"Wrote {rid:,} sensor rows -> {sensor_path.name}")

    # ---- Events: failure events on failed days + benign restorations ----
    failure_pool = ["outage", "voltage_sag", "surge", "overload", "equipment_fault"]
    events = []
    eid = 0

    def add_event(sub, region, day, etype, severity, duration, affected, resolved):
        nonlocal eid
        eid += 1
        secs = int(rng.integers(0, 86400))
        ts = (day + timedelta(seconds=secs)).strftime("%Y-%m-%dT%H:%M:%SZ")
        events.append([f"EVT-{eid:06d}", ts, sub, region, etype, severity,
                       int(duration), int(affected), str(resolved).lower()])

    for r in sub_days:
        if not r["failed"]:
            continue
        # Dominant failure type by the most extreme driver.
        drivers = {
            "surge": r["freq_dev"] / 0.15,
            "equipment_fault": r["freq_dev"] / 0.18,
            "voltage_sag": r["volt_dev"] / 10.0 + (0.93 - r["pf"]) * 5.0,
            "overload": r["overload"] / 10.0,
            "outage": 0.35,
        }
        etype = max(drivers, key=drivers.get)
        if etype not in failure_pool:
            etype = "outage"
        stress = drivers[etype]
        severity = ("critical" if stress > 1.0 else "high" if stress > 0.6
                    else "medium" if stress > 0.3 else "low")
        n_evt = int(rng.integers(1, 4))
        for _ in range(n_evt):
            duration = float(np.clip(rng.normal(600 + 1200 * stress, 300), 60, 7200))
            affected = float(np.clip(rng.normal(800 + 2500 * stress, 600), 20, 9000))
            add_event(r["sub"], r["region"], r["day"], etype, severity, duration, affected, False)
        # Restoration once the failure is handled.
        add_event(r["sub"], r["region"], r["day"], "restoration", "low",
                  rng.integers(60, 600), rng.integers(20, 1500), True)

    # Benign restoration / maintenance events on healthy days for realism
    # (excluded from the label by the feature-engineering filter).
    healthy = [r for r in sub_days if not r["failed"]]
    n_benign = max(0, 5000 - len(events))
    for r in rng.choice(healthy, size=min(n_benign, len(healthy)), replace=False):
        add_event(r["sub"], r["region"], r["day"], "restoration", "low",
                  rng.integers(60, 400), rng.integers(10, 800), True)

    rng.shuffle(events)
    events_path = OUT_DIR / "power_events.csv"
    with events_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["event_id", "timestamp", "substation_id", "region", "event_type",
                    "severity", "duration_sec", "affected_customers", "resolved"])
        w.writerows(events)
    print(f"Wrote {len(events):,} events -> {events_path.name}")


if __name__ == "__main__":
    main()
