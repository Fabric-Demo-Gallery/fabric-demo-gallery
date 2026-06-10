"""Reproducible generator for the Healthcare demo source data.

Produces ``staff_catalog.csv``, ``patient_admissions.csv`` and
``clinical_records.csv`` with a *learnable* relationship between observable
admission / patient / vitals features and the 30-day readmission label, so the
readmission-risk classifier trains to a credible AUC (~0.80-0.90) instead of
behaving like a coin flip on uncorrelated random data.

Signal model (per admission):
  * Latent readmission propensity is a logistic function of observable drivers:
      base
      + age risk          (older age groups riskier)
      + department risk    (Oncology / Cardiology / Neurology riskier)
      + admission-type risk (Emergency / Transfer riskier than Elective / Outpatient)
      + length-of-stay      (longer stays riskier)
      + diagnosis-chapter risk (I* cardiac/circulatory riskier than M* musculoskeletal)
      + prior-admissions count
      + abnormal-vitals burden during the stay
      + irreducible noise (keeps AUC < 1.0)
  * ``is_readmission = rng < sigmoid(logit)`` — tuned to ~18% prevalence.
  * Clinical-record vitals are generated AFTER the latent risk so that abnormal
    vitals are MORE frequent on admissions that go on to be readmitted — this
    makes the silver ``abnormal_vital_count`` aggregate a genuine predictor.

IDs are CONSISTENT across files. The ML feature-engineering notebook derives the
target from ``is_readmission`` and EXCLUDES the leaky silver column
``high_risk_flag`` (which is computed from the readmission flag) from the model.

Run:  python demos/healthcare/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_STAFF = 200
N_PATIENTS = 8000
N_ADMISSIONS = 20000
N_CLINICAL = 80000
N_DAYS = 90
START_DATE = datetime(2025, 1, 1)

OUT_DIR = Path(__file__).resolve().parent

DEPARTMENTS = ["Cardiology", "Emergency", "General Medicine", "Neurology",
               "Oncology", "Orthopaedics", "Paediatrics"]
# Department -> latent readmission offset.
DEPT_RISK = {
    "Cardiology": 0.85, "Emergency": 0.45, "General Medicine": 0.05,
    "Neurology": 0.70, "Oncology": 1.25, "Orthopaedics": -0.50, "Paediatrics": -0.70,
}
ADMISSION_TYPES = ["Elective", "Emergency", "Outpatient", "Transfer"]
ADMISSION_TYPE_RISK = {"Elective": -0.55, "Emergency": 0.85, "Outpatient": -0.95, "Transfer": 0.70}
INSURANCE = ["NHS", "Private", "International"]
AGE_GROUPS = ["0-17", "18-34", "35-54", "55-74", "75+"]
AGE_RISK = {"0-17": -0.70, "18-34": -0.45, "35-54": 0.00, "55-74": 0.70, "75+": 1.30}

ROLES = ["Doctor", "Consultant", "Nurse", "Technician", "Registrar"]
SHIFTS = ["Morning", "Afternoon", "Night"]

# Diagnosis chapters: I = circulatory (higher risk), M = musculoskeletal (lower).
DX_CHAPTERS = {"I": 0.70, "M": -0.45}

VITAL_TYPES = ["Blood Pressure Systolic", "Heart Rate", "Temperature", "O2 Saturation"]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Staff catalog ───────────────────────────────────────────────────────
    staff = []
    for i in range(1, N_STAFF + 1):
        hire_year = int(rng.integers(2008, 2025))
        staff.append({
            "staff_id": f"ST-{i:04d}",
            "role": str(rng.choice(ROLES)),
            "department": str(rng.choice(DEPARTMENTS)),
            "shift": str(rng.choice(SHIFTS)),
            "hire_date": datetime(hire_year, int(rng.integers(1, 13)), int(rng.integers(1, 28))).strftime("%Y-%m-%d"),
        })
    with (OUT_DIR / "staff_catalog.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["staff_id", "role", "department", "shift", "hire_date"])
        for s in staff:
            w.writerow([s["staff_id"], s["role"], s["department"], s["shift"], s["hire_date"]])
    print(f"Wrote {len(staff)} staff -> staff_catalog.csv")

    # ── Per-patient prior-admission counts (longitudinal signal) ────────────
    patient_prior = {f"P-{i:05d}": int(rng.poisson(0.7)) for i in range(1, N_PATIENTS + 1)}
    patient_ids = list(patient_prior.keys())

    # ── Admissions with learnable readmission signal ────────────────────────
    admissions = []
    n_readmit = 0
    for a in range(1, N_ADMISSIONS + 1):
        patient = patient_ids[int(rng.integers(0, N_PATIENTS))]
        dept = str(rng.choice(DEPARTMENTS))
        adm_type = str(rng.choice(ADMISSION_TYPES, p=[0.30, 0.40, 0.18, 0.12]))
        insurance = str(rng.choice(INSURANCE, p=[0.70, 0.22, 0.08]))
        age = str(rng.choice(AGE_GROUPS, p=[0.12, 0.20, 0.26, 0.28, 0.14]))
        chapter = str(rng.choice(list(DX_CHAPTERS.keys())))
        dx = f"{chapter}{int(rng.integers(10, 30))}"
        prior = patient_prior[patient]

        # Length of stay influenced by department + admission type + age.
        los_base = 2.5 + 2.0 * max(0.0, DEPT_RISK[dept]) + (1.5 if adm_type in ("Emergency", "Transfer") else 0.0)
        los = int(np.clip(rng.poisson(max(1.0, los_base)) + (2 if age == "75+" else 0), 0, 60))

        readmit_logit = (
            -2.85
            + AGE_RISK[age]
            + DEPT_RISK[dept]
            + ADMISSION_TYPE_RISK[adm_type]
            + 0.075 * los
            + DX_CHAPTERS[chapter]
            + 0.50 * prior
            + float(rng.normal(0, 0.30))
        )
        # latent_risk also drives abnormal-vital frequency below.
        latent_risk = sigmoid(readmit_logit)
        is_readmit = rng.random() < latent_risk
        if is_readmit:
            n_readmit += 1

        adm_day = START_DATE + timedelta(days=int(rng.integers(0, N_DAYS)))
        adm_hour = int(rng.integers(0, 24))
        adm_dt = adm_day + timedelta(hours=adm_hour)
        dis_dt = adm_dt + timedelta(days=los)
        admissions.append({
            "patient_id": patient,
            "admission_id": f"ADM-{a:06d}",
            "department": dept,
            "admission_type": adm_type,
            "admission_date": adm_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "discharge_date": dis_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "length_of_stay_days": los,
            "primary_dx_code": dx,
            "insurance_type": insurance,
            "is_readmission": bool(is_readmit),
            "age_group": age,
            "prior_admissions": prior,
            "assigned_staff_id": staff[int(rng.integers(0, N_STAFF))]["staff_id"],
            "latent_risk": latent_risk,
        })

    with (OUT_DIR / "patient_admissions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["patient_id", "admission_id", "department", "admission_type",
                    "admission_date", "discharge_date", "length_of_stay_days",
                    "primary_dx_code", "insurance_type", "is_readmission",
                    "age_group", "prior_admissions", "assigned_staff_id"])
        for r in admissions:
            w.writerow([r["patient_id"], r["admission_id"], r["department"], r["admission_type"],
                        r["admission_date"], r["discharge_date"], r["length_of_stay_days"],
                        r["primary_dx_code"], r["insurance_type"], r["is_readmission"],
                        r["age_group"], r["prior_admissions"], r["assigned_staff_id"]])
    print(f"Wrote {len(admissions):,} admissions -> patient_admissions.csv "
          f"({n_readmit:,} readmissions, {100 * n_readmit / len(admissions):.1f}%)")

    # ── Clinical records (vitals) — abnormal rate rises with latent risk ────
    staff_ids = [s["staff_id"] for s in staff]
    rows = []
    per_adm = max(1, N_CLINICAL // N_ADMISSIONS)
    rid = 0
    for adm in admissions:
        # Higher-risk admissions get a higher chance of abnormal vitals.
        p_abnormal = 0.06 + 0.70 * adm["latent_risk"]
        for _ in range(per_adm):
            rid += 1
            vital = str(rng.choice(VITAL_TYPES))
            abnormal = rng.random() < p_abnormal
            if vital == "Blood Pressure Systolic":
                value = float(rng.uniform(145, 190) if abnormal else rng.uniform(95, 138))
            elif vital == "Heart Rate":
                value = float(rng.uniform(101, 140) if abnormal else rng.uniform(62, 98))
            elif vital == "Temperature":
                value = float(rng.uniform(38.0, 40.0) if abnormal else rng.uniform(36.2, 37.6))
            else:  # O2 Saturation
                value = float(rng.uniform(85, 94) if abnormal else rng.uniform(95, 100))
            secs = int(rng.integers(0, 86400))
            rec_dt = datetime.strptime(adm["admission_date"], "%Y-%m-%d %H:%M:%S") + timedelta(seconds=secs)
            rows.append([
                f"REC-{rid:07d}", adm["admission_id"], adm["patient_id"], adm["department"],
                rec_dt.strftime("%Y-%m-%d %H:%M:%S"), vital, round(value, 1),
                str(rng.choice(staff_ids)),
            ])

    with (OUT_DIR / "clinical_records.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["record_id", "admission_id", "patient_id", "department",
                    "recorded_at", "vital_type", "value", "recorded_by"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} clinical records -> clinical_records.csv")


if __name__ == "__main__":
    main()
