"""Reproducible generator for the Education demo source data.

Produces ``students.csv``, ``faculty.csv``, ``enrolments.csv`` and
``assessments.csv`` with a *learnable* relationship between observable
enrolment / student / early-assessment features and the **dropout** label
(``is_withdrawn``), so the dropout classifier trains to a credible AUC
(~0.80-0.88).

Use case: Dropout Risk Prediction — predict whether a student enrolment will
end in *withdrawal*.

Signal model (per enrolment):
  * Dropout propensity is a logistic function of drivers:
      base
      - early assessment avg score (strong: poor performers drop out)
      - early assessment pass rate
      + level risk            (PhD attrition higher than UG)
      + department risk        (Medical / Law tougher)
      + age-at-enrolment risk   (mature students juggle more)
      - credits engaged
      + latent student grit (small, unobservable)
      + irreducible noise (keeps AUC < 1.0)
  * status is DERIVED from the label (post-hoc leakage); the FE notebook
    EXCLUDES status, is_completed.
  * Early-term assessments (attempt 1, first weeks) ARE legitimate features:
    avg_score / pass_rate / assessment_count are aggregated per enrolment.
  * Target prevalence ~26%.

IDs are CONSISTENT: every enrolment references an existing student + course;
assessments reference existing enrolments; the dropout signal is encoded in the
early assessment scores so the per-enrolment aggregates recover it.

Run:  python demos/education/data/_generate_data.py
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 42
N_STUDENTS = 6000
N_FACULTY = 200
N_ENROLMENTS = 24000
N_ASSESSMENTS = 90000
START_DATE = datetime(2023, 9, 1)

OUT_DIR = Path(__file__).resolve().parent

DEPARTMENTS = ["Arts", "Business", "Computing", "Education Dept", "Engineering",
               "Law School", "Medical School", "Social Sciences"]
DEPT_RISK = {"Arts": 0.10, "Business": -0.05, "Computing": 0.15, "Education Dept": -0.15,
             "Engineering": 0.25, "Law School": 0.45, "Medical School": 0.55, "Social Sciences": 0.05}
PROGRAMMES = ["Arts & Humanities", "Business Administration", "Computer Science", "Education",
              "Engineering", "Law", "Medicine", "Social Sciences"]
LEVELS = ["Undergraduate", "Postgraduate", "PhD"]
LEVEL_RISK = {"Undergraduate": -0.10, "Postgraduate": 0.15, "PhD": 0.55}
REGIONS = ["International", "London", "Midlands", "North West", "Scotland", "South East", "Wales"]
GENDERS = ["Female", "Male", "Non-binary", "Prefer not to say"]
ROLES = ["Lecturer", "Senior Lecturer", "Reader", "Professor", "Teaching Fellow"]
ASSESSMENT_TYPES = ["Coursework", "Dissertation", "Exam", "Group Project", "Lab Report", "Presentation"]
GRADE_BANDS = [(70, "A"), (60, "B"), (50, "C"), (40, "D"), (0, "F")]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def grade_for(score: float) -> str:
    for threshold, letter in GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ── Students (latent grit) ──────────────────────────────────────────────
    students = []
    for i in range(1, N_STUDENTS + 1):
        dept = str(rng.choice(DEPARTMENTS))
        level = str(rng.choice(LEVELS, p=[0.55, 0.32, 0.13]))
        students.append({
            "student_id": f"STU-{i:05d}",
            "programme": str(rng.choice(PROGRAMMES)),
            "department": dept,
            "level": level,
            "cohort_year": int(rng.integers(2021, 2025)),
            "enrolment_date": (START_DATE - timedelta(days=int(rng.integers(0, 60)))).strftime("%Y-%m-%d"),
            "status": "Active",
            "gender": str(rng.choice(GENDERS, p=[0.46, 0.46, 0.05, 0.03])),
            "region": str(rng.choice(REGIONS)),
            "age_at_enrolment": int(np.clip(rng.normal(24, 7), 17, 60)),
            "grit": float(rng.normal(0, 1)),  # latent, not written
        })
    with (OUT_DIR / "students.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "programme", "department", "level", "cohort_year",
                    "enrolment_date", "status", "gender", "region", "age_at_enrolment"])
        for s in students:
            w.writerow([s["student_id"], s["programme"], s["department"], s["level"],
                        s["cohort_year"], s["enrolment_date"], s["status"], s["gender"],
                        s["region"], s["age_at_enrolment"]])
    print(f"Wrote {len(students)} students -> students.csv")

    # ── Faculty ─────────────────────────────────────────────────────────────
    faculty = []
    for i in range(1, N_FACULTY + 1):
        faculty.append({
            "faculty_id": f"FAC-{i:04d}",
            "department": str(rng.choice(DEPARTMENTS)),
            "role": str(rng.choice(ROLES)),
            "years_at_institution": int(rng.integers(1, 36)),
            "courses_assigned": int(rng.integers(1, 7)),
            "research_active": "Y" if rng.random() < 0.6 else "N",
            "hire_date": (START_DATE - timedelta(days=int(rng.integers(365, 12000)))).strftime("%Y-%m-%d"),
        })
    with (OUT_DIR / "faculty.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["faculty_id", "department", "role", "years_at_institution",
                    "courses_assigned", "research_active", "hire_date"])
        for fa in faculty:
            w.writerow([fa["faculty_id"], fa["department"], fa["role"], fa["years_at_institution"],
                        fa["courses_assigned"], fa["research_active"], fa["hire_date"]])
    print(f"Wrote {len(faculty)} faculty -> faculty.csv")

    # ── Enrolments with learnable dropout signal ────────────────────────────
    # Latent "performance" drives both early assessment scores AND dropout, so the
    # per-enrolment assessment aggregates recover the signal (no direct leakage).
    enrolments = []
    n_withdrawn = 0
    for e in range(1, N_ENROLMENTS + 1):
        student = students[int(rng.integers(0, N_STUDENTS))]
        dept = student["department"]
        level = student["level"]
        credits = int(rng.choice([10, 15, 20, 30], p=[0.25, 0.40, 0.25, 0.10]))
        age = student["age_at_enrolment"]

        # Latent academic performance for this enrolment (unobservable directly).
        performance = (
            0.55 * student["grit"]
            - 0.30 * LEVEL_RISK[level]
            - 0.30 * DEPT_RISK[dept]
            + float(rng.normal(0, 0.7))
        )

        dropout_logit = (
            -1.70
            - 1.65 * performance
            + 1.70 * LEVEL_RISK[level]
            + 1.70 * DEPT_RISK[dept]
            + 0.030 * (age - 24)
            - 0.012 * (credits - 15)
            + float(rng.normal(0, 0.24))
        )
        is_withdrawn = int(rng.random() < sigmoid(dropout_logit))
        if is_withdrawn:
            n_withdrawn += 1
            status = "Withdrawn"
            is_completed = 0
        else:
            status = str(rng.choice(["Completed", "Enrolled", "Failed"], p=[0.62, 0.30, 0.08]))
            is_completed = 1 if status == "Completed" else 0

        enrolments.append({
            "enrolment_id": f"ENR-{e:06d}",
            "student_id": student["student_id"],
            "course_id": f"CRS-{int(rng.integers(1, 200)):04d}",
            "department": dept,
            "level": level,
            "credits": credits,
            "enrolment_date": (START_DATE + timedelta(days=int(rng.integers(0, 30)))).strftime("%Y-%m-%d"),
            "status": status,
            "is_completed": is_completed,
            "is_withdrawn": is_withdrawn,
            "age_at_enrolment": age,
            "_performance": performance,
        })
    with (OUT_DIR / "enrolments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["enrolment_id", "student_id", "course_id", "department", "level",
                    "credits", "enrolment_date", "status", "is_completed", "is_withdrawn",
                    "age_at_enrolment"])
        for en in enrolments:
            w.writerow([en["enrolment_id"], en["student_id"], en["course_id"], en["department"],
                        en["level"], en["credits"], en["enrolment_date"], en["status"],
                        en["is_completed"], en["is_withdrawn"], en["age_at_enrolment"]])
    print(f"Wrote {len(enrolments):,} enrolments -> enrolments.csv "
          f"({n_withdrawn:,} withdrawn, {100*n_withdrawn/len(enrolments):.1f}%)")

    # ── Assessments (early-term, scores reflect latent performance) ─────────
    arows = []
    for a in range(1, N_ASSESSMENTS + 1):
        en = enrolments[int(rng.integers(0, N_ENROLMENTS))]
        atype = str(rng.choice(ASSESSMENT_TYPES))
        # Score driven by enrolment performance + noise (genuine predictor of dropout).
        score = float(np.clip(rng.normal(62 + 16 * en["_performance"], 9), 0, 100))
        is_pass = int(score >= 40)
        arows.append([
            f"ASM-{a:07d}", en["enrolment_id"], en["student_id"], en["course_id"],
            en["department"], atype, int(rng.integers(1, 4)),
            (START_DATE + timedelta(days=int(rng.integers(20, 90)))).strftime("%Y-%m-%d"),
            round(score, 1), grade_for(score), is_pass, int(rng.integers(800, 4000)),
        ])
    with (OUT_DIR / "assessments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["assessment_id", "enrolment_id", "student_id", "course_id", "department",
                    "assessment_type", "attempt_number", "submitted_date", "score", "grade",
                    "is_pass", "word_count"])
        w.writerows(arows)
    print(f"Wrote {len(arows):,} assessments -> assessments.csv")


if __name__ == "__main__":
    main()
