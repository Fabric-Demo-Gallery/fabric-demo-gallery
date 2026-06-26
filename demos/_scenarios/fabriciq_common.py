"""Shared helpers for building per-industry Fabric IQ ontology packages (`*.iq`).

Each industry's `demos/<industry>/fabriciq/_build_iq.py` defines its ontology
spec with the compact ``Entity``/``Prop`` model below, shapes its own data, then
calls ``write_iq`` to emit the ZIP in the exact structure the Fabric IQ
accelerator wheel expects (validated against the official samples/*.iq).

The .iq ZIP layout:
    definition/entity_types.csv
    definition/relationship_types.csv
    binding/binding_entity_types.csv
    binding/binding_relationship_types.csv
    instance_data/<table>.csv   -> Lakehouse delta tables (static attributes)
    events_data/<table>.csv     -> Eventhouse/Kusto tables (time-series)

Key rules baked in (validated against the working samples):
  * Every time-series entity gets a ``TimestampUtc`` DateTime property
    (IsTimeseries=TRUE) bound to the kusto ``timestamp_utc`` column — added
    automatically by ``Entity`` when any property is time-series.
  * Dual-source entities re-bind their identifier column to the kusto table
    (IsIdentifier=FALSE, IsTimeseries=TRUE) so events carry the join key —
    also added automatically.
  * Relationship bindings use (source_identifier_col, fk_col_in_source_table,
    source_table) — BOTH key columns live in the source table.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field

ENTITY_HEADER = [
    "EntityTypeName", "PropertyName", "PropertyDataType",
    "IsIdentifier", "IsDisplayName", "IsTimeseries",
]
REL_HEADER = ["RelationshipName", "SourceEntityTypeName", "TargetEntityTypeName"]
BINDING_ENTITY_HEADER = [
    "EntityTypeName", "PropertyName", "PropertyDataType", "IsIdentifier", "IsDisplayName", "IsTimeseries",
    "SourceTableName", "BindingSourceColumnName", "DataBindingType", "SourceType", "TimestampColumnName",
    "ClusterUri", "DatabaseName", "WorkspaceId", "SourceItemId", "SourceSchema",
]
BINDING_REL_HEADER = [
    "RelationshipName", "SourceEntityTypeName", "TargetEntityTypeName",
    "SourceKeyColumnNames", "TargetKeyColumnNames", "SourceTableName", "WorkspaceId", "ItemId", "SourceSchema",
]


def _b(v: bool) -> str:
    return "TRUE" if v else "FALSE"


@dataclass
class Prop:
    """One ontology property. ``name`` is the PascalCase ontology property name,
    ``col`` the source column name, ``dtype`` one of
    String/Boolean/DateTime/BigInt/Double. ``ts`` marks a time-series column
    (lives in the eventhouse/kusto table)."""
    name: str
    col: str
    dtype: str = "String"
    ident: bool = False
    display: bool = False
    ts: bool = False


@dataclass
class Entity:
    """An ontology entity. ``lh_table`` is the lakehouse (static) source table;
    ``ts_table`` defaults to ``lh_table`` (dual-source entities share a logical
    table name across instance_data/ and events_data/)."""
    name: str
    lh_table: str
    props: list = field(default_factory=list)
    ts_table: str | None = None

    def __post_init__(self):
        if self.ts_table is None:
            self.ts_table = self.lh_table
        self.ident = next((p for p in self.props if p.ident), self.props[0])

    @property
    def has_ts(self) -> bool:
        return any(p.ts for p in self.props)

    def entity_rows(self) -> list[list]:
        rows = [[self.name, p.name, p.dtype, _b(p.ident), _b(p.display), _b(p.ts)] for p in self.props]
        if self.has_ts:
            rows.append([self.name, "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE"])
        return rows

    def binding_rows(self) -> list[list]:
        rows = []
        for p in self.props:
            if p.ts:
                rows.append([self.name, p.name, p.dtype, _b(p.ident), _b(p.display), "TRUE",
                             self.ts_table, p.col, "TimeSeries", "KustoTable", "timestamp_utc"])
            else:
                rows.append([self.name, p.name, p.dtype, _b(p.ident), _b(p.display), "FALSE",
                             self.lh_table, p.col, "NonTimeSeries", "LakehouseTable", ""])
        if self.has_ts:
            rows.append([self.name, "TimestampUtc", "DateTime", "FALSE", "FALSE", "TRUE",
                         self.ts_table, "timestamp_utc", "TimeSeries", "KustoTable", "timestamp_utc"])
            rows.append([self.name, self.ident.name, self.ident.dtype, "FALSE", "FALSE", "TRUE",
                         self.ts_table, self.ident.col, "TimeSeries", "KustoTable", "timestamp_utc"])
        return rows


def csv_bytes(header: list[str], rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def write_iq(
    out_path: str,
    entities: list,              # list[Entity]
    relationship_types: list,    # rows of 3: (RelName, SourceEntity, TargetEntity)
    binding_relationship: list,  # rows of 6: (RelName, Src, Tgt, SrcKeyCol, FkColInSrcTable, SrcTable)
    instance_tables: dict,       # {table_name: (header_list, rows)}
    events_tables: dict,         # {table_name: (header_list, rows)}
) -> None:
    entity_rows, binding_entity_rows = [], []
    for e in entities:
        entity_rows.extend(e.entity_rows())
        binding_entity_rows.extend(e.binding_rows())

    entity_csv = csv_bytes(ENTITY_HEADER, entity_rows)
    rel_csv = csv_bytes(REL_HEADER, [list(r) for r in relationship_types])
    binding_entity_csv = csv_bytes(BINDING_ENTITY_HEADER, [list(r) + ["", "", "", "", ""] for r in binding_entity_rows])
    binding_rel_csv = csv_bytes(BINDING_REL_HEADER, [list(r) + ["", "", ""] for r in binding_relationship])

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("definition/entity_types.csv", entity_csv)
        z.writestr("definition/relationship_types.csv", rel_csv)
        z.writestr("binding/binding_entity_types.csv", binding_entity_csv)
        z.writestr("binding/binding_relationship_types.csv", binding_rel_csv)
        for tname, (header, rows) in instance_tables.items():
            z.writestr(f"instance_data/{tname}.csv", csv_bytes(header, rows))
        for tname, (header, rows) in events_tables.items():
            z.writestr(f"events_data/{tname}.csv", csv_bytes(header, rows))
    print(f"Wrote {out_path}")
