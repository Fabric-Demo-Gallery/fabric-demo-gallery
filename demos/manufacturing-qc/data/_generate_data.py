"""Reproducible generator for the Manufacturing QC demo source data.

Produces ``sensor_readings.csv``, ``production_batches.csv`` and
``equipment_catalog.csv`` with a *physically plausible, learnable* relationship
between machine sensor stress and equipment-failure / maintenance events, so the
predictive-maintenance model trains to a credible AUC (~0.80-0.90) instead of
behaving like a coin flip on uncorrelated noise.

Signal model (per machine-day):
  * Older machines + intrinsically weak units + hot machine types run under more
    latent "stress".
  * Stress drives the observable daily sensor means UP (temperature, vibration,
    pressure) and humidity mildly, with within-day noise.
  * Failure probability is a steep logistic function of stress plus irreducible
    noise (so AUC stays < 1.0).
  * On a *failed* machine-day at least one production batch is flagged
    ``failure_event = 1`` and shows elevated downtime / defects. Healthy days
    carry ``failure_event = 0``. The feature-engineering notebook derives the
    label from ``failure_event`` (NOT from downtime/defects), so there is no
    target leakage.

The ML pipeline uses sensor_readings (features) + production_batches
(``failure_event`` label) + equipment_catalog (age). The extra ``machine_id`` and
``failure_event`` columns added to production_batches are additive and do not
break the other manufacturing scenarios that read this file by production_line.

Run:  python demos/manufacturing-qc/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_MACHINES = 50
N_DAYS = 45
N_SENSOR_ROWS = 100_000
START_DATE = datetime(2025, 2, 1)

LINES = ["Line-A", "Line-B", "Line-C", "Line-D", "Line-E"]
PRODUCTS = ["Widget-A", "Gear-X", "Bracket-Z", "Valve-Q", "Rotor-M"]

# Machine type -> baseline stress offset (hotter / harder-running types run higher).
MACHINE_TYPES = {
    "CNC Mill": 0.10,
    "Injection Molder": 0.35,
    "Stamping Press": 0.25,
    "Lathe": 0.00,
    "Welding Robot": 0.40,
    "Assembly Arm": -0.10,
}

OUT_DIR = Path(__file__).resolve().parent


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ---- Equipment catalog: stable machine master data ----
    type_names = list(MACHINE_TYPES.keys())
    machines = []
    for i in range(1, N_MACHINES + 1):
        mid = f"MCH-{i:04d}"
        mtype = type_names[i % len(type_names)]
        line = LINES[i % len(LINES)]
        # Install dates spread 2016-2024 so equipment age carries signal.
        install_year = int(rng.integers(2016, 2025))
        install_month = int(rng.integers(1, 13))
        install_day = int(rng.integers(1, 28))
        install_date = datetime(install_year, install_month, install_day)
        machines.append({
            "machine_id": mid,
            "machine_name": f"Machine {i}",
            "machine_type": mtype,
            "production_line": line,
            "install_date": install_date,
            "weakness": float(rng.normal(0, 1)),
            "type_offset": MACHINE_TYPES[mtype],
        })

    eq_path = OUT_DIR / "equipment_catalog.csv"
    with eq_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["machine_id", "machine_name", "machine_type", "production_line", "install_date"])
        for m in machines:
            w.writerow([m["machine_id"], m["machine_name"], m["machine_type"],
                        m["production_line"], m["install_date"].strftime("%Y-%m-%d")])
    print(f"Wrote {len(machines)} machines -> {eq_path.name}")

    # ---- Latent stress + failure label per machine-day ----
    machine_days = []
    for d in range(N_DAYS):
        day = START_DATE + timedelta(days=d)
        weekday = day.weekday()  # 0=Mon
        weekday_load = 0.20 if weekday < 5 else -0.30
        for m in machines:
            age_years = (day - m["install_date"]).days / 365.25
            heat_spike = float(rng.uniform(0.3, 0.9)) if rng.random() < 0.12 else 0.0

            stress_z = (
                -0.85
                + 0.55 * m["weakness"]
                + 0.95 * m["type_offset"]
                + 0.115 * (age_years - 4.0)
                + weekday_load
                + heat_spike
                + float(rng.normal(0, 0.45))
            )
            stress = sigmoid(stress_z)  # in (0, 1)

            # Observable daily sensor means are near-monotonic in stress.
            temp_day = float(np.clip(60.0 + 50.0 * stress + rng.normal(0, 3.0), 40.0, 135.0))
            vib_day = float(np.clip(1.0 + 5.5 * stress + rng.normal(0, 0.4), 0.2, 9.5))
            pres_day = float(np.clip(100.0 + 80.0 * stress + rng.normal(0, 5.0), 60.0, 230.0))
            hum_day = float(np.clip(40.0 + 16.0 * stress + rng.normal(0, 3.0), 18.0, 85.0))

            # Steep failure probability in stress; noise keeps AUC below 1.
            failed = rng.random() < sigmoid(6.0 * (stress - 0.60))

            machine_days.append({
                "m": m,
                "day": day,
                "stress": stress,
                "temp": temp_day,
                "vib": vib_day,
                "pres": pres_day,
                "hum": hum_day,
                "failed": bool(failed),
            })

    n_failed = sum(1 for r in machine_days if r["failed"])
    print(f"Machine-days: {len(machine_days):,} | failed: {n_failed:,} "
          f"({100 * n_failed / len(machine_days):.1f}%)")

    # ---- Sensor readings: spread N_SENSOR_ROWS across machine-days ----
    per_day = N_SENSOR_ROWS // len(machine_days)
    remainder = N_SENSOR_ROWS - per_day * len(machine_days)
    sensor_path = OUT_DIR / "sensor_readings.csv"
    rid = 0
    with sensor_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["reading_id", "machine_id", "production_line", "reading_timestamp",
                    "temperature", "pressure", "vibration", "humidity"])
        for idx, r in enumerate(machine_days):
            n = per_day + (1 if idx < remainder else 0)
            m = r["m"]
            temp_noise = 1.5 + 0.5 * r["stress"]
            vib_noise = 0.25 + 0.4 * r["stress"]
            pres_noise = 3.0 + 4.0 * r["stress"]
            for _ in range(n):
                rid += 1
                secs = int(rng.integers(0, 86400))
                ts = (r["day"] + timedelta(seconds=secs)).strftime("%Y-%m-%d %H:%M:%S")
                temperature = r["temp"] + float(rng.normal(0, temp_noise))
                pressure = r["pres"] + float(rng.normal(0, pres_noise))
                vibration = max(0.0, r["vib"] + float(rng.normal(0, vib_noise)))
                humidity = float(np.clip(r["hum"] + rng.normal(0, 2.0), 5.0, 100.0))
                w.writerow([
                    f"R-{rid:07d}", m["machine_id"], m["production_line"], ts,
                    round(temperature, 2), round(pressure, 2),
                    round(vibration, 3), round(humidity, 1),
                ])
    print(f"Wrote {rid:,} sensor rows -> {sensor_path.name}")

    # ---- Production batches: 1-3 per producing machine-day, carry failure_event ----
    batches = []
    bid = 0
    SHIFT_STARTS = [0, 8, 16]
    for r in machine_days:
        m = r["m"]
        # Machines produce on ~85% of days; always produce on a failed day so the
        # failure label is observable (otherwise the left-join would treat it as 0).
        if not (r["failed"] or rng.random() < 0.85):
            continue
        n_batch = int(rng.integers(1, 4))
        for _ in range(n_batch):
            bid += 1
            shift_start = int(rng.choice(SHIFT_STARTS))
            start = r["day"] + timedelta(hours=shift_start)
            end = start + timedelta(hours=8)
            planned = int(np.clip(rng.normal(320, 40), 120, 500))
            # Failed days lose output to downtime and produce more defects.
            base_defect_rate = 0.015 + 0.05 * r["stress"]
            if r["failed"]:
                downtime = float(np.clip(rng.normal(95 + 120 * r["stress"], 35), 60, 480))
                defect_rate = base_defect_rate + float(rng.uniform(0.03, 0.09))
                failure_event = 1
            else:
                downtime = float(np.clip(rng.normal(18 + 25 * r["stress"], 12), 0, 70))
                defect_rate = base_defect_rate
                failure_event = 0
            lost = int(planned * (downtime / 480.0) * 0.6)
            produced = max(0, planned - lost - int(rng.integers(0, 15)))
            defects = int(max(0, round(produced * defect_rate)))
            product = str(rng.choice(PRODUCTS))
            batches.append([
                f"B-{bid:05d}", m["production_line"], product,
                start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"),
                planned, produced, defects, round(downtime, 1),
                m["machine_id"], failure_event,
            ])

    rng.shuffle(batches)
    batch_path = OUT_DIR / "production_batches.csv"
    with batch_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["batch_id", "production_line", "product", "batch_start", "batch_end",
                    "planned_units", "units_produced", "defect_count", "downtime_minutes",
                    "machine_id", "failure_event"])
        w.writerows(batches)
    n_fail_batches = sum(1 for b in batches if b[-1] == 1)
    print(f"Wrote {len(batches):,} batches -> {batch_path.name} "
          f"({n_fail_batches:,} flagged failure_event=1)")


if __name__ == "__main__":
    main()
