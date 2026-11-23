# Databricks notebook source
# MAGIC %md
# MAGIC # Matching gold set v1 (US-013 step B)
# MAGIC
# MAGIC Builds the screening (W1) gold set from our own data with `rr_eval.matching_builder`:
# MAGIC
# MAGIC - **Repeat alerts:** alerts that share a GTIN or brand + model are one product. One alert
# MAGIC   becomes the listing and is excluded; the others must be found ("leave one out").
# MAGIC   Variants: with identifiers, without identifiers, German text, photo only, evasion.
# MAGIC - **Safe look-alikes:** ABO products of the alerted kinds; expected result "clear".
# MAGIC
# MAGIC Splits are per product (60 % dev, 30 % test, 10 % holdout), from a hash, so a rerun on
# MAGIC the same data gives the same file.
# MAGIC
# MAGIC Output in `/Volumes/<catalog>/gold/exports/evals/matching/v1/`:
# MAGIC `v1.jsonl` (dev + test), `v1.holdout.jsonl` and `spot_check.csv` (30 cases for the
# MAGIC Product Owner). The files are then committed to `evals/data/matching/`; CI validates
# MAGIC them against `rr_eval.schemas.MatchingCase`.

# COMMAND ----------

import csv
import io
import re
import sys
from collections import Counter
from pathlib import Path

from pyspark.sql import Column
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "rr_dev")
dbutils.widgets.text("max_groups", "300")
dbutils.widgets.text("max_look_alikes", "100")
CATALOG = dbutils.widgets.get("catalog")
if not re.fullmatch(r"rr_(dev|test|prod)", CATALOG):  # used in paths and table names
    raise ValueError(f"unexpected catalog {CATALOG!r}")
MAX_GROUPS = int(dbutils.widgets.get("max_groups"))
MAX_LOOK_ALIKES = int(dbutils.widgets.get("max_look_alikes"))

# The notebook runs with its own folder (<repo>/pipelines/eval) as working directory.
PACKAGE_SRC = Path.cwd().parents[1] / "packages" / "eval" / "src"
if not (PACKAGE_SRC / "rr_eval").is_dir():
    raise RuntimeError(f"rr_eval not found under {PACKAGE_SRC}: run from the Git folder")
sys.path.insert(0, str(PACKAGE_SRC))

# Only the plain-Python builder is imported here (no pydantic needed on the cluster).
from rr_eval.matching_builder import (
    AlertRecord,
    SafeListing,
    build_matching_cases,
    is_excluded,
    split_files,
    spot_check_sample,
)

GOLD = f"{CATALOG}.gold"
ABO = f"{CATALOG}.bronze.abo_listings_raw"
OUT = Path(f"/Volumes/{CATALOG}/gold/exports/evals/matching/v1")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read alerts with their exact keys and photos

# COMMAND ----------

identifiers = (
    spark.table(f"{GOLD}.kb_alert_identifiers")
    .groupBy("case_number")
    .agg(
        F.sort_array(F.collect_set(F.when(F.col("kind") == "gtin", F.col("value_norm")))).alias(
            "gtins"
        ),
        F.sort_array(
            F.collect_set(F.when(F.col("kind") == "brand_model", F.col("value_norm")))
        ).alias("brand_models"),
    )
)
photos = (
    spark.table(f"{GOLD}.kb_alert_images")
    .groupBy("case_number")
    .agg(F.array_sort(F.collect_list(F.struct("ordinal", "sha256"))).alias("_photos"))
    .select("case_number", F.col("_photos.sha256").alias("image_sha256"))
)
alert_rows = (
    spark.table(f"{GOLD}.kb_alerts")
    .where(~F.col("is_withdrawn"))
    .join(identifiers, "case_number", "left")
    .join(photos, "case_number", "left")
    .collect()
)


def text(value: str | None) -> str:
    """Empty text instead of NULL (the builder works with plain strings)."""
    return value or ""


alerts = [
    AlertRecord(
        case_number=row.case_number,
        title_en=text(row.title_en),
        title_de=text(row.title_de),
        description_en=text(row.description_en),
        description_de=text(row.description_de),
        category_en=text(row.category_en),
        brand=row.brand,
        model=row.model,
        gtins=tuple(row.gtins or ()),
        brand_models=tuple(row.brand_models or ()),
        image_sha256=tuple(row.image_sha256 or ()),
    )
    for row in alert_rows
]
print(f"{len(alerts)} alerts, {sum(map(is_excluded, alerts))} left out (motor vehicles)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read safe ABO listings (the product kinds chosen in `abo_category_map.csv`)

# COMMAND ----------

listings = spark.table(ABO)


def first_text(column: str, prefix: str) -> Column:
    """First value of a multilingual ABO field whose language tag starts with ``prefix``."""
    return F.get(F.filter(column, lambda x: x["language_tag"].startswith(prefix)), 0)["value"]


brand = (
    F.get(F.col("brand"), 0)["value"].cast("string") if "brand" in listings.columns else F.lit(None)
)
abo = (
    listings.select(
        "item_id",
        "sg_category",
        F.coalesce(first_text("item_name", "en"), first_text("item_name", "de")).alias("title"),
        F.when(first_text("item_name", "en").isNotNull(), "en").otherwise("de").alias("language"),
        brand.alias("brand"),
    )
    .where("title IS NOT NULL")
    .where(~F.col("title").startswith("[Find]"))  # ABO test items with romanised Japanese
    .dropDuplicates(["item_id"])  # ABO has duplicate item_ids (see silver backlog)
    .orderBy(F.xxhash64("item_id"))
    .limit(5000)
    .collect()
)
safe = [SafeListing(r.item_id, r.title, r.language, text(r.sg_category), r.brand) for r in abo]
print(f"{len(safe)} safe listings to choose from")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build, write and summarise

# COMMAND ----------

cases = build_matching_cases(alerts, safe, max_groups=MAX_GROUPS, max_look_alikes=MAX_LOOK_ALIKES)
main_text, holdout_text = split_files(cases)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "v1.jsonl").write_text(main_text, encoding="utf-8")
(OUT / "v1.holdout.jsonl").write_text(holdout_text, encoding="utf-8")

sample = spot_check_sample(cases)
buffer = io.StringIO()
writer = csv.writer(buffer)
writer.writerow(
    ["case_id", "slice", "expected", "title", "model", "source", "relevant", "ok?", "note"]
)
for case in sample:
    q = case["query"]
    writer.writerow(
        [
            case["case_id"],
            case["slices"][0],
            case["expected"],
            q.get("title", "(photo)"),
            q.get("model", ""),
            case["source"],
            " ".join(case["relevant"]),
            "",
            "",
        ]
    )
(OUT / "spot_check.csv").write_text(buffer.getvalue(), encoding="utf-8")

print(f"{len(cases)} cases written to {OUT}")
print("by split:", dict(Counter(c["split"] for c in cases)))
print("by slice:", dict(Counter(s for c in cases for s in c["slices"])))
print("by expected:", dict(Counter(c["expected"] for c in cases)))
