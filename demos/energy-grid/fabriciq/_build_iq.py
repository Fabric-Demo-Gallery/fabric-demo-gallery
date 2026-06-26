"""Build the energy-grid Fabric IQ ontology package.

Entities (5; GridSensor, PowerEvent, RenewableReading span Lakehouse + Eventhouse):
  Substation       PK substation_id  (derived from distinct substation_id)
  GridSensor       PK reading_id;  FK substation_id   (dual)
  PowerEvent       PK event_id;    FK substation_id   (dual)
  GenerationPlant  PK plant_id     (derived from distinct plant_id)
  RenewableReading PK reading_id;  FK plant_id         (dual)
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
OUT = os.path.join(HERE, "energy_grid_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Substation", "substations", [
        Prop("SubstationId", "substation_id", "String", ident=True, display=True),
        Prop("Region", "region"),
    ]),
    Entity("GridSensor", "grid_sensors", [
        Prop("ReadingId", "reading_id", "String", ident=True, display=True),
        Prop("SubstationId", "substation_id"),
        Prop("Region", "region"),
        Prop("VoltageV", "voltage_v", "Double", ts=True),
        Prop("FrequencyHz", "frequency_hz", "Double", ts=True),
        Prop("PowerFactor", "power_factor", "Double", ts=True),
        Prop("LoadMw", "load_mw", "Double", ts=True),
        Prop("TemperatureC", "temperature_c", "Double", ts=True),
    ]),
    Entity("PowerEvent", "power_events", [
        Prop("EventId", "event_id", "String", ident=True, display=True),
        Prop("SubstationId", "substation_id"),
        Prop("Region", "region"),
        Prop("EventType", "event_type"),
        Prop("Severity", "severity"),
        Prop("Resolved", "resolved", "Boolean"),
        Prop("DurationSec", "duration_sec", "BigInt", ts=True),
        Prop("AffectedCustomers", "affected_customers", "BigInt", ts=True),
    ]),
    Entity("GenerationPlant", "generation_plants", [
        Prop("PlantId", "plant_id", "String", ident=True, display=True),
        Prop("PlantType", "plant_type"),
        Prop("CapacityMw", "capacity_mw", "Double"),
    ]),
    Entity("RenewableReading", "renewable_generation", [
        Prop("ReadingId", "reading_id", "String", ident=True, display=True),
        Prop("PlantId", "plant_id"),
        Prop("Weather", "weather"),
        Prop("GenerationMw", "generation_mw", "Double", ts=True),
        Prop("CapacityFactor", "capacity_factor", "Double", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("GridSensorAtSubstation", "GridSensor", "Substation"),
    ("PowerEventAtSubstation", "PowerEvent", "Substation"),
    ("ReadingFromPlant", "RenewableReading", "GenerationPlant"),
]
BINDING_RELATIONSHIP = [
    ("GridSensorAtSubstation", "GridSensor", "Substation", "reading_id", "substation_id", "grid_sensors"),
    ("PowerEventAtSubstation", "PowerEvent", "Substation", "event_id", "substation_id", "power_events"),
    ("ReadingFromPlant", "RenewableReading", "GenerationPlant", "reading_id", "plant_id", "renewable_generation"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    sensors = _read("grid_sensors.csv")
    events = _read("power_events.csv")
    renew = _read("renewable_generation.csv")

    substations = OrderedDict()
    for r in sensors + events:
        substations.setdefault(r["substation_id"], r["region"])
    plants = OrderedDict()
    for r in renew:
        plants.setdefault(r["plant_id"], (r["plant_type"], r["capacity_mw"]))

    sensors_c = sensors[:EVENT_CAP]
    events_c = events[:EVENT_CAP]
    renew_c = renew[:EVENT_CAP]

    instance_tables = {
        "substations": (["substation_id", "region"], [[k, v] for k, v in substations.items()]),
        "grid_sensors": (["reading_id", "substation_id", "region"],
                         [[r["reading_id"], r["substation_id"], r["region"]] for r in sensors_c]),
        "power_events": (["event_id", "substation_id", "region", "event_type", "severity", "resolved"],
                         [[r["event_id"], r["substation_id"], r["region"], r["event_type"], r["severity"], r["resolved"]] for r in events_c]),
        "generation_plants": (["plant_id", "plant_type", "capacity_mw"],
                              [[k, v[0], v[1]] for k, v in plants.items()]),
        "renewable_generation": (["reading_id", "plant_id", "weather"],
                                 [[r["reading_id"], r["plant_id"], r["weather"]] for r in renew_c]),
    }
    events_tables = {
        "grid_sensors": (["reading_id", "timestamp_utc", "voltage_v", "frequency_hz", "power_factor", "load_mw", "temperature_c"],
                         [[r["reading_id"], r["timestamp"], r["voltage_v"], r["frequency_hz"], r["power_factor"], r["load_mw"], r["temperature_c"]] for r in sensors_c]),
        "power_events": (["event_id", "timestamp_utc", "duration_sec", "affected_customers"],
                         [[r["event_id"], r["timestamp"], r["duration_sec"], r["affected_customers"]] for r in events_c]),
        "renewable_generation": (["reading_id", "timestamp_utc", "generation_mw", "capacity_factor"],
                                 [[r["reading_id"], r["timestamp"], r["generation_mw"], r["capacity_factor"]] for r in renew_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Substations: {len(substations)}  Plants: {len(plants)}")
    print(f"  GridSensor: {len(sensors_c)}  PowerEvent: {len(events_c)}  RenewableReading: {len(renew_c)}")


if __name__ == "__main__":
    build()
