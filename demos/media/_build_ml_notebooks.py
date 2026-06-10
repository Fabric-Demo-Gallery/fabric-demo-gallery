"""One-shot builder for the media AI/ML notebooks.

Use case: content completion prediction (binary classification).
Target: had_complete (from is_completed). Built-in PySpark RandomForestClassifier.
Grain: one row per viewing session. Summary keyed by content genre.

Run once:  python demos/media/_build_ml_notebooks.py
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
    "    'duration_mins', 'release_year', 'monthly_fee',\n"
    "    'view_hour', 'view_dow', 'is_weekend',\n"
    "]\n"
    "cat_cols = ['genre', 'content_type', 'production_cost_bucket', 'language',\n"
    "            'plan_type', 'region', 'age_group', 'device_type']"
)

CSV = [
    ("content_catalog", "bronze_content"),
    ("subscribers", "bronze_subscribers"),
    ("viewing_history", "bronze_viewing"),
    ("ad_impressions", "bronze_ad_impressions"),
]

# ── batch/01_bronze_ingest ──────────────────────────────────────────────────
bronze_cells = [
    md("# Bronze Layer — Ingest Raw Media Data\n"
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
    md("# Silver Layer — Clean & Conform Media Data\n"
       "Dedupe, cast types. Keeps viewing label is_completed; FE drops post-view leakage."),
    code("from pyspark.sql.functions import (\n"
         "    col, when, lit, to_date, row_number, current_timestamp\n"
         ")\n"
         "from pyspark.sql.window import Window"),
    code("# Clean content catalog\n"
         "df_c = spark.read.format('delta').table('bronze_content')\n"
         "w = Window.partitionBy('content_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_c = (\n"
         "    df_c.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('release_year', col('release_year').cast('int'))\n"
         "    .withColumn('duration_mins', col('duration_mins').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_c.write.mode('overwrite').format('delta').saveAsTable('silver_content')\n"
         "print(f'silver_content: {df_c.count()} rows')"),
    code("# Clean subscribers\n"
         "df_s = spark.read.format('delta').table('bronze_subscribers')\n"
         "w2 = Window.partitionBy('subscriber_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_s = (\n"
         "    df_s.withColumn('_rn', row_number().over(w2)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('monthly_fee', col('monthly_fee').cast('double'))\n"
         "    .withColumn('is_churned', col('is_churned').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_s.write.mode('overwrite').format('delta').saveAsTable('silver_subscribers')\n"
         "print(f'silver_subscribers: {df_s.count()} rows')"),
    code("# Clean viewing history (keep label is_completed)\n"
         "df_v = spark.read.format('delta').table('bronze_viewing')\n"
         "w3 = Window.partitionBy('view_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_v = (\n"
         "    df_v.withColumn('_rn', row_number().over(w3)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('view_date', to_date('view_date'))\n"
         "    .withColumn('view_hour', col('view_hour').cast('int'))\n"
         "    .withColumn('watch_duration_mins', col('watch_duration_mins').cast('double'))\n"
         "    .withColumn('is_completed', col('is_completed').cast('int'))\n"
         "    .withColumn('rating', col('rating').cast('int'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_v.write.mode('overwrite').format('delta').saveAsTable('silver_viewing')\n"
         "print(f'silver_viewing: {df_v.count()} rows')"),
    code("# Clean ad impressions\n"
         "df_a = spark.read.format('delta').table('bronze_ad_impressions')\n"
         "df_a = (\n"
         "    df_a\n"
         "    .withColumn('ad_date', to_date('ad_date'))\n"
         "    .withColumn('impressions', col('impressions').cast('int'))\n"
         "    .withColumn('clicks', col('clicks').cast('int'))\n"
         "    .withColumn('revenue_usd', col('revenue_usd').cast('double'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_a.write.mode('overwrite').format('delta').saveAsTable('silver_ad_impressions')\n"
         "print(f'silver_ad_impressions: {df_a.count()} rows')"),
])

# ── ml/01_feature_engineering ───────────────────────────────────────────────
write(ML / "01_feature_engineering.ipynb", [
    md("# Feature Engineering — Content Completion Prediction\n\n"
       "Joins each viewing session with content + subscriber attributes and derives\n"
       "pre-view context features. EXCLUDES post-view leakage (watch_duration_mins, rating).\n\n"
       "**Reads:** `silver_viewing`, `silver_content`, `silver_subscribers`  "
       "**Writes:** `gold_ml_features`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, dayofweek\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "print('Spark session ready')"),
    code("vh = spark.read.table('silver_viewing')\n"
         "c = spark.read.table('silver_content')\n"
         "s = spark.read.table('silver_subscribers')\n"
         "print(f'views={vh.count():,} content={c.count():,} subscribers={s.count():,}')\n\n"
         "required = {'view_id', 'subscriber_id', 'content_id', 'is_completed', 'view_hour'}\n"
         "missing = required - set(vh.columns)\n"
         "if missing:\n"
         "    raise ValueError(f'silver_viewing missing columns {sorted(missing)}. Regenerate data and rerun bronze/silver.')"),
    code("# Join attributes + derive context features. EXCLUDE leakage (watch_duration_mins, rating).\n"
         "# dayofweek(): 1=Sunday..7=Saturday -> map to 0=Mon..6=Sun and weekend flag.\n"
         "ml_features = (\n"
         "    vh.select(\n"
         "        'view_id', 'subscriber_id', 'content_id', 'device_type', 'view_hour', 'view_date',\n"
         "        col('is_completed').alias('had_complete'),\n"
         "    )\n"
         "    .join(c.select('content_id', 'genre', 'content_type', 'release_year',\n"
         "                   'duration_mins', 'production_cost_bucket', 'language'),\n"
         "          'content_id', 'left')\n"
         "    .join(s.select('subscriber_id', 'plan_type', 'region', 'age_group', 'monthly_fee'),\n"
         "          'subscriber_id', 'left')\n"
         "    .withColumn('view_dow', ((dayofweek(col('view_date')) + 5) % 7))\n"
         "    .withColumn('is_weekend', when(col('view_dow') >= 5, lit(1)).otherwise(lit(0)))\n"
         "    .drop('view_date')\n"
         "    .na.fill(0)\n"
         "    .na.fill('unknown', subset=['genre', 'content_type', 'production_cost_bucket', 'language',\n"
         "                                'plan_type', 'region', 'age_group', 'device_type'])\n"
         "    .withColumn('feature_timestamp', current_timestamp())\n"
         ")\n\n"
         "total_rows = ml_features.count()\n"
         "positive_rows = ml_features.filter(col('had_complete') == 1).count()\n"
         "complete_rate = (positive_rows / total_rows * 100) if total_rows else 0.0\n\n"
         "if total_rows < 1000 or positive_rows < max(10, int(total_rows * 0.01)):\n"
         "    raise ValueError(\n"
         "        f'Label quality check failed: only {positive_rows}/{total_rows} completed rows '\n"
         "        f'({complete_rate:.2f}%). Check is_completed typing and source data.'\n"
         "    )\n\n"
         "ml_features.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_features')\n"
         "print(f'Gold ML features written: {total_rows:,} rows | completion rate {complete_rate:.1f}%')"),
    code("spark.sql('OPTIMIZE gold_ml_features')\n"
         "print('Feature table optimized')"),
])

# ── ml/02_model_training ────────────────────────────────────────────────────
write(ML / "02_model_training.ipynb", [
    md("# Model Training — Content Completion Prediction\n\n"
       "PySpark **RandomForest classifier** (built-in). Target `had_complete`.\n\n"
       "**Reads:** `gold_ml_features`  **Writes:** `gold_ml_model_metrics`, `Files/models/completion_rf`"),
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
         "df.groupBy('had_complete').count().show()"),
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_complete').cast('double').alias('label'))\n"
         "model_df = model_df.cache()\n"
         "print(f'Model rows: {model_df.count():,} | features: {len(all_features)}')"),
    code("train_df, test_df = model_df.randomSplit([0.8, 0.2], seed=42)\n"
         "print(f'Train: {train_df.count():,}  Test: {test_df.count():,}')"),
    code("rf = RandomForestClassifier(\n"
         "    featuresCol='features', labelCol='label',\n"
         "    predictionCol='prediction', rawPredictionCol='rawPrediction', probabilityCol='probability',\n"
         "    numTrees=100, maxDepth=10, seed=42,\n"
         ")\n"
         "model = rf.fit(train_df)\n"
         "print('RandomForest classifier trained')"),
    code("predictions = model.transform(test_df)\n"
         "auc = BinaryClassificationEvaluator(labelCol='label', rawPredictionCol='rawPrediction', metricName='areaUnderROC').evaluate(predictions)\n"
         "accuracy = MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='accuracy').evaluate(predictions)\n"
         "f1 = MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='f1').evaluate(predictions)\n"
         "print(f'AUC-ROC: {auc:.4f}  Accuracy: {accuracy:.4f}  F1: {f1:.4f}')"),
    code("metrics = spark.createDataFrame(\n"
         "    [('media', 'content-completion', 'RandomForestClassifier',\n"
         "      len(all_features), train_df.count(), test_df.count(),\n"
         "      float(auc), float(accuracy), float(f1))],\n"
         "    ['demo_id', 'use_case', 'model_type', 'feature_count',\n"
         "     'train_rows', 'test_rows', 'auc_roc', 'accuracy', 'f1_score']\n"
         ").withColumn('trained_at', current_timestamp())\n"
         "metrics.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_model_metrics')\n"
         "model.write().overwrite().save('Files/models/completion_rf')\n"
         "model_df.unpersist()\n"
         "print('Metrics + model saved')"),
])

# ── ml/03_model_evaluation ──────────────────────────────────────────────────
write(ML / "03_model_evaluation.ipynb", [
    md("# Model Evaluation — Content Completion Prediction\n\n"
       "Confusion matrix, precision/recall, feature importance.\n\n"
       "**Reads:** `gold_ml_features` + saved model  **Writes:** `gold_ml_feature_importance`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, isnan\n"
         "from pyspark.ml.feature import VectorAssembler, StringIndexer\n"
         "from pyspark.ml.classification import RandomForestClassificationModel\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "model = RandomForestClassificationModel.load('Files/models/completion_rf')\n"
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_complete').cast('double').alias('label'))\n"
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
    md("# Batch Scoring — Content Completion Prediction\n\n"
       "Scores every viewing session; writes predictions + per-genre engagement summary.\n\n"
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
         "model = RandomForestClassificationModel.load('Files/models/completion_rf')\n"
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
         "    .withColumn('complete_probability', spark_round(extract_prob(col('probability')), 4))\n"
         "    .withColumn('predicted_complete', col('prediction').cast('int'))\n"
         "    .withColumn('engagement_level',\n"
         "        when(col('complete_probability') > 0.8, 'very_high')\n"
         "        .when(col('complete_probability') > 0.6, 'high')\n"
         "        .when(col('complete_probability') > 0.4, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('scored_at', current_timestamp())\n"
         "    .select(\n"
         "        'view_id', 'subscriber_id', 'content_id', 'genre', 'content_type', 'device_type',\n"
         "        'plan_type', 'duration_mins',\n"
         "        'had_complete', 'predicted_complete', 'complete_probability', 'engagement_level',\n"
         "        'scored_at')\n"
         ")\n"
         "predictions.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_predictions')\n"
         "print(f'Predictions written: {predictions.count():,} rows')\n"
         "predictions.groupBy('engagement_level').count().orderBy('count', ascending=False).show()"),
    code("# Per-genre engagement summary\n"
         "summary = (\n"
         "    predictions\n"
         "    .groupBy('genre')\n"
         "    .agg(\n"
         "        count('*').alias('total_views'),\n"
         "        spark_sum('predicted_complete').alias('predicted_complete_count'),\n"
         "        spark_sum('had_complete').alias('actual_complete_count'),\n"
         "        spark_round(avg('complete_probability'), 4).alias('avg_complete_probability'),\n"
         "        spark_round(avg('duration_mins'), 1).alias('avg_duration_mins'),\n"
         "    )\n"
         "    .withColumn('completion_rate', spark_round(col('predicted_complete_count') / col('total_views') * 100, 1))\n"
         "    .withColumn('overall_engagement',\n"
         "        when(col('avg_complete_probability') > 0.6, 'high')\n"
         "        .when(col('avg_complete_probability') > 0.4, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('summary_timestamp', current_timestamp())\n"
         "    .orderBy(col('avg_complete_probability').desc())\n"
         ")\n"
         "summary.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_summary')\n"
         "print(f'Genre engagement summary: {summary.count()} rows')\n"
         "summary.show(15, truncate=False)"),
    code("spark.sql('OPTIMIZE gold_ml_predictions')\n"
         "spark.sql('OPTIMIZE gold_ml_summary')\n"
         "print('All Gold ML tables optimized')"),
])

print("done")
