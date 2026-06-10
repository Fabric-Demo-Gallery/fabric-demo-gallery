"""One-shot builder for the education AI/ML notebooks.

Use case: dropout risk prediction (enrolment withdrawal, binary classification).
Target: had_dropout (from is_withdrawn). Built-in PySpark RandomForestClassifier.
Grain: one row per enrolment. Summary keyed by department.

Run once:  python demos/education/_build_ml_notebooks.py
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
    "    'credits', 'age_at_enrolment', 'avg_score', 'pass_rate',\n"
    "    'assessment_count', 'cohort_year',\n"
    "]\n"
    "cat_cols = ['department', 'level', 'programme', 'gender', 'region']"
)

CSV = [
    ("students", "bronze_students"),
    ("faculty", "bronze_faculty"),
    ("enrolments", "bronze_enrolments"),
    ("assessments", "bronze_assessments"),
]

# ── batch/01_bronze_ingest ──────────────────────────────────────────────────
bronze_cells = [
    md("# Bronze Layer — Ingest Raw Education Data\n"
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
    md("# Silver Layer — Clean & Conform Education Data\n"
       "Dedupe, cast types. Keeps enrolment label is_withdrawn; FE drops post-outcome leakage."),
    code("from pyspark.sql.functions import (\n"
         "    col, when, lit, to_date, row_number, current_timestamp\n"
         ")\n"
         "from pyspark.sql.window import Window"),
    code("# Clean students\n"
         "df_s = spark.read.format('delta').table('bronze_students')\n"
         "w = Window.partitionBy('student_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_s = (\n"
         "    df_s.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('cohort_year', col('cohort_year').cast('int'))\n"
         "    .withColumn('age_at_enrolment', col('age_at_enrolment').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_s.write.mode('overwrite').format('delta').saveAsTable('silver_students')\n"
         "print(f'silver_students: {df_s.count()} rows')"),
    code("# Clean faculty\n"
         "df_f = spark.read.format('delta').table('bronze_faculty')\n"
         "w2 = Window.partitionBy('faculty_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_f = (\n"
         "    df_f.withColumn('_rn', row_number().over(w2)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('years_at_institution', col('years_at_institution').cast('int'))\n"
         "    .withColumn('courses_assigned', col('courses_assigned').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_f.write.mode('overwrite').format('delta').saveAsTable('silver_faculty')\n"
         "print(f'silver_faculty: {df_f.count()} rows')"),
    code("# Clean enrolments (keep label is_withdrawn)\n"
         "df_e = spark.read.format('delta').table('bronze_enrolments')\n"
         "w3 = Window.partitionBy('enrolment_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_e = (\n"
         "    df_e.withColumn('_rn', row_number().over(w3)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('credits', col('credits').cast('int'))\n"
         "    .withColumn('age_at_enrolment', col('age_at_enrolment').cast('int'))\n"
         "    .withColumn('is_completed', col('is_completed').cast('int'))\n"
         "    .withColumn('is_withdrawn', col('is_withdrawn').cast('int'))\n"
         "    .withColumn('enrolment_date', to_date('enrolment_date'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_e.write.mode('overwrite').format('delta').saveAsTable('silver_enrolments')\n"
         "print(f'silver_enrolments: {df_e.count()} rows')"),
    code("# Clean assessments\n"
         "df_a = spark.read.format('delta').table('bronze_assessments')\n"
         "df_a = (\n"
         "    df_a\n"
         "    .withColumn('submitted_date', to_date('submitted_date'))\n"
         "    .withColumn('score', col('score').cast('double'))\n"
         "    .withColumn('is_pass', col('is_pass').cast('int'))\n"
         "    .withColumn('attempt_number', col('attempt_number').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_a.write.mode('overwrite').format('delta').saveAsTable('silver_assessments')\n"
         "print(f'silver_assessments: {df_a.count()} rows')"),
])

# ── ml/01_feature_engineering ───────────────────────────────────────────────
write(ML / "01_feature_engineering.ipynb", [
    md("# Feature Engineering — Dropout Risk Prediction\n\n"
       "Aggregates early assessments per enrolment (avg_score, pass_rate, assessment_count),\n"
       "joins enrolment + student attributes. EXCLUDES post-outcome leakage (status, is_completed).\n\n"
       "**Reads:** `silver_enrolments`, `silver_students`, `silver_assessments`  "
       "**Writes:** `gold_ml_features`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, avg, count, round as spark_round\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "print('Spark session ready')"),
    code("en = spark.read.table('silver_enrolments')\n"
         "st = spark.read.table('silver_students')\n"
         "asm = spark.read.table('silver_assessments')\n"
         "print(f'enrolments={en.count():,} students={st.count():,} assessments={asm.count():,}')\n\n"
         "required = {'enrolment_id', 'student_id', 'is_withdrawn', 'credits'}\n"
         "missing = required - set(en.columns)\n"
         "if missing:\n"
         "    raise ValueError(f'silver_enrolments missing columns {sorted(missing)}. Regenerate data and rerun bronze/silver.')"),
    code("# Aggregate assessment performance per enrolment (legitimate early-term features).\n"
         "asm_agg = (\n"
         "    asm.groupBy('enrolment_id')\n"
         "    .agg(\n"
         "        spark_round(avg('score'), 2).alias('avg_score'),\n"
         "        spark_round(avg('is_pass'), 4).alias('pass_rate'),\n"
         "        count('*').alias('assessment_count'),\n"
         "    )\n"
         ")\n\n"
         "# Join attributes + select pre-outcome features. EXCLUDE leakage (status, is_completed).\n"
         "ml_features = (\n"
         "    en.select(\n"
         "        'enrolment_id', 'student_id', 'department', 'level', 'credits', 'age_at_enrolment',\n"
         "        col('is_withdrawn').alias('had_dropout'),\n"
         "    )\n"
         "    .join(asm_agg, 'enrolment_id', 'left')\n"
         "    .join(st.select('student_id', 'programme', 'gender', 'region', 'cohort_year'),\n"
         "          'student_id', 'left')\n"
         "    .na.fill(0, subset=['avg_score', 'pass_rate', 'assessment_count', 'credits',\n"
         "                        'age_at_enrolment', 'cohort_year'])\n"
         "    .na.fill('unknown', subset=['department', 'level', 'programme', 'gender', 'region'])\n"
         "    .withColumn('feature_timestamp', current_timestamp())\n"
         ")\n\n"
         "total_rows = ml_features.count()\n"
         "positive_rows = ml_features.filter(col('had_dropout') == 1).count()\n"
         "dropout_rate = (positive_rows / total_rows * 100) if total_rows else 0.0\n\n"
         "if total_rows < 1000 or positive_rows < max(10, int(total_rows * 0.01)):\n"
         "    raise ValueError(\n"
         "        f'Label quality check failed: only {positive_rows}/{total_rows} dropout rows '\n"
         "        f'({dropout_rate:.2f}%). Check is_withdrawn typing and source data.'\n"
         "    )\n\n"
         "ml_features.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_features')\n"
         "print(f'Gold ML features written: {total_rows:,} rows | dropout rate {dropout_rate:.1f}%')"),
    code("spark.sql('OPTIMIZE gold_ml_features')\n"
         "print('Feature table optimized')"),
])

# ── ml/02_model_training ────────────────────────────────────────────────────
write(ML / "02_model_training.ipynb", [
    md("# Model Training — Dropout Risk Prediction\n\n"
       "PySpark **RandomForest classifier** (built-in). Target `had_dropout`.\n\n"
       "**Reads:** `gold_ml_features`  **Writes:** `gold_ml_model_metrics`, `Files/models/dropout_rf`"),
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
         "df.groupBy('had_dropout').count().show()"),
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_dropout').cast('double').alias('label'))\n"
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
         "    [('education', 'dropout-risk', 'RandomForestClassifier',\n"
         "      len(all_features), train_df.count(), test_df.count(),\n"
         "      float(auc), float(accuracy), float(f1))],\n"
         "    ['demo_id', 'use_case', 'model_type', 'feature_count',\n"
         "     'train_rows', 'test_rows', 'auc_roc', 'accuracy', 'f1_score']\n"
         ").withColumn('trained_at', current_timestamp())\n"
         "metrics.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_model_metrics')\n"
         "model.write().overwrite().save('Files/models/dropout_rf')\n"
         "model_df.unpersist()\n"
         "print('Metrics + model saved')"),
])

# ── ml/03_model_evaluation ──────────────────────────────────────────────────
write(ML / "03_model_evaluation.ipynb", [
    md("# Model Evaluation — Dropout Risk Prediction\n\n"
       "Confusion matrix, precision/recall, feature importance.\n\n"
       "**Reads:** `gold_ml_features` + saved model  **Writes:** `gold_ml_feature_importance`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
         "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
         "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "model = RandomForestClassificationModel.load('Files/models/dropout_rf')\n"
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_dropout').cast('double').alias('label'))\n"
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
    md("# Batch Scoring — Dropout Risk Prediction\n\n"
       "Scores every enrolment; writes predictions + per-department dropout risk summary.\n\n"
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
         "model = RandomForestClassificationModel.load('Files/models/dropout_rf')\n"
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
         "    .withColumn('dropout_probability', spark_round(extract_prob(col('probability')), 4))\n"
         "    .withColumn('predicted_dropout', col('prediction').cast('int'))\n"
         "    .withColumn('risk_level',\n"
         "        when(col('dropout_probability') > 0.8, 'critical')\n"
         "        .when(col('dropout_probability') > 0.6, 'high')\n"
         "        .when(col('dropout_probability') > 0.4, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('scored_at', current_timestamp())\n"
         "    .select(\n"
         "        'enrolment_id', 'student_id', 'department', 'level', 'programme',\n"
         "        'credits', 'age_at_enrolment', 'avg_score', 'pass_rate',\n"
         "        'had_dropout', 'predicted_dropout', 'dropout_probability', 'risk_level',\n"
         "        'scored_at')\n"
         ")\n"
         "predictions.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_predictions')\n"
         "print(f'Predictions written: {predictions.count():,} rows')\n"
         "predictions.groupBy('risk_level').count().orderBy('count', ascending=False).show()"),
    code("# Per-department dropout risk summary\n"
         "summary = (\n"
         "    predictions\n"
         "    .groupBy('department')\n"
         "    .agg(\n"
         "        count('*').alias('total_enrolments'),\n"
         "        spark_sum('predicted_dropout').alias('predicted_dropout_count'),\n"
         "        spark_sum('had_dropout').alias('actual_dropout_count'),\n"
         "        spark_round(avg('dropout_probability'), 4).alias('avg_dropout_probability'),\n"
         "        spark_round(avg('avg_score'), 1).alias('avg_assessment_score'),\n"
         "        spark_round(avg('age_at_enrolment'), 1).alias('avg_age'),\n"
         "    )\n"
         "    .withColumn('dropout_rate', spark_round(col('predicted_dropout_count') / col('total_enrolments') * 100, 1))\n"
         "    .withColumn('overall_risk',\n"
         "        when(col('avg_dropout_probability') > 0.6, 'high')\n"
         "        .when(col('avg_dropout_probability') > 0.3, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('summary_timestamp', current_timestamp())\n"
         "    .orderBy(col('avg_dropout_probability').desc())\n"
         ")\n"
         "summary.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_summary')\n"
         "print(f'Department dropout summary: {summary.count()} rows')\n"
         "summary.show(15, truncate=False)"),
    code("spark.sql('OPTIMIZE gold_ml_predictions')\n"
         "spark.sql('OPTIMIZE gold_ml_summary')\n"
         "print('All Gold ML tables optimized')"),
])

print("done")
