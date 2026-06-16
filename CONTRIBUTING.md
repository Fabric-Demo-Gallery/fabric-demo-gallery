# Fabric Demo Gallery — Contributor Guide

A complete guide for adding new industry demos, understanding the deployment architecture, and avoiding the pitfalls we discovered during development.

## Contributor License Agreement (CLA)

This project welcomes contributions and suggestions. Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit <https://cla.opensource.microsoft.com>.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide a
CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [How Deployment Works](#how-deployment-works)
3. [Adding a New Industry Demo](#adding-a-new-industry-demo)
4. [Writing Notebooks](#writing-notebooks)
5. [Creating a Semantic Model (model.bim)](#creating-a-semantic-model)
6. [Creating a Power BI Report](#creating-a-power-bi-report)
7. [Generating Sample Data](#generating-sample-data)
8. [Pipeline Definition](#pipeline-definition)
9. [Frontend Changes](#frontend-changes)
10. [Common Errors & Solutions](#common-errors--solutions)
11. [API Permissions Required](#api-permissions-required)
12. [Testing Checklist](#testing-checklist)

---

## Architecture Overview

```
Frontend (Next.js)          Backend (FastAPI)              Microsoft Fabric
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────────────┐
│  Gallery UI      │───▶│  /api/demos          │    │  Workspace              │
│  MSAL Auth       │    │  /api/deploy/{id}    │───▶│  ├── Lakehouse          │
│  SSE Progress    │◀───│  /api/workspaces     │    │  ├── Notebooks (x3-5)   │
│  Capacity Picker │    │  /api/deploy/{wsId}  │    │  ├── Semantic Model     │
│  Cleanup Button  │    │  DELETE              │    │  ├── Power BI Report    │
└─────────────────┘    └──────────────────────┘    │  └── Pipeline           │
                                                    └─────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `backend/app/deployer.py` | Orchestrates all deployment steps sequentially |
| `backend/app/fabric_client.py` | Wraps Fabric REST APIs (workspaces, items, notebooks, OneLake) |
| `backend/app/report_builder.py` | Generates Power BI report definitions programmatically |
| `backend/app/auth.py` | Handles Azure AD tokens (MSAL + az CLI fallback) |
| `demos/{demo-id}/manifest.json` | Declares what the demo contains |
| `demos/{demo-id}/notebooks/*.ipynb` | PySpark notebook source files |
| `demos/{demo-id}/tmdl/model.bim` | Semantic model definition (TMSL format) |
| `demos/{demo-id}/data/*.csv` | Sample data files uploaded to lakehouse |
| `demos/schema.json` | JSON Schema for manifest validation |
| `demos/generate_sample_data.py` | Script to regenerate all sample data |

---

## How Deployment Works

The deployer (`deployer.py`) executes these steps in order:

```
1. Create workspace (with user-selected capacity)
2. Create lakehouse → capture lakehouse ID
3. Upload sample CSV files to lakehouse Files/landing/ via OneLake DFS API
4. Create notebooks (empty first, then updateDefinition with code)
5. Execute notebooks sequentially (Bronze → Silver → Gold → ...)
   - 30-second delay between runs to avoid Spark rate limiting
   - Auto-retry once on throttling (429/430) errors
6. Wait for SQL endpoint to become available
7. Create semantic model (model.bim with SQL endpoint injected)
8. Refresh semantic model (Direct Lake metadata sync)
9. Create Power BI report (PBIR-Legacy format, bound to semantic model)
10. Create pipeline (TridentNotebook activities chained sequentially)
```

Each step streams progress to the frontend via Server-Sent Events (SSE).

### Critical Detail: Token Audiences

The Fabric API and OneLake use DIFFERENT token audiences:

| Operation | Token Audience | How We Get It |
|-----------|---------------|---------------|
| Fabric REST APIs | `https://api.fabric.microsoft.com` | MSAL `.default` scope or az CLI |
| OneLake file upload | `https://storage.azure.com` | Separate MSAL scope or az CLI |

The `FabricClient` accepts both tokens in its constructor:
```python
client = FabricClient(fabric_token, storage_token=storage_token)
```

---

## Adding a New Industry Demo

### Step 1: Create the directory structure

```
demos/
└── {your-demo-id}/
    ├── manifest.json          # Required: declares all items
    ├── data/                  # Sample CSV/Parquet files
    │   ├── file1.csv
    │   └── file2.csv
    ├── notebooks/             # PySpark notebooks (.ipynb format)
    │   ├── 01_bronze_ingest.ipynb
    │   ├── 02_silver_transform.ipynb
    │   └── 03_gold_aggregate.ipynb
    └── tmdl/
        └── model.bim          # Semantic model definition
```

### Step 2: Write the manifest.json

```json
{
  "id": "your-demo-id",
  "industry": "Your Industry",
  "title": "Your Demo Title",
  "description": "Short description for the gallery card.",
  "longDescription": "Detailed multi-sentence description.",
  "icon": "🏭",
  "estimatedTime": "8-12 min",
  "prerequisites": [
    "Microsoft Fabric capacity (F2+ or Trial)",
    "Azure AD account with workspace creation permissions"
  ],
  "architecture": {
    "pattern": "medallion",
    "layers": ["Bronze (Raw Data)", "Silver (Cleaned)", "Gold (Aggregated)"]
  },
  "sampleData": [
    {
      "fileName": "your_data.csv",
      "description": "What this data represents",
      "format": "csv",
      "rows": 50000
    }
  ],
  "fabricItems": [
    { "type": "Lakehouse", "name": "your_lakehouse", "description": "Central lakehouse" },
    { "type": "Notebook", "name": "01_bronze_ingest", "definitionPath": "notebooks/01_bronze_ingest.ipynb", "description": "Ingest raw data", "order": 1 },
    { "type": "Notebook", "name": "02_silver_transform", "definitionPath": "notebooks/02_silver_transform.ipynb", "description": "Clean and transform", "order": 2 },
    { "type": "Notebook", "name": "03_gold_aggregate", "definitionPath": "notebooks/03_gold_aggregate.ipynb", "description": "Aggregate KPIs", "order": 3 },
    { "type": "SemanticModel", "name": "your_model", "definitionPath": "tmdl", "description": "Direct Lake semantic model" },
    { "type": "Report", "name": "Your Dashboard", "description": "Power BI dashboard" },
    { "type": "DataPipeline", "name": "daily_pipeline", "description": "Orchestrates notebooks" }
  ]
}
```

**Important rules:**
- `id` must match the folder name
- `definitionPath` for SemanticModel must point to the folder containing `model.bim`
- Notebook `order` determines execution sequence
- Notebook `definitionPath` must point to the `.ipynb` file

### Step 3: Write the notebooks (see section below)
### Step 4: Create the model.bim (see section below)
### Step 5: Add the report builder (see section below)
### Step 6: Update the frontend (see section below)

---

## Writing Notebooks

### Format

Notebooks are stored as standard `.ipynb` JSON files. The deployer converts them to Fabric's native `.py` format at deploy time. You write normal `.ipynb` — the conversion is automatic.

### Critical Rules

1. **Every code cell MUST have `"outputs": []` and `"execution_count": null`** — otherwise Fabric silently fails
2. **All imports must be complete** — we lost hours debugging because `when` was missing from a PySpark import. Triple-check your imports.
3. **Use `spark.read.format('delta').table('table_name')` for reading** — Fabric notebooks have the lakehouse context bound automatically
4. **Use `saveAsTable('table_name')` for writing** — creates managed Delta tables in the lakehouse
5. **Files land in `Files/landing/`** — the deployer uploads CSVs there, so Bronze notebooks should read from `'Files/landing/your_file.csv'`

### Notebook Template

```json
{
  "nbformat": 4,
  "nbformat_minor": 5,
  "metadata": {
    "language_info": { "name": "python" },
    "kernel_info": { "name": "synapse_pyspark" }
  },
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": ["# Title\nDescription"]
    },
    {
      "cell_type": "code",
      "metadata": {},
      "source": ["# Your PySpark code here\ndf = spark.read.format('csv').option('header', True).load('Files/landing/data.csv')"],
      "outputs": [],
      "execution_count": null
    }
  ]
}
```

### Bronze Notebook Pattern
```python
from pyspark.sql.functions import current_timestamp, input_file_name, lit
import uuid

batch_id = str(uuid.uuid4())

df = (
    spark.read.format('csv')
    .option('header', True)
    .option('inferSchema', True)
    .load('Files/landing/your_file.csv')
    .withColumn('ingestion_timestamp', current_timestamp())
    .withColumn('source_file', input_file_name())
    .withColumn('batch_id', lit(batch_id))
)

df.write.mode('overwrite').format('delta').saveAsTable('bronze_your_table')
print(f'Bronze: {df.count()} rows')
```

### Silver Notebook Pattern
```python
from pyspark.sql.functions import col, when, row_number, current_timestamp, to_timestamp
from pyspark.sql.window import Window

df = spark.read.format('delta').table('bronze_your_table')

# Deduplicate
w = Window.partitionBy('id_col').orderBy(col('ingestion_timestamp').desc())
df = df.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')

# Clean, validate, derive
df = df.filter(col('value') > 0).withColumn('derived_col', ...)

df.write.mode('overwrite').format('delta').saveAsTable('silver_your_table')
```

### Gold Notebook Pattern
```python
# Enable V-Order for read-optimized Gold tables
spark.conf.set('spark.sql.parquet.vorder.default', 'true')
spark.conf.set('spark.databricks.delta.optimizeWrite.enabled', 'true')

gold = df.groupBy(...).agg(...)
gold.write.mode('overwrite').format('delta').saveAsTable('gold_your_summary')

spark.sql('OPTIMIZE gold_your_summary')
```

**Common mistake:** Forgetting to import `when` — if you use `when()` anywhere in your notebook, it MUST be in the import list.

---

## Creating a Semantic Model

### Use `model.bim` (TMSL JSON format)

**DO NOT use TMDL folder format** — the Fabric API requires `model.bim` for `create item with definition`. We tried TMDL and it fails with "missing required artifact model.bim".

### Template

Create `demos/{your-demo}/tmdl/model.bim`:

```json
{
  "compatibilityLevel": 1604,
  "model": {
    "culture": "en-US",
    "defaultPowerBIDataSourceVersion": "powerBI_V3",
    "discourageImplicitMeasures": true,
    "expressions": [
      {
        "name": "DatabaseQuery",
        "kind": "m",
        "expression": "let\n    database = Sql.Database(\"{{SQL_ENDPOINT}}\", \"{{LAKEHOUSE_NAME}}\")\nin\n    database"
      }
    ],
    "relationships": [],
    "tables": [
      {
        "name": "gold_your_table",
        "columns": [
          {"name": "column_name", "dataType": "string", "sourceColumn": "column_name"},
          {"name": "numeric_col", "dataType": "double", "sourceColumn": "numeric_col"}
        ],
        "measures": [
          {"name": "Total Value", "expression": "SUM('gold_your_table'[numeric_col])", "formatString": "#,##0"}
        ],
        "partitions": [
          {
            "name": "gold_your_table",
            "mode": "directLake",
            "source": {
              "type": "entity",
              "entityName": "gold_your_table",
              "schemaName": "dbo",
              "expressionSource": "DatabaseQuery"
            }
          }
        ]
      }
    ]
  }
}
```

### Key Points

- **Use `mode: directLake`** — not `import`. Direct Lake reads directly from Delta tables in OneLake without data copy or credentials
- **`{{SQL_ENDPOINT}}` and `{{LAKEHOUSE_NAME}}` are placeholders** — the deployer replaces them at deploy time with actual values
- **Column names must exactly match** the Delta table column names from your Gold notebooks
- **`dataType` values**: `string`, `int64`, `double`, `boolean`, `dateTime`
- **`definition.pbism`** is auto-generated by the deployer — you don't need to create it

### Relationships

```json
"relationships": [
  {
    "name": "fact_to_dim",
    "fromTable": "fact_table",
    "fromColumn": "dim_key",
    "toTable": "dim_table",
    "toColumn": "dim_key",
    "crossFilteringBehavior": "bothDirections"
  }
]
```

### After Deployment

The semantic model will show ⚠️ warning triangles on tables. This is normal for Direct Lake on smaller capacities — it's an informational notice about potential DirectQuery fallback, not an error. Data is accessible.

---

## Creating a Power BI Report

### Format: PBIR-Legacy

We use the PBIR-Legacy format (`report.json` single file), NOT the PBIR folder format. The PBIR format requires exact schema version URLs that are underdocumented and change frequently.

### Implementation

Add a function to `backend/app/report_builder.py`:

```python
def build_your_report_definition(semantic_model_id: str) -> dict:
    # Build visuals using helper functions: _card, _bar, _donut, _line, _table, _textbox
    page1_visuals = [
        _card("v1", x=30, y=20, entity="gold_table", measure="Total Value", title="KPI Title"),
        _bar("v2", x=30, y=170, w=400, h=250, entity="gold_table", cat="category_col", meas="Total Value", title="Chart Title"),
        # ... more visuals
    ]

    # Assemble report
    report = json.dumps({
        "config": json.dumps({...}),
        "sections": [
            {"name": "pg1", "displayName": "Page Title", "displayOption": 2, "width": 1280, "height": 720, "visualContainers": page1_visuals},
        ],
        ...
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
```

### Visual Position Rules

- **Top-level `x/y/width/height`** on the visual container controls position on the canvas
- **DO NOT include `layouts` array** in the config — it overrides positions and causes all visuals to stack at (0,0)
- Canvas is 1280 x 720 pixels

### Available Visual Helpers

| Helper | Visual Type | Key Parameters |
|--------|-----------|----------------|
| `_card(name, x, y, entity, measure, title)` | KPI card | Single measure value |
| `_bar(name, x, y, w, h, entity, cat, meas, title, horiz)` | Bar chart | Category + measure |
| `_donut(name, x, y, w, h, entity, cat, meas, title)` | Donut chart | Category + measure |
| `_line(name, x, y, w, h, entity, xcol, meas, title, series)` | Line chart | X-axis + measure + optional series |
| `_table(name, x, y, w, h, entity, cols, title)` | Table | List of column names |
| `_textbox(name, x, y, w, h, text, font_size, bold)` | Text label | Static text |
| `_multi_bar(name, x, y, w, h, entity, cat, measures, title)` | Multi-measure bar | Category + multiple measures |

### Register Your Report Builder

In `deployer.py`, update `_build_report_definition`:

```python
def _build_report_definition(demo_id: str, semantic_model_id: str) -> dict:
    if demo_id == "manufacturing-qc":
        return build_manufacturing_report_definition(semantic_model_id)
    elif demo_id == "retail-sales":
        return build_retail_report_definition(semantic_model_id)
    elif demo_id == "your-demo-id":
        return build_your_report_definition(semantic_model_id)
```

---

## Generating Sample Data

Add your data generator to `demos/generate_sample_data.py`:

```python
def generate_your_data():
    out_dir = DEMOS_DIR / "your-demo-id" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    rows = []
    for i in range(50000):
        rows.append({
            "id": f"ID-{i:06d}",
            "value": round(random.gauss(100, 20), 2),
            "timestamp": (base_date + timedelta(days=random.randint(0, 89))).strftime("%Y-%m-%d %H:%M:%S"),
        })
    _write_csv(out_dir / "your_data.csv", rows)
```

**Keep datasets small** — under 50MB per demo. Large datasets slow down deployment and consume Spark capacity.

---

## Pipeline Definition

The pipeline is generated dynamically by the deployer based on the notebooks in your manifest. You don't need to create a pipeline definition file.

The deployer creates `TridentNotebook` activities chained sequentially:
- Each notebook depends on the previous one (`dependsOn: [{activity: prev_name, dependencyConditions: ["Succeeded"]}]`)
- Retry policy: 1 retry with 60-second interval
- Timeout: 12 hours per notebook

---

## Frontend Changes

### 1. Add demo data to `frontend/src/app/page.tsx`

Add an entry to the `DEMOS` array:

```typescript
{
  id: "your-demo-id",
  industry: "Your Industry",
  title: "Your Demo Title",
  desc: "Short description.",
  tags: ["Tag1", "Tag2", "Tag3"],
  time: "8–12 min",
  itemCount: 7,
}
```

### 2. Add demo details to `frontend/src/app/demos/[id]/page.tsx`

Add an entry to the `DEMOS` record with full details (sampleData, fabricItems, architecture, etc.). Follow the existing Manufacturing or Retail entries as templates.

---

## Common Errors & Solutions

### Notebook Creation

| Error | Cause | Solution |
|-------|-------|----------|
| `PyToIPynbFailure: prologue is invalid` | Line endings are LF instead of CRLF | The deployer handles this — uses `\r\n` in the conversion |
| `PyToIPynbFailure: .ipynb suffix not supported` | Using `notebook-content.ipynb` path | Use `notebook-content.py` path (the deployer converts .ipynb → Fabric .py format) |
| `Convert data from py to ipynb failed` | Missing `# Fabric notebook source` prologue | The deployer adds this automatically |

### Notebook Execution

| Error | Cause | Solution |
|-------|-------|----------|
| `TooManyRequestsForCapacity` (429/430) | Spark sessions back-to-back | Deployer adds 30s delay between runs + auto-retry |
| `System_Cancelled_Session_Statements_Failed` | Code error in notebook | Check the notebook code — usually a missing import or column name mismatch |
| `InsufficientScopes` | Missing API permissions | Add `Item.Execute.All` to the Azure AD app registration |

### Semantic Model

| Error | Cause | Solution |
|-------|-------|----------|
| `Missing required artifact 'model.bim'` | Using TMDL folder format | Use `model.bim` (TMSL JSON) instead |
| `Required artifact is missing in 'definition.pbism'` | No `definition.pbism` file | The deployer auto-generates this |
| `Invalid object name 'dbo.table_name'` | Gold tables don't exist yet | The Gold notebook failed — check execution logs |
| `default data connection without explicit connection credentials` | Using `import` mode | Use `directLake` mode in partitions |

### Power BI Report

| Error | Cause | Solution |
|-------|-------|----------|
| `Failed to deserialize report document` | Invalid `report.json` structure | Use PBIR-Legacy format, check JSON structure |
| `Can't resolve schema in 'version.json'` | Wrong PBIR format (folder-based) | Use PBIR-Legacy (single `report.json` file), not PBIR folder |
| `Required properties missing: pbiServiceModelId` | Wrong `definition.pbir` format | Use simple `connectionString: "semanticmodelid={id}"` |
| Visuals stacked at top-left | `layouts[].position` overriding | Remove `layouts` array from visual config entirely |

### OneLake Upload

| Error | Cause | Solution |
|-------|-------|----------|
| `FriendlyNameSupportDisabled` | Using names instead of GUIDs in path | Use `/{workspaceId}/{lakehouseId}/Files/...` |
| `AuthorizationFailure` (403) | Wrong token audience | OneLake needs `storage.azure.com` token, not Fabric token |

### Authentication

| Error | Cause | Solution |
|-------|-------|----------|
| `InsufficientScopes` on any operation | Missing API permission | Add the required permission in Azure AD app registration, sign out and back in |
| Token works for some operations but not others | Granular scopes vs `.default` | Use `https://api.fabric.microsoft.com/.default` scope |
| Capacities not loading | Token doesn't include capacity permissions | Add `Capacity.ReadWrite.All` permission |

---

## API Permissions Required

Add these to your Azure AD App Registration under **Power BI Service** (Delegated):

| Permission | Used For |
|------------|----------|
| `Workspace.ReadWrite.All` | Create/delete workspaces |
| `Item.ReadWrite.All` | Create/update all Fabric items |
| `Item.Execute.All` | Execute notebooks |
| `Lakehouse.ReadWrite.All` | Create lakehouses |
| `Notebook.ReadWrite.All` | Create/update notebooks |
| `Capacity.ReadWrite.All` | List available capacities |

Under **Azure Storage** (Delegated):
| Permission | Used For |
|------------|----------|
| `user_impersonation` | Upload files to OneLake |

The app registration should use **"Accounts in any organizational directory"** (multitenant) for broad access, and **SPA redirect URI** (`http://localhost:3000`).

---

## Testing Checklist

Before submitting a PR with a new demo:

- [ ] `manifest.json` validates against `demos/schema.json`
- [ ] All notebook `.ipynb` files have `"outputs": []` and `"execution_count": null` on every code cell
- [ ] All PySpark imports are complete (especially `when`, `col`, `lit`, etc.)
- [ ] Sample data files are under 50MB total
- [ ] `model.bim` column names exactly match Gold table column names
- [ ] `model.bim` uses `directLake` mode (not `import`)
- [ ] `model.bim` has `{{SQL_ENDPOINT}}` and `{{LAKEHOUSE_NAME}}` placeholders
- [ ] Report builder function exists in `report_builder.py`
- [ ] Report builder is registered in `deployer.py`'s `_build_report_definition`
- [ ] Frontend `page.tsx` has the demo in both the home page card list and the detail page `DEMOS` record
- [ ] Demo deploys end-to-end without errors
- [ ] All Gold tables are populated after notebook execution
- [ ] Semantic model shows tables (⚠️ warnings are OK on Trial capacity)
- [ ] Power BI report renders with data
- [ ] Cleanup (delete workspace) works

---

## Quick Reference: Deployment Flow

```
User clicks "Deploy"
  ↓
Frontend: POST /api/deploy/{demo_id} with SSE
  ↓
Backend: deployer.py → deploy_demo()
  ↓
1. create_workspace(name, capacity_id)
2. create_lakehouse(ws_id, name) → lakehouse_id
3. upload_file_to_lakehouse(ws_id, lh_id, remote_path, local_path)  [uses storage token]
4. For each notebook:
   a. create_item(ws_id, "Notebook", name)  [empty]
   b. Convert .ipynb → Fabric .py format (CRLF, prologue, METADATA, CELL markers)
   c. update_item_definition(ws_id, nb_id, definition)
5. For each notebook (in order):
   a. Sleep 30s (avoid rate limits)
   b. run_notebook(ws_id, nb_id, lh_id, lh_name) → poll until Completed
   c. Retry once on throttling
6. wait_for_sql_endpoint(ws_id, lh_id) → conn_string
7. _build_bim_definition(model.bim, {SQL_ENDPOINT: conn_string, LAKEHOUSE_NAME: lh_name})
   → create_semantic_model(ws_id, name, definition)
8. refresh_semantic_model(ws_id, sm_id)
9. _build_report_definition(demo_id, sm_id)
   → create_item(ws_id, "Report", name, definition)
10. _build_pipeline_definition(ws_id, notebooks, notebook_ids)
    → create_pipeline(ws_id, name, definition)
11. Done → stream "done" event with workspace ID
```

---

## Lessons Learned

1. **Fabric's notebook API is very particular** — the `.py` format requires exact prologue, CRLF line endings, and specific cell markers. We went through 5 iterations to get this right.

2. **TMDL doesn't work via REST API** — despite being documented, the API actually requires `model.bim`. Don't waste time on TMDL.

3. **PBIR (folder) format is fragile** — schema version URLs must match exactly what the service supports and there's no way to know without trial and error. PBIR-Legacy (single `report.json`) works reliably.

4. **Direct Lake needs no credentials** — but needs a refresh (metadata sync) after creation. The deployer does this automatically.

5. **Visual positioning in reports** — the `layouts` array in visual config overrides the top-level position. Remove it entirely and use only top-level `x/y/width/height`.

6. **Rate limiting is real** — on Trial/F2 capacities, back-to-back Spark sessions get throttled. A 30-second delay between notebook runs is essential.

7. **Two different tokens** — Fabric API and OneLake use different OAuth audiences. This is the most confusing part for new contributors.

8. **Empty items then update** — Notebooks and Pipelines must be created empty first, then have their definition pushed via `updateDefinition`. Semantic Models and Reports can be created with definition in one call.

9. **LRO polling** — most creation operations return 202 with a Location header. Poll until status is "Succeeded". The item won't appear in listings until the LRO completes.

10. **Test with az CLI first** — the test scripts (`test_step1_connect.py` through `test_step4_full_deploy.py`) let you verify each operation works before integrating into the full deployer.
