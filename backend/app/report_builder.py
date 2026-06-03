"""Power BI Report builder — generates a professional PBIR-Legacy report."""

import base64
import json


def _vc(name, x, y, w, h, visual_type, projections, proto_from, proto_select, title, sort=None, objects=None):
    """Build a visual container with proper config."""
    sv = {
        "visualType": visual_type,
        "projections": projections,
        "prototypeQuery": {
            "Version": 2,
            "From": proto_from,
            "Select": proto_select,
        },
        "vcObjects": {
            "title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                "fontSize": {"expr": {"Literal": {"Value": "12D"}}},
                "fontColor": {"expr": {"Literal": {"Value": "'#333333'"}}},
            }}],
        },
        "drillFilterOtherVisuals": True,
    }
    if sort:
        sv["prototypeQuery"]["OrderBy"] = sort
    if objects:
        sv["vcObjects"].update(objects)

    return {
        "x": x, "y": y, "z": 0, "width": w, "height": h,
        "config": json.dumps({
            "name": name,
            "singleVisual": sv,
        }),
        "filters": "[]",
    }


def _src(alias, entity):
    return {"Name": alias, "Entity": entity, "Type": 0}


def _col(alias, prop):
    return {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}}


def _meas(alias, prop):
    return {"Measure": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}}


def _sel_col(alias, entity, prop):
    return {**_col(alias, prop), "Name": f"{entity}.{prop}"}


def _sel_meas(alias, entity, prop):
    return {**_meas(alias, prop), "Name": f"{entity}.{prop}"}


def _card(name, x, y, w, h, entity, measure, title, color=None):
    a = "t"
    objs = {}
    if color:
        objs["labels"] = [{"properties": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}}]
    return _vc(name, x, y, w, h, "card",
        {"Values": [{"queryRef": f"{entity}.{measure}"}]},
        [_src(a, entity)],
        [_sel_meas(a, entity, measure)],
        title, objects=objs)


def _kpi_card(name, x, y, entity, measure, title, color="#0078D4"):
    return _card(name, x, y, 200, 100, entity, measure, title, color)


def _bar(name, x, y, w, h, entity, cat, meas, title, horiz=False):
    a = "t"
    vt = "clusteredBarChart" if horiz else "clusteredColumnChart"
    return _vc(name, x, y, w, h, vt,
        {"Category": [{"queryRef": f"{entity}.{cat}"}], "Y": [{"queryRef": f"{entity}.{meas}"}]},
        [_src(a, entity)],
        [_sel_col(a, entity, cat), _sel_meas(a, entity, meas)],
        title,
        sort=[{"Direction": 2, "Expression": _meas(a, meas)}])


def _multi_bar(name, x, y, w, h, entity, cat, measures, title, horiz=False):
    a = "t"
    vt = "clusteredBarChart" if horiz else "clusteredColumnChart"
    return _vc(name, x, y, w, h, vt,
        {"Category": [{"queryRef": f"{entity}.{cat}"}], "Y": [{"queryRef": f"{entity}.{m}"} for m in measures]},
        [_src(a, entity)],
        [_sel_col(a, entity, cat)] + [_sel_meas(a, entity, m) for m in measures],
        title)


def _donut(name, x, y, w, h, entity, cat, meas, title):
    a = "t"
    return _vc(name, x, y, w, h, "donutChart",
        {"Category": [{"queryRef": f"{entity}.{cat}"}], "Y": [{"queryRef": f"{entity}.{meas}"}]},
        [_src(a, entity)],
        [_sel_col(a, entity, cat), _sel_meas(a, entity, meas)],
        title)


def _line(name, x, y, w, h, entity, xcol, meas, title, series=None):
    a = "t"
    proj = {"Category": [{"queryRef": f"{entity}.{xcol}"}], "Y": [{"queryRef": f"{entity}.{meas}"}]}
    sel = [_sel_col(a, entity, xcol), _sel_meas(a, entity, meas)]
    if series:
        proj["Series"] = [{"queryRef": f"{entity}.{series}"}]
        sel.append(_sel_col(a, entity, series))
    return _vc(name, x, y, w, h, "lineChart", proj, [_src(a, entity)], sel, title)


def _table(name, x, y, w, h, entity, cols, title):
    a = "t"
    return _vc(name, x, y, w, h, "tableEx",
        {"Values": [{"queryRef": f"{entity}.{c}"} for c in cols]},
        [_src(a, entity)],
        [_sel_col(a, entity, c) for c in cols],
        title)


def _textbox(name, x, y, w, h, text, font_size="24", bold=True):
    weight = "bold" if bold else "normal"
    return {
        "x": x, "y": y, "z": 10000, "width": w, "height": h,
        "config": json.dumps({
            "name": name,
            "singleVisual": {
                "visualType": "textbox",
                "objects": {"general": [{"properties": {"paragraphs": {"expr": {"Literal": {"Value":
                    json.dumps([{"paragraphs": [{"textRuns": [{"value": text, "textStyle": {"fontWeight": weight, "fontSize": f"{font_size}px"}}]}]}])
                }}}}}]},
                "drillFilterOtherVisuals": True,
            },
        }),
        "filters": "[]",
    }


def build_manufacturing_report_definition(semantic_model_id: str) -> dict:
    P = "gold_production_daily_summary"
    E = "gold_equipment_health_daily"
    S = "gold_shift_performance"
    Q = "gold_product_quality"
    W = "gold_weekly_trends"
    L = "gold_line_scorecard"

    # ═══════════════════════════════════════════════════════════
    # PAGE 1: Executive Quality Overview
    # ═══════════════════════════════════════════════════════════
    p1 = [
        # Header
        _textbox("hdr1", 20, 5, 500, 35, "Manufacturing Quality Control", "20"),
        _textbox("sub1", 520, 12, 400, 25, "Executive Overview — 90 Day Analysis", "11", False),

        # Row 1: KPI Cards (5 across)
        _kpi_card("c_oee",     20,  45, P, "Avg OEE %",              "OEE",             "#0078D4"),
        _kpi_card("c_yield",  230,  45, P, "Avg Yield %",            "Yield",            "#107C10"),
        _kpi_card("c_units",  440,  45, P, "Total Units Produced",   "Total Production", "#5C2D91"),
        _kpi_card("c_defects",650,  45, P, "Total Defects",          "Defects",          "#D83B01"),
        _kpi_card("c_down",   860,  45, P, "Total Downtime (min)",   "Downtime (min)",   "#A4262C"),
        _card("c_batch", 1060, 45, 200, 100, P, "Batch Count",       "Batches",          "#004E8C"),

        # Row 2: OEE Trend + Donut charts
        _line("l_oee",     20, 155, 580, 250, P, "production_date", "Avg OEE %", "Daily OEE Trend by Production Line", "production_line"),
        _donut("d_class",  615, 155, 310, 250, P, "oee_class", "Batch Count", "OEE Classification Distribution"),
        _donut("d_health", 940, 155, 310, 250, E, "health_status", "Total Readings", "Equipment Health Status"),

        # Row 3: Bar charts
        _bar("b_shift",    20,  420, 400, 280, S, "shift", "Avg Units/Batch", "Output per Batch by Shift"),
        _bar("b_line",     435, 420, 400, 280, L, "production_line", "Overall OEE", "OEE by Production Line", True),
        _bar("b_weekly",   850, 420, 400, 280, W, "production_week", "Avg Weekly OEE", "Weekly OEE Trend"),
    ]

    # ═══════════════════════════════════════════════════════════
    # PAGE 2: Equipment Health & Reliability
    # ═══════════════════════════════════════════════════════════
    p2 = [
        _textbox("hdr2", 20, 5, 500, 35, "Equipment Health & Reliability", "20"),

        # KPI row
        _kpi_card("e_score",   20,  45, E, "Avg Health Score",       "Health Score",     "#107C10"),
        _kpi_card("e_anom",   230,  45, E, "Avg Anomaly Rate %",     "Anomaly Rate",     "#D83B01"),
        _kpi_card("e_reads",  440,  45, E, "Total Readings",         "Sensor Readings",  "#0078D4"),
        _kpi_card("e_temp",   650,  45, E, "Avg Temperature",        "Avg Temp (°)",     "#5C2D91"),
        _kpi_card("e_tanom",  860,  45, E, "Total Temp Anomalies",   "Temp Anomalies",   "#A4262C"),
        _card("e_vanom", 1060, 45, 200, 100, E, "Total Vibration Anomalies", "Vibr. Anomalies", "#004E8C"),

        # Charts row
        _line("e_trend",   20,  155, 620, 250, E, "reading_date", "Avg Health Score", "Health Score Trend by Line", "production_line"),
        _donut("e_dist",  655, 155, 290, 250, E, "health_status", "Total Readings", "Health Distribution"),
        _bar("e_mach",    960, 155, 290, 250, E, "machine_id", "Avg Anomaly Rate %", "Anomaly Rate by Machine", True),

        # Detail table
        _table("e_tbl", 20, 420, 1230, 280, E,
            ["reading_date", "machine_id", "production_line", "shift", "health_score", "health_status", "anomaly_rate", "avg_temperature", "avg_vibration", "temp_anomaly_count", "vibration_anomaly_count"],
            "Equipment Health Detail — All Machines"),
    ]

    # ═══════════════════════════════════════════════════════════
    # PAGE 3: Product Quality & Rankings
    # ═══════════════════════════════════════════════════════════
    p3 = [
        _textbox("hdr3", 20, 5, 500, 35, "Product Quality & Rankings", "20"),

        # KPI row
        _kpi_card("p_best",    20,  45, Q, "Best Yield",             "Best Product Yield","#107C10"),
        _kpi_card("p_prem",   230,  45, Q, "Premium Products",       "Premium Products",  "#0078D4"),
        _card("p_lines", 440, 45, 200, 100, L, "Total Lines",        "Production Lines",  "#5C2D91"),
        _card("p_boee",  650, 45, 200, 100, L, "Best Line OEE",      "Best Line OEE",     "#107C10"),
        _card("p_woee",  860, 45, 200, 100, L, "Worst Line OEE",     "Worst Line OEE",    "#A4262C"),
        _card("p_out",  1060, 45, 200, 100, L, "Daily Output",       "Avg Daily Output",  "#004E8C"),

        # Product quality table + bar
        _table("p_tbl", 20, 155, 650, 280, Q,
            ["quality_rank", "product", "avg_yield", "avg_defect_rate", "quality_tier", "total_units", "total_defects", "total_downtime", "lines_used"],
            "Product Quality Rankings"),
        _bar("p_bar", 685, 155, 565, 280, Q, "product", "Best Yield", "Yield by Product", True),

        # Line scorecard table
        _table("p_score", 20, 450, 1230, 250, L,
            ["production_line", "overall_oee", "overall_yield", "overall_defect_rate", "total_units_all_time", "total_defects_all_time", "total_downtime_all_time", "operating_days", "products_produced", "units_per_day"],
            "Production Line Scorecard — All-Time Performance"),
    ]

    # ═══════════════════════════════════════════════════════════
    # PAGE 4: Trends & Weekly Analysis
    # ═══════════════════════════════════════════════════════════
    p4 = [
        _textbox("hdr4", 20, 5, 500, 35, "Trends & Weekly Analysis", "20"),

        # Weekly trend charts
        _bar("w_units",    20,  50, 610, 300, W, "production_week", "Avg Weekly OEE", "Weekly Average OEE"),
        _table("w_tbl",   645,  50, 610, 300, W,
            ["production_week", "production_line", "weekly_units", "weekly_defects", "weekly_avg_oee", "weekly_downtime", "oee_wow_change", "trend_direction"],
            "Weekly Trend Detail with WoW Change"),

        # Shift comparison
        _multi_bar("s_bar", 20, 365, 610, 330, S, "shift", ["Avg Units/Batch", "Avg Defects/Batch"], "Shift Performance Comparison"),
        _table("s_tbl", 645, 365, 610, 330, S,
            ["shift", "production_line", "total_batches", "total_units", "total_defects", "avg_yield", "avg_defect_rate", "total_downtime", "days_active", "units_per_batch"],
            "Shift Performance Detail"),
    ]

    # ═══════════════════════════════════════════════════════════
    # Assemble report
    # ═══════════════════════════════════════════════════════════
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
            {"name": "pg_overview",  "displayName": "Quality Overview",       "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_equipment", "displayName": "Equipment Health",       "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_product",   "displayName": "Product Quality",        "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
            {"name": "pg_trends",    "displayName": "Trends & Weekly",        "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p4},
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


def build_retail_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for the retail sales demo."""

    S = "gold_sales_daily_summary"
    I = "gold_inventory_daily_summary"

    p1 = [
        _textbox("rh1", 20, 5, 500, 35, "Retail Sales & Inventory Analytics", "20"),
        _textbox("rs1", 520, 12, 400, 25, "Sales Overview — 90 Day Analysis", "11", False),
        _kpi_card("r_rev",     20,  45, S, "Total Revenue",          "Total Revenue",     "#0078D4"),
        _kpi_card("r_units",  230,  45, S, "Total Units Sold",       "Units Sold",        "#107C10"),
        _kpi_card("r_txn",   440,  45, S, "Transaction Count",       "Transactions",      "#5C2D91"),
        _kpi_card("r_basket", 650, 45, S, "Avg Basket Size",         "Avg Basket",        "#D83B01"),
        _kpi_card("r_margin", 860, 45, S, "Avg Margin %",            "Margin %",          "#107C10"),
        _card("r_gm", 1060, 45, 200, 100, S, "Gross Margin",         "Gross Margin",      "#004E8C"),
        _line("r_trend", 20, 155, 620, 260, S, "transaction_date", "Total Revenue", "Daily Revenue by Region", "region"),
        _donut("r_cat", 655, 155, 290, 260, S, "category", "Total Revenue", "Revenue by Category"),
        _donut("r_fmt", 955, 155, 295, 260, S, "store_format", "Total Revenue", "Revenue by Store Format"),
        _bar("r_region", 20, 430, 400, 270, S, "region", "Total Revenue", "Revenue by Region"),
        _bar("r_store", 435, 430, 400, 270, S, "store_name", "Total Revenue", "Top Stores by Revenue", True),
        _bar("r_subcat", 850, 430, 400, 270, S, "subcategory", "Total Units Sold", "Units by Subcategory", True),
    ]

    p2 = [
        _textbox("ih1", 20, 5, 500, 35, "Inventory & Stockout Risk", "20"),
        _kpi_card("i_onhand",  20,  45, I, "Total On Hand",          "On Hand",           "#0078D4"),
        _kpi_card("i_order",  230,  45, I, "Total On Order",         "On Order",          "#5C2D91"),
        _kpi_card("i_below",  440,  45, I, "Items Below Reorder",    "Below Reorder",     "#D83B01"),
        _kpi_card("i_risk",   650,  45, I, "Avg Stockout Risk %",    "Stockout Risk",     "#A4262C"),
        _kpi_card("i_sku",    860,  45, I, "Total SKUs",             "SKU Count",         "#107C10"),
        _bar("i_cat", 20, 155, 400, 260, I, "category", "Total On Hand", "Inventory by Category"),
        _donut("i_risk_d", 435, 155, 300, 260, I, "category", "Items Below Reorder", "Below Reorder by Category"),
        _bar("i_store", 750, 155, 500, 260, I, "store_id", "Avg Stockout Risk %", "Stockout Risk by Store", True),
        _table("i_tbl", 20, 430, 1230, 270, I,
            ["snapshot_date", "store_id", "category", "total_on_hand", "total_on_order", "items_below_reorder", "sku_count", "stockout_risk_pct"],
            "Inventory Detail"),
    ]

    p3 = [
        _textbox("mh1", 20, 5, 500, 35, "Margin & Basket Analysis", "20"),
        _kpi_card("m_gm",      20,  45, S, "Gross Margin",           "Gross Margin",      "#107C10"),
        _kpi_card("m_mpct",   230,  45, S, "Avg Margin %",           "Margin %",          "#0078D4"),
        _kpi_card("m_bask",   440,  45, S, "Avg Basket Size",        "Basket Size",       "#5C2D91"),
        _kpi_card("m_items",  650,  45, S, "Avg Items/Basket",       "Items/Basket",      "#D83B01"),
        _kpi_card("m_disc",   860,  45, S, "Avg Discount %",         "Avg Discount",      "#A4262C"),
        _card("m_cost", 1060, 45, 200, 100, S, "Total Cost",          "Total Cost",        "#004E8C"),
        _bar("m_cat", 20, 155, 400, 260, S, "category", "Gross Margin", "Margin by Category"),
        _bar("m_reg", 435, 155, 400, 260, S, "region", "Avg Margin %", "Margin % by Region"),
        _line("m_trend", 850, 155, 400, 260, S, "transaction_date", "Gross Margin", "Daily Margin Trend"),
        _table("m_tbl", 20, 430, 1230, 270, S,
            ["transaction_date", "store_name", "region", "category", "subcategory", "total_revenue", "total_cost", "gross_margin", "margin_pct", "avg_basket_size", "transaction_count"],
            "Sales Detail — Revenue, Cost & Margin"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_sales", "displayName": "Sales Overview", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_inv", "displayName": "Inventory & Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_margin", "displayName": "Margin & Basket", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_energy_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for the energy smart grid demo."""

    G = "gold_grid_health"
    O = "gold_outage_summary"
    R = "gold_renewable_summary"

    p1 = [
        _textbox("eh1", 20, 5, 500, 35, "Smart Grid Monitoring", "20"),
        _textbox("es1", 520, 12, 400, 25, "Grid Health Overview", "11", False),
        _kpi_card("e_volt",    20,  45, G, "Avg Voltage",        "Avg Voltage (V)",      "#0078D4"),
        _kpi_card("e_freq",   230,  45, G, "Avg Frequency",      "Frequency (Hz)",       "#107C10"),
        _kpi_card("e_load",   440,  45, G, "Avg Load MW",        "Avg Load (MW)",        "#5C2D91"),
        _kpi_card("e_anom",   650,  45, G, "Total Anomalies",    "Voltage Anomalies",    "#D83B01"),
        _kpi_card("e_pf",     860,  45, G, "Avg Power Factor",   "Power Factor",         "#107C10"),
        _card("e_score", 1060, 45, 200, 100, G, "Grid Health Score", "Health Score",      "#004E8C"),
        _line("e_vtrend", 20, 155, 620, 260, G, "date", "Avg Voltage", "Daily Avg Voltage by Region", "region"),
        _bar("e_sub_anom", 655, 155, 300, 260, G, "substation_id", "Total Anomalies", "Anomalies by Substation", True),
        _donut("e_region", 970, 155, 290, 260, G, "region", "Total Readings", "Readings by Region"),
        _line("e_ltrend", 20, 430, 620, 270, G, "date", "Avg Load MW", "Daily Load Trend by Region", "region"),
        _bar("e_hour_load", 655, 430, 300, 270, G, "hour", "Avg Load MW", "Avg Load by Hour"),
        _table("e_tbl", 970, 430, 290, 270, G, ["substation_id", "avg_voltage", "avg_frequency", "avg_load", "voltage_anomalies"], "Substation Details"),
    ]

    p2 = [
        _textbox("oh1", 20, 5, 500, 35, "Outage & Event Analysis", "20"),
        _textbox("os1", 520, 12, 400, 25, "Reliability Metrics", "11", False),
        _kpi_card("o_tot",     20,  45, O, "Total Events",             "Total Events",         "#0078D4"),
        _kpi_card("o_out",    230,  45, O, "Total Outages",            "Outages",              "#D83B01"),
        _kpi_card("o_cust",   440,  45, O, "Total Affected Customers", "Affected Customers",   "#A4262C"),
        _kpi_card("o_dur",    650,  45, O, "Avg Outage Duration Min",  "Avg Duration (min)",   "#5C2D91"),
        _kpi_card("o_crit",   860,  45, O, "Critical Events",          "Critical Events",      "#A4262C"),
        _card("o_saidi", 1060, 45, 200, 100, O, "SAIDI", "SAIDI Index",                        "#004E8C"),
        _line("o_trend", 20, 155, 620, 260, O, "date", "Total Events", "Daily Events by Region", "region"),
        _multi_bar("o_types", 655, 155, 300, 260, O, "region", ["outages", "surges", "sags", "faults"], "Event Types by Region"),
        _donut("o_reg", 970, 155, 290, 260, O, "region", "Total Outages", "Outages by Region"),
        _line("o_cust_trend", 20, 430, 620, 270, O, "date", "Total Affected Customers", "Affected Customers Trend"),
        _bar("o_dur_reg", 655, 430, 300, 270, O, "region", "Avg Outage Duration Min", "Avg Duration by Region"),
        _table("o_tbl", 970, 430, 290, 270, O, ["date", "region", "total_events", "outages", "total_affected", "critical_events"], "Daily Summary"),
    ]

    p3 = [
        _textbox("rh2", 20, 5, 500, 35, "Renewable Energy Performance", "20"),
        _textbox("rs2", 520, 12, 400, 25, "Solar, Wind & Hydro", "11", False),
        _kpi_card("r_gen",     20,  45, R, "Total Generation MW",  "Total Generation (MW)",   "#107C10"),
        _kpi_card("r_cap",    230,  45, R, "Total Capacity MW",    "Total Capacity (MW)",     "#0078D4"),
        _kpi_card("r_cf",     440,  45, R, "Avg Capacity Factor",  "Avg Capacity Factor",     "#5C2D91"),
        _kpi_card("r_util",   650,  45, R, "Utilization %",        "Utilization %",           "#D83B01"),
        _line("r_gen_trend", 20, 155, 620, 260, R, "date", "Total Generation MW", "Daily Generation by Type", "plant_type"),
        _bar("r_type_gen", 655, 155, 300, 260, R, "plant_type", "Total Generation MW", "Generation by Type"),
        _donut("r_type_cap", 970, 155, 290, 260, R, "plant_type", "Avg Capacity Factor", "Capacity Factor by Type"),
        _line("r_cf_trend", 20, 430, 620, 270, R, "date", "Avg Capacity Factor", "Capacity Factor Trend", "plant_type"),
        _table("r_tbl", 655, 430, 605, 270, R, ["date", "plant_type", "total_generation_mw", "avg_capacity_factor", "total_capacity_mw"], "Daily Renewable Summary"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_grid", "displayName": "Grid Health", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_outage", "displayName": "Outage Analysis", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_renewable", "displayName": "Renewable Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
        ],
    })

    pbir_e = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={semantic_model_id}"}},
    })

    return {
        "parts": [
            {"path": "definition.pbir", "payload": base64.b64encode(pbir_e.encode()).decode(), "payloadType": "InlineBase64"},
            {"path": "report.json", "payload": base64.b64encode(report.encode()).decode(), "payloadType": "InlineBase64"},
        ]
    }


def build_energy_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for the energy AI & ML (outage prediction) demo.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 — Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 600, 35, "Outage Prediction — Model Performance", "20"),
        _textbox("ms1", 620, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc",   20,  45, M, "Model AUC",       "AUC-ROC",        "#0078D4"),
        _kpi_card("m_acc",  230,  45, M, "Model Accuracy",  "Accuracy",       "#107C10"),
        _kpi_card("m_f1",   440,  45, M, "F1 Score",        "F1 Score",       "#5C2D91"),
        _kpi_card("m_feat", 650,  45, M, "Feature Count",   "Features Used",  "#004E8C"),
        _kpi_card("m_train",860,  45, M, "Training Rows",   "Training Rows",  "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows",      "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 — Outage Predictions
    p2 = [
        _textbox("ph1", 20, 5, 600, 35, "Outage Predictions", "20"),
        _textbox("ps1", 620, 12, 400, 25, "Per Substation-Day Scoring", "11", False),
        _kpi_card("p_tot",   20,  45, P, "Total Predictions",      "Scored Records",     "#0078D4"),
        _kpi_card("p_pred", 230,  45, P, "Predicted Outages",      "Predicted Outages",  "#D83B01"),
        _kpi_card("p_act",  440,  45, P, "Actual Outages",         "Actual Outages",     "#A4262C"),
        _kpi_card("p_prob", 650,  45, P, "Avg Outage Probability", "Avg Probability",    "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Outage Rate %", "Outage Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_region", 415, 155, 400, 260, P, "region", "Predicted Outages", "Predicted Outages by Region"),
        _donut("p_act_reg", 830, 155, 430, 260, P, "region", "Actual Outages", "Actual Outages by Region"),
        _line("p_trend", 20, 430, 795, 270, P, "sensor_date", "Avg Outage Probability", "Avg Outage Probability by Region", "region"),
        _table("p_tbl", 830, 430, 430, 270, P, ["substation_id", "region", "risk_level", "outage_probability", "predicted_outage", "had_outage"], "Prediction Detail"),
    ]

    # Page 3 — Substation Risk
    p3 = [
        _textbox("sh1", 20, 5, 600, 35, "Substation Risk Summary", "20"),
        _textbox("ss1", 620, 12, 400, 25, "Aggregated Risk by Substation", "11", False),
        _kpi_card("s_sub",   20,  45, S, "Substations",          "Substations",       "#0078D4"),
        _kpi_card("s_risk", 230,  45, S, "Avg Outage Risk",      "Avg Outage Risk",   "#5C2D91"),
        _kpi_card("s_rate", 440,  45, S, "Avg Outage Rate",      "Avg Outage Rate %", "#D83B01"),
        _kpi_card("s_days", 650,  45, S, "Predicted Outage Days","Predicted Days",    "#107C10"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Substations", "High Risk", "#A4262C"),
        _bar("s_bar", 20, 155, 760, 545, S, "substation_id", "Avg Outage Risk", "Avg Outage Risk by Substation", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Substations", "Substations by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["substation_id", "region", "overall_risk", "avg_outage_risk", "outage_rate", "predicted_outage_days"], "Substation Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Outage Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Substation Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
        ],
    })

    pbir_ml = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={semantic_model_id}"}},
    })

    return {
        "parts": [
            {"path": "definition.pbir", "payload": base64.b64encode(pbir_ml.encode()).decode(), "payloadType": "InlineBase64"},
            {"path": "report.json", "payload": base64.b64encode(report.encode()).decode(), "payloadType": "InlineBase64"},
        ]
    }
