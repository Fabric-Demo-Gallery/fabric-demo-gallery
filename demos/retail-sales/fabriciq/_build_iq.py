"""Build the retail Fabric IQ ontology package (`retail_ontology_package.iq`).

The `.iq` file is a ZIP with four parts the Fabric IQ accelerator wheel consumes:

    definition/entity_types.csv          ontology schema (entities + properties)
    definition/relationship_types.csv    named relationships between entities
    binding/binding_entity_types.csv     each property -> table + column (LH or Kusto)
    binding/binding_relationship_types.csv relationships -> source/target key columns
    instance_data/*.csv                  -> Lakehouse delta tables (static attributes)
    events_data/*.csv                    -> Eventhouse/Kusto tables (time-series)

It reuses the retail-sales demo's own CSVs (../data/*.csv) so the ontology is
backed by the same data the retail demo already ships — no parallel dataset.

Run:  python demos/retail-sales/fabriciq/_build_iq.py
Output: demos/retail-sales/fabriciq/retail_ontology_package.iq

Entities (4; Inventory + PosTransaction span Lakehouse + Eventhouse):
  Product        PK sku
  Store          PK store_id
  Inventory      PK inventory_id (= INV-{store_id}-{product_id}); FK product_id->sku, store_id
  PosTransaction PK transaction_id;                                FK product_id->sku, store_id
"""

from __future__ import annotations

import csv
import io
import os
import zipfile
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "retail_ontology_package.iq")

# Cap the time-series rows so the package stays small (the full POS file is ~130k rows).
POS_EVENT_CAP = 20000

# ── entity_types.csv rows ────────────────────────────────────────────────────
# (EntityTypeName, PropertyName, PropertyDataType, IsIdentifier, IsDisplayName, IsTimeseries)
ENTITY_TYPES = [
    # Product (Lakehouse only)
    ("Product", "ProductSku", "String", "TRUE", "FALSE", "FALSE"),
    ("Product", "ProductName", "String", "FALSE", "TRUE", "FALSE"),
    ("Product", "Category", "String", "FALSE", "FALSE", "FALSE"),
    ("Product", "Subcategory", "String", "FALSE", "FALSE", "FALSE"),
    ("Product", "Brand", "String", "FALSE", "FALSE", "FALSE"),
    ("Product", "UnitCost", "Double", "FALSE", "FALSE", "FALSE"),
    # Store (Lakehouse only)
    ("Store", "StoreId", "String", "TRUE", "FALSE", "FALSE"),
    ("Store", "StoreName", "String", "FALSE", "TRUE", "FALSE"),
    ("Store", "City", "String", "FALSE", "FALSE", "FALSE"),
    ("Store", "State", "String", "FALSE", "FALSE", "FALSE"),
    ("Store", "Region", "String", "FALSE", "FALSE", "FALSE"),
    ("Store", "StoreFormat", "String", "FALSE", "FALSE", "FALSE"),
    # Inventory (Lakehouse static + Eventhouse time-series)
    ("Inventory", "InventoryId", "String", "TRUE", "TRUE", "FALSE"),
    ("Inventory", "StoreId", "String", "FALSE", "FALSE", "FALSE"),
    ("Inventory", "ProductId", "String", "FALSE", "FALSE", "FALSE"),
    ("Inventory", "ReorderPoint", "BigInt", "FALSE", "FALSE", "FALSE"),
    ("Inventory", "QuantityOnHand", "BigInt", "FALSE", "FALSE", "TRUE"),
    ("Inventory", "QuantityOnOrder", "BigInt", "FALSE", "FALSE", "TRUE"),
    ("Inventory", "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE"),
    # PosTransaction (Lakehouse static + Eventhouse time-series)
    ("PosTransaction", "TransactionId", "String", "TRUE", "TRUE", "FALSE"),
    ("PosTransaction", "StoreId", "String", "FALSE", "FALSE", "FALSE"),
    ("PosTransaction", "ProductId", "String", "FALSE", "FALSE", "FALSE"),
    ("PosTransaction", "Quantity", "BigInt", "FALSE", "FALSE", "FALSE"),
    ("PosTransaction", "UnitPrice", "Double", "FALSE", "FALSE", "TRUE"),
    ("PosTransaction", "DiscountPercent", "Double", "FALSE", "FALSE", "TRUE"),
    ("PosTransaction", "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE"),
]

# ── relationship_types.csv rows ──────────────────────────────────────────────
# (RelationshipName, SourceEntityTypeName, TargetEntityTypeName)
RELATIONSHIP_TYPES = [
    ("InventoryForProduct", "Inventory", "Product"),
    ("InventoryAtStore", "Inventory", "Store"),
    ("TransactionForProduct", "PosTransaction", "Product"),
    ("TransactionAtStore", "PosTransaction", "Store"),
]

# ── binding_entity_types.csv rows ────────────────────────────────────────────
# Each property -> a (table, column) in either a Lakehouse table (NonTimeSeries)
# or a Kusto table (TimeSeries, with a TimestampColumnName).
# (EntityType, Property, DataType, IsId, IsDisplay, IsTimeseries,
#  SourceTableName, BindingSourceColumnName, DataBindingType, SourceType, TimestampColumnName)
BINDING_ENTITY = [
    # Product -> lakehouse table "products"
    ("Product", "ProductSku", "String", "TRUE", "FALSE", "FALSE", "products", "sku", "NonTimeSeries", "LakehouseTable", ""),
    ("Product", "ProductName", "String", "FALSE", "TRUE", "FALSE", "products", "product_name", "NonTimeSeries", "LakehouseTable", ""),
    ("Product", "Category", "String", "FALSE", "FALSE", "FALSE", "products", "category", "NonTimeSeries", "LakehouseTable", ""),
    ("Product", "Subcategory", "String", "FALSE", "FALSE", "FALSE", "products", "subcategory", "NonTimeSeries", "LakehouseTable", ""),
    ("Product", "Brand", "String", "FALSE", "FALSE", "FALSE", "products", "brand", "NonTimeSeries", "LakehouseTable", ""),
    ("Product", "UnitCost", "Double", "FALSE", "FALSE", "FALSE", "products", "unit_cost", "NonTimeSeries", "LakehouseTable", ""),
    # Store -> lakehouse table "stores"
    ("Store", "StoreId", "String", "TRUE", "FALSE", "FALSE", "stores", "store_id", "NonTimeSeries", "LakehouseTable", ""),
    ("Store", "StoreName", "String", "FALSE", "TRUE", "FALSE", "stores", "store_name", "NonTimeSeries", "LakehouseTable", ""),
    ("Store", "City", "String", "FALSE", "FALSE", "FALSE", "stores", "city", "NonTimeSeries", "LakehouseTable", ""),
    ("Store", "State", "String", "FALSE", "FALSE", "FALSE", "stores", "state", "NonTimeSeries", "LakehouseTable", ""),
    ("Store", "Region", "String", "FALSE", "FALSE", "FALSE", "stores", "region", "NonTimeSeries", "LakehouseTable", ""),
    ("Store", "StoreFormat", "String", "FALSE", "FALSE", "FALSE", "stores", "store_format", "NonTimeSeries", "LakehouseTable", ""),
    # Inventory static -> lakehouse table "inventory"
    ("Inventory", "InventoryId", "String", "TRUE", "TRUE", "FALSE", "inventory", "inventory_id", "NonTimeSeries", "LakehouseTable", ""),
    ("Inventory", "StoreId", "String", "FALSE", "FALSE", "FALSE", "inventory", "store_id", "NonTimeSeries", "LakehouseTable", ""),
    ("Inventory", "ProductId", "String", "FALSE", "FALSE", "FALSE", "inventory", "product_id", "NonTimeSeries", "LakehouseTable", ""),
    ("Inventory", "ReorderPoint", "BigInt", "FALSE", "FALSE", "FALSE", "inventory", "reorder_point", "NonTimeSeries", "LakehouseTable", ""),
    # Inventory time-series -> kusto table "inventory"
    ("Inventory", "QuantityOnHand", "BigInt", "FALSE", "FALSE", "TRUE", "inventory", "quantity_on_hand", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("Inventory", "QuantityOnOrder", "BigInt", "FALSE", "FALSE", "TRUE", "inventory", "quantity_on_order", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("Inventory", "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE", "inventory", "timestamp_utc", "TimeSeries", "KustoTable", "timestamp_utc"),
    # Inventory identifier re-bound to the kusto table (join key for events rows)
    ("Inventory", "InventoryId", "String", "FALSE", "FALSE", "TRUE", "inventory", "inventory_id", "TimeSeries", "KustoTable", "timestamp_utc"),
    # PosTransaction static -> lakehouse table "pos_transactions"
    ("PosTransaction", "TransactionId", "String", "TRUE", "TRUE", "FALSE", "pos_transactions", "transaction_id", "NonTimeSeries", "LakehouseTable", ""),
    ("PosTransaction", "StoreId", "String", "FALSE", "FALSE", "FALSE", "pos_transactions", "store_id", "NonTimeSeries", "LakehouseTable", ""),
    ("PosTransaction", "ProductId", "String", "FALSE", "FALSE", "FALSE", "pos_transactions", "product_id", "NonTimeSeries", "LakehouseTable", ""),
    ("PosTransaction", "Quantity", "BigInt", "FALSE", "FALSE", "FALSE", "pos_transactions", "quantity", "NonTimeSeries", "LakehouseTable", ""),
    # PosTransaction time-series -> kusto table "pos_transactions"
    ("PosTransaction", "UnitPrice", "Double", "FALSE", "FALSE", "TRUE", "pos_transactions", "unit_price", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("PosTransaction", "DiscountPercent", "Double", "FALSE", "FALSE", "TRUE", "pos_transactions", "discount_pct", "TimeSeries", "KustoTable", "timestamp_utc"),
    ("PosTransaction", "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE", "pos_transactions", "timestamp_utc", "TimeSeries", "KustoTable", "timestamp_utc"),
    # PosTransaction identifier re-bound to the kusto table (join key for events rows)
    ("PosTransaction", "TransactionId", "String", "FALSE", "FALSE", "TRUE", "pos_transactions", "transaction_id", "TimeSeries", "KustoTable", "timestamp_utc"),
]

# ── binding_relationship_types.csv rows ──────────────────────────────────────
# (RelationshipName, Source, Target, SourceKeyColumnNames, TargetKeyColumnNames, SourceTableName)
# Mirrors the official sample: SourceKey = the SOURCE entity's identifier column,
# TargetKey = the FK column (in the SAME source table) that points to the target
# entity's identity. BOTH columns live in SourceTableName.
BINDING_RELATIONSHIP = [
    ("InventoryForProduct", "Inventory", "Product", "inventory_id", "product_id", "inventory"),
    ("InventoryAtStore", "Inventory", "Store", "inventory_id", "store_id", "inventory"),
    ("TransactionForProduct", "PosTransaction", "Product", "transaction_id", "product_id", "pos_transactions"),
    ("TransactionAtStore", "PosTransaction", "Store", "transaction_id", "store_id", "pos_transactions"),
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
    # ── Read the retail demo's own data ──────────────────────────────────────
    _, products = _read_csv("products.csv")
    _, stores = _read_csv("stores.csv")
    _, inv_snaps = _read_csv("inventory_snapshots.csv")
    _, pos = _read_csv("pos_transactions.csv")

    # instance_data: products (static, columns kept as-is)
    products_instance = _csv_bytes(
        ["sku", "product_name", "category", "subcategory", "brand", "unit_cost"],
        [[p["sku"], p["product_name"], p["category"], p["subcategory"], p["brand"], p["unit_cost"]] for p in products],
    )

    # instance_data: stores (static)
    stores_instance = _csv_bytes(
        ["store_id", "store_name", "city", "state", "region", "store_format"],
        [[s["store_id"], s["store_name"], s["city"], s["state"], s["region"], s["store_format"]] for s in stores],
    )

    # Inventory: collapse snapshots to one static row per (store_id, product_id);
    # emit every snapshot as a time-series row keyed by the synthesized inventory_id.
    inv_static: "OrderedDict[str, list]" = OrderedDict()
    inv_events: list[list] = []
    for row in inv_snaps:
        store_id, product_id = row["store_id"], row["product_id"]
        inv_id = f"INV-{store_id}-{product_id}"
        if inv_id not in inv_static:
            inv_static[inv_id] = [inv_id, store_id, product_id, row["reorder_point"]]
        inv_events.append([inv_id, row["snapshot_date"], row["quantity_on_hand"], row["quantity_on_order"]])

    inventory_instance = _csv_bytes(
        ["inventory_id", "store_id", "product_id", "reorder_point"],
        list(inv_static.values()),
    )
    inventory_events = _csv_bytes(
        ["inventory_id", "timestamp_utc", "quantity_on_hand", "quantity_on_order"],
        inv_events,
    )

    # PosTransaction: static identity in LH; price/discount as time-series in EH.
    pos_capped = pos[:POS_EVENT_CAP]
    pos_instance = _csv_bytes(
        ["transaction_id", "store_id", "product_id", "quantity"],
        [[t["transaction_id"], t["store_id"], t["product_id"], t["quantity"]] for t in pos_capped],
    )
    pos_events = _csv_bytes(
        ["transaction_id", "timestamp_utc", "unit_price", "discount_pct"],
        [[t["transaction_id"], t["transaction_timestamp"], t["unit_price"], t["discount_pct"]] for t in pos_capped],
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
        z.writestr("instance_data/products.csv", products_instance)
        z.writestr("instance_data/stores.csv", stores_instance)
        z.writestr("instance_data/inventory.csv", inventory_instance)
        z.writestr("instance_data/pos_transactions.csv", pos_instance)
        z.writestr("events_data/inventory.csv", inventory_events)
        z.writestr("events_data/pos_transactions.csv", pos_events)

    print(f"Wrote {OUT}")
    print(f"  Products: {len(products)}  Stores: {len(stores)}")
    print(f"  Inventory: {len(inv_static)} static / {len(inv_events)} events")
    print(f"  PosTransaction: {len(pos_capped)} (capped from {len(pos)})")


if __name__ == "__main__":
    build()
