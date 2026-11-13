# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze: Safety Gate alerts (US-007)
# MAGIC
# MAGIC Reads new weekly report files from the landing volume with **Auto Loader** and appends one
# MAGIC row per alert (`<notifications>` element) to `<catalog>.bronze.sg_alerts_raw`.
# MAGIC
# MAGIC - **Exactly once per file:** the checkpoint remembers which files were processed; a re-run
# MAGIC   or a re-upload of the same file adds nothing.
# MAGIC - **Raw:** every field is kept as text, exactly as delivered; silver cleans it (US-010).
# MAGIC - **Unknown fields are kept** in `_rescued_data` (schema evolution mode `rescue`).
# MAGIC - **Metadata:** `_source_file`, `_ingested_at`, `_batch_id`, `_report_reference`,
# MAGIC   `_licence`.
# MAGIC
# MAGIC Design: `docs/architecture/data-storage-design.md`, section 6.

# COMMAND ----------

import re
import uuid

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "rr_dev")
CATALOG = dbutils.widgets.get("catalog")
if not re.fullmatch(r"rr_(dev|test|prod)", CATALOG):  # used in paths and table names
    raise ValueError(f"unexpected catalog {CATALOG!r}")
BATCH_ID = str(uuid.uuid4())

VOLUME = f"/Volumes/{CATALOG}/bronze/landing"
SOURCE = f"{VOLUME}/safety_gate/reports"
STATE = f"{VOLUME}/_state/sg_alerts_raw"  # Auto Loader checkpoint + inferred schema
TARGET = f"{CATALOG}.bronze.sg_alerts_raw"
LICENCE = "European Commission, Safety Gate; reuse with attribution (Decision 2011/833/EU)"

print(f"batch_id={BATCH_ID}\nsource={SOURCE}\ntarget={TARGET}")

# COMMAND ----------


def read_alerts(source: str, schema_location: str) -> DataFrame:
    """Stream new report files from ``source``; one row per <notifications> element."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "xml")
        .option("rowTag", "notifications")
        .option("excludeAttribute", "true")  # xsi:type / xsi:nil carry no data
        .option("cloudFiles.inferColumnTypes", "false")  # bronze keeps text as text
        .option("cloudFiles.schemaLocation", schema_location)
        .option("cloudFiles.schemaEvolutionMode", "rescue")  # unknown fields -> _rescued_data
        .option("cloudFiles.partitionColumns", "lang")  # from the lang=en / lang=de folders
        .load(source)
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn(
            "_report_reference",
            F.regexp_extract(F.col("_metadata.file_name"), r"^(Report-\d{4}-\d+)_", 1),
        )
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_batch_id", F.lit(BATCH_ID))
        .withColumn("_licence", F.lit(LICENCE))
    )


def ingest(source: str, target: str, state: str) -> None:
    """Process all files not yet seen, then stop (no cluster left running)."""
    query = (
        read_alerts(source, f"{state}/schema")
        .writeStream.option("checkpointLocation", f"{state}/checkpoint")
        .trigger(availableNow=True)
        .toTable(target)
    )
    query.awaitTermination()


# COMMAND ----------

ingest(SOURCE, TARGET, STATE)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check: rows, alerts and files per language

# COMMAND ----------

display(
    spark.table(TARGET)
    .groupBy("lang")
    .agg(
        F.count("*").alias("alert_rows"),
        F.countDistinct("caseNumber").alias("distinct_cases"),
        F.countDistinct("_source_file").alias("files"),
        F.max("_ingested_at").alias("last_ingested_at"),
    )
    .orderBy("lang")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Self-test of the acceptance criteria (temporary table, removed at the end)
# MAGIC
# MAGIC 1. A known file is ingested.
# MAGIC 2. The same file again adds no rows.
# MAGIC 3. A file with an unknown field keeps that field in `_rescued_data`.

# COMMAND ----------

TEST_DIR = f"{VOLUME}/_selftest/{BATCH_ID}"
TEST_STATE = f"{VOLUME}/_state/selftest_{BATCH_ID}"
TEST_TABLE = f"{CATALOG}.bronze.selftest_{BATCH_ID.replace('-', '_')}"

KNOWN = (
    "<Safety-Gate><notifications><caseNumber>TEST/00001/26</caseNumber>"
    "<brand>A</brand></notifications></Safety-Gate>"
)
UNKNOWN = (
    "<Safety-Gate><notifications><caseNumber>TEST/00002/26</caseNumber>"
    "<brand>B</brand><brandNewField>kept</brandNewField></notifications></Safety-Gate>"
)

try:
    dbutils.fs.put(f"{TEST_DIR}/lang=en/Report-0000-1_known.xml", KNOWN, True)
    ingest(TEST_DIR, TEST_TABLE, TEST_STATE)
    after_first = spark.table(TEST_TABLE).count()

    ingest(TEST_DIR, TEST_TABLE, TEST_STATE)  # same file again
    after_rerun = spark.table(TEST_TABLE).count()

    dbutils.fs.put(f"{TEST_DIR}/lang=en/Report-0000-2_unknown.xml", UNKNOWN, True)
    ingest(TEST_DIR, TEST_TABLE, TEST_STATE)
    rescued = (
        spark.table(TEST_TABLE)
        .where("caseNumber = 'TEST/00002/26'")
        .select("_rescued_data")
        .first()[0]
    )

    print(f"1. rows after first run: {after_first} (expected 1)")
    print(f"2. rows after re-run:    {after_rerun} (expected 1)")
    print(f"3. _rescued_data:        {rescued} (expected to contain brandNewField)")
    assert after_first == 1 and after_rerun == 1
    assert rescued is not None and "brandNewField" in rescued
    print("SELF-TEST PASSED")
finally:
    spark.sql(f"DROP TABLE IF EXISTS {TEST_TABLE}")
    dbutils.fs.rm(TEST_DIR, True)
    dbutils.fs.rm(TEST_STATE, True)
