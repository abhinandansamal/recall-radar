# Databricks notebook source
# MAGIC %md
# MAGIC # Safety Gate photos (US-011)
# MAGIC
# MAGIC Downloads alert photos into the private volume `<catalog>.bronze.images`, **once per
# MAGIC SHA-256** (ADR-0004, D4), newest alerts first, and builds the silver tables from the
# MAGIC download log.
# MAGIC
# MAGIC - **Download (incremental):** up to `max_photos` photo URLs of current alerts that were
# MAGIC   never stored, at most `requests_per_second`. Every attempt is appended to
# MAGIC   `ops.image_downloads`, so a stopped run loses nothing and a re-run skips stored photos.
# MAGIC - **Silver (full rebuild from the log):** `silver.images` (one row per photo file),
# MAGIC   `silver.sg_alert_images` (which alert uses which photo, `is_main` = first photo),
# MAGIC   `ops.quarantine_images`, counts in `ops.dq_results`.
# MAGIC - Rule (as rule A for barcodes): a bad or missing photo never removes the alert.
# MAGIC
# MAGIC Photo checks live in `packages/ingest` (`rr_ingest.images`), unit-tested in CI.
# MAGIC The photos are never served publicly; the UI shows the official EC image URL.

# COMMAND ----------

# MAGIC %md
# MAGIC Pillow decodes photos from the internet, so it must be a patched version. The runtime
# MAGIC ships an older one; install the version pinned in `packages/ingest/pyproject.toml`.

# COMMAND ----------

# MAGIC %pip install pillow==13.0.0

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "rr_dev")
dbutils.widgets.text("max_photos", "2000")
dbutils.widgets.text("requests_per_second", "5")
CATALOG = dbutils.widgets.get("catalog")
if not re.fullmatch(r"rr_(dev|test|prod)", CATALOG):  # used in paths and table names
    raise ValueError(f"unexpected catalog {CATALOG!r}")
MAX_PHOTOS = int(dbutils.widgets.get("max_photos"))
RATE = float(dbutils.widgets.get("requests_per_second"))
if not (0 <= MAX_PHOTOS <= 50_000 and 0 < RATE <= 5):  # 5/s is the polite limit (design 4)
    raise ValueError("max_photos must be 0..50000 and requests_per_second 0..5")

UTC = timezone.utc  # noqa: UP017 - datetime.UTC needs Python 3.11; the runtime may be older
RUN_ID = str(uuid.uuid4())
RUN_AT = datetime.now(UTC)

# The notebook runs with its own folder (<repo>/pipelines/silver) as working directory.
PACKAGE_SRC = Path.cwd().parents[1] / "packages" / "ingest" / "src"
if not (PACKAGE_SRC / "rr_ingest").is_dir():
    raise RuntimeError(f"rr_ingest not found under {PACKAGE_SRC}: run from the Git folder")
sys.path.insert(0, str(PACKAGE_SRC))

import PIL

from rr_ingest.images import check_photo

if PIL.__version__ != "13.0.0":  # same pin as packages/ingest/pyproject.toml
    raise RuntimeError(f"Pillow {PIL.__version__} loaded; run the %pip cell first")
from rr_ingest.landing import write_once

IMAGES_ROOT = Path(f"/Volumes/{CATALOG}/bronze/images")
ALERTS = f"{CATALOG}.silver.sg_alerts"
LOG = f"{CATALOG}.ops.image_downloads"
IMAGES = f"{CATALOG}.silver.images"
ALERT_IMAGES = f"{CATALOG}.silver.sg_alert_images"
Q_IMAGES = f"{CATALOG}.ops.quarantine_images"
DQ_RESULTS = f"{CATALOG}.ops.dq_results"
USER_AGENT = "recall-radar/0.1 (+https://github.com/abhinandansamal/recall-radar)"
LICENCE = "European Commission, Safety Gate; reuse with attribution (Decision 2011/833/EU)"

# Pre-flight: the volume must accept the atomic write used for every photo.
_probe = f"_selftest/{RUN_ID}.txt"
assert write_once(IMAGES_ROOT, _probe, b"ok") and not write_once(IMAGES_ROOT, _probe, b"ok")
(IMAGES_ROOT / _probe).unlink()
print(f"run_id={RUN_ID}\npillow={PIL.__version__}\nvolume={IMAGES_ROOT} (write ok)")
print(f"max_photos={MAX_PHOTOS} at {RATE}/s")

# COMMAND ----------

LOG_SCHEMA = (
    "run_id STRING, attempted_at TIMESTAMP, source_url STRING, status STRING, "
    "http_status INT, reason STRING, sha256 STRING, ext STRING, mime STRING, "
    "size_bytes BIGINT, width INT, height INT, dhash STRING, stored_path STRING"
)
# ok: stored. quarantined: downloaded but not a usable photo. missing: 404/410 at the EC.
# error: network problem or 429/5xx; retried by the next run.
FINAL = ("ok", "quarantined", "missing")


def table_exists(name: str) -> bool:
    """Whether a Unity Catalog table exists."""
    return bool(spark.catalog.tableExists(name))


def photo_urls() -> DataFrame:
    """Photo URLs of current alerts: one row per (alert, position); EN and DE share URLs."""
    return (
        spark.table(ALERTS)
        .where("is_current")
        .select("case_number", "publication_date", F.posexplode("picture_urls").alias("pos", "url"))
        .distinct()
    )


def latest_attempts() -> DataFrame:
    """The newest download attempt per URL."""
    newest = Window.partitionBy("source_url").orderBy(F.desc("attempted_at"))
    return spark.table(LOG).withColumn("_n", F.row_number().over(newest)).where("_n = 1").drop("_n")


def pending_photos(limit: int | None) -> list[str]:
    """URLs never finished, newest alerts first (ADR-0004: newest years first)."""
    urls = photo_urls().groupBy("url").agg(F.max("publication_date").alias("newest"))
    if table_exists(LOG):
        done = (
            latest_attempts()
            .where(F.col("status").isin(*FINAL))
            .select(F.col("source_url").alias("url"))
        )
        urls = urls.join(done, "url", "left_anti")
    ordered = urls.orderBy(F.desc("newest"), "url")
    return [r.url for r in (ordered.limit(limit) if limit is not None else ordered).collect()]


class RateLimiter:
    """Allows at most ``rate`` calls per second across all threads."""

    def __init__(self, rate: float) -> None:
        """Create the limiter."""
        self.interval = 1.0 / rate
        self.next_at = time.monotonic()
        self.lock = threading.Lock()

    def wait(self) -> None:
        """Block until the next call is allowed."""
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_at)
            self.next_at = start + self.interval
        time.sleep(max(0.0, start - now))


def _log_row(url: str, row: dict[str, object]) -> tuple[object, ...]:
    """Turn the result of one attempt into a row of ``LOG_SCHEMA``."""
    keys = ("sha256", "ext", "mime", "size_bytes", "width", "height", "dhash", "stored_path")
    return (
        RUN_ID,
        datetime.now(UTC),
        url,
        row["status"],
        row.get("http_status"),
        row.get("reason"),
        *(row.get(k) for k in keys),
    )


def download(url: str, limiter: RateLimiter) -> tuple[object, ...]:
    """Download one photo, check it, store it once; return one log row."""
    if not url.startswith("https://"):  # only web photos, never file:// or other schemes
        return _log_row(url, {"status": "quarantined", "reason": "not_https"})
    limiter.wait()
    row: dict[str, object] = {"status": "error"}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - https only
            data = response.read()
            row["http_status"] = response.status
        check = check_photo(data)
        row.update(
            sha256=check.sha256,
            ext=check.ext,
            mime=check.mime,
            size_bytes=check.size_bytes,
            width=check.width,
            height=check.height,
            dhash=check.dhash,
        )
        if check.is_valid:
            write_once(IMAGES_ROOT, check.path, data)  # False = same photo already stored
            row.update(status="ok", stored_path=check.path)
        else:
            row.update(status="quarantined", reason=check.error)
    except urllib.error.HTTPError as error:
        row.update(
            http_status=error.code,
            status="missing" if error.code in (404, 410) else "error",
            reason=f"http_{error.code}",
        )
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        row["reason"] = type(error).__name__
    return _log_row(url, row)


def download_batch(urls: list[str], workers: int = 4, flush_every: int = 250) -> None:
    """Download URLs in parallel; append the log every ``flush_every`` photos."""
    limiter = RateLimiter(RATE)
    rows: list[tuple[object, ...]] = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, row in enumerate(pool.map(lambda u: download(u, limiter), urls), start=1):
            rows.append(row)
            if len(rows) == flush_every or done == len(urls):
                spark.createDataFrame(rows, LOG_SCHEMA).write.mode("append").saveAsTable(LOG)
                rows = []
                print(f"{done}/{len(urls)} photos, {time.monotonic() - started:.0f}s")


# COMMAND ----------

# MAGIC %md
# MAGIC ## Download (incremental)

# COMMAND ----------

todo = pending_photos(MAX_PHOTOS)
print(f"{len(todo)} photos to download in this run")
if todo:
    download_batch(todo)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver tables (rebuilt from the log)

# COMMAND ----------

latest = latest_attempts().cache()
stored = latest.where("status = 'ok'")

first_seen = Window.partitionBy("sha256").orderBy("attempted_at", "source_url")
images = (
    stored.withColumn("_n", F.row_number().over(first_seen))
    .where("_n = 1")
    .select(
        "sha256",
        "ext",
        "mime",
        "size_bytes",
        "width",
        "height",
        "dhash",
        "stored_path",
        F.col("source_url").alias("first_source_url"),
        F.col("attempted_at").alias("first_stored_at"),
        F.lit(LICENCE).alias("licence"),
    )
)
alert_images = (
    photo_urls()
    .select("case_number", "pos", "url")
    .distinct()
    .join(stored.select(F.col("source_url").alias("url"), "sha256"), "url")
    .select(
        "case_number",
        (F.col("pos") + 1).alias("ordinal"),
        (F.col("pos") == 0).alias("is_main"),
        F.col("url").alias("source_url"),
        "sha256",
    )
)
quarantine = latest.where(F.col("status").isin("quarantined", "missing"))

COMMENTS = {
    IMAGES: "Safety Gate photos stored once per SHA-256 in bronze.images (private). US-011.",
    ALERT_IMAGES: "Which current alert uses which stored photo; is_main = first photo. US-011.",
    Q_IMAGES: "Photo URLs that are missing at the EC or not a usable image; alerts stay.",
}
for table, frame in [(IMAGES, images), (ALERT_IMAGES, alert_images), (Q_IMAGES, quarantine)]:
    frame.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
    spark.sql(f"COMMENT ON TABLE {table} IS '{COMMENTS[table]}'")
    print(f"written {table}")

counts = {r.status: r["count"] for r in latest.groupBy("status").count().collect()}
finished = sum(counts.get(s, 0) for s in FINAL)
dq = [
    (
        "photo_valid",
        "images",
        counts.get("ok", 0) + counts.get("quarantined", 0),
        counts.get("quarantined", 0),
    ),
    ("photo_available", "images", finished, counts.get("missing", 0)),
]
spark.createDataFrame(
    [
        (RUN_ID, RUN_AT, rule, target, int(checked), int(failed))
        for rule, target, checked, failed in dq
    ],
    "run_id STRING, run_at TIMESTAMP, rule STRING, target STRING, checked BIGINT, failed BIGINT",
).write.mode("append").saveAsTable(DQ_RESULTS)
print(counts)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Checks (acceptance criteria)

# COMMAND ----------

files = spark.table(IMAGES)
duplicate_hashes = files.groupBy("sha256").count().where("count > 1").count()
orphans = spark.table(ALERT_IMAGES).join(files, "sha256", "left_anti").count()
sample = files.select("stored_path", "size_bytes").limit(50).collect()
bad_files = [
    r.stored_path
    for r in sample
    if not (IMAGES_ROOT / r.stored_path).is_file()
    or (IMAGES_ROOT / r.stored_path).stat().st_size != r.size_bytes
]
redownload = set(pending_photos(None)) & {
    r.source_url for r in stored.select("source_url").collect()
}

print(f"1. photo files: {files.count()}, duplicate hashes: {duplicate_hashes} (expected 0)")
print(f"2. alert-photo links without a stored file: {orphans} (expected 0)")
print(f"3. sampled files missing or wrong size: {len(bad_files)} of {len(sample)} (expected 0)")
print(f"4. stored photos a re-run would download again: {len(redownload)} (expected 0)")
assert duplicate_hashes == 0 and orphans == 0 and not bad_files and not redownload
print("CHECKS PASSED")

# COMMAND ----------

# Coverage and size: input for the storage estimate (design section 4)
display(
    files.agg(
        F.count("*").alias("photo_files"),
        F.round(F.sum("size_bytes") / 1e9, 2).alias("total_gb"),
        F.round(F.avg("size_bytes") / 1e3, 0).alias("avg_kb"),
        F.round(F.expr("percentile(size_bytes, 0.5)") / 1e3, 0).alias("median_kb"),
    ).crossJoin(
        photo_urls().agg(
            F.countDistinct("url").alias("photo_urls_of_current_alerts"),
            F.countDistinct("case_number").alias("alerts_with_photos"),
        )
    )
)
display(files.groupBy("mime").count().orderBy(F.desc("count")))
display(quarantine.groupBy("status", "reason").count().orderBy(F.desc("count")))
