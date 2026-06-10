"""One-shot builder for the technology (SaaS) AI/ML notebooks.

Use case: account churn prediction (binary classification).
Target: had_churn (from is_churned). Built-in PySpark RandomForestClassifier.

Run once:  python demos/technology/_build_ml_notebooks.py
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


# Shared feature lists (used by 02/03/04).
FEATURE_DEFS = (
    "numeric_features = [\n"
    "    'mrr_usd', 'seat_count', 'tenure_days', 'health_score',\n"
    "    'user_count', 'active_user_count', 'avg_logins_30d',\n"
    "    'event_count', 'distinct_features', 'avg_duration',\n"
    "    'ticket_count', 'sla_breach_count', 'avg_csat', 'avg_resolution_hrs',\n"
    "]\n"
    "cat_cols = ['plan', 'industry', 'region']"
)

CSV = [
    ("accounts", "bronze_accounts"),
    ("users", "bronze_users"),
    ("events", "bronze_events"),
    ("support_tickets", "bronze_support_tickets"),
]

# ── batch/01_bronze_ingest ──────────────────────────────────────────────────
bronze_cells = [
    md("# Bronze Layer — Ingest Raw SaaS Data\n"
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
    md("# Silver Layer — Clean & Conform SaaS Data\n"
       "Dedupe accounts/users, derive tenure and engagement bands. NO churn-derived flags (avoids leakage)."),
    code("from pyspark.sql.functions import (\n"
         "    col, when, lit, to_timestamp, to_date, datediff, current_date,\n"
         "    row_number, current_timestamp\n"
         ")\n"
         "from pyspark.sql.window import Window"),
    code("# Clean accounts (dedupe, derive tenure_days). Keep is_churned; drop churn_date leakage downstream in FE.\n"
         "df_acc = spark.read.format('delta').table('bronze_accounts')\n"
         "w = Window.partitionBy('account_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_acc = (\n"
         "    df_acc.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('signup_date', to_date('signup_date'))\n"
         "    .withColumn('mrr_usd', col('mrr_usd').cast('double'))\n"
         "    .withColumn('seat_count', col('seat_count').cast('int'))\n"
         "    .withColumn('health_score', col('health_score').cast('double'))\n"
         "    .withColumn('is_churned', col('is_churned').cast('int'))\n"
         "    .withColumn('tenure_days', datediff(current_date(), col('signup_date')))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_acc.write.mode('overwrite').format('delta').saveAsTable('silver_accounts')\n"
         "print(f'silver_accounts: {df_acc.count()} rows')"),
    code("# Clean users\n"
         "df_usr = spark.read.format('delta').table('bronze_users')\n"
         "w2 = Window.partitionBy('user_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_usr = (\n"
         "    df_usr.withColumn('_rn', row_number().over(w2)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('is_active', col('is_active').cast('int'))\n"
         "    .withColumn('logins_last_30_days', col('logins_last_30_days').cast('int'))\n"
         "    .withColumn('last_login_date', to_date('last_login_date'))\n"
         "    .withColumn('engagement_band',\n"
         "        when(col('logins_last_30_days') >= 20, 'Power User')\n"
         "        .when(col('logins_last_30_days') >= 10, 'Regular')\n"
         "        .when(col('logins_last_30_days') >= 1, 'Occasional')\n"
         "        .otherwise('Dormant'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_usr.write.mode('overwrite').format('delta').saveAsTable('silver_users')\n"
         "print(f'silver_users: {df_usr.count()} rows')"),
    code("# Clean events\n"
         "df_ev = spark.read.format('delta').table('bronze_events')\n"
         "df_ev = (\n"
         "    df_ev\n"
         "    .withColumn('event_date', to_date('event_date'))\n"
         "    .withColumn('duration_secs', col('duration_secs').cast('double'))\n"
         "    .filter(col('event_date').isNotNull())\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_ev.write.mode('overwrite').format('delta').saveAsTable('silver_events')\n"
         "print(f'silver_events: {df_ev.count()} rows')"),
    code("# Clean support tickets\n"
         "df_tk = spark.read.format('delta').table('bronze_support_tickets')\n"
         "df_tk = (\n"
         "    df_tk\n"
         "    .withColumn('created_at', to_timestamp('created_at'))\n"
         "    .withColumn('resolution_hrs', col('resolution_hrs').cast('double'))\n"
         "    .withColumn('sla_target_hrs', col('sla_target_hrs').cast('double'))\n"
         "    .withColumn('is_sla_breached', col('is_sla_breached').cast('int'))\n"
         "    .withColumn('csat_score', col('csat_score').cast('double'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_tk.write.mode('overwrite').format('delta').saveAsTable('silver_support_tickets')\n"
         "print(f'silver_support_tickets: {df_tk.count()} rows')"),
])

# ── ml/01_feature_engineering ───────────────────────────────────────────────
write(ML / "01_feature_engineering.ipynb", [
    md("# Feature Engineering — Account Churn Prediction\n\n"
       "Aggregates users/events/support per account and joins account attributes\n"
       "to build a per-account feature table for churn classification.\n\n"
       "**Reads:** `silver_accounts`, `silver_users`, `silver_events`, `silver_support_tickets`  "
       "**Writes:** `gold_ml_features`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import (\n"
         "    col, lit, current_timestamp, when, count, avg, countDistinct,\n"
         "    sum as spark_sum\n"
         ")\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "print('Spark session ready')"),
    code("acc = spark.read.table('silver_accounts')\n"
         "usr = spark.read.table('silver_users')\n"
         "ev = spark.read.table('silver_events')\n"
         "tk = spark.read.table('silver_support_tickets')\n"
         "print(f'accounts={acc.count():,} users={usr.count():,} events={ev.count():,} tickets={tk.count():,}')\n\n"
         "required = {'account_id', 'is_churned', 'health_score', 'mrr_usd'}\n"
         "missing = required - set(acc.columns)\n"
         "if missing:\n"
         "    raise ValueError(f'silver_accounts missing columns {sorted(missing)}. Regenerate data and rerun bronze/silver.')"),
    code("# Per-account aggregates\n"
         "u = usr.groupBy('account_id').agg(\n"
         "    count('*').alias('user_count'),\n"
         "    spark_sum('is_active').alias('active_user_count'),\n"
         "    avg('logins_last_30_days').alias('avg_logins_30d'))\n"
         "e = ev.groupBy('account_id').agg(\n"
         "    count('*').alias('event_count'),\n"
         "    countDistinct('feature').alias('distinct_features'),\n"
         "    avg('duration_secs').alias('avg_duration'))\n"
         "t = tk.groupBy('account_id').agg(\n"
         "    count('*').alias('ticket_count'),\n"
         "    spark_sum('is_sla_breached').alias('sla_breach_count'),\n"
         "    avg('csat_score').alias('avg_csat'),\n"
         "    avg('resolution_hrs').alias('avg_resolution_hrs'))"),
    code("# Join account attributes + aggregates. EXCLUDE churn_date leakage; label = is_churned.\n"
         "ml_features = (\n"
         "    acc.select(\n"
         "        'account_id', 'plan', 'industry', 'region',\n"
         "        'mrr_usd', 'seat_count', 'health_score', 'tenure_days',\n"
         "        col('is_churned').alias('had_churn'),\n"
         "    )\n"
         "    .join(u, 'account_id', 'left')\n"
         "    .join(e, 'account_id', 'left')\n"
         "    .join(t, 'account_id', 'left')\n"
         "    .na.fill(0, ['user_count', 'active_user_count', 'avg_logins_30d', 'event_count',\n"
         "                 'distinct_features', 'avg_duration', 'ticket_count', 'sla_breach_count',\n"
         "                 'avg_csat', 'avg_resolution_hrs'])\n"
         "    .na.fill('unknown', subset=['plan', 'industry', 'region'])\n"
         "    .withColumn('feature_timestamp', current_timestamp())\n"
         ")\n\n"
         "total_rows = ml_features.count()\n"
         "positive_rows = ml_features.filter(col('had_churn') == 1).count()\n"
         "churn_rate = (positive_rows / total_rows * 100) if total_rows else 0.0\n\n"
         "if total_rows < 500 or positive_rows < max(10, int(total_rows * 0.01)):\n"
         "    raise ValueError(\n"
         "        f'Label quality check failed: only {positive_rows}/{total_rows} churn rows '\n"
         "        f'({churn_rate:.2f}%). Check is_churned typing and source data.'\n"
         "    )\n\n"
         "ml_features.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_features')\n"
         "print(f'Gold ML features written: {total_rows:,} rows | churn rate {churn_rate:.1f}%')"),
    code("spark.sql('OPTIMIZE gold_ml_features')\n"
         "print('Feature table optimized')"),
])

# ── ml/02_model_training ────────────────────────────────────────────────────
write(ML / "02_model_training.ipynb", [
    md("# Model Training — Account Churn Prediction\n\n"
       "PySpark **RandomForest classifier** (built-in). Target `had_churn`.\n\n"
       "**Reads:** `gold_ml_features`  **Writes:** `gold_ml_model_metrics`, `Files/models/churn_rf`"),
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
         "df.groupBy('had_churn').count().show()"),
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_churn').cast('double').alias('label'))\n"
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
         "    [('technology', 'churn-prediction', 'RandomForestClassifier',\n"
         "      len(all_features), train_df.count(), test_df.count(),\n"
         "      float(auc), float(accuracy), float(f1))],\n"
         "    ['demo_id', 'use_case', 'model_type', 'feature_count',\n"
         "     'train_rows', 'test_rows', 'auc_roc', 'accuracy', 'f1_score']\n"
         ").withColumn('trained_at', current_timestamp())\n"
         "metrics.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_model_metrics')\n"
         "model.write().overwrite().save('Files/models/churn_rf')\n"
         "model_df.unpersist()\n"
         "print('Metrics + model saved')"),
])

# ── ml/03_model_evaluation ──────────────────────────────────────────────────
write(ML / "03_model_evaluation.ipynb", [
    md("# Model Evaluation — Account Churn Prediction\n\n"
       "Confusion matrix, precision/recall, feature importance.\n\n"
       "**Reads:** `gold_ml_features` + saved model  **Writes:** `gold_ml_feature_importance`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
         "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
         "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "model = RandomForestClassificationModel.load('Files/models/churn_rf')\n"
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_churn').cast('double').alias('label'))\n"
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
    md("# Batch Scoring — Account Churn Prediction\n\n"
       "Scores every account; writes predictions + per-industry churn risk summary.\n\n"
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
         "model = RandomForestClassificationModel.load('Files/models/churn_rf')\n"
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
         "    .withColumn('churn_probability', spark_round(extract_prob(col('probability')), 4))\n"
         "    .withColumn('predicted_churn', col('prediction').cast('int'))\n"
         "    .withColumn('risk_level',\n"
         "        when(col('churn_probability') > 0.8, 'critical')\n"
         "        .when(col('churn_probability') > 0.6, 'high')\n"
         "        .when(col('churn_probability') > 0.4, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('scored_at', current_timestamp())\n"
         "    .select(\n"
         "        'account_id', 'plan', 'industry', 'region',\n"
         "        'mrr_usd', 'health_score', 'avg_logins_30d', 'avg_csat',\n"
         "        'had_churn', 'predicted_churn', 'churn_probability', 'risk_level',\n"
         "        'scored_at')\n"
         ")\n"
         "predictions.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_predictions')\n"
         "print(f'Predictions written: {predictions.count():,} rows')\n"
         "predictions.groupBy('risk_level').count().orderBy('count', ascending=False).show()"),
    code("# Per-industry churn risk summary\n"
         "summary = (\n"
         "    predictions\n"
         "    .groupBy('industry')\n"
         "    .agg(\n"
         "        count('*').alias('total_accounts'),\n"
         "        spark_sum('predicted_churn').alias('predicted_churn_count'),\n"
         "        spark_sum('had_churn').alias('actual_churn_count'),\n"
         "        spark_round(avg('churn_probability'), 4).alias('avg_churn_probability'),\n"
         "        spark_round(spark_sum('mrr_usd'), 0).alias('total_mrr'),\n"
         "        spark_round(avg('health_score'), 1).alias('avg_health_score'),\n"
         "    )\n"
         "    .withColumn('churn_rate', spark_round(col('predicted_churn_count') / col('total_accounts') * 100, 1))\n"
         "    .withColumn('overall_risk',\n"
         "        when(col('avg_churn_probability') > 0.6, 'high')\n"
         "        .when(col('avg_churn_probability') > 0.3, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('summary_timestamp', current_timestamp())\n"
         "    .orderBy(col('avg_churn_probability').desc())\n"
         ")\n"
         "summary.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_summary')\n"
         "print(f'Industry churn summary: {summary.count()} rows')\n"
         "summary.show(15, truncate=False)"),
    code("spark.sql('OPTIMIZE gold_ml_predictions')\n"
         "spark.sql('OPTIMIZE gold_ml_summary')\n"
         "print('All Gold ML tables optimized')"),
])

print("done")
