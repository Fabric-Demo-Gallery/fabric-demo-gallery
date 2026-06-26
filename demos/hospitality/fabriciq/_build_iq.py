"""Build the hospitality Fabric IQ ontology package.

Entities (4; Booking, Review span Lakehouse + Eventhouse):
  Property  PK property_id
  Guest     PK guest_id
  Booking   PK booking_id;  FK property_id, guest_id            (dual)
  Review    PK review_id;   FK booking_id, property_id, guest_id (dual)
"""

from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_scenarios"))
from fabriciq_common import Entity, Prop, write_iq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "hospitality_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Property", "properties", [
        Prop("PropertyId", "property_id", "String", ident=True, display=True),
        Prop("PropertyName", "property_name"),
        Prop("City", "city"),
        Prop("Country", "country"),
        Prop("PropertyType", "property_type"),
        Prop("StarRating", "star_rating", "BigInt"),
        Prop("RoomCount", "room_count", "BigInt"),
    ]),
    Entity("Guest", "guests", [
        Prop("GuestId", "guest_id", "String", ident=True, display=True),
        Prop("LoyaltyTier", "loyalty_tier"),
        Prop("Region", "region"),
        Prop("AgeGroup", "age_group"),
        Prop("Nationality", "nationality"),
        Prop("TotalStays", "total_stays", "BigInt"),
        Prop("TotalSpend", "total_spend", "Double"),
        Prop("PreferredChannel", "preferred_channel"),
    ]),
    Entity("Booking", "bookings", [
        Prop("BookingId", "booking_id", "String", ident=True, display=True),
        Prop("PropertyId", "property_id"),
        Prop("GuestId", "guest_id"),
        Prop("RoomType", "room_type"),
        Prop("Channel", "channel"),
        Prop("MealPlan", "meal_plan"),
        Prop("Status", "status"),
        Prop("IsCancelled", "is_cancelled", "BigInt"),
        Prop("Nights", "nights", "BigInt", ts=True),
        Prop("RoomRate", "room_rate", "Double", ts=True),
        Prop("TotalAmount", "total_amount", "Double", ts=True),
        Prop("LeadTimeDays", "lead_time_days", "BigInt", ts=True),
    ]),
    Entity("Review", "reviews", [
        Prop("ReviewId", "review_id", "String", ident=True, display=True),
        Prop("BookingId", "booking_id"),
        Prop("PropertyId", "property_id"),
        Prop("GuestId", "guest_id"),
        Prop("Sentiment", "sentiment"),
        Prop("Platform", "platform"),
        Prop("OverallScore", "overall_score", "BigInt", ts=True),
        Prop("CleanlinessScore", "cleanliness_score", "BigInt", ts=True),
        Prop("ServiceScore", "service_score", "BigInt", ts=True),
        Prop("ValueScore", "value_score", "BigInt", ts=True),
        Prop("FoodScore", "food_score", "BigInt", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("BookingAtProperty", "Booking", "Property"),
    ("BookingByGuest", "Booking", "Guest"),
    ("ReviewForBooking", "Review", "Booking"),
    ("ReviewForProperty", "Review", "Property"),
    ("ReviewByGuest", "Review", "Guest"),
]
BINDING_RELATIONSHIP = [
    ("BookingAtProperty", "Booking", "Property", "booking_id", "property_id", "bookings"),
    ("BookingByGuest", "Booking", "Guest", "booking_id", "guest_id", "bookings"),
    ("ReviewForBooking", "Review", "Booking", "review_id", "booking_id", "reviews"),
    ("ReviewForProperty", "Review", "Property", "review_id", "property_id", "reviews"),
    ("ReviewByGuest", "Review", "Guest", "review_id", "guest_id", "reviews"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    props = _read("properties.csv")
    guests = _read("guests.csv")
    bookings = _read("bookings.csv")
    reviews = _read("reviews.csv")

    bookings_c = bookings[:EVENT_CAP]
    reviews_c = reviews[:EVENT_CAP]

    instance_tables = {
        "properties": (["property_id", "property_name", "city", "country", "property_type", "star_rating", "room_count"],
                       [[r["property_id"], r["property_name"], r["city"], r["country"], r["property_type"], r["star_rating"], r["room_count"]] for r in props]),
        "guests": (["guest_id", "loyalty_tier", "region", "age_group", "nationality", "total_stays", "total_spend", "preferred_channel"],
                   [[r["guest_id"], r["loyalty_tier"], r["region"], r["age_group"], r["nationality"], r["total_stays"], r["total_spend"], r["preferred_channel"]] for r in guests]),
        "bookings": (["booking_id", "property_id", "guest_id", "room_type", "channel", "meal_plan", "status", "is_cancelled"],
                     [[r["booking_id"], r["property_id"], r["guest_id"], r["room_type"], r["channel"], r["meal_plan"], r["status"], r["is_cancelled"]] for r in bookings_c]),
        "reviews": (["review_id", "booking_id", "property_id", "guest_id", "sentiment", "platform"],
                    [[r["review_id"], r["booking_id"], r["property_id"], r["guest_id"], r["sentiment"], r["platform"]] for r in reviews_c]),
    }
    events_tables = {
        "bookings": (["booking_id", "timestamp_utc", "nights", "room_rate", "total_amount", "lead_time_days"],
                     [[r["booking_id"], r["check_in_date"], r["nights"], r["room_rate"], r["total_amount"], r["lead_time_days"]] for r in bookings_c]),
        "reviews": (["review_id", "timestamp_utc", "overall_score", "cleanliness_score", "service_score", "value_score", "food_score"],
                    [[r["review_id"], r["review_date"], r["overall_score"], r["cleanliness_score"], r["service_score"], r["value_score"], r["food_score"]] for r in reviews_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Properties: {len(props)}  Guests: {len(guests)}  Bookings: {len(bookings_c)}  Reviews: {len(reviews_c)}")


if __name__ == "__main__":
    build()
