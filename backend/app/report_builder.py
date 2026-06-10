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
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
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


def build_manufacturing_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for manufacturing AI & ML maintenance risk.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Predictive Maintenance - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Failure Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Failure Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Machine-Day Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Records", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Failures", "Predicted Failures", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Failures", "Actual Failures", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Failure Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Failure Rate %", "Failure Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_line", 415, 155, 400, 260, P, "production_line", "Predicted Failures", "Predicted Failures by Line"),
        _donut("p_act_line", 830, 155, 430, 260, P, "production_line", "Actual Failures", "Actual Failures by Line"),
        _line("p_trend", 20, 430, 795, 270, P, "sensor_date", "Avg Failure Probability", "Avg Failure Probability by Line", "production_line"),
        _table("p_tbl", 830, 430, 430, 270, P, ["machine_id", "production_line", "risk_level", "failure_probability", "predicted_failure", "had_failure"], "Prediction Detail"),
    ]

    # Page 3 - Machine Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Machine Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Machine", "11", False),
        _kpi_card("s_machines", 20, 45, S, "Machines", "Machines", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Failure Risk", "Avg Failure Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Failure Rate", "Avg Failure Rate", "#D83B01"),
        _kpi_card("s_days", 650, 45, S, "Predicted Failure Days", "Predicted Days", "#107C10"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Machines", "High Risk", "#A4262C"),
        _bar("s_bar", 20, 155, 760, 545, S, "machine_id", "Avg Failure Risk", "Avg Failure Risk by Machine", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Machines", "Machines by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["machine_id", "production_line", "overall_risk", "avg_failure_risk", "failure_rate", "predicted_failure_days"], "Machine Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Failure Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Machine Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_retail_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for retail AI & ML demand forecasting.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Demand Forecasting - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Regressor", "11", False),
        _kpi_card("m_r2", 20, 45, M, "Model R2", "R-Squared", "#0078D4"),
        _kpi_card("m_rmse", 230, 45, M, "Model RMSE", "RMSE (units)", "#D83B01"),
        _kpi_card("m_mae", 440, 45, M, "Model MAE", "MAE (units)", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#A4262C"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Demand Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Demand Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Store-Product-Day Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Records", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Avg Predicted Demand", "Avg Predicted", "#107C10"),
        _kpi_card("p_act", 440, 45, P, "Avg Actual Demand", "Avg Actual", "#5C2D91"),
        _kpi_card("p_gap", 650, 45, P, "Avg Demand Gap", "Avg Gap", "#D83B01"),
        _card("p_rev", 1060, 45, 200, 100, P, "Total Revenue", "Total Revenue", "#004E8C"),
        _donut("p_signal", 20, 155, 380, 260, P, "demand_signal", "Total Predictions", "Predictions by Demand Signal"),
        _bar("p_cat", 415, 155, 400, 260, P, "category", "Avg Predicted Demand", "Avg Predicted Demand by Category"),
        _donut("p_rev_region", 830, 155, 430, 260, P, "region", "Total Revenue", "Revenue by Region"),
        _line("p_trend", 20, 430, 795, 270, P, "txn_date", "Avg Predicted Demand", "Predicted Demand Trend by Region", "region"),
        _table("p_tbl", 830, 430, 430, 270, P, ["store_id", "product_id", "category", "demand_signal", "predicted_demand", "daily_quantity"], "Prediction Detail"),
    ]

    # Page 3 - Demand Outlook Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Demand Outlook Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated by Category & Region", "11", False),
        _kpi_card("s_combos", 20, 45, S, "Category-Region Combos", "Segments", "#0078D4"),
        _kpi_card("s_pred", 230, 45, S, "Avg Predicted Demand (Summary)", "Avg Predicted", "#107C10"),
        _kpi_card("s_grow", 440, 45, S, "Growing Segments", "Growing", "#107C10"),
        _kpi_card("s_decl", 650, 45, S, "Declining Segments", "Declining", "#D83B01"),
        _card("s_rev", 1060, 45, 200, 100, S, "Total Revenue (Summary)", "Total Revenue", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "category", "Total Revenue (Summary)", "Revenue by Category", True),
        _donut("s_trend", 795, 155, 465, 260, S, "demand_trend", "Category-Region Combos", "Segments by Demand Trend"),
        _table("s_tbl", 795, 430, 465, 270, S, ["category", "region", "demand_trend", "avg_predicted_demand", "avg_actual_demand", "total_revenue"], "Category-Region Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Demand Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_outlook", "displayName": "Demand Outlook", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_financial_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for financial-services AI & ML fraud detection.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Fraud Detection - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Fraud Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Fraud Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Transaction Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Txns", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Fraud", "Predicted Fraud", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Fraud", "Actual Fraud", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Fraud Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Fraud Rate %", "Fraud Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_chan", 415, 155, 400, 260, P, "channel", "Predicted Fraud", "Predicted Fraud by Channel"),
        _donut("p_country", 830, 155, 430, 260, P, "country", "Predicted Fraud", "Predicted Fraud by Country"),
        _bar("p_seg", 20, 430, 795, 270, P, "segment", "Avg Fraud Probability", "Avg Fraud Probability by Segment"),
        _table("p_tbl", 830, 430, 430, 270, P, ["transaction_id", "merchant_category", "channel", "risk_level", "fraud_probability", "predicted_fraud", "had_fraud"], "Prediction Detail"),
    ]

    # Page 3 - Merchant Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Merchant Category Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Merchant Category", "11", False),
        _kpi_card("s_cats", 20, 45, S, "Merchant Categories", "Categories", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Fraud Risk", "Avg Fraud Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Fraud Rate", "Avg Fraud Rate", "#D83B01"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Fraud", "Predicted Fraud", "#A4262C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Categories", "High Risk", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "merchant_category", "Avg Fraud Risk", "Avg Fraud Risk by Merchant Category", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Merchant Categories", "Categories by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["merchant_category", "overall_risk", "avg_fraud_probability", "fraud_rate", "predicted_fraud_count", "total_transactions"], "Merchant Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Fraud Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Merchant Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_healthcare_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for healthcare AI & ML readmission risk.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Readmission Risk - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Readmission Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Readmission Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Admission Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Admissions", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Readmissions", "Predicted", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Readmissions", "Actual", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Readmission Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Readmission Rate %", "Readmit Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_dept", 415, 155, 400, 260, P, "department", "Predicted Readmissions", "Predicted Readmissions by Department"),
        _donut("p_age", 830, 155, 430, 260, P, "age_group", "Predicted Readmissions", "Predicted Readmissions by Age Group"),
        _bar("p_adt", 20, 430, 795, 270, P, "admission_type", "Avg Readmission Probability", "Avg Readmission Probability by Admission Type"),
        _table("p_tbl", 830, 430, 430, 270, P, ["admission_id", "department", "age_group", "risk_level", "readmission_probability", "predicted_readmission", "had_readmission"], "Prediction Detail"),
    ]

    # Page 3 - Department Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Department Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Department", "11", False),
        _kpi_card("s_dept", 20, 45, S, "Departments", "Departments", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Readmission Risk", "Avg Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Readmission Rate", "Avg Rate", "#D83B01"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Readmissions", "Predicted", "#A4262C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Departments", "High Risk", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "department", "Avg Readmission Risk", "Avg Readmission Risk by Department", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Departments", "Departments by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["department", "overall_risk", "avg_readmission_probability", "readmission_rate", "predicted_readmission_count", "total_admissions"], "Department Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Readmission Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Department Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_technology_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for technology AI & ML account churn.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Churn Prediction - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Churn Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Churn Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Account Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Accounts", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Churn", "Predicted Churn", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Churn", "Actual Churn", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Churn Probability", "Avg Probability", "#5C2D91"),
        _card("p_mrr", 1060, 45, 200, 100, P, "Total MRR", "Total MRR", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_plan", 415, 155, 400, 260, P, "plan", "Predicted Churn", "Predicted Churn by Plan"),
        _donut("p_region", 830, 155, 430, 260, P, "region", "Predicted Churn", "Predicted Churn by Region"),
        _bar("p_ind", 20, 430, 795, 270, P, "industry", "Avg Churn Probability", "Avg Churn Probability by Industry"),
        _table("p_tbl", 830, 430, 430, 270, P, ["account_id", "plan", "industry", "risk_level", "churn_probability", "predicted_churn", "had_churn"], "Prediction Detail"),
    ]

    # Page 3 - Industry Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Industry Churn Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Industry", "11", False),
        _kpi_card("s_ind", 20, 45, S, "Industries", "Industries", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Churn Risk", "Avg Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Churn Rate", "Avg Rate", "#D83B01"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Churn", "Predicted", "#A4262C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Industries", "High Risk", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "industry", "Avg Churn Risk", "Avg Churn Risk by Industry", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Industries", "Industries by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["industry", "overall_risk", "avg_churn_probability", "churn_rate", "predicted_churn_count", "total_accounts"], "Industry Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Churn Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Industry Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_transportation_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for transportation AI & ML delivery delay.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Delivery Delay - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Delay Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Delay Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Delivery Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Deliveries", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Late", "Predicted Late", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Late", "Actual Late", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Delay Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Late Rate %", "Late Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_route", 415, 155, 400, 260, P, "route_type", "Predicted Late", "Predicted Late by Route Type"),
        _donut("p_veh", 830, 155, 430, 260, P, "vehicle_type", "Predicted Late", "Predicted Late by Vehicle Type"),
        _bar("p_depot", 20, 430, 795, 270, P, "depot", "Avg Delay Probability", "Avg Delay Probability by Depot"),
        _table("p_tbl", 830, 430, 430, 270, P, ["delivery_id", "depot", "route_type", "risk_level", "delay_probability", "predicted_late", "had_late"], "Prediction Detail"),
    ]

    # Page 3 - Depot Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Depot Delay Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Depot", "11", False),
        _kpi_card("s_depot", 20, 45, S, "Depots", "Depots", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Delay Risk", "Avg Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Late Rate", "Avg Rate", "#D83B01"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Late", "Predicted", "#A4262C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Depots", "High Risk", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "depot", "Avg Delay Risk", "Avg Delay Risk by Depot", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Depots", "Depots by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["depot", "overall_risk", "avg_delay_probability", "late_rate", "predicted_late_count", "total_deliveries"], "Depot Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Delay Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Depot Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_hospitality_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for hospitality AI & ML booking cancellation.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Booking Cancellation - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Cancellation Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Cancellation Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Booking Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Bookings", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Cancellations", "Predicted", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Cancellations", "Actual", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Cancel Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Cancel Rate %", "Cancel Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_room", 415, 155, 400, 260, P, "room_type", "Predicted Cancellations", "Predicted Cancellations by Room Type"),
        _donut("p_loy", 830, 155, 430, 260, P, "loyalty_tier", "Predicted Cancellations", "Predicted Cancellations by Loyalty Tier"),
        _bar("p_chan", 20, 430, 795, 270, P, "channel", "Avg Cancel Probability", "Avg Cancel Probability by Channel"),
        _table("p_tbl", 830, 430, 430, 270, P, ["booking_id", "channel", "loyalty_tier", "risk_level", "cancel_probability", "predicted_cancel", "had_cancel"], "Prediction Detail"),
    ]

    # Page 3 - Channel Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Channel Cancellation Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Booking Channel", "11", False),
        _kpi_card("s_chan", 20, 45, S, "Channels", "Channels", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Cancel Risk", "Avg Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Cancel Rate", "Avg Rate", "#D83B01"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Cancellations", "Predicted", "#A4262C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Channels", "High Risk", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "channel", "Avg Cancel Risk", "Avg Cancel Risk by Channel", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Channels", "Channels by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["channel", "overall_risk", "avg_cancel_probability", "cancel_rate", "predicted_cancel_count", "total_bookings"], "Channel Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Cancellation Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Channel Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_media_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for media AI & ML content completion.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Content Completion - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Completion Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Completion Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Viewing Session Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Sessions", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Completions", "Predicted", "#107C10"),
        _kpi_card("p_act", 440, 45, P, "Actual Completions", "Actual", "#004E8C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Completion Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Completion Rate %", "Completion Rate %", "#D83B01"),
        _donut("p_eng", 20, 155, 380, 260, P, "engagement_level", "Total Predictions", "Sessions by Engagement Level"),
        _bar("p_ctype", 415, 155, 400, 260, P, "content_type", "Predicted Completions", "Predicted Completions by Content Type"),
        _donut("p_dev", 830, 155, 430, 260, P, "device_type", "Predicted Completions", "Predicted Completions by Device"),
        _bar("p_plan", 20, 430, 795, 270, P, "plan_type", "Avg Completion Probability", "Avg Completion Probability by Plan"),
        _table("p_tbl", 830, 430, 430, 270, P, ["view_id", "genre", "content_type", "device_type", "engagement_level", "complete_probability", "predicted_complete"], "Prediction Detail"),
    ]

    # Page 3 - Genre Engagement Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Genre Engagement Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Engagement by Content Genre", "11", False),
        _kpi_card("s_genre", 20, 45, S, "Genres", "Genres", "#0078D4"),
        _kpi_card("s_eng", 230, 45, S, "Avg Engagement Score", "Avg Engagement", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Completion Rate", "Avg Rate", "#107C10"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Completions", "Predicted", "#004E8C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Engagement Genres", "High Engagement", "#D83B01"),
        _bar("s_bar", 20, 155, 760, 545, S, "genre", "Avg Engagement Score", "Avg Engagement by Genre", True),
        _donut("s_eng_dist", 795, 155, 465, 260, S, "overall_engagement", "Genres", "Genres by Engagement Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["genre", "overall_engagement", "avg_complete_probability", "completion_rate", "predicted_complete_count", "total_views"], "Genre Engagement Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Completion Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_engagement", "displayName": "Genre Engagement", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_professional_services_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for professional-services AI & ML project overrun.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Project Outcome - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Overrun Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Budget Overrun Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Engagement Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Engagements", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Overruns", "Predicted", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Overruns", "Actual", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Overrun Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Overrun Rate %", "Overrun Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_ind", 415, 155, 400, 260, P, "industry", "Predicted Overruns", "Predicted Overruns by Industry"),
        _donut("p_tier", 830, 155, 430, 260, P, "tier", "Predicted Overruns", "Predicted Overruns by Client Tier"),
        _bar("p_prac", 20, 430, 795, 270, P, "practice", "Avg Overrun Probability", "Avg Overrun Probability by Practice"),
        _table("p_tbl", 830, 430, 430, 270, P, ["engagement_id", "practice", "tier", "risk_level", "overrun_probability", "predicted_overrun", "had_overrun"], "Prediction Detail"),
    ]

    # Page 3 - Practice Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Practice Overrun Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Practice", "11", False),
        _kpi_card("s_prac", 20, 45, S, "Practices", "Practices", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Overrun Risk", "Avg Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Overrun Rate", "Avg Rate", "#D83B01"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Overruns", "Predicted", "#A4262C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Practices", "High Risk", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "practice", "Avg Overrun Risk", "Avg Overrun Risk by Practice", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Practices", "Practices by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["practice", "overall_risk", "avg_overrun_probability", "overrun_rate", "predicted_overrun_count", "total_engagements"], "Practice Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Overrun Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Practice Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_construction_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for construction AI & ML project delay.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Project Delay - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Delay Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Task Delay Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Task Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Tasks", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Delays", "Predicted", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Delays", "Actual", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Delay Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Delay Rate %", "Delay Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_task", 415, 155, 400, 260, P, "task_name", "Predicted Delays", "Predicted Delays by Task Type"),
        _donut("p_ptype", 830, 155, 430, 260, P, "project_type", "Predicted Delays", "Predicted Delays by Project Type"),
        _bar("p_trade", 20, 430, 795, 270, P, "sub_trade", "Avg Delay Probability", "Avg Delay Probability by Trade"),
        _table("p_tbl", 830, 430, 430, 270, P, ["task_id", "sub_trade", "task_name", "risk_level", "delay_probability", "predicted_delay", "had_delay"], "Prediction Detail"),
    ]

    # Page 3 - Trade Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Trade Delay Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Subcontractor Trade", "11", False),
        _kpi_card("s_trade", 20, 45, S, "Trades", "Trades", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Delay Risk", "Avg Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Delay Rate", "Avg Rate", "#D83B01"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Delays", "Predicted", "#A4262C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Trades", "High Risk", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "trade", "Avg Delay Risk", "Avg Delay Risk by Trade", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Trades", "Trades by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["trade", "overall_risk", "avg_delay_probability", "delay_rate", "predicted_delay_count", "total_tasks"], "Trade Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Delay Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Trade Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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


def build_education_ml_report_definition(semantic_model_id: str) -> dict:
    """Build a 3-page Power BI report for education AI & ML dropout risk.

    References the gold_ml_* tables produced by the ML notebooks:
    gold_ml_model_metrics, gold_ml_feature_importance, gold_ml_predictions, gold_ml_summary.
    """

    M = "gold_ml_model_metrics"
    F = "gold_ml_feature_importance"
    P = "gold_ml_predictions"
    S = "gold_ml_summary"

    # Page 1 - Model Performance
    p1 = [
        _textbox("mh1", 20, 5, 650, 35, "Dropout Risk - Model Performance", "20"),
        _textbox("ms1", 700, 12, 400, 25, "RandomForest Classifier", "11", False),
        _kpi_card("m_auc", 20, 45, M, "Model AUC", "AUC-ROC", "#0078D4"),
        _kpi_card("m_acc", 230, 45, M, "Model Accuracy", "Accuracy", "#107C10"),
        _kpi_card("m_f1", 440, 45, M, "F1 Score", "F1 Score", "#5C2D91"),
        _kpi_card("m_feat", 650, 45, M, "Feature Count", "Features Used", "#004E8C"),
        _kpi_card("m_train", 860, 45, M, "Training Rows", "Training Rows", "#107C10"),
        _card("m_test", 1060, 45, 200, 100, M, "Test Rows", "Test Rows", "#D83B01"),
        _bar("m_fi", 20, 155, 760, 545, F, "feature", "Total Importance", "Feature Importance (RandomForest)", True),
        _table("m_fi_tbl", 795, 155, 465, 545, F, ["feature", "importance"], "Feature Importance Detail"),
    ]

    # Page 2 - Dropout Predictions
    p2 = [
        _textbox("ph1", 20, 5, 650, 35, "Dropout Risk Predictions", "20"),
        _textbox("ps1", 700, 12, 450, 25, "Per Enrolment Scoring", "11", False),
        _kpi_card("p_tot", 20, 45, P, "Total Predictions", "Scored Enrolments", "#0078D4"),
        _kpi_card("p_pred", 230, 45, P, "Predicted Dropouts", "Predicted", "#D83B01"),
        _kpi_card("p_act", 440, 45, P, "Actual Dropouts", "Actual", "#A4262C"),
        _kpi_card("p_prob", 650, 45, P, "Avg Dropout Probability", "Avg Probability", "#5C2D91"),
        _card("p_rate", 1060, 45, 200, 100, P, "Predicted Dropout Rate %", "Dropout Rate %", "#004E8C"),
        _donut("p_risk", 20, 155, 380, 260, P, "risk_level", "Total Predictions", "Predictions by Risk Level"),
        _bar("p_level", 415, 155, 400, 260, P, "level", "Predicted Dropouts", "Predicted Dropouts by Level"),
        _donut("p_prog", 830, 155, 430, 260, P, "programme", "Predicted Dropouts", "Predicted Dropouts by Programme"),
        _bar("p_dept", 20, 430, 795, 270, P, "department", "Avg Dropout Probability", "Avg Dropout Probability by Department"),
        _table("p_tbl", 830, 430, 430, 270, P, ["enrolment_id", "department", "level", "risk_level", "dropout_probability", "predicted_dropout", "had_dropout"], "Prediction Detail"),
    ]

    # Page 3 - Department Risk Summary
    p3 = [
        _textbox("sh1", 20, 5, 650, 35, "Department Dropout Risk Summary", "20"),
        _textbox("ss1", 700, 12, 450, 25, "Aggregated Risk by Department", "11", False),
        _kpi_card("s_dept", 20, 45, S, "Departments", "Departments", "#0078D4"),
        _kpi_card("s_risk", 230, 45, S, "Avg Dropout Risk", "Avg Risk", "#5C2D91"),
        _kpi_card("s_rate", 440, 45, S, "Avg Dropout Rate", "Avg Rate", "#D83B01"),
        _kpi_card("s_pred", 650, 45, S, "Total Predicted Dropouts", "Predicted", "#A4262C"),
        _card("s_high", 1060, 45, 200, 100, S, "High Risk Departments", "High Risk", "#004E8C"),
        _bar("s_bar", 20, 155, 760, 545, S, "department", "Avg Dropout Risk", "Avg Dropout Risk by Department", True),
        _donut("s_risk_dist", 795, 155, 465, 260, S, "overall_risk", "Departments", "Departments by Risk Tier"),
        _table("s_tbl", 795, 430, 465, 270, S, ["department", "overall_risk", "avg_dropout_probability", "dropout_rate", "predicted_dropout_count", "total_enrolments"], "Department Risk Detail"),
    ]

    config = {"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY25SU12", "version": "2.5.0", "type": 2}}, "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True}

    report = json.dumps({
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {"name": "SharedResources", "type": 2, "items": [{"type": 202, "name": "CY25SU12", "path": "BaseThemes/CY25SU12.json"}]}}],
        "sections": [
            {"name": "pg_model", "displayName": "Model Performance", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p1},
            {"name": "pg_predictions", "displayName": "Dropout Predictions", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p2},
            {"name": "pg_risk", "displayName": "Department Risk", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": p3},
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
