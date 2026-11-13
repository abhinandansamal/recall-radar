# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze: GPSR legal text (US-009)
# MAGIC
# MAGIC Reads new JSON envelopes (one per document version and language) from the landing volume
# MAGIC with **Auto Loader** and appends them to `<catalog>.bronze.gpsr_raw`.
# MAGIC
# MAGIC - One row per version and language: original (2023), consolidated (2026); EN + DE.
# MAGIC - `content` holds the XHTML text exactly as delivered by the Publications Office (Cellar).
# MAGIC - `source_url` and `retrieved_at` come from the downloader (acceptance criterion of US-009).
# MAGIC - Splitting into articles and paragraphs happens in silver.

# COMMAND ----------

import re
import uuid

from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "rr_dev")
CATALOG = dbutils.widgets.get("catalog")
if not re.fullmatch(r"rr_(dev|test|prod)", CATALOG):  # used in paths and table names
    raise ValueError(f"unexpected catalog {CATALOG!r}")
BATCH_ID = str(uuid.uuid4())

VOLUME = f"/Volumes/{CATALOG}/bronze/landing"
SOURCE = f"{VOLUME}/gpsr"
STATE = f"{VOLUME}/_state/gpsr_raw"
TARGET = f"{CATALOG}.bronze.gpsr_raw"

print(f"batch_id={BATCH_ID}\nsource={SOURCE}\ntarget={TARGET}")

# COMMAND ----------

query = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.inferColumnTypes", "false")  # bronze keeps text as text
    .option("cloudFiles.schemaLocation", f"{STATE}/schema")
    .option("cloudFiles.schemaEvolutionMode", "rescue")
    .option("cloudFiles.partitionColumns", "lang")  # from the lang=en / lang=de folders
    .load(SOURCE)
    .withColumn("_source_file", F.col("_metadata.file_path"))
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_batch_id", F.lit(BATCH_ID))
    .writeStream.option("checkpointLocation", f"{STATE}/checkpoint")
    .trigger(availableNow=True)
    .toTable(TARGET)
)
query.awaitTermination()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check: one row per version and language, with source and retrieval date

# COMMAND ----------

display(
    spark.table(TARGET)
    .select(
        "version",
        "lang",
        "celex",
        "article_count",
        "size_bytes",
        F.length("content").alias("content_chars"),
        "source_url",
        "retrieved_at",
        "_ingested_at",
    )
    .orderBy("version", "lang")
)
