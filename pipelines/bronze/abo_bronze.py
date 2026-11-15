# Databricks notebook source
# MAGIC %md
# MAGIC # ABO catalogue: landing and bronze (US-008)
# MAGIC
# MAGIC Amazon Berkeley Objects is the realistic **marketplace catalogue** that RadarMart sells
# MAGIC from (`docs/data/data-sources.md`, section 2).
# MAGIC
# MAGIC 1. **Landing:** the 16 listing files and `images.csv.gz` (~94 MB) are copied unchanged
# MAGIC    from the public S3 bucket into `<catalog>.bronze.landing/abo/…`, write-once.
# MAGIC 2. **Bronze:** the listings of the product types selected in
# MAGIC    `pipelines/reference/abo_category_map.csv` (a Product Owner decision based on
# MAGIC    `pipelines/profiling/abo_profile.py`) and the metadata of their images go to
# MAGIC    `bronze.abo_listings_raw` and `bronze.abo_images_raw`, with licence attribution.
# MAGIC
# MAGIC ABO is a static dataset, so bronze is rebuilt completely (no streaming state needed).

# COMMAND ----------

# MAGIC %pip install defusedxml==0.7.1

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import csv
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StructType

dbutils.widgets.text("catalog", "rr_dev")
CATALOG = dbutils.widgets.get("catalog")
if not re.fullmatch(r"rr_(dev|test|prod)", CATALOG):  # used in paths and table names
    raise ValueError(f"unexpected catalog {CATALOG!r}")

UTC = timezone.utc  # noqa: UP017 - datetime.UTC needs Python 3.11; the runtime may be older
RUN_AT = datetime.now(UTC)

REPO = Path.cwd().parents[1]  # the notebook runs in <repo>/pipelines/bronze
sys.path.insert(0, str(REPO / "packages" / "ingest" / "src"))

from rr_ingest.abo import (
    BUCKET_URL,
    IMAGES_PREFIX,
    LICENCE,
    LISTINGS_PREFIX,
    download_error,
    landing_path,
    listing_url,
    parse_bucket_listing,
)
from rr_ingest.landing import write_once

LANDING = Path(f"/Volumes/{CATALOG}/bronze/landing")
MAPPING = REPO / "pipelines" / "reference" / "abo_category_map.csv"
LISTINGS = f"{CATALOG}.bronze.abo_listings_raw"
IMAGES = f"{CATALOG}.bronze.abo_images_raw"
USER_AGENT = "recall-radar/0.1 (+https://github.com/abhinandansamal/recall-radar)"


def fetch(url: str) -> bytes:
    """Download a URL of the public ABO bucket."""
    if not url.startswith(BUCKET_URL):
        raise ValueError(f"not an ABO bucket URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - fixed https host
        return response.read()


# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Landing (idempotent: files already stored are skipped)

# COMMAND ----------

objects = [
    o
    for prefix in (LISTINGS_PREFIX, IMAGES_PREFIX)
    for o in parse_bucket_listing(fetch(listing_url(prefix)))
]
written = skipped = 0
for obj in objects:
    target = LANDING / landing_path(obj.key)
    if target.is_file() and target.stat().st_size == obj.size:
        skipped += 1
        continue
    data = fetch(f"{BUCKET_URL}/{obj.key}")
    error = download_error(data, obj)
    if error:
        raise RuntimeError(f"{obj.key}: {error}; nothing stored")
    written += write_once(LANDING, landing_path(obj.key), data)
    print(f"stored {obj.key} ({obj.size:,} bytes, etag {obj.etag})")
print(f"landing: {len(objects)} files in the bucket, {written} written, {skipped} already stored")
assert len([o for o in objects if o.key.startswith(LISTINGS_PREFIX)]) == 16, (
    "expected 16 listing files"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Bronze: listings and image metadata of the selected product types

# COMMAND ----------


def first_value(df: DataFrame, column: str) -> Column:
    """ABO stores most fields as ``[{"value": ...}]``; return the first value as text."""
    kind = df.schema[column].dataType
    if isinstance(kind, ArrayType) and isinstance(kind.elementType, StructType):
        return F.get(F.col(column), 0)["value"].cast("string")  # NULL if empty
    return F.col(column).cast("string")


if not MAPPING.is_file():
    dbutils.notebook.exit(
        f"Landing done. {MAPPING.name} not found: run pipelines/profiling/abo_profile.py, "
        "decide the product types, commit the mapping, then run this notebook again."
    )

with MAPPING.open(encoding="utf-8") as handle:
    chosen = [
        (row["abo_product_type"], row["sg_category"])
        for row in csv.DictReader(handle)
        if row["include"].strip().lower() == "true"
    ]
if not chosen:
    raise RuntimeError(f"{MAPPING.name} selects no product type")
selection = spark.createDataFrame(chosen, "product_type_value STRING, sg_category STRING")

raw = spark.read.json(str(LANDING / "abo" / LISTINGS_PREFIX)).select(
    "*", F.col("_metadata.file_path").alias("_source_file")
)
listings = (
    raw.withColumn("product_type_value", first_value(raw, "product_type"))
    .join(F.broadcast(selection), "product_type_value")
    .withColumn("_ingested_at", F.lit(RUN_AT))
    .withColumn("_licence", F.lit(LICENCE))
)
listings.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(LISTINGS)

listings = spark.table(LISTINGS)
image_ids = (
    listings.select(F.col("main_image_id").alias("image_id"))
    .union(listings.select(F.explode_outer("other_image_id").alias("image_id")))
    .where("image_id IS NOT NULL")
    .distinct()
)
images = (
    spark.read.option("header", True)
    .csv(str(LANDING / "abo" / IMAGES_PREFIX))
    .select("*", F.col("_metadata.file_path").alias("_source_file"))
    .join(image_ids, "image_id", "left_semi")
    .withColumn("_ingested_at", F.lit(RUN_AT))
    .withColumn("_licence", F.lit(LICENCE))
)
images.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(IMAGES)
print(f"written {LISTINGS} and {IMAGES}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Checks

# COMMAND ----------

stored = spark.table(LISTINGS)
pictures = spark.table(IMAGES)
n_listings, n_items = stored.count(), stored.select("item_id").distinct().count()
n_images = pictures.count()
missing_main = (
    stored.join(
        pictures.select(F.col("image_id").alias("main_image_id")), "main_image_id", "left_anti"
    )
    .where("main_image_id IS NOT NULL")
    .count()
)
unlicensed = stored.where("_licence IS NULL").count() + pictures.where("_licence IS NULL").count()
types_found = stored.select("product_type_value").distinct().count()

print(
    f"1. listings: {n_listings:,} ({n_items:,} distinct item_id), "
    f"product types: {types_found} of {len(chosen)}"
)
print(f"2. image metadata rows: {n_images:,}")
print(f"3. listings whose main image has no metadata: {missing_main} (expected 0)")
print(f"4. rows without licence attribution: {unlicensed} (expected 0)")
assert n_listings > 0 and missing_main == 0 and unlicensed == 0
print("CHECKS PASSED")
display(stored.groupBy("sg_category").count().orderBy(F.desc("count")))
