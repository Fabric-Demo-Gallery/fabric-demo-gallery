"""One-shot builder for the financial-services AI/ML notebooks.

Writes 2 batch notebooks (bronze, silver) + 4 ML notebooks (feature engineering,
training, evaluation, batch scoring) as valid Jupyter JSON. Uses built-in PySpark
ML (RandomForestClassifier) — no SynapseML dependency — matching the proven
manufacturing/energy/retail pattern.

Run once:  python demos/financial-services/_build_ml_notebooks.py
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
    return {
        "cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
        "source": text.strip("\n").splitlines(keepends=True),
    }


def notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }


def write(path: Path, cells: list[dict]) -> None:
    path.write_text(json.dumps(notebook(cells), indent=1), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


# ── batch/01_bronze_ingest ──────────────────────────────────────────────────
write(BATCH / "01_bronze_ingest.ipynb", [
    md("# Bronze Layer — Ingest Raw Financial Data\n"
       "Reads CSV files from lakehouse `{{DATA_SOURCE_PATH}}/` and writes Delta tables with metadata columns."),
    code(
        "from pyspark.sql.functions import current_timestamp, input_file_name, lit\n"
        "import uuid\n\n"
        "ingestion_batch_id = str(uuid.uuid4())"
    ),
    code(
        "# Ingest customers\n"
        "df_customers = (\n"
        "    spark.read.format('csv')\n"
        "    .option('header', True)\n"
        "    .option('inferSchema', True)\n"
        "    .load('{{DATA_SOURCE_PATH}}/customers.csv')\n"
        "    .withColumn('ingestion_timestamp', current_timestamp())\n"
        "    .withColumn('source_file', input_file_name())\n"
        "    .withColumn('ingestion_batch_id', lit(ingestion_batch_id))\n"
        ")\n"
        "df_customers.write.mode('overwrite').format('delta').saveAsTable('bronze_customers')\n"
        "print(f'Bronze customers: {df_customers.count()} rows')"
    ),
    code(
        "# Ingest accounts\n"
        "df_accounts = (\n"
        "    spark.read.format('csv')\n"
        "    .option('header', True)\n"
        "    .option('inferSchema', True)\n"
        "    .load('{{DATA_SOURCE_PATH}}/accounts.csv')\n"
        "    .withColumn('ingestion_timestamp', current_timestamp())\n"
        "    .withColumn('source_file', input_file_name())\n"
        "    .withColumn('ingestion_batch_id', lit(ingestion_batch_id))\n"
        ")\n"
        "df_accounts.write.mode('overwrite').format('delta').saveAsTable('bronze_accounts')\n"
        "print(f'Bronze accounts: {df_accounts.count()} rows')"
    ),
    code(
        "# Ingest transactions\n"
        "df_transactions = (\n"
        "    spark.read.format('csv')\n"
        "    .option('header', True)\n"
        "    .option('inferSchema', True)\n"
        "    .load('{{DATA_SOURCE_PATH}}/transactions.csv')\n"
        "    .withColumn('ingestion_timestamp', current_timestamp())\n"
        "    .withColumn('source_file', input_file_name())\n"
        "    .withColumn('ingestion_batch_id', lit(ingestion_batch_id))\n"
        ")\n"
        "df_transactions.write.mode('overwrite').format('delta').saveAsTable('bronze_transactions')\n"
        "print(f'Bronze transactions: {df_transactions.count()} rows')"
    ),
])

# ── batch/02_silver_transform ───────────────────────────────────────────────
write(BATCH / "02_silver_transform.ipynb", [
    md("# Silver Layer — Clean & Risk-Flag Financial Data\n"
       "Validate transactions, deduplicate accounts, derive credit-utilisation bands and basic risk indicators."),
    code(
        "from pyspark.sql.functions import (\n"
        "    col, when, lit, to_timestamp, to_date, date_format,\n"
        "    hour, row_number, current_timestamp\n"
        ")\n"
        "from pyspark.sql.window import Window"
    ),
    code(
        "# Pass-through customers — clean dimension\n"
        "df_cust = spark.read.format('delta').table('bronze_customers')\n"
        "df_cust = df_cust.withColumn('silver_timestamp', current_timestamp())\n"
        "df_cust.write.mode('overwrite').format('delta').saveAsTable('silver_customers')\n"
        "print(f'Silver customers: {df_cust.count()} rows')"
    ),
    code(
        "# Clean accounts\n"
        "df_acct = spark.read.format('delta').table('bronze_accounts')\n"
        "w = Window.partitionBy('account_id').orderBy(col('ingestion_timestamp').desc())\n"
        "df_acct = (\n"
        "    df_acct.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')\n"
        "    .withColumn('balance', col('balance').cast('double'))\n"
        "    .withColumn('credit_limit', col('credit_limit').cast('double'))\n"
        "    .withColumn('credit_utilisation_pct', col('credit_utilisation_pct').cast('double'))\n"
        "    .withColumn('open_date', to_date('open_date'))\n"
        "    .filter(col('balance') >= 0)\n"
        "    .withColumn('utilisation_band',\n"
        "        when(col('credit_limit') == 0, 'N/A')\n"
        "        .when(col('credit_utilisation_pct') <= 30, 'Low')\n"
        "        .when(col('credit_utilisation_pct') <= 60, 'Medium')\n"
        "        .when(col('credit_utilisation_pct') <= 90, 'High')\n"
        "        .otherwise('Very High'))\n"
        "    .withColumn('silver_timestamp', current_timestamp())\n"
        ")\n"
        "df_acct.write.mode('overwrite').format('delta').saveAsTable('silver_accounts')\n"
        "print(f'Silver accounts: {df_acct.count()} rows')"
    ),
    code(
        "# Clean transactions + derive NON-LEAKY indicators (no fraud-derived columns)\n"
        "df_txn = spark.read.format('delta').table('bronze_transactions')\n"
        "w2 = Window.partitionBy('transaction_id').orderBy(col('ingestion_timestamp').desc())\n"
        "df_txn = (\n"
        "    df_txn.withColumn('_rn', row_number().over(w2)).filter(col('_rn') == 1).drop('_rn')\n"
        "    .withColumn('transaction_date', to_timestamp('transaction_date'))\n"
        "    .withColumn('amount', col('amount').cast('double'))\n"
        "    .withColumn('is_flagged_fraud', col('is_flagged_fraud').cast('boolean'))\n"
        "    .filter(col('transaction_date').isNotNull())\n"
        "    .filter(col('amount') > 0)\n"
        "    .withColumn('transaction_date_only', date_format('transaction_date', 'yyyy-MM-dd'))\n"
        "    .withColumn('transaction_hour', hour('transaction_date'))\n"
        "    .withColumn('is_night_transaction', (hour('transaction_date') >= 22) | (hour('transaction_date') < 6))\n"
        "    .withColumn('is_international', col('country') != 'UK')\n"
        "    .withColumn('is_high_value', col('amount') > 5000)\n"
        "    .withColumn('silver_timestamp', current_timestamp())\n"
        ")\n"
        "df_txn.write.mode('overwrite').format('delta').saveAsTable('silver_transactions')\n"
        "print(f'Silver transactions: {df_txn.count()} rows')"
    ),
])

# ── ml/01_feature_engineering ───────────────────────────────────────────────
write(ML / "01_feature_engineering.ipynb", [
    md("# Feature Engineering — Fraud Detection\n\n"
       "Joins silver transactions with account + customer dimensions to build a\n"
       "transaction-level feature table for fraud classification.\n\n"
       "**Reads from:** `silver_transactions`, `silver_accounts`, `silver_customers`\n\n"
       "**Writes to:** `gold_ml_features`"),
    code(
        "from pyspark.sql import SparkSession\n"
        "from pyspark.sql.functions import col, lit, current_timestamp, when, log1p\n\n"
        "spark = SparkSession.builder.getOrCreate()\n"
        "print('Spark session ready')"
    ),
    code(
        "txn = spark.read.table('silver_transactions')\n"
        "acct = spark.read.table('silver_accounts')\n"
        "cust = spark.read.table('silver_customers')\n"
        "print(f'Transactions: {txn.count():,} | Accounts: {acct.count():,} | Customers: {cust.count():,}')\n\n"
        "required = {'transaction_id', 'account_id', 'customer_id', 'amount', 'is_flagged_fraud'}\n"
        "missing = required - set(txn.columns)\n"
        "if missing:\n"
        "    raise ValueError(f'silver_transactions missing columns {sorted(missing)}. Regenerate data and rerun bronze/silver.')"
    ),
    code(
        "# Join transaction + account + customer attributes. EXCLUDE silver leakage\n"
        "# columns (risk_score / risk_band are derived from the fraud flag).\n"
        "ml_features = (\n"
        "    txn.select(\n"
        "        'transaction_id', 'account_id', 'customer_id', 'transaction_date',\n"
        "        'transaction_type', 'merchant_category', 'channel', 'country',\n"
        "        'amount', 'transaction_hour',\n"
        "        col('is_night_transaction').cast('int').alias('is_night'),\n"
        "        col('is_international').cast('int').alias('is_international'),\n"
        "        col('is_high_value').cast('int').alias('is_high_value'),\n"
        "        col('is_flagged_fraud').cast('int').alias('had_fraud'),\n"
        "    )\n"
        "    .join(\n"
        "        acct.select('account_id', 'account_type', 'balance', 'credit_limit', 'credit_utilisation_pct'),\n"
        "        'account_id', 'left')\n"
        "    .join(\n"
        "        cust.select('customer_id', 'age_group', 'segment', 'region', 'risk_tier'),\n"
        "        'customer_id', 'left')\n"
        "    .withColumn('log_amount', log1p(col('amount')))\n"
        "    .na.fill(0)\n"
        "    .na.fill('unknown', subset=['transaction_type', 'merchant_category', 'channel',\n"
        "                                'country', 'account_type', 'age_group', 'segment',\n"
        "                                'region', 'risk_tier'])\n"
        "    .withColumn('feature_timestamp', current_timestamp())\n"
        ")\n\n"
        "total_rows = ml_features.count()\n"
        "positive_rows = ml_features.filter(col('had_fraud') == 1).count()\n"
        "fraud_rate = (positive_rows / total_rows * 100) if total_rows else 0.0\n\n"
        "# Guardrail: fail fast if positives collapse (silent label loss).\n"
        "if total_rows < 1000 or positive_rows < max(10, int(total_rows * 0.01)):\n"
        "    raise ValueError(\n"
        "        f'Label quality check failed: only {positive_rows}/{total_rows} fraud rows '\n"
        "        f'({fraud_rate:.2f}%). Check is_flagged_fraud typing and source data.'\n"
        "    )\n\n"
        "ml_features.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_features')\n"
        "print(f'Gold ML features written: {total_rows:,} rows | fraud rate {fraud_rate:.1f}%')"
    ),
    code(
        "spark.sql('OPTIMIZE gold_ml_features')\n"
        "print('Feature table optimized')"
    ),
])

# ── ml/02_model_training ────────────────────────────────────────────────────
write(ML / "02_model_training.ipynb", [
    md("# Model Training — Fraud Detection\n\n"
       "Trains a PySpark **RandomForest classifier** (built-in, no SynapseML) to\n"
       "predict the fraud flag from transaction / account / customer features.\n\n"
       "**Target:** `had_fraud`  **Reads:** `gold_ml_features`  "
       "**Writes:** `gold_ml_model_metrics`, `Files/models/fraud_detection_rf`"),
    code(
        "from pyspark.sql import SparkSession\n"
        "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
        "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
        "from pyspark.ml.classification import RandomForestClassifier\n"
        "from pyspark.ml.evaluation import BinaryClassificationEvaluator, MulticlassClassificationEvaluator\n\n"
        "spark = SparkSession.builder.getOrCreate()\n"
        "print('Spark session ready')"
    ),
    code(
        "df = spark.read.table('gold_ml_features')\n"
        "print(f'Feature rows: {df.count():,}')\n\n"
        "for c, dtype in df.dtypes:\n"
        "    if dtype in ('double', 'float'):\n"
        "        df = df.withColumn(c, when(col(c).isNull() | isnan(col(c)), lit(0.0)).otherwise(col(c)))\n"
        "    elif dtype in ('int', 'bigint', 'long'):\n"
        "        df = df.withColumn(c, when(col(c).isNull(), lit(0)).otherwise(col(c)))\n\n"
        "df.groupBy('had_fraud').count().show()"
    ),
    code(
        "numeric_features = [\n"
        "    'amount', 'log_amount', 'transaction_hour', 'is_night', 'is_international',\n"
        "    'is_high_value', 'balance', 'credit_limit', 'credit_utilisation_pct',\n"
        "]\n"
        "cat_cols = ['transaction_type', 'merchant_category', 'channel', 'country',\n"
        "            'account_type', 'age_group', 'segment', 'region', 'risk_tier']\n\n"
        "indexed_df = df\n"
        "cat_idx_cols = []\n"
        "for c in cat_cols:\n"
        "    idx_col = f'{c}_idx'\n"
        "    indexer = StringIndexer(inputCol=c, outputCol=idx_col, handleInvalid='keep')\n"
        "    indexed_df = indexer.fit(indexed_df).transform(indexed_df)\n"
        "    cat_idx_cols.append(idx_col)\n\n"
        "all_features = numeric_features + cat_idx_cols\n"
        "assembler = VectorAssembler(inputCols=all_features, outputCol='features', handleInvalid='keep')\n"
        "model_df = assembler.transform(indexed_df).select('features', col('had_fraud').cast('double').alias('label'))\n"
        "model_df = model_df.cache()\n"
        "print(f'Model rows: {model_df.count():,} | features: {len(all_features)}')"
    ),
    code(
        "train_df, test_df = model_df.randomSplit([0.8, 0.2], seed=42)\n"
        "print(f'Train: {train_df.count():,}  Test: {test_df.count():,}')"
    ),
    code(
        "rf = RandomForestClassifier(\n"
        "    featuresCol='features', labelCol='label',\n"
        "    predictionCol='prediction', rawPredictionCol='rawPrediction', probabilityCol='probability',\n"
        "    numTrees=80, maxDepth=10, seed=42,\n"
        ")\n"
        "model = rf.fit(train_df)\n"
        "print('RandomForest classifier trained')"
    ),
    code(
        "predictions = model.transform(test_df)\n"
        "auc = BinaryClassificationEvaluator(labelCol='label', rawPredictionCol='rawPrediction', metricName='areaUnderROC').evaluate(predictions)\n"
        "accuracy = MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='accuracy').evaluate(predictions)\n"
        "f1 = MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='f1').evaluate(predictions)\n"
        "print(f'AUC-ROC: {auc:.4f}  Accuracy: {accuracy:.4f}  F1: {f1:.4f}')"
    ),
    code(
        "metrics = spark.createDataFrame(\n"
        "    [('financial-services', 'fraud-detection', 'RandomForestClassifier',\n"
        "      len(all_features), train_df.count(), test_df.count(),\n"
        "      float(auc), float(accuracy), float(f1))],\n"
        "    ['demo_id', 'use_case', 'model_type', 'feature_count',\n"
        "     'train_rows', 'test_rows', 'auc_roc', 'accuracy', 'f1_score']\n"
        ").withColumn('trained_at', current_timestamp())\n"
        "metrics.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_model_metrics')\n"
        "model.write().overwrite().save('Files/models/fraud_detection_rf')\n"
        "model_df.unpersist()\n"
        "print('Metrics + model saved')"
    ),
])

# ── ml/03_model_evaluation ──────────────────────────────────────────────────
write(ML / "03_model_evaluation.ipynb", [
    md("# Model Evaluation — Fraud Detection\n\n"
       "Confusion matrix, precision/recall, and feature importance for the trained model.\n\n"
       "**Reads:** `gold_ml_features` + saved model  **Writes:** `gold_ml_feature_importance`"),
    code(
        "from pyspark.sql import SparkSession\n"
        "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
        "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
        "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
        "spark = SparkSession.builder.getOrCreate()\n"
        "model = RandomForestClassificationModel.load('Files/models/fraud_detection_rf')\n"
        "print('Model loaded')"
    ),
    code(
        "df = spark.read.table('gold_ml_features')\n"
        "for c, dtype in df.dtypes:\n"
        "    if dtype in ('double', 'float'):\n"
        "        df = df.withColumn(c, when(col(c).isNull() | isnan(col(c)), lit(0.0)).otherwise(col(c)))\n"
        "    elif dtype in ('int', 'bigint', 'long'):\n"
        "        df = df.withColumn(c, when(col(c).isNull(), lit(0)).otherwise(col(c)))\n\n"
        "numeric_features = [\n"
        "    'amount', 'log_amount', 'transaction_hour', 'is_night', 'is_international',\n"
        "    'is_high_value', 'balance', 'credit_limit', 'credit_utilisation_pct',\n"
        "]\n"
        "cat_cols = ['transaction_type', 'merchant_category', 'channel', 'country',\n"
        "            'account_type', 'age_group', 'segment', 'region', 'risk_tier']\n"
        "indexed_df = df\n"
        "cat_idx_cols = []\n"
        "for c in cat_cols:\n"
        "    idx_col = f'{c}_idx'\n"
        "    indexer = StringIndexer(inputCol=c, outputCol=idx_col, handleInvalid='keep')\n"
        "    indexed_df = indexer.fit(indexed_df).transform(indexed_df)\n"
        "    cat_idx_cols.append(idx_col)\n\n"
        "all_features = numeric_features + cat_idx_cols\n"
        "assembler = VectorAssembler(inputCols=all_features, outputCol='features', handleInvalid='keep')\n"
        "model_df = assembler.transform(indexed_df).select('features', col('had_fraud').cast('double').alias('label'))\n"
        "_, test_df = model_df.randomSplit([0.8, 0.2], seed=42)\n"
        "predictions = model.transform(test_df)\n"
        "print(f'Test predictions: {predictions.count():,} rows')"
    ),
    code(
        "print('=== Confusion Matrix ===')\n"
        "predictions.groupBy('label', 'prediction').count().orderBy('label', 'prediction').show()\n"
        "tp = predictions.filter((col('label') == 1) & (col('prediction') == 1)).count()\n"
        "fp = predictions.filter((col('label') == 0) & (col('prediction') == 1)).count()\n"
        "fn = predictions.filter((col('label') == 1) & (col('prediction') == 0)).count()\n"
        "tn = predictions.filter((col('label') == 0) & (col('prediction') == 0)).count()\n"
        "precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0\n"
        "recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0\n"
        "print(f'TP={tp} FP={fp} FN={fn} TN={tn}')\n"
        "print(f'Precision: {precision:.4f}  Recall: {recall:.4f}')"
    ),
    code(
        "# Feature importance — build Delta from plain python tuples (no pandas) for robustness\n"
        "importances = model.featureImportances.toArray()\n"
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
        "print('Feature importance saved')"
    ),
    code(
        "spark.sql('OPTIMIZE gold_ml_feature_importance')\n"
        "print('Evaluation complete')"
    ),
])

# ── ml/04_batch_scoring ─────────────────────────────────────────────────────
write(ML / "04_batch_scoring.ipynb", [
    md("# Batch Scoring — Fraud Detection\n\n"
       "Scores every transaction with the trained model to produce fraud-risk\n"
       "predictions and a per-merchant-category risk summary.\n\n"
       "**Reads:** `gold_ml_features` + saved model  "
       "**Writes:** `gold_ml_predictions`, `gold_ml_summary`"),
    code(
        "from pyspark.sql import SparkSession\n"
        "from pyspark.sql.functions import (\n"
        "    col, lit, current_timestamp, when, avg, count, isnan, udf,\n"
        "    sum as spark_sum, round as spark_round\n"
        ")\n"
        "from pyspark.sql.types import DoubleType\n"
        "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
        "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
        "spark = SparkSession.builder.getOrCreate()\n"
        "model = RandomForestClassificationModel.load('Files/models/fraud_detection_rf')\n"
        "df = spark.read.table('gold_ml_features')\n"
        "print(f'Scoring {df.count():,} feature rows')"
    ),
    code(
        "for c, dtype in df.dtypes:\n"
        "    if dtype in ('double', 'float'):\n"
        "        df = df.withColumn(c, when(col(c).isNull() | isnan(col(c)), lit(0.0)).otherwise(col(c)))\n"
        "    elif dtype in ('int', 'bigint', 'long'):\n"
        "        df = df.withColumn(c, when(col(c).isNull(), lit(0)).otherwise(col(c)))\n\n"
        "numeric_features = [\n"
        "    'amount', 'log_amount', 'transaction_hour', 'is_night', 'is_international',\n"
        "    'is_high_value', 'balance', 'credit_limit', 'credit_utilisation_pct',\n"
        "]\n"
        "cat_cols = ['transaction_type', 'merchant_category', 'channel', 'country',\n"
        "            'account_type', 'age_group', 'segment', 'region', 'risk_tier']\n"
        "indexed_df = df\n"
        "for c in cat_cols:\n"
        "    idx_col = f'{c}_idx'\n"
        "    indexer = StringIndexer(inputCol=c, outputCol=idx_col, handleInvalid='keep')\n"
        "    indexed_df = indexer.fit(indexed_df).transform(indexed_df)\n\n"
        "all_features = numeric_features + [f'{c}_idx' for c in cat_cols]\n"
        "assembler = VectorAssembler(inputCols=all_features, outputCol='features', handleInvalid='keep')\n"
        "model_df = assembler.transform(indexed_df)"
    ),
    code(
        "scored = model.transform(model_df)\n"
        "extract_prob = udf(lambda v: float(v[1]) if v is not None and len(v) > 1 else 0.0, DoubleType())\n\n"
        "predictions = (\n"
        "    scored\n"
        "    .withColumn('fraud_probability', spark_round(extract_prob(col('probability')), 4))\n"
        "    .withColumn('predicted_fraud', col('prediction').cast('int'))\n"
        "    .withColumn('risk_level',\n"
        "        when(col('fraud_probability') > 0.8, 'critical')\n"
        "        .when(col('fraud_probability') > 0.6, 'high')\n"
        "        .when(col('fraud_probability') > 0.4, 'medium')\n"
        "        .otherwise('low'))\n"
        "    .withColumn('scored_at', current_timestamp())\n"
        "    .select(\n"
        "        'transaction_id', 'account_id', 'customer_id', 'transaction_date',\n"
        "        'merchant_category', 'channel', 'country', 'segment', 'region',\n"
        "        'amount', 'had_fraud', 'predicted_fraud', 'fraud_probability', 'risk_level',\n"
        "        'scored_at')\n"
        ")\n"
        "predictions.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_predictions')\n"
        "print(f'Predictions written: {predictions.count():,} rows')\n"
        "predictions.groupBy('risk_level').count().orderBy('count', ascending=False).show()"
    ),
    code(
        "# Per merchant-category fraud risk summary\n"
        "summary = (\n"
        "    predictions\n"
        "    .groupBy('merchant_category')\n"
        "    .agg(\n"
        "        count('*').alias('total_transactions'),\n"
        "        spark_sum('predicted_fraud').alias('predicted_fraud_count'),\n"
        "        spark_sum('had_fraud').alias('actual_fraud_count'),\n"
        "        spark_round(avg('fraud_probability'), 4).alias('avg_fraud_probability'),\n"
        "        spark_round(spark_sum('amount'), 2).alias('total_amount'),\n"
        "    )\n"
        "    .withColumn('fraud_rate', spark_round(col('predicted_fraud_count') / col('total_transactions') * 100, 1))\n"
        "    .withColumn('overall_risk',\n"
        "        when(col('avg_fraud_probability') > 0.6, 'high')\n"
        "        .when(col('avg_fraud_probability') > 0.3, 'medium')\n"
        "        .otherwise('low'))\n"
        "    .withColumn('summary_timestamp', current_timestamp())\n"
        "    .orderBy(col('avg_fraud_probability').desc())\n"
        ")\n"
        "summary.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_summary')\n"
        "print(f'Merchant-category risk summary: {summary.count()} rows')\n"
        "summary.show(15, truncate=False)"
    ),
    code(
        "spark.sql('OPTIMIZE gold_ml_predictions')\n"
        "spark.sql('OPTIMIZE gold_ml_summary')\n"
        "print('All Gold ML tables optimized')"
    ),
])

print("done")
