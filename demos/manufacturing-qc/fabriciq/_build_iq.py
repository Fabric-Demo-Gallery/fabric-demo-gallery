"""Build the manufacturing-QC Fabric IQ ontology package (`manufacturing_qc_ontology_package.iq`).

The `.iq` file is a ZIP with the parts the Fabric IQ accelerator wheel consumes:

    definition/entity_types.csv          ontology schema (entities + properties)
    definition/relationship_types.csv    named relationships between entities
    binding/binding_entity_types.csv     each property -> table + column (LH or Kusto)
    binding/binding_relationship_types.csv relationships -> source/target key columns
    instance_data/*.csv                  -> Lakehouse delta tables (static attributes)
    events_data/*.csv                    -> Eventhouse/Kusto tables (time-series)

It reuses the manufacturing-qc demo's own CSVs (../data/*.csv).

Run:  python demos/manufacturing-qc/fabriciq/_build_iq.py
Output: demos/manufacturing-qc/fabriciq/manufacturing_qc_ontology_package.iq

Entities (4; ProductionBatch + SensorReading span Lakehouse + Eventhouse):
  Machine         PK machine_id;  FK production_line -> ProductionLine
  ProductionLine  PK line_id      (derived from distinct production_line values)
  ProductionBatch PK batch_id;    FK machine_id -> Machine, production_line -> ProductionLine
  SensorReading   PK reading_id;  FK machine_id -> Machine
"""

from __future__ import annotations

import csv
import io
import os
import zipfile
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "manufacturing_qc_ontology_package.iq")

# Cap the time-series rows so the package stays small.
SENSOR_EVENT_CAP = 20000

# ── entity_types.csv rows ────────────────────────────────────────────────────
# (EntityTypeName, PropertyName, PropertyDataType, IsIdentifier, IsDisplayName, IsTimeseries)
ENTITY_TYPES = [
    # Machine (Lakehouse only)
    ("Machine", "MachineId", "String", "TRUE", "FALSE", "FALSE"),
    ("Machine", "MachineName", "String", "FALSE", "TRUE", "FALSE"),
    ("Machine", "MachineType", "String", "FALSE", "FALSE", "FALSE"),
    ("Machine", "ProductionLine", "String", "FALSE", "FALSE", "FALSE"),
    ("Machine", "InstallDate", "DateTime", "FALSE", "FALSE", "FALSE"),
    # ProductionLine (Lakehouse only)
    ("ProductionLine", "LineId", "String", "TRUE", "TRUE", "FALSE"),
    ("ProductionLine", "LineName", "String", "FALSE", "FALSE", "FALSE"),
    # ProductionBatch (Lakehouse static + Eventhouse time-series)
    ("ProductionBatch", "BatchId", "String", "TRUE", "TRUE", "FALSE"),
    ("ProductionBatch", "MachineId", "String", "FALSE", "FALSE", "FALSE"),
    ("ProductionBatch", "ProductionLine", "String", "FALSE", "FALSE", "FALSE"),
    ("ProductionBatch", "Product", "String", "FALSE", "FALSE", "FALSE"),
    ("ProductionBatch", "PlannedUnits", "BigInt", "FALSE", "FALSE", "FALSE"),
    ("ProductionBatch", "FailureEvent", "BigInt", "FALSE", "FALSE", "FALSE"),
    ("ProductionBatch", "UnitsProduced", "BigInt", "FALSE", "FALSE", "TRUE"),
    ("ProductionBatch", "DefectCount", "BigInt", "FALSE", "FALSE", "TRUE"),
    ("ProductionBatch", "DowntimeMinutes", "Double", "FALSE", "FALSE", "TRUE"),
    ("ProductionBatch", "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE"),
    # SensorReading (Lakehouse static + Eventhouse time-series)
    ("SensorReading", "ReadingId", "String", "TRUE", "TRUE", "FALSE"),
    ("SensorReading", "MachineId", "String", "FALSE", "FALSE", "FALSE"),
    ("SensorReading", "ProductionLine", "String", "FALSE", "FALSE", "FALSE"),
    ("SensorReading", "Temperature", "Double", "FALSE", "FALSE", "TRUE"),
    ("SensorReading", "Pressure", "Double", "FALSE", "FALSE", "TRUE"),
    ("SensorReading", "Vibration", "Double", "FALSE", "FALSE", "TRUE"),
    ("SensorReading", "Humidity", "Double", "FALSE", "FALSE", "TRUE"),
    ("SensorReading", "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE"),
]

# ── relationship_types.csv rows ──────────────────────────────────────────────
# (RelationshipName, SourceEntityTypeName, TargetEntityTypeName)
RELATIONSHIP_TYPES = [
    ("MachineOnLine", "Machine", "ProductionLine"),
    ("BatchOnMachine", "ProductionBatch", "Machine"),
    ("BatchOnLine", "ProductionBatch", "ProductionLine"),
    ("SensorReadingFromMachine", "SensorReading", "Machine"),
]

# ── binding_entity_types.csv rows ────────────────────────────────────────────
# (EntityType, Property, DataType, IsId, IsDisplay, IsTimeseries,
#  SourceTableName, BindingSourceColumnName, DataBindingType, SourceType, TimestampColumnName)
BINDING_ENTITY = [
    # Machine -> lakehouse table "machines"
    ("Machine", "MachineId", "String", "TRUE", "FALSE", "FALSE", "machines", "machine_id", "NonTimeSeries", "LakehouseTable", ""),
    ("Machine", "MachineName", "String", "FALSE", "TRUE", "FALSE", "machines", "machine_name", "NonTimeSeries", "LakehouseTable", ""),
    ("Machine", "MachineType", "String", "FALSE", "FALSE", "FALSE", "machines", "machine_type", "NonTimeSeries", "LakehouseTable", ""),
    ("Machine", "ProductionLine", "String", "FALSE", "FALSE", "FALSE", "machines", "production_line", "NonTimeSeries", "LakehouseTable", ""),
    ("Machine", "InstallDate", "DateTime", "FALSE", "FALSE", "FALSE", "machines", "install_date", "NonTimeSeries", "LakehouseTable", ""),
    # ProductionLine -> lakehouse table "production_lines"
    ("ProductionLine", "LineId", "String", "TRUE", "TRUE", "FALSE", "production_lines", "line_id", "NonTimeSeries", "LakehouseTable", ""),
    ("ProductionLine", "LineName", "String", "FALSE", "FALSE", "FALSE", "production_lines", "line_name", "NonTimeSeries", "LakehouseTable", ""),
    # ProductionBatch static -> lakehouse table "production_batches"
    ("ProductionBatch", "BatchId", "String", "TRUE", "TRUE", "FALSE", "production_batches", "batch_id", "NonTimeSeries", "LakehouseTable", ""),
    ("ProductionBatch", "MachineId", "String", "FALSE", "FALSE", "FALSE", "production_batches", "machine_id", "NonTimeSeries", "LakehouseTable", ""),
    ("ProductionBatch", "ProductionLine", "String", "FALSE", "FALSE", "FALSE", "production_batches", "production_line", "NonTimeSeries", "LakehouseTable", ""),
    ("ProductionBatch", "Product", "String", "FALSE", "FALSE", "FALSE", "production_batches", "product", "NonTimeSeries", "LakehouseTable", ""),
    ("ProductionBatch", "PlannedUnits", "BigInt", "FALSE", "FALSE", "FALSE", "production_batches", "planned_units", "NonTimeSeries", "LakehouseTable", ""),
    ("ProductionBatch", "FailureEvent", "BigInt", "FALSE", "FALSE", "FALSE", "production_batches", "failure_event", "NonTimeSeries", "LakehouseTable", ""),
    # ProductionBatch time-series -> kusto table "production_batches"
    ("ProductionBatch", "UnitsProduced", "BigInt", "FALSE", "FALSE", "TRUE", "production_batches", "units_produced", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("ProductionBatch", "DefectCount", "BigInt", "FALSE", "FALSE", "TRUE", "production_batches", "defect_count", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("ProductionBatch", "DowntimeMinutes", "Double", "FALSE", "FALSE", "TRUE", "production_batches", "downtime_minutes", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("ProductionBatch", "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE", "production_batches", "timestamp_utc", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("ProductionBatch", "BatchId", "String", "FALSE", "FALSE", "TRUE", "production_batches", "batch_id", "TimeSeries", "KustoTable", "timestamp_utc"),
    # SensorReading static -> lakehouse table "sensor_readings"
    ("SensorReading", "ReadingId", "String", "TRUE", "TRUE", "FALSE", "sensor_readings", "reading_id", "NonTimeSeries", "LakehouseTable", ""),
    ("SensorReading", "MachineId", "String", "FALSE", "FALSE", "FALSE", "sensor_readings", "machine_id", "NonTimeSeries", "LakehouseTable", ""),
    ("SensorReading", "ProductionLine", "String", "FALSE", "FALSE", "FALSE", "sensor_readings", "production_line", "NonTimeSeries", "LakehouseTable", ""),
    # SensorReading time-series -> kusto table "sensor_readings"
    ("SensorReading", "Temperature", "Double", "FALSE", "FALSE", "TRUE", "sensor_readings", "temperature", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("SensorReading", "Pressure", "Double", "FALSE", "FALSE", "TRUE", "sensor_readings", "pressure", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("SensorReading", "Vibration", "Double", "FALSE", "FALSE", "TRUE", "sensor_readings", "vibration", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("SensorReading", "Humidity", "Double", "FALSE", "FALSE", "TRUE", "sensor_readings", "humidity", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("SensorReading", "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE", "sensor_readings", "timestamp_utc", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("SensorReading", "ReadingId", "String", "FALSE", "FALSE", "TRUE", "sensor_readings", "reading_id", "TimeSeries", "KustoTable", "timestamp_utc"),
]

# ── binding_relationship_types.csv rows ──────────────────────────────────────
# (RelationshipName, Source, Target, SourceKeyColumnNames, TargetKeyColumnNames, SourceTableName)
# SourceKey = SOURCE entity's identifier column; TargetKey = the FK column IN THE
# SAME SOURCE TABLE that points at the target. BOTH columns live in SourceTableName.
BINDING_RELATIONSHIP = [
    ("MachineOnLine", "Machine", "ProductionLine", "machine_id", "production_line", "machines"),
    ("BatchOnMachine", "ProductionBatch", "Machine", "batch_id", "machine_id", "production_batches"),
    ("BatchOnLine", "ProductionBatch", "ProductionLine", "batch_id", "production_line", "production_batches"),
    ("SensorReadingFromMachine", "SensorReading", "Machine", "reading_id", "machine_id", "sensor_readings"),
]


def _read_csv(name: str) -> tuple[list[str], list[dict]]:
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)
        return r.fieldnames or [], rows


def _csv_bytes(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def build() -> None:
    # ── Read the manufacturing demo's own data ───────────────────────────────
    _, machines = _read_csv("equipment_catalog.csv")
    _, batches = _read_csv("production_batches.csv")
    _, sensors = _read_csv("sensor_readings.csv")

    # instance_data: machines (static)
    machines_instance = _csv_bytes(
        ["machine_id", "machine_name", "machine_type", "production_line", "install_date"],
        [[m["machine_id"], m["machine_name"], m["machine_type"], m["production_line"], m["install_date"]] for m in machines],
    )

    # ProductionLine: derive distinct lines from machines + batches.
    line_ids: "OrderedDict[str, None]" = OrderedDict()
    for m in machines:
        if m["production_line"]:
            line_ids.setdefault(m["production_line"], None)
    for b in batches:
        if b["production_line"]:
            line_ids.setdefault(b["production_line"], None)
    lines_instance = _csv_bytes(
        ["line_id", "line_name"],
        [[lid, lid] for lid in line_ids],
    )

    # ProductionBatch: static identity + attrs in LH; produced/defect/downtime as
    # time-series in EH keyed by batch_end.
    batch_instance = _csv_bytes(
        ["batch_id", "machine_id", "production_line", "product", "planned_units", "failure_event"],
        [[b["batch_id"], b["machine_id"], b["production_line"], b["product"], b["planned_units"], b["failure_event"]] for b in batches],
    )
    batch_events = _csv_bytes(
        ["batch_id", "timestamp_utc", "units_produced", "defect_count", "downtime_minutes"],
        [[b["batch_id"], b["batch_end"], b["units_produced"], b["defect_count"], b["downtime_minutes"]] for b in batches],
    )

    # SensorReading: static identity in LH; the gauge columns as time-series in EH.
    sensors_capped = sensors[:SENSOR_EVENT_CAP]
    sensor_instance = _csv_bytes(
        ["reading_id", "machine_id", "production_line"],
        [[s["reading_id"], s["machine_id"], s["production_line"]] for s in sensors_capped],
    )
    sensor_events = _csv_bytes(
        ["reading_id", "timestamp_utc", "temperature", "pressure", "vibration", "humidity"],
        [[s["reading_id"], s["reading_timestamp"], s["temperature"], s["pressure"], s["vibration"], s["humidity"]] for s in sensors_capped],
    )

    # ── definition + binding CSVs ────────────────────────────────────────────
    entity_types_csv = _csv_bytes(
        ["EntityTypeName", "PropertyName", "PropertyDataType", "IsIdentifier", "IsDisplayName", "IsTimeseries"],
        [list(r) for r in ENTITY_TYPES],
    )
    relationship_types_csv = _csv_bytes(
        ["RelationshipName", "SourceEntityTypeName", "TargetEntityTypeName"],
        [list(r) for r in RELATIONSHIP_TYPES],
    )
    binding_entity_csv = _csv_bytes(
        ["EntityTypeName", "PropertyName", "PropertyDataType", "IsIdentifier", "IsDisplayName", "IsTimeseries",
         "SourceTableName", "BindingSourceColumnName", "DataBindingType", "SourceType", "TimestampColumnName",
         "ClusterUri", "DatabaseName", "WorkspaceId", "SourceItemId", "SourceSchema"],
        [list(r) + ["", "", "", "", ""] for r in BINDING_ENTITY],
    )
    binding_relationship_csv = _csv_bytes(
        ["RelationshipName", "SourceEntityTypeName", "TargetEntityTypeName", "SourceKeyColumnNames",
         "TargetKeyColumnNames", "SourceTableName", "WorkspaceId", "ItemId", "SourceSchema"],
        [list(r) + ["", "", ""] for r in BINDING_RELATIONSHIP],
    )

    # ── Zip it up as the .iq package ─────────────────────────────────────────
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("definition/entity_types.csv", entity_types_csv)
        z.writestr("definition/relationship_types.csv", relationship_types_csv)
        z.writestr("binding/binding_entity_types.csv", binding_entity_csv)
        z.writestr("binding/binding_relationship_types.csv", binding_relationship_csv)
        z.writestr("instance_data/machines.csv", machines_instance)
        z.writestr("instance_data/production_lines.csv", lines_instance)
        z.writestr("instance_data/production_batches.csv", batch_instance)
        z.writestr("instance_data/sensor_readings.csv", sensor_instance)
        z.writestr("events_data/production_batches.csv", batch_events)
        z.writestr("events_data/sensor_readings.csv", sensor_events)

    print(f"Wrote {OUT}")
    print(f"  Machines: {len(machines)}  Lines: {len(line_ids)}")
    print(f"  ProductionBatch: {len(batches)} static / {len(batches)} events")
    print(f"  SensorReading: {len(sensors_capped)} (capped from {len(sensors)})")


if __name__ == "__main__":
    build()
