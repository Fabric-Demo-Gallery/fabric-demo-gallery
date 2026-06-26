"""Build the healthcare Fabric IQ ontology package.

Entities (4; Admission, ClinicalRecord span Lakehouse + Eventhouse):
  Staff          PK staff_id
  Admission      PK admission_id;  FK patient/department/assigned_staff_id  (dual; LOS over time)
  ClinicalRecord PK record_id;     FK admission_id, patient_id              (dual; vital readings)
  Department     PK department_id  (derived from distinct department)
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
OUT = os.path.join(HERE, "healthcare_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Department", "departments", [
        Prop("DepartmentId", "department_id", "String", ident=True, display=True),
        Prop("DepartmentName", "department_name"),
    ]),
    Entity("Staff", "staff", [
        Prop("StaffId", "staff_id", "String", ident=True, display=True),
        Prop("Role", "role"),
        Prop("Department", "department"),
        Prop("Shift", "shift"),
        Prop("HireDate", "hire_date", "DateTime"),
    ]),
    Entity("Admission", "admissions", [
        Prop("AdmissionId", "admission_id", "String", ident=True, display=True),
        Prop("PatientId", "patient_id"),
        Prop("Department", "department"),
        Prop("AssignedStaffId", "assigned_staff_id"),
        Prop("AdmissionType", "admission_type"),
        Prop("InsuranceType", "insurance_type"),
        Prop("PrimaryDxCode", "primary_dx_code"),
        Prop("AgeGroup", "age_group"),
        Prop("LengthOfStayDays", "length_of_stay_days", "BigInt", ts=True),
        Prop("PriorAdmissions", "prior_admissions", "BigInt", ts=True),
    ]),
    Entity("ClinicalRecord", "clinical_records", [
        Prop("RecordId", "record_id", "String", ident=True, display=True),
        Prop("AdmissionId", "admission_id"),
        Prop("PatientId", "patient_id"),
        Prop("Department", "department"),
        Prop("VitalType", "vital_type"),
        Prop("RecordedBy", "recorded_by"),
        Prop("Value", "value", "Double", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("StaffInDepartment", "Staff", "Department"),
    ("AdmissionInDepartment", "Admission", "Department"),
    ("AdmissionAssignedStaff", "Admission", "Staff"),
    ("RecordForAdmission", "ClinicalRecord", "Admission"),
]
BINDING_RELATIONSHIP = [
    ("StaffInDepartment", "Staff", "Department", "staff_id", "department", "staff"),
    ("AdmissionInDepartment", "Admission", "Department", "admission_id", "department", "admissions"),
    ("AdmissionAssignedStaff", "Admission", "Staff", "admission_id", "assigned_staff_id", "admissions"),
    ("RecordForAdmission", "ClinicalRecord", "Admission", "record_id", "admission_id", "clinical_records"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    staff = _read("staff_catalog.csv")
    adm = _read("patient_admissions.csv")
    rec = _read("clinical_records.csv")

    depts = OrderedDict()
    for r in staff + adm:
        if r.get("department"):
            depts.setdefault(r["department"], None)

    adm_c = adm[:EVENT_CAP]
    rec_c = rec[:EVENT_CAP]

    instance_tables = {
        "departments": (["department_id", "department_name"], [[k, k] for k in depts]),
        "staff": (["staff_id", "role", "department", "shift", "hire_date"],
                  [[r["staff_id"], r["role"], r["department"], r["shift"], r["hire_date"]] for r in staff]),
        "admissions": (["admission_id", "patient_id", "department", "assigned_staff_id", "admission_type", "insurance_type", "primary_dx_code", "age_group"],
                       [[r["admission_id"], r["patient_id"], r["department"], r.get("assigned_staff_id", ""), r["admission_type"], r["insurance_type"], r["primary_dx_code"], r["age_group"]] for r in adm_c]),
        "clinical_records": (["record_id", "admission_id", "patient_id", "department", "vital_type", "recorded_by"],
                             [[r["record_id"], r["admission_id"], r["patient_id"], r["department"], r["vital_type"], r["recorded_by"]] for r in rec_c]),
    }
    events_tables = {
        "admissions": (["admission_id", "timestamp_utc", "length_of_stay_days", "prior_admissions"],
                       [[r["admission_id"], r["admission_date"], r["length_of_stay_days"], r["prior_admissions"]] for r in adm_c]),
        "clinical_records": (["record_id", "timestamp_utc", "value"],
                             [[r["record_id"], r["recorded_at"], r["value"]] for r in rec_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Departments: {len(depts)}  Staff: {len(staff)}  Admissions: {len(adm_c)}  Records: {len(rec_c)}")


if __name__ == "__main__":
    build()
