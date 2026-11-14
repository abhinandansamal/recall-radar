# Databricks notebook source
# MAGIC %md
# MAGIC # Silver: Safety Gate alerts (US-010)
# MAGIC
# MAGIC Rebuilds the silver tables **completely** from `<catalog>.bronze.sg_alerts_raw` on every
# MAGIC run: silver = rules(bronze). Bronze is append-only and small (~96k rows), so a full
# MAGIC rebuild takes about a minute, is always correct and needs no merge logic.
# MAGIC
# MAGIC - `silver.sg_alerts`: one row per alert **version** and language (SCD2: `valid_from`,
# MAGIC   `valid_to`, `is_current`, `is_withdrawn`)
# MAGIC - `silver.sg_alert_identifiers`: exact-match keys of the newest version, `gtin` (14 digits)
# MAGIC   and `brand_model`
# MAGIC - `ops.quarantine_sg_alerts`: alerts without a usable case number or date, with reasons
# MAGIC - `ops.quarantine_sg_identifiers`: barcode candidates that are no valid GTIN (rule A: the
# MAGIC   alert stays)
# MAGIC - `ops.dq_results`: checked / failed counts per rule and run (appended)
# MAGIC
# MAGIC The rules live in `packages/transform` (`rr_transform`) and are unit-tested in CI.
# MAGIC Run this notebook from the **Git folder** so it can import them.
# MAGIC
# MAGIC Evidence for every rule: `docs/data/profiles/sg-alerts-bronze-2026-11-14.md`.

# COMMAND ----------

import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pyspark import cloudpickle
from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "rr_dev")
CATALOG = dbutils.widgets.get("catalog")
if not re.fullmatch(r"rr_(dev|test|prod)", CATALOG):  # used in paths and table names
    raise ValueError(f"unexpected catalog {CATALOG!r}")

RUN_ID = str(uuid.uuid4())
UTC = timezone.utc  # noqa: UP017 - datetime.UTC needs Python 3.11; the runtime may be older
RUN_AT = datetime.now(UTC)
RUN_DATE = RUN_AT.date()

# The notebook runs with its own folder (<repo>/pipelines/silver) as working directory.
PACKAGE_SRC = Path.cwd().parents[1] / "packages" / "transform" / "src"
if not (PACKAGE_SRC / "rr_transform").is_dir():
    raise RuntimeError(f"rr_transform not found under {PACKAGE_SRC}: run from the Git folder")
sys.path.insert(0, str(PACKAGE_SRC))

import rr_transform  # noqa: E402
from rr_transform.sg_alert import SPARK_SCHEMA, clean_sg_alert  # noqa: E402

# Ship the package's code inside the UDF itself, so the Spark workers need no install.
cloudpickle.register_pickle_by_value(rr_transform)

SOURCE = f"/Volumes/{CATALOG}/bronze/landing/safety_gate/reports"
BRONZE = f"{CATALOG}.bronze.sg_alerts_raw"
ALERTS = f"{CATALOG}.silver.sg_alerts"
IDENTIFIERS = f"{CATALOG}.silver.sg_alert_identifiers"
Q_ALERTS = f"{CATALOG}.ops.quarantine_sg_alerts"
Q_IDENTIFIERS = f"{CATALOG}.ops.quarantine_sg_identifiers"
DQ_RESULTS = f"{CATALOG}.ops.dq_results"

print(f"run_id={RUN_ID}\nrun_date={RUN_DATE}\npython={sys.version.split()[0]}\nsource={BRONZE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transformation functions
# MAGIC
# MAGIC Pure functions from DataFrames to DataFrames: the self-test at the end runs them on tiny
# MAGIC in-memory data.

# COMMAND ----------

# bronze column -> silver column (text fields, trimmed, empty -> NULL)
TEXT_FIELDS = {
    "category": "category",
    "product": "product",
    "name": "product_name",
    "brand": "brand",
    "type_numberOfModel": "model",
    "batchNumber": "batch_number",
    "barcode": "barcode",
    "riskType": "risk_type",
    "danger": "danger",
    "measures": "measures",
    "description": "description",
    "notifyingCountry": "notifying_country",
    "countryOfOrigin": "country_of_origin",
    "type": "alert_type",
    "level": "risk_level_text",
    "URLrecall": "recall_url",
    "onlineTrader": "online_trader",
    "companyRecallCode": "company_recall_code",
    "productionDates": "production_dates",
    "reference": "source_url",
}
# Everything that makes up the content of a version; a change in any of them is a new version.
CONTENT = [
    "publication_date",
    "risk_level",
    *TEXT_FIELDS.values(),
    "picture_urls",
]


def _text(name: str) -> Column:
    """Trimmed text; empty strings become NULL."""
    trimmed = F.trim(F.col(name))
    return F.when(trimmed == "", None).otherwise(trimmed)


@F.udf(returnType=SPARK_SCHEMA)
def _clean(
    case_number: str | None,
    publication_date: str | None,
    level: str | None,
    brand: str | None,
    model: str | None,
    barcode: str | None,
    pictures: str | None,
) -> dict[str, object]:
    """Apply all rr_transform rules to one bronze row (runs on the Spark workers)."""
    return clean_sg_alert(
        case_number=case_number,
        publication_date=publication_date,
        level=level,
        brand=brand,
        model=model,
        barcode=barcode,
        pictures=pictures,
        today=RUN_DATE,
    ).as_row()


def list_report_files(source: str) -> DataFrame:
    """List the landing files with their modification time (when we stored that version).

    Bronze rows of the same report can come from several files (corrected reports). The
    file stored first is the original; later files are corrections.
    """
    rows = [
        (
            f.path.removeprefix("dbfs:"),
            datetime.fromtimestamp(f.modificationTime / 1000, UTC),
        )
        for folder in dbutils.fs.ls(source)
        if folder.name.startswith("lang=")
        for f in dbutils.fs.ls(folder.path)
        if f.name.endswith(".xml")
    ]
    return spark.createDataFrame(rows, "source_file STRING, file_stored_at TIMESTAMP")


def position_files(bronze: DataFrame, files: DataFrame) -> DataFrame:
    """Add report year/week and the position of each file inside its report.

    Adds ``file_rank`` (1 = original file of the report), ``files_in_report`` and
    ``next_file_stored_at`` (when the following correction of the same report was stored).
    """
    report_files = (
        bronze.select(
            F.regexp_replace("_source_file", "^dbfs:", "").alias("source_file"),
            "_report_reference",
            "lang",
        )
        .distinct()
        .join(files, "source_file", "left")
    )
    missing = report_files.where("file_stored_at IS NULL").count()
    if missing:
        raise RuntimeError(f"{missing} bronze files are not in the landing volume listing")
    in_report = Window.partitionBy("_report_reference", "lang")
    ordered = in_report.orderBy("file_stored_at", "source_file")
    report_files = (
        report_files.withColumn("file_rank", F.row_number().over(ordered))
        .withColumn("files_in_report", F.count("*").over(in_report))
        .withColumn("next_file_stored_at", F.lead("file_stored_at").over(ordered))
        .drop("_report_reference", "lang")
    )
    return (
        bronze.withColumn("source_file", F.regexp_replace("_source_file", "^dbfs:", ""))
        .join(report_files, "source_file")
        .withColumn(
            "report_year", F.regexp_extract("_report_reference", r"-(\d{4})-", 1).cast("int")
        )
        .withColumn("report_week", F.regexp_extract("_report_reference", r"-(\d+)$", 1).cast("int"))
        .withColumn("report_order", F.col("order").cast("int"))
    )


def clean(positioned: DataFrame) -> DataFrame:
    """Apply the rules: one struct column ``c`` with typed values and errors."""
    return positioned.withColumn(
        "c",
        _clean(
            "caseNumber",
            "publicationDate",
            "level",
            "brand",
            "type_numberOfModel",
            "barcode",
            "pictures",
        ),
    )


def quarantine_alerts(cleaned: DataFrame) -> DataFrame:
    """Rows with an alert-level error, with reasons and the raw record."""
    return cleaned.where(F.size("c.errors") > 0).select(
        F.col("caseNumber").alias("case_number_raw"),
        "lang",
        F.col("c.errors").alias("reasons"),
        "_report_reference",
        "source_file",
        F.to_json(
            F.struct(*[F.col(c) for c in ["caseNumber", "publicationDate", *TEXT_FIELDS]])
        ).alias("raw_record"),
        F.lit(RUN_ID).alias("run_id"),
        F.lit(RUN_AT).alias("quarantined_at"),
    )


def build_alert_versions(cleaned: DataFrame) -> DataFrame:
    """Build SCD2 versions per (case_number, lang).

    Order of appearances: report year, report week, file (original before corrections),
    position in the report. Consecutive identical contents collapse into one version.
    ``valid_from`` is the publication date for the original file and the time the correction
    was stored for later files. If the newest file of a report no longer lists a case that an
    older file of that report listed, the case was withdrawn then.
    """
    valid = cleaned.where(F.size("c.errors") == 0).select(
        F.col("c.case_number").alias("case_number"),
        "lang",
        F.col("c.publication_date").alias("publication_date"),
        F.col("c.risk_level").alias("risk_level"),
        *[_text(src).alias(dst) for src, dst in TEXT_FIELDS.items()],
        F.col("c.picture_urls").alias("picture_urls"),
        F.col("c.brand_key").alias("brand_key"),
        F.col("c.model_keys").alias("model_keys"),
        F.col("c.gtins").alias("gtins"),
        F.col("c.rejected_gtins").alias("rejected_gtins"),
        "_report_reference",
        "report_year",
        "report_week",
        "report_order",
        "source_file",
        "file_rank",
        "files_in_report",
        "next_file_stored_at",
        "file_stored_at",
        "_licence",
    )
    valid = valid.withColumn(
        "row_hash", F.sha2(F.to_json(F.struct(*[F.col(c) for c in CONTENT])), 256)
    ).withColumn(
        "seen_at",
        F.when(F.col("file_rank") == 1, F.col("publication_date").cast("timestamp")).otherwise(
            F.col("file_stored_at")
        ),
    )
    key = Window.partitionBy("case_number", "lang")
    in_order = key.orderBy("report_year", "report_week", "file_rank", "report_order", "row_hash")

    # Withdrawal: look at the last appearance of each case.
    last = (
        valid.withColumn("_next", F.lead("row_hash").over(in_order))
        .where(F.col("_next").isNull())
        .select(
            "case_number",
            "lang",
            F.when(
                F.col("file_rank") < F.col("files_in_report"), F.col("next_file_stored_at")
            ).alias("withdrawn_at"),
        )
    )

    versions = (
        valid.withColumn("_prev", F.lag("row_hash").over(in_order))
        .where(F.col("_prev").isNull() | (F.col("_prev") != F.col("row_hash")))
        .withColumn(
            "valid_from",
            F.max("seen_at").over(
                in_order.rowsBetween(Window.unboundedPreceding, Window.currentRow)
            ),
        )
        .withColumn("version", F.row_number().over(in_order))
        .withColumn("_next_from", F.lead("valid_from").over(in_order))
        .join(last, ["case_number", "lang"])
    )
    is_last = F.col("_next_from").isNull()
    return versions.select(
        "case_number",
        "lang",
        "version",
        "valid_from",
        F.coalesce("_next_from", "withdrawn_at").alias("valid_to"),
        (is_last & F.col("withdrawn_at").isNull()).alias("is_current"),
        (is_last & F.col("withdrawn_at").isNotNull()).alias("is_withdrawn"),
        F.when(is_last, F.col("withdrawn_at")).alias("withdrawn_at"),
        "row_hash",
        *CONTENT,
        "brand_key",
        "model_keys",
        "gtins",
        "rejected_gtins",
        F.col("_report_reference").alias("report_reference"),
        "report_order",
        "source_file",
        "_licence",
        F.lit(RUN_ID).alias("_run_id"),
        F.lit(RUN_AT).alias("_built_at"),
    )


def latest_versions(alerts: DataFrame) -> DataFrame:
    """The newest version of every alert, current or withdrawn."""
    return alerts.where(F.col("is_current") | F.col("is_withdrawn"))


def build_identifiers(alerts: DataFrame) -> DataFrame:
    """Exact-match keys of the newest version of every alert (EN and DE give the same keys)."""
    latest = latest_versions(alerts)
    gtins = latest.select(
        "case_number", F.lit("gtin").alias("kind"), F.explode("gtins").alias("value_norm")
    )
    brand_models = (
        latest.where(F.col("brand_key").isNotNull())
        .select("case_number", "brand_key", F.explode("model_keys").alias("model_key"))
        .select(
            "case_number",
            F.lit("brand_model").alias("kind"),
            F.concat_ws("|", "brand_key", "model_key").alias("value_norm"),
        )
    )
    return gtins.unionByName(brand_models).distinct().withColumn("_run_id", F.lit(RUN_ID))


def quarantine_identifiers(alerts: DataFrame) -> DataFrame:
    """Rejected barcode candidates of the newest versions (rule A: the alert stays)."""
    return (
        latest_versions(alerts)
        .select("case_number", "barcode", F.explode("rejected_gtins").alias("r"))
        .select("case_number", "barcode", "r.candidate", "r.reason")
        .distinct()
        .withColumn("run_id", F.lit(RUN_ID))
        .withColumn("quarantined_at", F.lit(RUN_AT))
    )


def dq_results(cleaned: DataFrame, alerts: DataFrame) -> DataFrame:
    """Checked and failed counts per rule for this run."""
    errors = F.col("c.errors")
    a = cleaned.agg(
        F.count("*").alias("rows"),
        F.sum(F.exists(errors, lambda e: e.startswith("case_number")).cast("int")).alias(
            "bad_case"
        ),
        F.sum(F.exists(errors, lambda e: e.startswith("publication_date")).cast("int")).alias(
            "bad_date"
        ),
    ).first()
    latest = latest_versions(alerts)
    b = latest.agg(
        F.count("*").alias("latest"),
        F.sum((F.col("risk_level") == "unknown").cast("int")).alias("bad_level"),
        F.sum(F.size("gtins") + F.size("rejected_gtins")).alias("candidates"),
        F.sum(F.size("rejected_gtins")).alias("bad_gtins"),
    ).first()
    rows = [
        ("case_number_valid", "sg_alerts", a.rows, a.bad_case or 0),
        ("publication_date_valid", "sg_alerts", a.rows, a.bad_date or 0),
        ("risk_level_known", "sg_alerts", b.latest, b.bad_level or 0),
        ("gtin_check_digit", "sg_alert_identifiers", b.candidates or 0, b.bad_gtins or 0),
    ]
    return spark.createDataFrame(
        [
            (RUN_ID, RUN_AT, rule, table, int(checked), int(failed))
            for rule, table, checked, failed in rows
        ],
        "run_id STRING, run_at TIMESTAMP, rule STRING, target STRING, "
        "checked BIGINT, failed BIGINT",
    )


# COMMAND ----------

# MAGIC %md
# MAGIC ## Build and write
# MAGIC
# MAGIC Each `overwrite` is atomic per table (Delta): readers see the old or the new table,
# MAGIC never half of it. `ops.dq_results` is appended, so it keeps the history of runs.

# COMMAND ----------

cleaned = clean(position_files(spark.table(BRONZE), list_report_files(SOURCE))).cache()
alerts = build_alert_versions(cleaned).cache()

COMMENTS = {
    ALERTS: "Safety Gate alerts, one row per version and language (SCD2). Built by US-010.",
    IDENTIFIERS: "Exact-match keys (gtin, brand_model) of the newest alert versions.",
    Q_ALERTS: "Bronze alerts without a usable case number or publication date.",
    Q_IDENTIFIERS: "Barcode candidates that are no valid GTIN; the alert itself stays in silver.",
}
for table, frame in [
    (ALERTS, alerts),
    (IDENTIFIERS, build_identifiers(alerts)),
    (Q_ALERTS, quarantine_alerts(cleaned)),
    (Q_IDENTIFIERS, quarantine_identifiers(alerts)),
]:
    frame.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
    spark.sql(f"COMMENT ON TABLE {table} IS '{COMMENTS[table]}'")
    print(f"written {table}")

dq_results(cleaned, alerts).write.mode("append").option("mergeSchema", "true").saveAsTable(
    DQ_RESULTS
)
display(spark.table(DQ_RESULTS).where(F.col("run_id") == RUN_ID))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Checks on the real data (acceptance criteria)

# COMMAND ----------

bronze_rows = spark.table(BRONZE).count()
silver = spark.table(ALERTS)
appearances = cleaned.where(F.size("c.errors") == 0).count()
quarantined = spark.table(Q_ALERTS).count()
keys = silver.select("case_number", "lang").distinct().count()
current = silver.where("is_current").count()
withdrawn = silver.where("is_withdrawn").count()
more_than_one_current = (
    silver.where("is_current").groupBy("case_number", "lang").count().where("count > 1").count()
)
bad_intervals = silver.where("valid_to < valid_from").count()
bad_gtins = (
    spark.table(IDENTIFIERS).where("kind = 'gtin' AND value_norm NOT RLIKE '^[0-9]{14}$'").count()
)

print(f"1. bronze rows {bronze_rows} = clean appearances {appearances} + quarantined {quarantined}")
print(f"2. alerts (case, lang): {keys} = current {current} + withdrawn {withdrawn}")
print(f"3. keys with more than one current version: {more_than_one_current} (expected 0)")
print(f"4. versions ending before they start: {bad_intervals} (expected 0)")
print(f"5. GTIN keys not 14 digits: {bad_gtins} (expected 0)")
assert bronze_rows == appearances + quarantined
assert keys == current + withdrawn
assert more_than_one_current == 0 and bad_intervals == 0 and bad_gtins == 0
print("CHECKS PASSED")

# COMMAND ----------

display(
    silver.groupBy("lang")
    .agg(
        F.count("*").alias("versions"),
        F.countDistinct("case_number").alias("alerts"),
        F.count_if("is_current").alias("current"),
        F.count_if("is_withdrawn").alias("withdrawn"),
        F.count_if(F.col("version") > 1).alias("later_versions"),
    )
    .orderBy("lang")
)

# COMMAND ----------

# Reports with more than one file: file 1 must be the original, file 2 the correction.
# Compare with the local landing folder: `ls -lT data/local/landing/safety_gate/reports/lang=en/`
display(
    cleaned.where("files_in_report > 1")
    .select("_report_reference", "lang", "file_rank", "file_stored_at", "source_file")
    .distinct()
    .orderBy("_report_reference", "lang", "file_rank")
)

# COMMAND ----------

# Alerts with history: corrected reports and repeated cases (profile Q6)
display(
    silver.where((F.col("version") > 1) | F.col("is_withdrawn"))
    .select("case_number", "lang")
    .distinct()
    .join(silver, ["case_number", "lang"])
    .select(
        "case_number",
        "lang",
        "version",
        "valid_from",
        "valid_to",
        "is_current",
        "is_withdrawn",
        "report_reference",
        "source_file",
    )
    .orderBy("case_number", "lang", "version")
)

# COMMAND ----------

display(spark.table(Q_ALERTS).orderBy("case_number_raw", "lang"))
display(spark.table(Q_IDENTIFIERS).groupBy("reason").count().orderBy(F.desc("count")))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Self-test of the SCD2 logic (in memory, no tables touched)
# MAGIC
# MAGIC Report-2099-1 has two files; the correction (file 2) changes alert A, repeats alert B
# MAGIC unchanged and drops alert C. Alert D has a bad case number, alert E a bad barcode.

# COMMAND ----------

_BRONZE_COLUMNS = [
    "caseNumber",
    "publicationDate",
    "order",
    "pictures",
    *TEXT_FIELDS,
    "lang",
    "_source_file",
    "_report_reference",
    "_licence",
]
_BRONZE_SCHEMA = ", ".join(f"`{c}` STRING" for c in _BRONZE_COLUMNS)


def _row(case: str, file: int, order: int, danger: str, barcode: str = "") -> dict[str, str]:
    """One fake bronze row of Report-2099-1."""
    row = dict.fromkeys(TEXT_FIELDS, "")
    row.update(
        caseNumber=case,
        publicationDate="01-01-2026",
        order=str(order),
        pictures="<picture>https://x.eu/1</picture>",
        brand="Acme",
        type_numberOfModel="TX-100",
        level="Serious risk",
        danger=danger,
        barcode=barcode,
        lang="en",
        _source_file=f"dbfs:/t/lang=en/Report-2099-1_{file}.xml",
        _report_reference="Report-2099-1",
        _licence="test",
    )
    return row


_rows = [
    _row("SR/00001/99", 1, 1, "fire"),
    _row("SR/00002/99", 1, 2, "cut", "4006381333931"),
    _row("SR/00003/99", 1, 3, "choking"),
    _row("SR 4/99", 1, 4, "x"),
    _row("SR/00005/99", 1, 5, "burn", "5054298241092"),
    _row("SR/00001/99", 2, 1, "fire and shock"),  # changed: new version
    _row("SR/00002/99", 2, 2, "cut", "4006381333931"),  # unchanged: no new version
    _row("SR/00005/99", 2, 3, "burn", "5054298241092"),
    # SR/00003/99 is missing from file 2: withdrawn
]
_bronze = spark.createDataFrame(
    [tuple(r[c] for c in _BRONZE_COLUMNS) for r in _rows], _BRONZE_SCHEMA
)
_files = spark.createDataFrame(
    [
        ("/t/lang=en/Report-2099-1_1.xml", datetime(2026, 1, 1, 9)),
        ("/t/lang=en/Report-2099-1_2.xml", datetime(2026, 1, 8, 9)),
    ],
    "source_file STRING, file_stored_at TIMESTAMP",
)
_cleaned = clean(position_files(_bronze, _files))
_alerts = {(r.case_number, r.version): r for r in build_alert_versions(_cleaned).collect()}
_ids = {
    (r.case_number, r.kind, r.value_norm)
    for r in build_identifiers(build_alert_versions(_cleaned)).collect()
}
_q = quarantine_alerts(_cleaned).collect()
_qi = quarantine_identifiers(build_alert_versions(_cleaned)).collect()

a1, a2 = _alerts[("SR/00001/99", 1)], _alerts[("SR/00001/99", 2)]
assert (a1.is_current, a2.is_current, a2.danger) == (False, True, "fire and shock"), (
    "A: new version"
)
assert a1.valid_to == a2.valid_from == datetime(2026, 1, 8, 9), "A: correction starts when stored"
assert ("SR/00002/99", 2) not in _alerts and _alerts[("SR/00002/99", 1)].is_current, "B: collapsed"
c = _alerts[("SR/00003/99", 1)]
assert c.is_withdrawn and not c.is_current and c.valid_to == datetime(2026, 1, 8, 9), "C: withdrawn"
assert [(r.case_number_raw, list(r.reasons)) for r in _q] == [
    ("SR 4/99", ["case_number_format"])
], "D"
assert _alerts[("SR/00005/99", 1)].is_current, "E: alert stays despite the bad barcode (rule A)"
assert [(r.case_number, r.reason) for r in _qi] == [("SR/00005/99", "check_digit")], (
    "E: quarantined"
)
assert ("SR/00002/99", "gtin", "04006381333931") in _ids, "GTIN key"
assert ("SR/00001/99", "brand_model", "acme|tx100") in _ids, "brand+model key"
print("SELF-TEST PASSED")
