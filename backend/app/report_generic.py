"""Generic, schema-driven semantic model + report builders.

Used for any sector that does NOT ship a hand-authored ``tmdl/model.bim``. The
gold tables' schema is discovered from the lakehouse at deploy time and a
lightweight Direct Lake semantic model + a one-page overview report are generated
from it, so every sector gets a working model and report instead of a silent skip.

The model and the report are derived from the same ``_generic_plan`` so the report
can only reference columns and measures the model actually defines.
"""

import base64
import json

from app.report_builder import _textbox, _kpi_card, _bar, _table


# SQL Server types (as returned by FabricClient.discover_lakehouse_schema)
# mapped to TMDL/BIM dataTypes.
_SQL_TO_BIM_TYPE = {
    "varchar": "string", "nvarchar": "string", "char": "string", "nchar": "string",
    "string": "string", "text": "string", "uniqueidentifier": "string",
    "bigint": "int64", "int": "int64", "integer": "int64", "smallint": "int64", "tinyint": "int64",
    "float": "double", "real": "double", "double": "double",
    "decimal": "double", "numeric": "double", "money": "double",
    "datetime2": "dateTime", "datetime": "dateTime", "date": "dateTime", "timestamp": "dateTime",
    "bit": "boolean",
}


def _bim_type(sql_type: str) -> str:
    return _SQL_TO_BIM_TYPE.get((sql_type or "string").split("(")[0].strip().lower(), "string")


def _pretty_label(name: str) -> str:
    """gold_weekly_trends -> 'Weekly Trends'; total_revenue -> 'Total Revenue'."""
    for prefix in ("gold_ml_", "gold_", "dim_", "silver_", "bronze_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return " ".join(w.capitalize() for w in name.replace("_", " ").split()) or name


def _generic_plan(tables: dict) -> dict:
    """Given ``{table: [(col, sql_type), ...]}`` produce a per-table plan with BIM
    column types, categorised columns, and globally-unique measure names so the
    model and report stay in sync."""
    used: set[str] = set()

    def uniq(base: str) -> str:
        name, i = base, 2
        while name in used:
            name = f"{base} ({i})"
            i += 1
        used.add(name)
        return name

    def _rank(t: str) -> tuple:
        # gold first, then dims, then everything else; alpha within each group.
        return (0 if t.startswith("gold_") else 1 if t.startswith("dim_") else 2, t)

    plan: dict = {}
    for tname in sorted(tables.keys(), key=_rank):
        bim_cols = [(c, _bim_type(t)) for c, t in tables[tname]]
        numeric = [c for c, bt in bim_cols if bt in ("int64", "double")]
        strings = [c for c, bt in bim_cols if bt == "string"]
        label = _pretty_label(tname)
        count_measure = uniq(f"{label} Rows")
        sum_measures = [(uniq(f"Total {_pretty_label(c)}"), c) for c in numeric[:3]]
        plan[tname] = {
            "bim_cols": bim_cols, "numeric": numeric, "strings": strings,
            "label": label, "count_measure": count_measure, "sum_measures": sum_measures,
        }
    return plan


def build_generic_model_definition(tables: dict, sql_endpoint: str, lakehouse_name: str) -> dict:
    """Build a lightweight Direct Lake semantic model from discovered gold tables.

    Each table becomes a Direct Lake table with its columns plus a row-count
    measure and a SUM measure for up to three numeric columns. No relationships are
    inferred (kept intentionally simple and safe)."""
    plan = _generic_plan(tables)
    model_tables = []
    for tname, meta in plan.items():
        columns = [{"name": c, "dataType": bt, "sourceColumn": c} for c, bt in meta["bim_cols"]]
        measures = [{
            "name": meta["count_measure"],
            "expression": f"COUNTROWS('{tname}')",
            "formatString": "#,##0",
        }]
        for mname, col in meta["sum_measures"]:
            measures.append({
                "name": mname,
                "expression": f"SUM('{tname}'[{col}])",
                "formatString": "#,##0.00",
            })
        model_tables.append({
            "name": tname,
            "columns": columns,
            "measures": measures,
            "partitions": [{
                "name": tname,
                "mode": "directLake",
                "source": {"type": "entity", "entityName": tname, "schemaName": "dbo",
                           "expressionSource": "DatabaseQuery"},
            }],
        })

    model = {
        "compatibilityLevel": 1604,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "discourageImplicitMeasures": True,
            "expressions": [{
                "name": "DatabaseQuery",
                "kind": "m",
                "expression": (
                    'let\n    database = Sql.Database("' + sql_endpoint + '", "'
                    + lakehouse_name + '")\nin\n    database'
                ),
            }],
            "tables": model_tables,
        },
    }
    bim_encoded = base64.b64encode(json.dumps(model).encode("utf-8")).decode()
    pbism_encoded = base64.b64encode(json.dumps({"version": "1.0", "settings": {}}).encode("utf-8")).decode()
    return {
        "parts": [
            {"path": "model.bim", "payload": bim_encoded, "payloadType": "InlineBase64"},
            {"path": "definition.pbism", "payload": pbism_encoded, "payloadType": "InlineBase64"},
        ]
    }


def build_generic_report_definition(tables: dict, semantic_model_id: str, title: str) -> dict:
    """Build a one-page overview report over the generic model's gold tables.

    Visuals only reference columns and measures that ``build_generic_model_definition``
    is guaranteed to have created (both derive from the same ``_generic_plan``)."""
    plan = _generic_plan(tables)
    gold = [t for t in plan if t.startswith("gold_")] or list(plan.keys())

    visuals = [_textbox("g_title", 20, 5, 900, 35, title, "20")]

    # KPI cards: row-count per gold table (up to 6 across the top).
    x = 20
    for i, t in enumerate(gold[:6]):
        visuals.append(_kpi_card(f"g_kpi{i}", x, 45, t, plan[t]["count_measure"], plan[t]["label"]))
        x += 210

    # A bar chart from the first gold table that has both a category and a SUM measure.
    bar_added = False
    for t in gold:
        meta = plan[t]
        if meta["strings"] and meta["sum_measures"]:
            mname, mcol = meta["sum_measures"][0]
            visuals.append(_bar(
                "g_bar", 20, 155, 610, 270, t, meta["strings"][0], mname,
                f"{_pretty_label(mcol)} by {_pretty_label(meta['strings'][0])}"))
            bar_added = True
            break

    # A detail table for the first gold table (first 10 columns).
    t0 = gold[0]
    cols0 = [c for c, _ in plan[t0]["bim_cols"]][:10]
    if bar_added:
        visuals.append(_table("g_tbl", 645, 155, 615, 270, t0, cols0, f"{plan[t0]['label']} Detail"))
    else:
        visuals.append(_table("g_tbl", 20, 155, 1240, 270, t0, cols0, f"{plan[t0]['label']} Detail"))

    # A second detail table on the next row for the second gold table, if any.
    if len(gold) > 1:
        t1 = gold[1]
        cols1 = [c for c, _ in plan[t1]["bim_cols"]][:10]
        visuals.append(_table("g_tbl2", 20, 440, 1240, 260, t1, cols1, f"{plan[t1]['label']} Detail"))

    config = {
        "version": "5.54",
        "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}},
        "activeSectionIndex": 0,
        "defaultDrillFilterOtherVisuals": True,
    }
    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_overview", "displayName": "Overview", "displayOption": 2,
             "width": 1280, "height": 720, "visualContainers": visuals},
        ],
    })
    pbir = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={semantic_model_id}"}},
    })
    return {
        "parts": [
            {"path": "definition.pbir", "payload": base64.b64encode(pbir.encode()).decode(), "payloadType": "InlineBase64"},
            {"path": "report.json", "payload": base64.b64encode(report.encode()).decode(), "payloadType": "InlineBase64"},
        ]
    }
