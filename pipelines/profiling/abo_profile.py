# Databricks notebook source
# MAGIC %md
# MAGIC # Profile: ABO catalogue vs Safety Gate (US-008)
# MAGIC
# MAGIC Reads the ABO files in the landing volume (run `pipelines/bronze/abo_bronze.py` once
# MAGIC first) and measures what the matching needs: product types, filled fields, languages,
# MAGIC images, and the **category overlap with Safety Gate**. The overlap goes into
# MAGIC `evals/reports/F03.md`.
# MAGIC
# MAGIC It also writes a **proposal** for the category mapping (keyword rules in
# MAGIC `rr_ingest.abo`) to the landing volume. The Product Owner reviews it and commits the final
# MAGIC version as `pipelines/reference/abo_category_map.csv`.

# COMMAND ----------

# MAGIC %pip install defusedxml==0.7.1

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import csv
import io
import re
import sys
from pathlib import Path

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StructType

dbutils.widgets.text("catalog", "rr_dev")
CATALOG = dbutils.widgets.get("catalog")
if not re.fullmatch(r"rr_(dev|test|prod)", CATALOG):
    raise ValueError(f"unexpected catalog {CATALOG!r}")

REPO = Path.cwd().parents[1]  # the notebook runs in <repo>/pipelines/profiling
sys.path.insert(0, str(REPO / "packages" / "ingest" / "src"))

from rr_ingest.abo import propose_category

LANDING = Path(f"/Volumes/{CATALOG}/bronze/landing/abo")
MAPPING = REPO / "pipelines" / "reference" / "abo_category_map.csv"
PROPOSAL = LANDING / "_profile" / "abo_category_map.proposed.csv"
SG_ALERTS = f"{CATALOG}.silver.sg_alerts"

listings = spark.read.json(str(LANDING / "listings" / "metadata"))
images = spark.read.option("header", True).csv(str(LANDING / "images" / "metadata"))
listings.printSchema()


def first_value(df: DataFrame, column: str) -> Column:
    """ABO stores most fields as ``[{"value": ...}]``; return the first value as text."""
    kind = df.schema[column].dataType
    if isinstance(kind, ArrayType) and isinstance(kind.elementType, StructType):
        return F.get(F.col(column), 0)["value"].cast("string")  # NULL if empty
    return F.col(column).cast("string")


def text_in(column: str, prefix: str) -> Column:
    """First text of a multilingual field whose language tag starts with ``prefix``."""
    return F.get(F.filter(column, lambda x: x["language_tag"].startswith(prefix)), 0)["value"]


def optional(column: str) -> Column:
    """First value of a field, or NULL if the field does not exist in the files."""
    return first_value(listings, column) if column in listings.columns else F.lit(None)


abo = listings.select(
    "item_id",
    first_value(listings, "product_type").alias("product_type"),
    text_in("item_name", "en").alias("name_en"),
    text_in("item_name", "de").alias("name_de"),
    optional("brand").alias("brand"),
    optional("model_number").alias("model_number"),
    optional("model_name").alias("model_name"),
    "main_image_id",
    F.size("other_image_id").alias("other_images"),
    "country",
    "marketplace",
).cache()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Size and filled fields

# COMMAND ----------

total = abo.count()
fill = abo.agg(
    *[
        F.round(
            100
            * F.avg(F.when(F.col(c).isNotNull() & (F.col(c).cast("string") != ""), 1).otherwise(0)),
            1,
        ).alias(c)
        for c in [
            "product_type",
            "name_en",
            "name_de",
            "brand",
            "model_number",
            "model_name",
            "main_image_id",
        ]
    ]
)
print(f"listings: {total:,}, distinct item_id: {abo.select('item_id').distinct().count():,}")
print(f"product types: {abo.select('product_type').distinct().count()}")
display(fill)  # percent filled
display(abo.groupBy("marketplace", "country").count().orderBy(F.desc("count")).limit(20))
display(
    listings.select(F.explode("item_name.language_tag").alias("language"))
    .groupBy("language")
    .count()
    .orderBy(F.desc("count"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Images

# COMMAND ----------

print(f"image metadata rows: {images.count():,}")
display(
    images.agg(
        F.expr("percentile(int(width), 0.5)").alias("median_width"),
        F.expr("percentile(int(height), 0.5)").alias("median_height"),
    )
)
with_image = abo.join(
    images.select(F.col("image_id").alias("main_image_id")), "main_image_id", "left_semi"
).count()
print(f"listings whose main image has metadata: {with_image:,} of {total:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Safety Gate categories and the overlap

# COMMAND ----------

sg = (
    spark.table(SG_ALERTS)
    .where("is_current AND lang = 'en'")
    .groupBy(F.col("category").alias("sg_category"))
    .agg(F.count("*").alias("sg_alerts"))
)
sg_categories = [r.sg_category for r in sg.collect() if r.sg_category]

types = abo.groupBy("product_type").count().orderBy(F.desc("count")).collect()
proposal = [
    (r.product_type, propose_category(r.product_type, sg_categories), r["count"]) for r in types
]

if MAPPING.is_file():
    with MAPPING.open(encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r["include"].strip().lower() == "true"]
    mapping = {r["abo_product_type"]: r["sg_category"] for r in rows}
    source = f"committed mapping ({MAPPING.name})"
else:
    mapping = {t: c for t, c, _ in proposal if c}
    source = "keyword proposal (not yet reviewed)"

mapped = spark.createDataFrame(list(mapping.items()), "product_type STRING, sg_category STRING")
overlap = (
    abo.join(mapped, "product_type")
    .groupBy("sg_category")
    .agg(
        F.count("*").alias("abo_listings"),
        F.countDistinct("product_type").alias("abo_product_types"),
    )
    .join(sg, "sg_category", "full")
    .fillna(0, ["abo_listings", "abo_product_types"])
    .orderBy(F.desc("sg_alerts"))
)
print(f"overlap based on the {source}")
display(overlap)
selected = sum(r.abo_listings for r in overlap.collect())
covered = (
    overlap.where("abo_listings > 0 AND sg_alerts > 0").agg(F.sum("sg_alerts")).first()[0] or 0
)
all_alerts = sg.agg(F.sum("sg_alerts")).first()[0]
print(
    f"ABO listings in overlapping categories: {selected:,} of {total:,} "
    f"({100 * selected / total:.1f} %)"
)
print(
    f"Safety Gate alerts in categories that ABO covers: {covered:,} of {all_alerts:,} "
    f"({100 * covered / all_alerts:.1f} %)"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Proposal for the mapping (to review)

# COMMAND ----------

buffer = io.StringIO()
writer = csv.writer(buffer, lineterminator="\n")
writer.writerow(["abo_product_type", "sg_category", "include", "abo_listings"])
for product_type, category, count in proposal:
    writer.writerow([product_type, category or "", "true" if category else "false", count])
PROPOSAL.parent.mkdir(parents=True, exist_ok=True)
PROPOSAL.write_text(buffer.getvalue(), encoding="utf-8")
n_proposed = sum(1 for _, category, _ in proposal if category)
print(f"proposal written: {PROPOSAL} ({n_proposed} of {len(proposal)} types proposed)")
if MAPPING.is_file():  # never suggest overwriting the reviewed decision
    print(f"compare with the committed mapping: databricks fs cp dbfs:{PROPOSAL} /tmp/")
else:
    print(f"download: databricks fs cp dbfs:{PROPOSAL} pipelines/reference/abo_category_map.csv")
display(
    spark.createDataFrame(
        proposal, "abo_product_type STRING, proposed_sg_category STRING, abo_listings BIGINT"
    )
)
