"""One-shot builder for the construction AI/ML notebooks.

Use case: project delay prediction (task delay, binary classification).
Target: had_delay (from is_delayed). Built-in PySpark RandomForestClassifier.
Grain: one row per task. Summary keyed by trade.

Run once:  python demos/construction/_build_ml_notebooks.py
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
    "    'planned_duration_days', 'budget', 'sub_rating', 'sub_years', 'sub_accredited_flag',\n"
    "]\n"
    "cat_cols = ['task_name', 'project_type', 'project_region', 'sub_trade']"
)

CSV = [
    ("subcontractors", "bronze_subcontractors"),
    ("projects", "bronze_projects"),
    ("tasks", "bronze_tasks"),
    ("cost_ledger", "bronze_cost_ledger"),
]

# ── batch/01_bronze_ingest ──────────────────────────────────────────────────
bronze_cells = [
    md("# Bronze Layer — Ingest Raw Construction Data\n"
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
    md("# Silver Layer — Clean & Conform Construction Data\n"
       "Dedupe, cast types. Keeps task label is_delayed; FE drops post-task leakage."),
    code("from pyspark.sql.functions import (\n"
         "    col, when, lit, to_date, row_number, current_timestamp\n"
         ")\n"
         "from pyspark.sql.window import Window"),
    code("# Clean subcontractors\n"
         "df_s = spark.read.format('delta').table('bronze_subcontractors')\n"
         "w = Window.partitionBy('subcontractor_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_s = (\n"
         "    df_s.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('rating', col('rating').cast('double'))\n"
         "    .withColumn('years_active', col('years_active').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_s.write.mode('overwrite').format('delta').saveAsTable('silver_subcontractors')\n"
         "print(f'silver_subcontractors: {df_s.count()} rows')"),
    code("# Clean projects\n"
         "df_p = spark.read.format('delta').table('bronze_projects')\n"
         "w2 = Window.partitionBy('project_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_p = (\n"
         "    df_p.withColumn('_rn', row_number().over(w2)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('budget', col('budget').cast('double'))\n"
         "    .withColumn('planned_start_date', to_date('planned_start_date'))\n"
         "    .withColumn('planned_end_date', to_date('planned_end_date'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_p.write.mode('overwrite').format('delta').saveAsTable('silver_projects')\n"
         "print(f'silver_projects: {df_p.count()} rows')"),
    code("# Clean tasks (keep label is_delayed)\n"
         "df_t = spark.read.format('delta').table('bronze_tasks')\n"
         "w3 = Window.partitionBy('task_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_t = (\n"
         "    df_t.withColumn('_rn', row_number().over(w3)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('planned_start_date', to_date('planned_start_date'))\n"
         "    .withColumn('planned_end_date', to_date('planned_end_date'))\n"
         "    .withColumn('planned_duration_days', col('planned_duration_days').cast('int'))\n"
         "    .withColumn('schedule_variance_days', col('schedule_variance_days').cast('int'))\n"
         "    .withColumn('is_delayed', col('is_delayed').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_t.write.mode('overwrite').format('delta').saveAsTable('silver_tasks')\n"
         "print(f'silver_tasks: {df_t.count()} rows')"),
    code("# Clean cost ledger\n"
         "df_c = spark.read.format('delta').table('bronze_cost_ledger')\n"
         "df_c = (\n"
         "    df_c\n"
         "    .withColumn('entry_date', to_date('entry_date'))\n"
         "    .withColumn('planned_cost', col('planned_cost').cast('double'))\n"
         "    .withColumn('actual_cost', col('actual_cost').cast('double'))\n"
         "    .withColumn('cost_variance_pct', col('cost_variance_pct').cast('double'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_c.write.mode('overwrite').format('delta').saveAsTable('silver_cost_ledger')\n"
         "print(f'silver_cost_ledger: {df_c.count()} rows')"),
])

# ── ml/01_feature_engineering ───────────────────────────────────────────────
write(ML / "01_feature_engineering.ipynb", [
    md("# Feature Engineering — Project Delay Prediction\n\n"
       "Joins each task with project + assigned-subcontractor attributes and derives\n"
       "pre-task features. EXCLUDES post-task leakage (actual_start_date, forecast_end_date,\n"
       "schedule_variance_days, status, pct_complete).\n\n"
       "**Reads:** `silver_tasks`, `silver_projects`, `silver_subcontractors`  "
       "**Writes:** `gold_ml_features`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "print('Spark session ready')"),
    code("tk = spark.read.table('silver_tasks')\n"
         "pr = spark.read.table('silver_projects')\n"
         "sb = spark.read.table('silver_subcontractors')\n"
         "print(f'tasks={tk.count():,} projects={pr.count():,} subcontractors={sb.count():,}')\n\n"
         "required = {'task_id', 'project_id', 'assigned_subcontractor_id', 'is_delayed', 'planned_duration_days'}\n"
         "missing = required - set(tk.columns)\n"
         "if missing:\n"
         "    raise ValueError(f'silver_tasks missing columns {sorted(missing)}. Regenerate data and rerun bronze/silver.')"),
    code("# Subcontractor attrs (rename to avoid clash with project.region / task fields).\n"
         "sub = sb.select(\n"
         "    col('subcontractor_id').alias('assigned_subcontractor_id'),\n"
         "    col('trade').alias('sub_trade'),\n"
         "    col('rating').alias('sub_rating'),\n"
         "    col('years_active').alias('sub_years'),\n"
         "    when(col('accredited') == 'Y', lit(1)).otherwise(lit(0)).alias('sub_accredited_flag'),\n"
         ")\n\n"
         "# Join attributes + select pre-task features. EXCLUDE leakage.\n"
         "ml_features = (\n"
         "    tk.select(\n"
         "        'task_id', 'project_id', 'assigned_subcontractor_id', 'task_name',\n"
         "        'planned_duration_days',\n"
         "        col('is_delayed').alias('had_delay'),\n"
         "    )\n"
         "    .join(pr.select('project_id', 'project_type',\n"
         "                    col('region').alias('project_region'), 'budget'),\n"
         "          'project_id', 'left')\n"
         "    .join(sub, 'assigned_subcontractor_id', 'left')\n"
         "    .na.fill(0)\n"
         "    .na.fill('unknown', subset=['task_name', 'project_type', 'project_region', 'sub_trade'])\n"
         "    .withColumn('feature_timestamp', current_timestamp())\n"
         ")\n\n"
         "total_rows = ml_features.count()\n"
         "positive_rows = ml_features.filter(col('had_delay') == 1).count()\n"
         "delay_rate = (positive_rows / total_rows * 100) if total_rows else 0.0\n\n"
         "if total_rows < 1000 or positive_rows < max(10, int(total_rows * 0.01)):\n"
         "    raise ValueError(\n"
         "        f'Label quality check failed: only {positive_rows}/{total_rows} delayed rows '\n"
         "        f'({delay_rate:.2f}%). Check is_delayed typing and source data.'\n"
         "    )\n\n"
         "ml_features.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_features')\n"
         "print(f'Gold ML features written: {total_rows:,} rows | delay rate {delay_rate:.1f}%')"),
    code("spark.sql('OPTIMIZE gold_ml_features')\n"
         "print('Feature table optimized')"),
])

# ── ml/02_model_training ────────────────────────────────────────────────────
write(ML / "02_model_training.ipynb", [
    md("# Model Training — Project Delay Prediction\n\n"
       "PySpark **RandomForest classifier** (built-in). Target `had_delay`.\n\n"
       "**Reads:** `gold_ml_features`  **Writes:** `gold_ml_model_metrics`, `Files/models/delay_rf`"),
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
         "df.groupBy('had_delay').count().show()"),
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_delay').cast('double').alias('label'))\n"
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
         "    [('construction', 'project-delay', 'RandomForestClassifier',\n"
         "      len(all_features), train_df.count(), test_df.count(),\n"
         "      float(auc), float(accuracy), float(f1))],\n"
         "    ['demo_id', 'use_case', 'model_type', 'feature_count',\n"
         "     'train_rows', 'test_rows', 'auc_roc', 'accuracy', 'f1_score']\n"
         ").withColumn('trained_at', current_timestamp())\n"
         "metrics.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_model_metrics')\n"
         "model.write().overwrite().save('Files/models/delay_rf')\n"
         "model_df.unpersist()\n"
         "print('Metrics + model saved')"),
])

# ── ml/03_model_evaluation ──────────────────────────────────────────────────
write(ML / "03_model_evaluation.ipynb", [
    md("# Model Evaluation — Project Delay Prediction\n\n"
       "Confusion matrix, precision/recall, feature importance.\n\n"
       "**Reads:** `gold_ml_features` + saved model  **Writes:** `gold_ml_feature_importance`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
         "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
         "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "model = RandomForestClassificationModel.load('Files/models/delay_rf')\n"
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_delay').cast('double').alias('label'))\n"
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
    md("# Batch Scoring — Project Delay Prediction\n\n"
       "Scores every task; writes predictions + per-trade delay risk summary.\n\n"
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
         "model = RandomForestClassificationModel.load('Files/models/delay_rf')\n"
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
         "    .withColumn('delay_probability', spark_round(extract_prob(col('probability')), 4))\n"
         "    .withColumn('predicted_delay', col('prediction').cast('int'))\n"
         "    .withColumn('risk_level',\n"
         "        when(col('delay_probability') > 0.8, 'critical')\n"
         "        .when(col('delay_probability') > 0.6, 'high')\n"
         "        .when(col('delay_probability') > 0.4, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('scored_at', current_timestamp())\n"
         "    .select(\n"
         "        'task_id', 'project_id', 'assigned_subcontractor_id', 'sub_trade', 'task_name', 'project_type',\n"
         "        'planned_duration_days', 'sub_rating',\n"
         "        'had_delay', 'predicted_delay', 'delay_probability', 'risk_level',\n"
         "        'scored_at')\n"
         ")\n"
         "predictions.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_predictions')\n"
         "print(f'Predictions written: {predictions.count():,} rows')\n"
         "predictions.groupBy('risk_level').count().orderBy('count', ascending=False).show()"),
    code("# Per-trade delay risk summary\n"
         "summary = (\n"
         "    predictions\n"
         "    .groupBy('sub_trade')\n"
         "    .agg(\n"
         "        count('*').alias('total_tasks'),\n"
         "        spark_sum('predicted_delay').alias('predicted_delay_count'),\n"
         "        spark_sum('had_delay').alias('actual_delay_count'),\n"
         "        spark_round(avg('delay_probability'), 4).alias('avg_delay_probability'),\n"
         "        spark_round(avg('planned_duration_days'), 1).alias('avg_duration_days'),\n"
         "        spark_round(avg('sub_rating'), 2).alias('avg_sub_rating'),\n"
         "    )\n"
         "    .withColumn('delay_rate', spark_round(col('predicted_delay_count') / col('total_tasks') * 100, 1))\n"
         "    .withColumn('overall_risk',\n"
         "        when(col('avg_delay_probability') > 0.6, 'high')\n"
         "        .when(col('avg_delay_probability') > 0.3, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('summary_timestamp', current_timestamp())\n"
         "    .withColumnRenamed('sub_trade', 'trade')\n"
         "    .orderBy(col('avg_delay_probability').desc())\n"
         ")\n"
         "summary.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_summary')\n"
         "print(f'Trade delay summary: {summary.count()} rows')\n"
         "summary.show(15, truncate=False)"),
    code("spark.sql('OPTIMIZE gold_ml_predictions')\n"
         "spark.sql('OPTIMIZE gold_ml_summary')\n"
         "print('All Gold ML tables optimized')"),
])

print("done")
