"""Build the transportation Fabric IQ ontology package.

Entities (4; Delivery, FuelLog span Lakehouse + Eventhouse):
  Vehicle   PK vehicle_id
  Route     PK route_id
  Delivery  PK delivery_id;  FK vehicle_id, route_id   (dual)
  FuelLog   PK log_id;       FK vehicle_id              (dual)
"""

from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_scenarios"))
from fabriciq_common import Entity, Prop, write_iq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "transportation_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Vehicle", "vehicles", [
        Prop("VehicleId", "vehicle_id", "String", ident=True, display=True),
        Prop("VehicleType", "vehicle_type"),
        Prop("Depot", "depot"),
        Prop("CapacityTonnes", "capacity_tonnes", "Double"),
        Prop("YearRegistered", "year_registered", "BigInt"),
        Prop("Status", "status"),
        Prop("DriverId", "driver_id"),
    ]),
    Entity("Route", "routes", [
        Prop("RouteId", "route_id", "String", ident=True, display=True),
        Prop("Origin", "origin"),
        Prop("Destination", "destination"),
        Prop("DistanceKm", "distance_km", "Double"),
        Prop("RouteType", "route_type"),
        Prop("SlaHours", "sla_hours", "Double"),
        Prop("TollCostGbp", "toll_cost_gbp", "Double"),
    ]),
    Entity("Delivery", "deliveries", [
        Prop("DeliveryId", "delivery_id", "String", ident=True, display=True),
        Prop("VehicleId", "vehicle_id"),
        Prop("RouteId", "route_id"),
        Prop("Status", "status"),
        Prop("IsLate", "is_late", "BigInt"),
        Prop("ActualDurationHrs", "actual_duration_hrs", "Double", ts=True),
        Prop("DelayHrs", "delay_hrs", "Double", ts=True),
        Prop("LoadTonnes", "load_tonnes", "Double", ts=True),
    ]),
    Entity("FuelLog", "fuel_logs", [
        Prop("LogId", "log_id", "String", ident=True, display=True),
        Prop("VehicleId", "vehicle_id"),
        Prop("Depot", "depot"),
        Prop("FuelType", "fuel_type"),
        Prop("OdometerKm", "odometer_km", "BigInt", ts=True),
        Prop("LitresFilled", "litres_filled", "Double", ts=True),
        Prop("TotalCostGbp", "total_cost_gbp", "Double", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("DeliveryByVehicle", "Delivery", "Vehicle"),
    ("DeliveryOnRoute", "Delivery", "Route"),
    ("FuelLogForVehicle", "FuelLog", "Vehicle"),
]
BINDING_RELATIONSHIP = [
    ("DeliveryByVehicle", "Delivery", "Vehicle", "delivery_id", "vehicle_id", "deliveries"),
    ("DeliveryOnRoute", "Delivery", "Route", "delivery_id", "route_id", "deliveries"),
    ("FuelLogForVehicle", "FuelLog", "Vehicle", "log_id", "vehicle_id", "fuel_logs"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    vehicles = _read("vehicles.csv")
    routes = _read("routes.csv")
    deliveries = _read("deliveries.csv")
    fuel = _read("fuel_logs.csv")

    deliveries_c = deliveries[:EVENT_CAP]
    fuel_c = fuel[:EVENT_CAP]

    instance_tables = {
        "vehicles": (["vehicle_id", "vehicle_type", "depot", "capacity_tonnes", "year_registered", "status", "driver_id"],
                     [[r["vehicle_id"], r["vehicle_type"], r["depot"], r["capacity_tonnes"], r["year_registered"], r["status"], r["driver_id"]] for r in vehicles]),
        "routes": (["route_id", "origin", "destination", "distance_km", "route_type", "sla_hours", "toll_cost_gbp"],
                   [[r["route_id"], r["origin"], r["destination"], r["distance_km"], r["route_type"], r["sla_hours"], r["toll_cost_gbp"]] for r in routes]),
        "deliveries": (["delivery_id", "vehicle_id", "route_id", "status", "is_late"],
                       [[r["delivery_id"], r["vehicle_id"], r["route_id"], r["status"], r["is_late"]] for r in deliveries_c]),
        "fuel_logs": (["log_id", "vehicle_id", "depot", "fuel_type"],
                      [[r["log_id"], r["vehicle_id"], r["depot"], r["fuel_type"]] for r in fuel_c]),
    }
    events_tables = {
        "deliveries": (["delivery_id", "timestamp_utc", "actual_duration_hrs", "delay_hrs", "load_tonnes"],
                       [[r["delivery_id"], r["actual_arrival"], r["actual_duration_hrs"], r["delay_hrs"], r["load_tonnes"]] for r in deliveries_c]),
        "fuel_logs": (["log_id", "timestamp_utc", "odometer_km", "litres_filled", "total_cost_gbp"],
                      [[r["log_id"], r["log_date"], r["odometer_km"], r["litres_filled"], r["total_cost_gbp"]] for r in fuel_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Vehicles: {len(vehicles)}  Routes: {len(routes)}  Deliveries: {len(deliveries_c)}  FuelLogs: {len(fuel_c)}")


if __name__ == "__main__":
    build()
