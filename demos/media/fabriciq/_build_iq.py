"""Build the media Fabric IQ ontology package.

Entities (4; ViewingEvent, AdImpression span Lakehouse + Eventhouse):
  Content       PK content_id
  Subscriber    PK subscriber_id
  ViewingEvent  PK view_id;        FK subscriber_id, content_id   (dual)
  AdImpression  PK impression_id;  FK content_id                  (dual)
"""

from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_scenarios"))
from fabriciq_common import Entity, Prop, write_iq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "media_ontology_package.iq")
EVENT_CAP = 20000

ENTITIES = [
    Entity("Content", "content", [
        Prop("ContentId", "content_id", "String", ident=True, display=True),
        Prop("Title", "title"),
        Prop("Genre", "genre"),
        Prop("ContentType", "content_type"),
        Prop("ReleaseYear", "release_year", "BigInt"),
        Prop("DurationMins", "duration_mins", "BigInt"),
        Prop("ProductionCostBucket", "production_cost_bucket"),
        Prop("Language", "language"),
    ]),
    Entity("Subscriber", "subscribers", [
        Prop("SubscriberId", "subscriber_id", "String", ident=True, display=True),
        Prop("PlanType", "plan_type"),
        Prop("Region", "region"),
        Prop("AgeGroup", "age_group"),
        Prop("PaymentMethod", "payment_method"),
        Prop("MonthlyFee", "monthly_fee", "Double"),
        Prop("IsChurned", "is_churned", "BigInt"),
    ]),
    Entity("ViewingEvent", "viewing_history", [
        Prop("ViewId", "view_id", "String", ident=True, display=True),
        Prop("SubscriberId", "subscriber_id"),
        Prop("ContentId", "content_id"),
        Prop("DeviceType", "device_type"),
        Prop("IsCompleted", "is_completed", "BigInt"),
        Prop("WatchDurationMins", "watch_duration_mins", "Double", ts=True),
        Prop("Rating", "rating", "BigInt", ts=True),
    ]),
    Entity("AdImpression", "ad_impressions", [
        Prop("ImpressionId", "impression_id", "String", ident=True, display=True),
        Prop("ContentId", "content_id"),
        Prop("AdType", "ad_type"),
        Prop("Impressions", "impressions", "BigInt", ts=True),
        Prop("Clicks", "clicks", "BigInt", ts=True),
        Prop("RevenueUsd", "revenue_usd", "Double", ts=True),
        Prop("Cpm", "cpm", "Double", ts=True),
    ]),
]

RELATIONSHIP_TYPES = [
    ("ViewBySubscriber", "ViewingEvent", "Subscriber"),
    ("ViewOfContent", "ViewingEvent", "Content"),
    ("AdForContent", "AdImpression", "Content"),
]
BINDING_RELATIONSHIP = [
    ("ViewBySubscriber", "ViewingEvent", "Subscriber", "view_id", "subscriber_id", "viewing_history"),
    ("ViewOfContent", "ViewingEvent", "Content", "view_id", "content_id", "viewing_history"),
    ("AdForContent", "AdImpression", "Content", "impression_id", "content_id", "ad_impressions"),
]


def _read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build():
    content = _read("content_catalog.csv")
    subs = _read("subscribers.csv")
    views = _read("viewing_history.csv")
    ads = _read("ad_impressions.csv")

    views_c = views[:EVENT_CAP]
    ads_c = ads[:EVENT_CAP]

    instance_tables = {
        "content": (["content_id", "title", "genre", "content_type", "release_year", "duration_mins", "production_cost_bucket", "language"],
                    [[r["content_id"], r["title"], r["genre"], r["content_type"], r["release_year"], r["duration_mins"], r["production_cost_bucket"], r["language"]] for r in content]),
        "subscribers": (["subscriber_id", "plan_type", "region", "age_group", "payment_method", "monthly_fee", "is_churned"],
                        [[r["subscriber_id"], r["plan_type"], r["region"], r["age_group"], r["payment_method"], r["monthly_fee"], r["is_churned"]] for r in subs]),
        "viewing_history": (["view_id", "subscriber_id", "content_id", "device_type", "is_completed"],
                            [[r["view_id"], r["subscriber_id"], r["content_id"], r["device_type"], r["is_completed"]] for r in views_c]),
        "ad_impressions": (["impression_id", "content_id", "ad_type"],
                           [[r["impression_id"], r["content_id"], r["ad_type"]] for r in ads_c]),
    }
    events_tables = {
        "viewing_history": (["view_id", "timestamp_utc", "watch_duration_mins", "rating"],
                            [[r["view_id"], r["view_date"], r["watch_duration_mins"], r["rating"]] for r in views_c]),
        "ad_impressions": (["impression_id", "timestamp_utc", "impressions", "clicks", "revenue_usd", "cpm"],
                           [[r["impression_id"], r["ad_date"], r["impressions"], r["clicks"], r["revenue_usd"], r["cpm"]] for r in ads_c]),
    }

    write_iq(OUT, ENTITIES, RELATIONSHIP_TYPES, BINDING_RELATIONSHIP, instance_tables, events_tables)
    print(f"  Content: {len(content)}  Subscribers: {len(subs)}  Views: {len(views_c)}  Ads: {len(ads_c)}")


if __name__ == "__main__":
    build()
