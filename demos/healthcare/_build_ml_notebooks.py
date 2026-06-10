"""One-shot builder for the healthcare AI/ML notebooks.

Writes 2 batch notebooks (bronze, silver) + 4 ML notebooks (feature engineering,
training, evaluation, batch scoring) as valid Jupyter JSON. Uses built-in PySpark
ML (RandomForestClassifier) — no SynapseML — matching the proven pattern.

Use case: 30-day readmission risk prediction (binary classification).
Target: had_readmission (from is_readmission).

Run once:  python demos/healthcare/_build_ml_notebooks.py
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
    return {"cells": cells, "metadata": {"language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5}


def write(path: Path, cells: list[dict]) -> None:
    path.write_text(json.dumps(notebook(cells), indent=1), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


# ── batch/01_bronze_ingest ──────────────────────────────────────────────────
write(BATCH / "01_bronze_ingest.ipynb", [
    md("# Bronze Layer — Ingest Raw Healthcare Data\n"
       "Reads CSV files from lakehouse `{{DATA_SOURCE_PATH}}/` and writes Delta tables with metadata columns."),
    code(
        "from pyspark.sql.functions import current_timestamp, input_file_name, lit\n"
        "import uuid\n\n"
        "ingestion_batch_id = str(uuid.uuid4())"
    ),
    code(
        "# Ingest staff catalog\n"
        "df_staff = (\n"
        "    spark.read.format('csv').option('header', True).option('inferSchema', True)\n"
        "    .load('{{DATA_SOURCE_PATH}}/staff_catalog.csv')\n"
        "    .withColumn('ingestion_timestamp', current_timestamp())\n"
        "    .withColumn('source_file', input_file_name())\n"
        "    .withColumn('ingestion_batch_id', lit(ingestion_batch_id))\n"
        ")\n"
        "df_staff.write.mode('overwrite').format('delta').saveAsTable('bronze_staff_catalog')\n"
        "print(f'Bronze staff catalog: {df_staff.count()} rows')"
    ),
    code(
        "# Ingest patient admissions\n"
        "df_admissions = (\n"
        "    spark.read.format('csv').option('header', True).option('inferSchema', True)\n"
        "    .load('{{DATA_SOURCE_PATH}}/patient_admissions.csv')\n"
        "    .withColumn('ingestion_timestamp', current_timestamp())\n"
        "    .withColumn('source_file', input_file_name())\n"
        "    .withColumn('ingestion_batch_id', lit(ingestion_batch_id))\n"
        ")\n"
        "df_admissions.write.mode('overwrite').format('delta').saveAsTable('bronze_patient_admissions')\n"
        "print(f'Bronze patient admissions: {df_admissions.count()} rows')"
    ),
    code(
        "# Ingest clinical records (vitals)\n"
        "df_clinical = (\n"
        "    spark.read.format('csv').option('header', True).option('inferSchema', True)\n"
        "    .load('{{DATA_SOURCE_PATH}}/clinical_records.csv')\n"
        "    .withColumn('ingestion_timestamp', current_timestamp())\n"
        "    .withColumn('source_file', input_file_name())\n"
        "    .withColumn('ingestion_batch_id', lit(ingestion_batch_id))\n"
        ")\n"
        "df_clinical.write.mode('overwrite').format('delta').saveAsTable('bronze_clinical_records')\n"
        "print(f'Bronze clinical records: {df_clinical.count()} rows')"
    ),
])

# ── batch/02_silver_transform ───────────────────────────────────────────────
write(BATCH / "02_silver_transform.ipynb", [
    md("# Silver Layer — Clean & Enrich Healthcare Data\n"
       "Validate admissions, deduplicate records, derive LOS buckets and flag abnormal vitals.\n"
       "Does NOT derive any readmission-based flags (avoids target leakage)."),
    code(
        "from pyspark.sql.functions import (\n"
        "    col, when, lit, to_timestamp, date_format, hour,\n"
        "    row_number, current_timestamp\n"
        ")\n"
        "from pyspark.sql.window import Window"
    ),
    code(
        "# Pass-through staff catalog — already clean dimension\n"
        "df_staff = spark.read.format('delta').table('bronze_staff_catalog')\n"
        "df_staff = df_staff.withColumn('silver_timestamp', current_timestamp())\n"
        "df_staff.write.mode('overwrite').format('delta').saveAsTable('silver_staff_catalog')\n"
        "print(f'Silver staff catalog: {df_staff.count()} rows')"
    ),
    code(
        "# Clean patient admissions (no readmission-derived columns)\n"
        "df_adm = spark.read.format('delta').table('bronze_patient_admissions')\n"
        "w = Window.partitionBy('admission_id').orderBy(col('ingestion_timestamp').desc())\n"
        "df_adm = (\n"
        "    df_adm.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')\n"
        "    .withColumn('admission_date', to_timestamp('admission_date'))\n"
        "    .withColumn('discharge_date', to_timestamp('discharge_date'))\n"
        "    .withColumn('length_of_stay_days', col('length_of_stay_days').cast('int'))\n"
        "    .withColumn('prior_admissions', col('prior_admissions').cast('int'))\n"
        "    .withColumn('is_readmission', col('is_readmission').cast('boolean'))\n"
        "    .filter(col('admission_date').isNotNull())\n"
        "    .filter(col('length_of_stay_days') >= 0)\n"
        "    .withColumn('los_bucket',\n"
        "        when(col('length_of_stay_days') == 0, 'Same Day')\n"
        "        .when(col('length_of_stay_days') <= 2, '1-2 Days')\n"
        "        .when(col('length_of_stay_days') <= 7, '3-7 Days')\n"
        "        .when(col('length_of_stay_days') <= 14, '8-14 Days')\n"
        "        .otherwise('15+ Days'))\n"
        "    .withColumn('dx_chapter', col('primary_dx_code').substr(1, 1))\n"
        "    .withColumn('admission_date_only', date_format('admission_date', 'yyyy-MM-dd'))\n"
        "    .withColumn('admission_shift',\n"
        "        when(hour('admission_date') < 8, 'Night')\n"
        "        .when(hour('admission_date') < 16, 'Day')\n"
        "        .otherwise('Evening'))\n"
        "    .withColumn('silver_timestamp', current_timestamp())\n"
        ")\n"
        "df_adm.write.mode('overwrite').format('delta').saveAsTable('silver_patient_admissions')\n"
        "print(f'Silver admissions: {df_adm.count()} rows')"
    ),
    code(
        "# Clean clinical records (vitals) + flag abnormal readings\n"
        "df_clin = spark.read.format('delta').table('bronze_clinical_records')\n"
        "w2 = Window.partitionBy('record_id').orderBy(col('ingestion_timestamp').desc())\n"
        "df_clin = (\n"
        "    df_clin.withColumn('_rn', row_number().over(w2)).filter(col('_rn') == 1).drop('_rn')\n"
        "    .withColumn('recorded_at', to_timestamp('recorded_at'))\n"
        "    .withColumn('value', col('value').cast('double'))\n"
        "    .filter(col('recorded_at').isNotNull())\n"
        "    .filter(col('value').isNotNull())\n"
        "    .withColumn('is_abnormal',\n"
        "        when((col('vital_type') == 'Blood Pressure Systolic') & ((col('value') < 90) | (col('value') > 140)), True)\n"
        "        .when((col('vital_type') == 'Heart Rate') & ((col('value') < 60) | (col('value') > 100)), True)\n"
        "        .when((col('vital_type') == 'Temperature') & ((col('value') < 36.1) | (col('value') > 37.8)), True)\n"
        "        .when((col('vital_type') == 'O2 Saturation') & (col('value') < 95), True)\n"
        "        .otherwise(False))\n"
        "    .withColumn('recorded_date', date_format('recorded_at', 'yyyy-MM-dd'))\n"
        "    .withColumn('silver_timestamp', current_timestamp())\n"
        ")\n"
        "df_clin.write.mode('overwrite').format('delta').saveAsTable('silver_clinical_records')\n"
        "print(f'Silver clinical records: {df_clin.count()} rows')"
    ),
])

# Shared feature-prep snippet (numeric + categorical lists) used by 02/03/04.
FEATURE_DEFS = (
    "numeric_features = [\n"
    "    'length_of_stay_days', 'prior_admissions', 'admission_hour',\n"
    "    'vital_count', 'abnormal_vital_count', 'abnormal_vital_ratio', 'avg_vital_value',\n"
    "]\n"
    "cat_cols = ['department', 'admission_type', 'insurance_type', 'age_group', 'dx_chapter']"
)

# ── ml/01_feature_engineering ───────────────────────────────────────────────
write(ML / "01_feature_engineering.ipynb", [
    md("# Feature Engineering — Readmission Risk Prediction\n\n"
       "Aggregates clinical vitals per admission and joins with admission attributes\n"
       "to build a per-admission feature table for 30-day readmission classification.\n\n"
       "**Reads:** `silver_patient_admissions`, `silver_clinical_records`  "
       "**Writes:** `gold_ml_features`"),
    code(
        "from pyspark.sql import SparkSession\n"
        "from pyspark.sql.functions import (\n"
        "    col, lit, current_timestamp, when, hour, count, avg,\n"
        "    sum as spark_sum\n"
        ")\n\n"
        "spark = SparkSession.builder.getOrCreate()\n"
        "print('Spark session ready')"
    ),
    code(
        "adm = spark.read.table('silver_patient_admissions')\n"
        "clin = spark.read.table('silver_clinical_records')\n"
        "print(f'Admissions: {adm.count():,} | Clinical records: {clin.count():,}')\n\n"
        "required = {'admission_id', 'is_readmission', 'length_of_stay_days'}\n"
        "missing = required - set(adm.columns)\n"
        "if missing:\n"
        "    raise ValueError(f'silver_patient_admissions missing columns {sorted(missing)}. Regenerate data and rerun bronze/silver.')"
    ),
    code(
        "# Aggregate vitals per admission\n"
        "vitals = (\n"
        "    clin.groupBy('admission_id')\n"
        "    .agg(\n"
        "        count('*').alias('vital_count'),\n"
        "        spark_sum(when(col('is_abnormal'), 1).otherwise(0)).alias('abnormal_vital_count'),\n"
        "        avg('value').alias('avg_vital_value'),\n"
        "    )\n"
        "    .withColumn('abnormal_vital_ratio',\n"
        "        col('abnormal_vital_count') / when(col('vital_count') > 0, col('vital_count')).otherwise(1))\n"
        ")"
    ),
    code(
        "# Join admission attributes + vitals. EXCLUDE any readmission-derived columns.\n"
        "ml_features = (\n"
        "    adm.select(\n"
        "        'admission_id', 'patient_id', 'department', 'admission_type',\n"
        "        'insurance_type', 'age_group', 'dx_chapter', 'los_bucket',\n"
        "        'length_of_stay_days', 'prior_admissions',\n"
        "        hour('admission_date').alias('admission_hour'),\n"
        "        col('is_readmission').cast('int').alias('had_readmission'),\n"
        "    )\n"
        "    .join(vitals, 'admission_id', 'left')\n"
        "    .na.fill(0, ['vital_count', 'abnormal_vital_count', 'avg_vital_value', 'abnormal_vital_ratio'])\n"
        "    .na.fill('unknown', subset=['department', 'admission_type', 'insurance_type', 'age_group', 'dx_chapter'])\n"
        "    .withColumn('feature_timestamp', current_timestamp())\n"
        ")\n\n"
        "total_rows = ml_features.count()\n"
        "positive_rows = ml_features.filter(col('had_readmission') == 1).count()\n"
        "readmit_rate = (positive_rows / total_rows * 100) if total_rows else 0.0\n\n"
        "if total_rows < 1000 or positive_rows < max(10, int(total_rows * 0.01)):\n"
        "    raise ValueError(\n"
        "        f'Label quality check failed: only {positive_rows}/{total_rows} readmission rows '\n"
        "        f'({readmit_rate:.2f}%). Check is_readmission typing and source data.'\n"
        "    )\n\n"
        "ml_features.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_features')\n"
        "print(f'Gold ML features written: {total_rows:,} rows | readmission rate {readmit_rate:.1f}%')"
    ),
    code(
        "spark.sql('OPTIMIZE gold_ml_features')\n"
        "print('Feature table optimized')"
    ),
])

# ── ml/02_model_training ────────────────────────────────────────────────────
write(ML / "02_model_training.ipynb", [
    md("# Model Training — Readmission Risk Prediction\n\n"
       "Trains a PySpark **RandomForest classifier** (built-in, no SynapseML) to\n"
       "predict 30-day readmission from admission + vitals features.\n\n"
       "**Target:** `had_readmission`  **Reads:** `gold_ml_features`  "
       "**Writes:** `gold_ml_model_metrics`, `Files/models/readmission_rf`"),
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
        "print(f'Feature rows: {df.count():,}')\n"
        "for c, dtype in df.dtypes:\n"
        "    if dtype in ('double', 'float'):\n"
        "        df = df.withColumn(c, when(col(c).isNull() | isnan(col(c)), lit(0.0)).otherwise(col(c)))\n"
        "    elif dtype in ('int', 'bigint', 'long'):\n"
        "        df = df.withColumn(c, when(col(c).isNull(), lit(0)).otherwise(col(c)))\n"
        "df.groupBy('had_readmission').count().show()"
    ),
    code(
        FEATURE_DEFS + "\n\n"
        "indexed_df = df\n"
        "cat_idx_cols = []\n"
        "for c in cat_cols:\n"
        "    idx_col = f'{c}_idx'\n"
        "    indexer = StringIndexer(inputCol=c, outputCol=idx_col, handleInvalid='keep')\n"
        "    indexed_df = indexer.fit(indexed_df).transform(indexed_df)\n"
        "    cat_idx_cols.append(idx_col)\n\n"
        "all_features = numeric_features + cat_idx_cols\n"
        "assembler = VectorAssembler(inputCols=all_features, outputCol='features', handleInvalid='keep')\n"
        "model_df = assembler.transform(indexed_df).select('features', col('had_readmission').cast('double').alias('label'))\n"
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
        "    [('healthcare', 'readmission-prediction', 'RandomForestClassifier',\n"
        "      len(all_features), train_df.count(), test_df.count(),\n"
        "      float(auc), float(accuracy), float(f1))],\n"
        "    ['demo_id', 'use_case', 'model_type', 'feature_count',\n"
        "     'train_rows', 'test_rows', 'auc_roc', 'accuracy', 'f1_score']\n"
        ").withColumn('trained_at', current_timestamp())\n"
        "metrics.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_model_metrics')\n"
        "model.write().overwrite().save('Files/models/readmission_rf')\n"
        "model_df.unpersist()\n"
        "print('Metrics + model saved')"
    ),
])

# ── ml/03_model_evaluation ──────────────────────────────────────────────────
write(ML / "03_model_evaluation.ipynb", [
    md("# Model Evaluation — Readmission Risk Prediction\n\n"
       "Confusion matrix, precision/recall, and feature importance.\n\n"
       "**Reads:** `gold_ml_features` + saved model  **Writes:** `gold_ml_feature_importance`"),
    code(
        "from pyspark.sql import SparkSession\n"
        "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
        "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
        "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
        "spark = SparkSession.builder.getOrCreate()\n"
        "model = RandomForestClassificationModel.load('Files/models/readmission_rf')\n"
        "print('Model loaded')"
    ),
    code(
        "df = spark.read.table('gold_ml_features')\n"
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
        "model_df = assembler.transform(indexed_df).select('features', col('had_readmission').cast('double').alias('label'))\n"
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
    md("# Batch Scoring — Readmission Risk Prediction\n\n"
       "Scores every admission with the trained model to produce readmission-risk\n"
       "predictions and a per-department risk summary.\n\n"
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
        "model = RandomForestClassificationModel.load('Files/models/readmission_rf')\n"
        "df = spark.read.table('gold_ml_features')\n"
        "print(f'Scoring {df.count():,} feature rows')"
    ),
    code(
        "for c, dtype in df.dtypes:\n"
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
        "model_df = assembler.transform(indexed_df)"
    ),
    code(
        "scored = model.transform(model_df)\n"
        "extract_prob = udf(lambda v: float(v[1]) if v is not None and len(v) > 1 else 0.0, DoubleType())\n\n"
        "predictions = (\n"
        "    scored\n"
        "    .withColumn('readmission_probability', spark_round(extract_prob(col('probability')), 4))\n"
        "    .withColumn('predicted_readmission', col('prediction').cast('int'))\n"
        "    .withColumn('risk_level',\n"
        "        when(col('readmission_probability') > 0.8, 'critical')\n"
        "        .when(col('readmission_probability') > 0.6, 'high')\n"
        "        .when(col('readmission_probability') > 0.4, 'medium')\n"
        "        .otherwise('low'))\n"
        "    .withColumn('scored_at', current_timestamp())\n"
        "    .select(\n"
        "        'admission_id', 'patient_id', 'department', 'admission_type',\n"
        "        'insurance_type', 'age_group', 'los_bucket',\n"
        "        'length_of_stay_days', 'abnormal_vital_count',\n"
        "        'had_readmission', 'predicted_readmission', 'readmission_probability', 'risk_level',\n"
        "        'scored_at')\n"
        ")\n"
        "predictions.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_predictions')\n"
        "print(f'Predictions written: {predictions.count():,} rows')\n"
        "predictions.groupBy('risk_level').count().orderBy('count', ascending=False).show()"
    ),
    code(
        "# Per-department readmission risk summary\n"
        "summary = (\n"
        "    predictions\n"
        "    .groupBy('department')\n"
        "    .agg(\n"
        "        count('*').alias('total_admissions'),\n"
        "        spark_sum('predicted_readmission').alias('predicted_readmission_count'),\n"
        "        spark_sum('had_readmission').alias('actual_readmission_count'),\n"
        "        spark_round(avg('readmission_probability'), 4).alias('avg_readmission_probability'),\n"
        "        spark_round(avg('length_of_stay_days'), 1).alias('avg_length_of_stay'),\n"
        "        spark_round(avg('abnormal_vital_count'), 2).alias('avg_abnormal_vitals'),\n"
        "    )\n"
        "    .withColumn('readmission_rate', spark_round(col('predicted_readmission_count') / col('total_admissions') * 100, 1))\n"
        "    .withColumn('overall_risk',\n"
        "        when(col('avg_readmission_probability') > 0.6, 'high')\n"
        "        .when(col('avg_readmission_probability') > 0.3, 'medium')\n"
        "        .otherwise('low'))\n"
        "    .withColumn('summary_timestamp', current_timestamp())\n"
        "    .orderBy(col('avg_readmission_probability').desc())\n"
        ")\n"
        "summary.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_summary')\n"
        "print(f'Department risk summary: {summary.count()} rows')\n"
        "summary.show(15, truncate=False)"
    ),
    code(
        "spark.sql('OPTIMIZE gold_ml_predictions')\n"
        "spark.sql('OPTIMIZE gold_ml_summary')\n"
        "print('All Gold ML tables optimized')"
    ),
])

print("done")
