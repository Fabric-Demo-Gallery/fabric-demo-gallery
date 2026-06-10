"""One-shot builder for the transportation AI/ML notebooks.

Use case: delivery delay (is_late) prediction (binary classification).
Target: had_late (from is_late). Built-in PySpark RandomForestClassifier.

Run once:  python demos/transportation/_build_ml_notebooks.py
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
    "    'planned_duration_hrs', 'distance_km', 'load_tonnes', 'load_utilisation',\n"
    "    'sla_hours', 'toll_cost_gbp', 'capacity_tonnes', 'vehicle_age',\n"
    "    'departure_hour', 'departure_dow', 'is_weekend', 'is_rush',\n"
    "]\n"
    "cat_cols = ['vehicle_type', 'depot', 'route_type']"
)

CSV = [
    ("vehicles", "bronze_vehicles"),
    ("routes", "bronze_routes"),
    ("deliveries", "bronze_deliveries"),
    ("fuel_logs", "bronze_fuel_logs"),
]

# ── batch/01_bronze_ingest ──────────────────────────────────────────────────
bronze_cells = [
    md("# Bronze Layer — Ingest Raw Transportation Data\n"
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
    md("# Silver Layer — Clean & Conform Transportation Data\n"
       "Dedupe, cast timestamps, derive vehicle age. NO post-trip leakage columns added."),
    code("from pyspark.sql.functions import (\n"
         "    col, when, lit, to_timestamp, year, current_date,\n"
         "    row_number, current_timestamp\n"
         ")\n"
         "from pyspark.sql.window import Window"),
    code("# Clean vehicles\n"
         "df_v = spark.read.format('delta').table('bronze_vehicles')\n"
         "w = Window.partitionBy('vehicle_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_v = (\n"
         "    df_v.withColumn('_rn', row_number().over(w)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('capacity_tonnes', col('capacity_tonnes').cast('double'))\n"
         "    .withColumn('year_registered', col('year_registered').cast('int'))\n"
         "    .withColumn('vehicle_age', year(current_date()) - col('year_registered'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_v.write.mode('overwrite').format('delta').saveAsTable('silver_vehicles')\n"
         "print(f'silver_vehicles: {df_v.count()} rows')"),
    code("# Clean routes\n"
         "df_r = spark.read.format('delta').table('bronze_routes')\n"
         "w2 = Window.partitionBy('route_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_r = (\n"
         "    df_r.withColumn('_rn', row_number().over(w2)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('distance_km', col('distance_km').cast('double'))\n"
         "    .withColumn('sla_hours', col('sla_hours').cast('double'))\n"
         "    .withColumn('toll_cost_gbp', col('toll_cost_gbp').cast('double'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_r.write.mode('overwrite').format('delta').saveAsTable('silver_routes')\n"
         "print(f'silver_routes: {df_r.count()} rows')"),
    code("# Clean deliveries (keep label is_late; downstream FE drops post-trip leakage)\n"
         "df_d = spark.read.format('delta').table('bronze_deliveries')\n"
         "w3 = Window.partitionBy('delivery_id').orderBy(col('ingestion_timestamp').desc())\n"
         "df_d = (\n"
         "    df_d.withColumn('_rn', row_number().over(w3)).filter(col('_rn') == 1).drop('_rn')\n"
         "    .withColumn('planned_departure', to_timestamp('planned_departure'))\n"
         "    .withColumn('planned_duration_hrs', col('planned_duration_hrs').cast('double'))\n"
         "    .withColumn('distance_km', col('distance_km').cast('double'))\n"
         "    .withColumn('load_tonnes', col('load_tonnes').cast('double'))\n"
         "    .withColumn('is_late', col('is_late').cast('int'))\n"
         "    .filter(col('planned_departure').isNotNull())\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_d.write.mode('overwrite').format('delta').saveAsTable('silver_deliveries')\n"
         "print(f'silver_deliveries: {df_d.count()} rows')"),
    code("# Clean fuel logs\n"
         "df_f = spark.read.format('delta').table('bronze_fuel_logs')\n"
         "df_f = (\n"
         "    df_f\n"
         "    .withColumn('litres_filled', col('litres_filled').cast('double'))\n"
         "    .withColumn('total_cost_gbp', col('total_cost_gbp').cast('double'))\n"
         "    .withColumn('silver_timestamp', current_timestamp())\n"
         ")\n"
         "df_f.write.mode('overwrite').format('delta').saveAsTable('silver_fuel_logs')\n"
         "print(f'silver_fuel_logs: {df_f.count()} rows')"),
])

# ── ml/01_feature_engineering ───────────────────────────────────────────────
write(ML / "01_feature_engineering.ipynb", [
    md("# Feature Engineering — Delivery Delay Prediction\n\n"
       "Joins deliveries with vehicle + route attributes and derives pre-departure\n"
       "features for delay classification. EXCLUDES post-trip leakage\n"
       "(actual_arrival, actual_duration_hrs, delay_hrs, status).\n\n"
       "**Reads:** `silver_deliveries`, `silver_vehicles`, `silver_routes`  "
       "**Writes:** `gold_ml_features`"),
    code("from pyspark.sql import SparkSession\n"
         "from pyspark.sql.functions import col, lit, current_timestamp, when, hour, dayofweek\n\n"
         "spark = SparkSession.builder.getOrCreate()\n"
         "print('Spark session ready')"),
    code("dl = spark.read.table('silver_deliveries')\n"
         "veh = spark.read.table('silver_vehicles')\n"
         "rt = spark.read.table('silver_routes')\n"
         "print(f'deliveries={dl.count():,} vehicles={veh.count():,} routes={rt.count():,}')\n\n"
         "required = {'delivery_id', 'vehicle_id', 'route_id', 'is_late', 'planned_duration_hrs'}\n"
         "missing = required - set(dl.columns)\n"
         "if missing:\n"
         "    raise ValueError(f'silver_deliveries missing columns {sorted(missing)}. Regenerate data and rerun bronze/silver.')"),
    code("# Join attributes + derive pre-departure features. EXCLUDE leakage columns.\n"
         "ml_features = (\n"
         "    dl.select(\n"
         "        'delivery_id', 'vehicle_id', 'route_id', 'planned_departure',\n"
         "        'planned_duration_hrs', 'distance_km', 'load_tonnes',\n"
         "        col('is_late').alias('had_late'),\n"
         "    )\n"
         "    .join(veh.select('vehicle_id', 'vehicle_type', 'depot', 'capacity_tonnes', 'vehicle_age'),\n"
         "          'vehicle_id', 'left')\n"
         "    .join(rt.select('route_id', 'route_type', 'sla_hours', 'toll_cost_gbp'),\n"
         "          'route_id', 'left')\n"
         "    .withColumn('load_utilisation',\n"
         "        when(col('capacity_tonnes') > 0, col('load_tonnes') / col('capacity_tonnes')).otherwise(0.0))\n"
         "    .withColumn('departure_hour', hour('planned_departure'))\n"
         "    .withColumn('departure_dow', dayofweek('planned_departure'))\n"
         "    .withColumn('is_weekend', when(dayofweek('planned_departure').isin(1, 7), 1).otherwise(0))\n"
         "    .withColumn('is_rush', when(hour('planned_departure').isin(7, 8, 9, 16, 17, 18, 19), 1).otherwise(0))\n"
         "    .na.fill(0)\n"
         "    .na.fill('unknown', subset=['vehicle_type', 'depot', 'route_type'])\n"
         "    .withColumn('feature_timestamp', current_timestamp())\n"
         ")\n\n"
         "total_rows = ml_features.count()\n"
         "positive_rows = ml_features.filter(col('had_late') == 1).count()\n"
         "late_rate = (positive_rows / total_rows * 100) if total_rows else 0.0\n\n"
         "if total_rows < 1000 or positive_rows < max(10, int(total_rows * 0.01)):\n"
         "    raise ValueError(\n"
         "        f'Label quality check failed: only {positive_rows}/{total_rows} late rows '\n"
         "        f'({late_rate:.2f}%). Check is_late typing and source data.'\n"
         "    )\n\n"
         "ml_features.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_features')\n"
         "print(f'Gold ML features written: {total_rows:,} rows | late rate {late_rate:.1f}%')"),
    code("spark.sql('OPTIMIZE gold_ml_features')\n"
         "print('Feature table optimized')"),
])

# ── ml/02_model_training ────────────────────────────────────────────────────
write(ML / "02_model_training.ipynb", [
    md("# Model Training — Delivery Delay Prediction\n\n"
       "PySpark **RandomForest classifier** (built-in). Target `had_late`.\n\n"
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
         "df.groupBy('had_late').count().show()"),
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_late').cast('double').alias('label'))\n"
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
         "    [('transportation', 'delivery-delay', 'RandomForestClassifier',\n"
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
    md("# Model Evaluation — Delivery Delay Prediction\n\n"
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
         "model_df = assembler.transform(indexed_df).select('features', col('had_late').cast('double').alias('label'))\n"
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
    md("# Batch Scoring — Delivery Delay Prediction\n\n"
       "Scores every delivery; writes predictions + per-depot delay risk summary.\n\n"
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
         "    .withColumn('predicted_late', col('prediction').cast('int'))\n"
         "    .withColumn('risk_level',\n"
         "        when(col('delay_probability') > 0.8, 'critical')\n"
         "        .when(col('delay_probability') > 0.6, 'high')\n"
         "        .when(col('delay_probability') > 0.4, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('scored_at', current_timestamp())\n"
         "    .select(\n"
         "        'delivery_id', 'vehicle_id', 'route_id', 'vehicle_type', 'depot', 'route_type',\n"
         "        'distance_km', 'load_utilisation', 'planned_duration_hrs',\n"
         "        'had_late', 'predicted_late', 'delay_probability', 'risk_level',\n"
         "        'scored_at')\n"
         ")\n"
         "predictions.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_predictions')\n"
         "print(f'Predictions written: {predictions.count():,} rows')\n"
         "predictions.groupBy('risk_level').count().orderBy('count', ascending=False).show()"),
    code("# Per-depot delay risk summary\n"
         "summary = (\n"
         "    predictions\n"
         "    .groupBy('depot')\n"
         "    .agg(\n"
         "        count('*').alias('total_deliveries'),\n"
         "        spark_sum('predicted_late').alias('predicted_late_count'),\n"
         "        spark_sum('had_late').alias('actual_late_count'),\n"
         "        spark_round(avg('delay_probability'), 4).alias('avg_delay_probability'),\n"
         "        spark_round(avg('distance_km'), 1).alias('avg_distance_km'),\n"
         "        spark_round(avg('load_utilisation'), 3).alias('avg_load_utilisation'),\n"
         "    )\n"
         "    .withColumn('late_rate', spark_round(col('predicted_late_count') / col('total_deliveries') * 100, 1))\n"
         "    .withColumn('overall_risk',\n"
         "        when(col('avg_delay_probability') > 0.6, 'high')\n"
         "        .when(col('avg_delay_probability') > 0.3, 'medium')\n"
         "        .otherwise('low'))\n"
         "    .withColumn('summary_timestamp', current_timestamp())\n"
         "    .orderBy(col('avg_delay_probability').desc())\n"
         ")\n"
         "summary.write.mode('overwrite').option('overwriteSchema', 'true').format('delta').saveAsTable('gold_ml_summary')\n"
         "print(f'Depot delay summary: {summary.count()} rows')\n"
         "summary.show(15, truncate=False)"),
    code("spark.sql('OPTIMIZE gold_ml_predictions')\n"
         "spark.sql('OPTIMIZE gold_ml_summary')\n"
         "print('All Gold ML tables optimized')"),
])

print("done")
