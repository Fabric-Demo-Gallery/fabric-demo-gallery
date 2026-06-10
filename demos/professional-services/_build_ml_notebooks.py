"""One-shot builder for the professional-services AI/ML notebooks.

Use case: project outcome prediction (budget overrun, binary classification).
Target: had_overrun (from is_over_budget). Built-in PySpark RandomForestClassifier.
Grain: one row per engagement. Summary keyed by practice.

Run once:  python demos/professional-services/_build_ml_notebooks.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BATCH = ROOT / "notebooks" / "batch"
ML = ROOT / "notebooks" / "ml"
BATCH.mkdir(parents=True, exist_ok=True)
ML.mkdir(parents=True, exist_ok=True)


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def notebook(cells: list[dict]) -> dict:
    return {"cells": cells, "metadata": {"language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5}


def write(path: Path, cells: list[dict]) -> None:
    path.write_text(json.dumps(notebook(cells), indent=1), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


FEATURE_DEFS = (
    "numeric_features = [\n"
    "    'budget_gbp', 'headcount', 'planned_duration_days', 'contract_value_gbp',\n"
    "    'relationship_years', 'nps_score', 'lead_experience', 'lead_daily_rate',\n"
    "]\n"
    "cat_cols = ['practice', 'industry', 'tier', 'region', 'lead_grade']"
)

CSV = [
    ("clients", "bronze_clients"),
    ("consultants", "bronze_consultants"),
    ("engagements", "bronze_engagements"),
    ("timesheets", "bronze_timesheets"),
]

# ── batch/01_bronze_ingest ──────────────────────────────────────────────────
bronze_cells = [
    md("# Bronze Layer — Ingest Raw Professional-Services Data\n"
       "Reads CSV files from lakehouse `{{DATA_SOURCE_PATH}}/` and writes Delta tables with metadata columns."),
    code("from pyspark.sql.functions import current_timestamp, input_file_name, lit\n"
         "import uuid\n\n"
         "ingestion_batch_id = str(uuid.uuid4())"),
]
for csv_name, tbl in CSV:
    bronze_cells.append(code(
        f"# Ingest {csv_name}\n"
        f"df = (\n"
        f"    spark.read.format('csv').option('header', True).option('inferSchema', True)\n"
        f"    .load('{{{{DATA_SOURCE_PATH}}}}/{csv_name}.csv')\n"
        f"    .withColumn('ingestion_timestamp', current_timestamp())\n"
        f"    .withColumn('source_file', input_file_name())\n"
        f"    .withColumn('ingestion_batch_id', lit(ingestion_batch_id))\n"
        f")\n"
        f"df.write.mode('overwrite').format('delta').saveAsTable('{tbl}')\n"
        f"print(f'{tbl}: {{df.count()}} rows')"
    ))
write(BATCH / "01_bronze_ingest.ipynb", bronze_cells)

# ── batch/02_silver_transform ───────────────────────────────────────────────
write(BATCH / "02_silver_transform.ipynb", [
    md("# Silver Layer — Clean & Conform Professional-Services Data\n"
       "Dedupe, cast types. Keeps engagement label is_over_budget; FE drops post-project leakage."),
    code("from pyspark.sql.functions import (\n"
         "    col, when, lit, to_date, row_number, current_timestamp\n"
         ")\n"
         "from pyspark.sql.window import Window"),
    code("# Clean clients\n"
         "df_c = spark.read.format('delta').table('bronze_clients')\n"
         "w = Window.partitionBy('client_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_c = (\n"
         "    df_c.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('contract_value_gbp', col('contract_value_gbp').cast('double'))\n"
         "    .withColumn('relationship_years', col('relationship_years').cast('int'))\n"
         "    .withColumn('nps_score', col('nps_score').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_c.write.mode('overwrite').format('delta').saveAsTable('silver_clients')\n"
         "print(f'silver_clients: {df_c.count()} rows')"),
    code("# Clean consultants\n"
         "df_n = spark.read.format('delta').table('bronze_consultants')\n"
         "w2 = Window.partitionBy('consultant_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_n = (\n"
         "    df_n.withColumn('_rn', row_number().over(w2)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('daily_rate_gbp', col('daily_rate_gbp').cast('double'))\n"
         "    .withColumn('years_experience', col('years_experience').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_n.write.mode('overwrite').format('delta').saveAsTable('silver_consultants')\n"
         "print(f'silver_consultants: {df_n.count()} rows')"),
    code("# Clean engagements (keep label is_over_budget)\n"
         "df_e = spark.read.format('delta').table('bronze_engagements')\n"
         "w3 = Window.partitionBy('engagement_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_e = (\n"
         "    df_e.withColumn('_rn', row_number().over(w3)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('start_date', to_date('start_date'))\n"
         "    .withColumn('planned_end_date', to_date('planned_end_date'))\n"
         "    .withColumn('budget_gbp', col('budget_gbp').cast('double'))\n"
         "    .withColumn('headcount', col('headcount').cast('int'))\n"
         "    .withColumn('planned_duration_days', col('planned_duration_days').cast('int'))\n"
         "    .withColumn('is_over_budget', col('is_over_budget').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_e.write.mode('overwrite').format('delta').saveAsTable('silver_engagements')\n"
         "print(f'silver_engagements: {df_e.count()} rows')"),
    code("# Clean timesheets\n"
         "df_t = spark.read.format('delta').table('bronze_timesheets')\n"
         "df_t = (\n"
         "    df_t\n"
         "    .withColumn('week_starting', to_date('week_starting'))\n"
         "    .withColumn('hours_logged', col('hours_logged').cast('double'))\n"
         "    .withColumn('billed_value_gbp', col('billed_value_gbp').cast('double'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_t.write.mode('overwrite').format('delta').saveAsTable('silver_timesheets')\n"
         "print(f'silver_timesheets: {df_t.count()} rows')"),
])

# ── ml/01_feature_engineering ───────────────────────────────────────────────
write(ML / "01_feature_engineering.ipynb", [
    md("# Feature Engineering — Project Outcome Prediction\n\n"
       "Joins each engagement with client + lead-consultant attributes and derives\n"
       "pre-project features. EXCLUDES post-project leakage (actual_spend_gbp, margin_pct, status).\n\n"
       "**Reads:** `silver_engagements`, `silver_clients`, `silver_consultants`  "
       "**Writes:** `gold_ml_features`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "print('Spark session ready')"),
    code("eng = spark.read.table('silver_engagements')\n"
         "cl = spark.read.table('silver_clients')\n"
         "cn = spark.read.table('silver_consultants')\n"
         "print(f'engagements={eng.count():,} clients={cl.count():,} consultants={cn.count():,}')\n\n"
         "required = {'engagement_id', 'client_id', 'lead_consultant_id', 'is_over_budget', 'budget_gbp'}\n"
         "missing = required - set(eng.columns)\n"
         "if missing:\n"
         "    raise ValueError(f'silver_engagements missing columns {sorted(missing)}. Regenerate data and rerun bronze/silver.')"),
    code("# Lead consultant attrs (rename to avoid clash with engagement.practice / client.region).\n"
         "lead = cn.select(\n"
         "    col('consultant_id').alias('lead_consultant_id'),\n"
         "    col('grade').alias('lead_grade'),\n"
         "    col('years_experience').alias('lead_experience'),\n"
         "    col('daily_rate_gbp').alias('lead_daily_rate'),\n"
         ")\n\n"
         "# Join attributes + select pre-project features. EXCLUDE leakage (actual_spend_gbp, margin_pct, status).\n"
         "ml_features = (\n"
         "    eng.select(\n"
         "        'engagement_id', 'client_id', 'lead_consultant_id', 'practice',\n"
         "        'budget_gbp', 'headcount', 'planned_duration_days',\n"
         "        col('is_over_budget').alias('had_overrun'),\n"
         "    )\n"
         "    .join(cl.select('client_id', 'industry', 'tier', 'region',\n"
         "                    'contract_value_gbp', 'relationship_years', 'nps_score'),\n"
         "          'client_id', 'left')\n"
         "    .join(lead, 'lead_consultant_id', 'left')\n"
         "    .na.fill(0)\n"
         "    .na.fill('unknown', subset=['practice', 'industry', 'tier', 'region', 'lead_grade'])\n"
         "    .withColumn('feature_timestamp', current_timestamp())\n"
         ")\n\n"
         "total_rows = ml_features.count()\n"
         "positive_rows = ml_features.filter(col('had_overrun') == 1).count()\n"
         "overrun_rate = (positive_rows / total_rows * 100) if total_rows else 0.0\n\n"
         "if total_rows < 1000 or positive_rows < max(10, int(total_rows * 0.01)):\n"
         "    raise ValueError(\n"
         "        f'Label quality check failed: only {positive_rows}/{total_rows} overrun rows '\n"
         "        f'({overrun_rate:.2f}%). Check is_over_budget typing and source data.'\n"
         "    )\n\n"
         "ml_features.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_features')\n"
         "print(f'Gold ML features written: {total_rows:,} rows | overrun rate {overrun_rate:.1f}%')"),
    code("spark.sql('OPTIMIZE gold_ml_features')\n"
         "print('Feature table optimized')"),
])

# ── ml/02_model_training ────────────────────────────────────────────────────
write(ML / "02_model_training.ipynb", [
    md("# Model Training — Project Outcome Prediction\n\n"
       "PySpark **RandomForest classifier** (built-in). Target `had_overrun`.\n\n"
       "**Reads:** `gold_ml_features`  **Writes:** `gold_ml_model_metrics`, `Files/models/overrun_rf`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
         "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
         "from pyspark.ml.classification import RandomForestClassifier\n"
         "from pyspark.ml.evaluation import BinaryClassificationEvaluator, MulticlassClassificationEvaluator\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "print('Spark session ready')"),
    code("df = spark.read.table('gold_ml_features')\n"
         "print(f'Feature rows: {df.count():,}')\n"
         "for c, dtype in df.dtypes:\n"
         "    if dtype in ('double', 'float'):\n"
         "        df = df.withColumn(c, when(col(c).isNull() | isnan(col(c)), lit(0.0)).otherwise(col(c)))\n"
         "    elif dtype in ('int', 'bigint', 'long'):\n"
         "        df = df.withColumn(c, when(col(c).isNull(), lit(0)).otherwise(col(c)))\n"
         "df.groupBy('had_overrun').count().show()"),
    code(FEATURE_DEFS + "\n\n"
         "indexed_df = df\n"
         "cat_idx_cols = []\n"
         "for c in cat_cols:\n"
         "    idx_col = f'{c}_idx'\n"
         "    indexer = StringIndexer(inputCol=c, outputCol=idx_col, handleInvalid='keep')\n"
         "    indexed_df = indexer.fit(indexed_df).transform(indexed_df)\n"
         "    cat_idx_cols.append(idx_col)\n\n"
         "all_features = numeric_features + cat_idx_cols\n"
         "assembler = VectorAssembler(inputCols=all_features, outputCol='features', handleInvalid='keep')\n"
         "model_df = assembler.transform(indexed_df).select('features', col('had_overrun').cast('double').alias('label'))\n"
         "model_df = model_df.cache()\n"
         "print(f'Model rows: {model_df.count():,} | features: {len(all_features)}')"),
    code("train_df, test_df = model_df.randomSplit([0.8, 0.2], seed=42)\n"
         "print(f'Train: {train_df.count():,}  Test: {test_df.count():,}')"),
    code("rf = RandomForestClassifier(\n"
         "    featuresCol='features', labelCol='label',\n"
         "    predictionCol='prediction', rawPredictionCol='rawPrediction', probabilityCol='probability',\n"
         "    numTrees=120, maxDepth=10, seed=42,\n"
         ")\n"
         "model = rf.fit(train_df)\n"
         "print('RandomForest classifier trained')"),
    code("predictions = model.transform(test_df)\n"
         "auc = BinaryClassificationEvaluator(labelCol='label', rawPredictionCol='rawPrediction', metricName='areaUnderROC').evaluate(predictions)\n"
         "accuracy = MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='accuracy').evaluate(predictions)\n"
         "f1 = MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='f1').evaluate(predictions)\n"
         "print(f'AUC-ROC: {auc:.4f}  Accuracy: {accuracy:.4f}  F1: {f1:.4f}')"),
    code("metrics = spark.createDataFrame(\n"
         "    [('professional-services', 'project-overrun', 'RandomForestClassifier',\n"
         "      len(all_features), train_df.count(), test_df.count(),\n"
         "      float(auc), float(accuracy), float(f1))],\n"
         "    ['demo_id', 'use_case', 'model_type', 'feature_count',\n"
         "     'train_rows', 'test_rows', 'auc_roc', 'accuracy', 'f1_score']\n"
         ").withColumn('trained_at', current_timestamp())\n"
         "metrics.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_model_metrics')\n"
         "model.write().overwrite().save('Files/models/overrun_rf')\n"
         "model_df.unpersist()\n"
         "print('Metrics + model saved')"),
])

# ── ml/03_model_evaluation ──────────────────────────────────────────────────
write(ML / "03_model_evaluation.ipynb", [
    md("# Model Evaluation — Project Outcome Prediction\n\n"
       "Confusion matrix, precision/recall, feature importance.\n\n"
       "**Reads:** `gold_ml_features` + saved model  **Writes:** `gold_ml_feature_importance`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
         "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
         "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "model = RandomForestClassificationModel.load('Files/models/overrun_rf')\n"
         "print('Model loaded')"),
    code("df = spark.read.table('gold_ml_features')\n"
         "for c, dtype in df.dtypes:\n"
         "    if dtype in ('double', 'float'):\n"
         "        df = df.withColumn(c, when(col(c).isNull() | isnan(col(c)), lit(0.0)).otherwise(col(c)))\n"
         "    elif dtype in ('int', 'bigint', 'long'):\n"
         "        df = df.withColumn(c, when(col(c).isNull(), lit(0)).otherwise(col(c)))\n\n"
         + FEATURE_DEFS + "\n"
         "indexed_df = df\n"
         "cat_idx_cols = []\n"
         "for c in cat_cols:\n"
         "    idx_col = f'{c}_idx'\n"
         "    indexer = StringIndexer(inputCol=c, outputCol=idx_col, handleInvalid='keep')\n"
         "    indexed_df = indexer.fit(indexed_df).transform(indexed_df)\n"
         "    cat_idx_cols.append(idx_col)\n\n"
         "all_features = numeric_features + cat_idx_cols\n"
         "assembler = VectorAssembler(inputCols=all_features, outputCol='features', handleInvalid='keep')\n"
         "model_df = assembler.transform(indexed_df).select('features', col('had_overrun').cast('double').alias('label'))\n"
         "_, test_df = model_df.randomSplit([0.8, 0.2], seed=42)\n"
         "predictions = model.transform(test_df)\n"
         "print(f'Test predictions: {predictions.count():,} rows')"),
    code("print('=== Confusion Matrix ===')\n"
         "predictions.groupBy('label', 'prediction').count().orderBy('label', 'prediction').show()\n"
         "tp = predictions.filter((col('label') == 1) & (col('prediction') == 1)).count()\n"
         "fp = predictions.filter((col('label') == 0) & (col('prediction') == 1)).count()\n"
         "fn = predictions.filter((col('label') == 1) & (col('prediction') == 0)).count()\n"
         "tn = predictions.filter((col('label') == 0) & (col('prediction') == 0)).count()\n"
         "precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0\n"
         "recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0\n"
         "print(f'TP={tp} FP={fp} FN={fn} TN={tn}')\n"
         "print(f'Precision: {precision:.4f}  Recall: {recall:.4f}')"),
    code("importances = model.featureImportances.toArray()\n"
         "rows = sorted(\n"
         "    zip(all_features, [float(importances[i]) if i < len(importances) else 0.0\n"
         "                       for i in range(len(all_features))]),\n"
         "    key=lambda r: r[1], reverse=True,\n"
         ")\n"
         "print('=== Top 10 Features ===')\n"
         "for name, imp in rows[:10]:\n"
         "    print(f'  {name:30s} {imp:.4f}')\n"
         "fi_spark = spark.createDataFrame(rows, ['feature', 'importance']).withColumn('model_timestamp', current_timestamp())\n"
         "fi_spark.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_feature_importance')\n"
         "print('Feature importance saved')"),
    code("spark.sql('OPTIMIZE gold_ml_feature_importance')\n"
         "print('Evaluation complete')"),
])

# ── ml/04_batch_scoring ─────────────────────────────────────────────────────
write(ML / "04_batch_scoring.ipynb", [
    md("# Batch Scoring — Project Outcome Prediction\n\n"
       "Scores every engagement; writes predictions + per-practice overrun risk summary.\n\n"
       "**Reads:** `gold_ml_features` + saved model  **Writes:** `gold_ml_predictions`, `gold_ml_summary`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import (\n"
         "    col, lit, current_timestamp, when, avg, count, isnan, udf,\n"
         "    sum as spark_sum, round as spark_round\n"
         ")\n"
         "from pyspark.sql.types import DoubleType\n"
         "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
         "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "model = RandomForestClassificationModel.load('Files/models/overrun_rf')\n"
         "df = spark.read.table('gold_ml_features')\n"
         "print(f'Scoring {df.count():,} feature rows')"),
    code("for c, dtype in df.dtypes:\n"
         "    if dtype in ('double', 'float'):\n"
         "        df = df.withColumn(c, when(col(c).isNull() | isnan(col(c)), lit(0.0)).otherwise(col(c)))\n"
         "    elif dtype in ('int', 'bigint', 'long'):\n"
         "        df = df.withColumn(c, when(col(c).isNull(), lit(0)).otherwise(col(c)))\n\n"
         + FEATURE_DEFS + "\n"
         "indexed_df = df\n"
         "for c in cat_cols:\n"
         "    idx_col = f'{c}_idx'\n"
         "    indexer = StringIndexer(inputCol=c, outputCol=idx_col, handleInvalid='keep')\n"
         "    indexed_df = indexer.fit(indexed_df).transform(indexed_df)\n\n"
         "all_features = numeric_features + [f'{c}_idx' for c in cat_cols]\n"
         "assembler = VectorAssembler(inputCols=all_features, outputCol='features', handleInvalid='keep')\n"
         "model_df = assembler.transform(indexed_df)"),
    code("scored = model.transform(model_df)\n"
         "extract_prob = udf(lambda v: float(v[1]) if v is not None and len(v) > 1 else 0.0, DoubleType())\n\n"
         "predictions = (\n"
         "    scored\n"
         "    .withColumn('overrun_probability', spark_round(extract_prob(col('probability')), 4))\n"
         "    .withColumn('predicted_overrun', col('prediction').cast('int'))\n"
         "    .withColumn('risk_level',\n"
         "        when(col('overrun_probability') > 0.8, 'critical')\n"
         "        .when(col('overrun_probability') > 0.6, 'high')\n"
         "        .when(col('overrun_probability') > 0.4, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('scored_at', current_timestamp())\n"
         "    .select(\n"
         "        'engagement_id', 'client_id', 'lead_consultant_id', 'practice', 'industry', 'tier',\n"
         "        'budget_gbp', 'headcount', 'planned_duration_days',\n"
         "        'had_overrun', 'predicted_overrun', 'overrun_probability', 'risk_level',\n"
         "        'scored_at')\n"
         ")\n"
         "predictions.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_predictions')\n"
         "print(f'Predictions written: {predictions.count():,} rows')\n"
         "predictions.groupBy('risk_level').count().orderBy('count', ascending=False).show()"),
    code("# Per-practice overrun risk summary\n"
         "summary = (\n"
         "    predictions\n"
         "    .groupBy('practice')\n"
         "    .agg(\n"
         "        count('*').alias('total_engagements'),\n"
         "        spark_sum('predicted_overrun').alias('predicted_overrun_count'),\n"
         "        spark_sum('had_overrun').alias('actual_overrun_count'),\n"
         "        spark_round(avg('overrun_probability'), 4).alias('avg_overrun_probability'),\n"
         "        spark_round(avg('budget_gbp'), 2).alias('avg_budget_gbp'),\n"
         "        spark_round(avg('planned_duration_days'), 1).alias('avg_duration_days'),\n"
         "    )\n"
         "    .withColumn('overrun_rate', spark_round(col('predicted_overrun_count') / col('total_engagements') * 100, 1))\n"
         "    .withColumn('overall_risk',\n"
         "        when(col('avg_overrun_probability') > 0.6, 'high')\n"
         "        .when(col('avg_overrun_probability') > 0.3, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('summary_timestamp', current_timestamp())\n"
         "    .orderBy(col('avg_overrun_probability').desc())\n"
         ")\n"
         "summary.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_summary')\n"
         "print(f'Practice overrun summary: {summary.count()} rows')\n"
         "summary.show(15, truncate=False)"),
    code("spark.sql('OPTIMIZE gold_ml_predictions')\n"
         "spark.sql('OPTIMIZE gold_ml_summary')\n"
         "print('All Gold ML tables optimized')"),
])

print("done")
