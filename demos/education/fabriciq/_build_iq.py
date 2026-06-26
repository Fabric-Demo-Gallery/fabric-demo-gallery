"""Build the education Fabric IQ ontology package.

Entities (5; Assessment, PlatformEvent span Lakehouse + Eventhouse):
  Student       PK student_id
  Course        PK course_id  (derived from distinct course_id)
  Enrolment     PK enrolment_id;   FK student_id, course_id
  Assessment    PK assessment_id;  FK enrolment_id, student_id, course_id  (dual)
  PlatformEvent PK event_id;       FK student_id, course_id                (dual)
"""

from __future__ import annotations

import csv
import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_scenarios"))
from fabriciq_common import Entity, Prop, write_iq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "education_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Student", "students", [
        Prop("StudentId", "student_id", "String", ident=True, display=True),
        Prop("Programme", "programme"),
        Prop("Department", "department"),
        Prop("Level", "level"),
        Prop("CohortYear", "cohort_year", "BigInt"),
        Prop("Status", "status"),
        Prop("Gender", "gender"),
        Prop("Region", "region"),
        Prop("AgeAtEnrolment", "age_at_enrolment", "BigInt"),
    ]),
    Entity("Course", "courses", [
        Prop("CourseId", "course_id", "String", ident=True, display=True),
        Prop("Department", "department"),
    ]),
    Entity("Enrolment", "enrolments", [
        Prop("EnrolmentId", "enrolment_id", "String", ident=True, display=True),
        Prop("StudentId", "student_id"),
        Prop("CourseId", "course_id"),
        Prop("Department", "department"),
        Prop("Level", "level"),
        Prop("Credits", "credits", "BigInt"),
        Prop("Status", "status"),
        Prop("IsCompleted", "is_completed", "BigInt"),
        Prop("IsWithdrawn", "is_withdrawn", "BigInt"),
    ]),
    Entity("Assessment", "assessments", [
        Prop("AssessmentId", "assessment_id", "String", ident=True, display=True),
        Prop("EnrolmentId", "enrolment_id"),
        Prop("StudentId", "student_id"),
        Prop("CourseId", "course_id"),
        Prop("AssessmentType", "assessment_type"),
        Prop("Grade", "grade"),
        Prop("IsPass", "is_pass", "BigInt"),
        Prop("Score", "score", "Double", ts=True),
        Prop("AttemptNumber", "attempt_number", "BigInt", ts=True),
        Prop("WordCount", "word_count", "BigInt", ts=True),
    ]),
    Entity("PlatformEvent", "platform_events", [
        Prop("EventId", "event_id", "String", ident=True, display=True),
        Prop("StudentId", "student_id"),
        Prop("CourseId", "course_id"),
        Prop("EventType", "event_type"),
        Prop("Platform", "platform"),
        Prop("IsError", "is_error", "Boolean"),
        Prop("SessionDurationSecs", "session_duration_secs", "BigInt", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("EnrolmentOfStudent", "Enrolment", "Student"),
    ("EnrolmentInCourse", "Enrolment", "Course"),
    ("AssessmentForEnrolment", "Assessment", "Enrolment"),
    ("AssessmentByStudent", "Assessment", "Student"),
    ("EventByStudent", "PlatformEvent", "Student"),
    ("EventInCourse", "PlatformEvent", "Course"),
]
BINDING_RELATIONSHIP = [
    ("EnrolmentOfStudent", "Enrolment", "Student", "enrolment_id", "student_id", "enrolments"),
    ("EnrolmentInCourse", "Enrolment", "Course", "enrolment_id", "course_id", "enrolments"),
    ("AssessmentForEnrolment", "Assessment", "Enrolment", "assessment_id", "enrolment_id", "assessments"),
    ("AssessmentByStudent", "Assessment", "Student", "assessment_id", "student_id", "assessments"),
    ("EventByStudent", "PlatformEvent", "Student", "event_id", "student_id", "platform_events"),
    ("EventInCourse", "PlatformEvent", "Course", "event_id", "course_id", "platform_events"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    students = _read("students.csv")
    enrolments = _read("enrolments.csv")
    assessments = _read("assessments.csv")
    events = _read("platform_events.csv")

    courses = OrderedDict()
    for r in enrolments + assessments + events:
        cid = r.get("course_id")
        if cid:
            courses.setdefault(cid, r.get("department", ""))

    enr_c = enrolments[:EVENT_CAP]
    asm_c = assessments[:EVENT_CAP]
    ev_c = events[:EVENT_CAP]

    instance_tables = {
        "students": (["student_id", "programme", "department", "level", "cohort_year", "status", "gender", "region", "age_at_enrolment"],
                     [[r["student_id"], r["programme"], r["department"], r["level"], r["cohort_year"], r["status"], r["gender"], r["region"], r["age_at_enrolment"]] for r in students]),
        "courses": (["course_id", "department"], [[k, v] for k, v in courses.items()]),
        "enrolments": (["enrolment_id", "student_id", "course_id", "department", "level", "credits", "status", "is_completed", "is_withdrawn"],
                       [[r["enrolment_id"], r["student_id"], r["course_id"], r["department"], r["level"], r["credits"], r["status"], r["is_completed"], r["is_withdrawn"]] for r in enr_c]),
        "assessments": (["assessment_id", "enrolment_id", "student_id", "course_id", "assessment_type", "grade", "is_pass"],
                        [[r["assessment_id"], r["enrolment_id"], r["student_id"], r["course_id"], r["assessment_type"], r["grade"], r["is_pass"]] for r in asm_c]),
        "platform_events": (["event_id", "student_id", "course_id", "event_type", "platform", "is_error"],
                            [[r["event_id"], r["student_id"], r["course_id"], r["event_type"], r["platform"], r["is_error"]] for r in ev_c]),
    }
    events_tables = {
        "assessments": (["assessment_id", "timestamp_utc", "score", "attempt_number", "word_count"],
                        [[r["assessment_id"], r["submitted_date"], r["score"], r["attempt_number"], r["word_count"]] for r in asm_c]),
        "platform_events": (["event_id", "timestamp_utc", "session_duration_secs"],
                            [[r["event_id"], r["timestamp"], r["session_duration_secs"]] for r in ev_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Students: {len(students)}  Courses: {len(courses)}  Enrolments: {len(enr_c)}  Assessments: {len(asm_c)}  Events: {len(ev_c)}")


if __name__ == "__main__":
    build()
