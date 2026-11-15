# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: knowledge base for Postgres (US-012)
# MAGIC
# MAGIC Builds the gold tables the app searches, in exactly the shape of the Postgres `kb` schema,
# MAGIC and writes them as an **export** (Parquet + `manifest.json`) into the volume
# MAGIC `<catalog>.gold.exports`. The exporter `rr_export.kb_job` then loads the export into
# MAGIC Postgres: staging tables, indexes, checks, **atomic swap** (design section 7.4).
# MAGIC
# MAGIC - `gold.kb_alerts`: one row per alert (newest version), EN + DE texts side by side
# MAGIC - `gold.kb_alert_identifiers`: exact-match keys (`gtin`, `brand_model`)
# MAGIC - `gold.kb_alert_images`: photos per alert (`is_main` = first photo)
# MAGIC
# MAGIC Columns and version come from `packages/export/src/rr_export/kb_schema.py`: the one
# MAGIC contract shared by this notebook, the exporter and the contract tests.
# MAGIC
# MAGIC Why files and not a direct database write: Databricks serverless cannot reach our Postgres
# MAGIC (firewall: developer IP only), and the lake never needs database passwords.

# COMMAND ----------

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "rr_dev")
CATALOG = dbutils.widgets.get("catalog")
if not re.fullmatch(r"rr_(dev|test|prod)", CATALOG):  # used in paths and table names
    raise ValueError(f"unexpected catalog {CATALOG!r}")

UTC = timezone.utc  # noqa: UP017 - datetime.UTC needs Python 3.11; the runtime may be older
RUN_AT = datetime.now(UTC)
EXPORT_ID = RUN_AT.strftime("%Y%m%dT%H%M%SZ")

# The notebook runs with its own folder (<repo>/pipelines/gold) as working directory.
PACKAGE_SRC = Path.cwd().parents[1] / "packages" / "export" / "src"
if not (PACKAGE_SRC / "rr_export").is_dir():
    raise RuntimeError(f"rr_export not found under {PACKAGE_SRC}: run from the Git folder")
sys.path.insert(0, str(PACKAGE_SRC))

from rr_export.kb_schema import LOAD_COLUMNS, SCHEMA_VERSION

EXPORT_ROOT = Path(f"/Volumes/{CATALOG}/gold/exports")
if not EXPORT_ROOT.is_dir():
    raise RuntimeError(f"{EXPORT_ROOT} missing: apply infra/terraform/unity-catalog first")
EXPORT_DIR = EXPORT_ROOT / "kb" / EXPORT_ID

SILVER = f"{CATALOG}.silver"
GOLD = {name: f"{CATALOG}.gold.kb_{name}" for name in LOAD_COLUMNS}
print(f"export_id={EXPORT_ID}\nschema_version={SCHEMA_VERSION}\nexport_dir={EXPORT_DIR}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build the gold tables

# COMMAND ----------


def title(df: DataFrame) -> Column:
    """Product type and name ("Toy car - Speedy 3000"); the category if both are empty."""
    joined = F.concat_ws(" - ", df["product"], df["product_name"])
    return F.when(joined != "", joined).otherwise(df["category"])


def build_alerts() -> DataFrame:
    """One row per alert: language-neutral fields once, texts per language side by side."""
    latest = spark.table(f"{SILVER}.sg_alerts").where("is_current OR is_withdrawn")
    english_first = Window.partitionBy("case_number").orderBy(F.desc(F.col("lang") == "en"))
    neutral = (
        latest.withColumn("_n", F.row_number().over(english_first))
        .where("_n = 1")
        .select(
            "case_number",
            "risk_level",
            "brand",
            "model",
            "notifying_country",
            "country_of_origin",
            F.col("publication_date").alias("published_at"),
            "is_withdrawn",
            "source_url",
            # As UTC text: Parquet timestamps differ between writers; Postgres parses ISO 8601.
            F.date_format(
                F.to_utc_timestamp("valid_from", spark.conf.get("spark.sql.session.timeZone")),
                "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'+00:00'",
            ).alias("valid_from"),
        )
    )

    def texts(lang: str) -> DataFrame:
        part = latest.where(F.col("lang") == lang)
        return part.select(
            "case_number",
            title(part).alias(f"title_{lang}"),
            F.col("category").alias(f"category_{lang}"),
            F.col("risk_type").alias(f"risk_type_{lang}"),
            F.col("description").alias(f"description_{lang}"),
            F.col("danger").alias(f"danger_{lang}"),
            F.col("measures").alias(f"measures_{lang}"),
        )

    alerts = neutral.join(texts("en"), "case_number", "left").join(
        texts("de"), "case_number", "left"
    )
    return alerts.select(*LOAD_COLUMNS["alerts"])


alerts = build_alerts()
keys = alerts.select("case_number")
identifiers = (
    spark.table(f"{SILVER}.sg_alert_identifiers")
    .join(keys, "case_number", "left_semi")
    .select(*LOAD_COLUMNS["alert_identifiers"])
    .distinct()
)
first_use = Window.partitionBy("case_number", "sha256").orderBy("ordinal")
images = (
    spark.table(f"{SILVER}.sg_alert_images")
    .join(keys, "case_number", "left_semi")
    .withColumn("_n", F.row_number().over(first_use))  # same photo twice in one alert: keep one
    .where("_n = 1")
    .select(*LOAD_COLUMNS["alert_images"])
)

for name, frame in [
    ("alerts", alerts),
    ("alert_identifiers", identifiers),
    ("alert_images", images),
]:
    frame.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(GOLD[name])
    print(f"written {GOLD[name]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Checks before export
# MAGIC
# MAGIC The same rules as the Postgres constraints, so a problem shows here and not halfway
# MAGIC through a database load.

# COMMAND ----------

g_alerts, g_ids, g_images = (spark.table(GOLD[n]) for n in LOAD_COLUMNS)
counts = {name: spark.table(GOLD[name]).count() for name in LOAD_COLUMNS}
problems = {
    "duplicate alert keys": g_alerts.groupBy("case_number").count().where("count > 1").count(),
    "duplicate identifier keys": g_ids.groupBy(*LOAD_COLUMNS["alert_identifiers"])
    .count()
    .where("count > 1")
    .count(),
    "duplicate image keys": g_images.groupBy("case_number", "sha256")
    .count()
    .where("count > 1")
    .count(),
    "identifiers of unknown alerts": g_ids.join(g_alerts, "case_number", "left_anti").count(),
    "images of unknown alerts": g_images.join(g_alerts, "case_number", "left_anti").count(),
    "unknown risk level codes": g_alerts.where(
        ~F.col("risk_level").isin("serious", "other_risk", "other_alert", "unknown")
    ).count(),
    "missing dates": g_alerts.where("published_at IS NULL OR valid_from IS NULL").count(),
    "GTINs not 14 digits": g_ids.where(
        "kind = 'gtin' AND value_norm NOT RLIKE '^[0-9]{14}$'"
    ).count(),
    "bad photo hashes": g_images.where("sha256 NOT RLIKE '^[0-9a-f]{64}$'").count(),
}
for check, failed in problems.items():
    print(f"{check}: {failed} (expected 0)")
print(f"rows: {counts}")
assert not any(problems.values()), "gold checks failed: nothing exported"
print("CHECKS PASSED")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write the export
# MAGIC
# MAGIC Data first, `manifest.json` last: an export without a manifest is incomplete, and the
# MAGIC exporter refuses it.

# COMMAND ----------

for name in LOAD_COLUMNS:
    spark.table(GOLD[name]).coalesce(1).write.mode("overwrite").parquet(str(EXPORT_DIR / name))

manifest = {
    "export_id": EXPORT_ID,
    "schema_version": SCHEMA_VERSION,
    "created_at": RUN_AT.isoformat(),
    "catalog": CATALOG,
    "tables": {
        name: {"rows": counts[name], "columns": list(LOAD_COLUMNS[name])} for name in LOAD_COLUMNS
    },
}
(EXPORT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"export {EXPORT_ID} written: {counts}")
print(
    "\nLoad it into Postgres from your laptop:\n"
    f"  databricks fs cp -r dbfs:{EXPORT_DIR} data/local/exports/kb/{EXPORT_ID}\n"
    f"  uv run python -m rr_export.kb_job --export-dir data/local/exports/kb/{EXPORT_ID}"
)
