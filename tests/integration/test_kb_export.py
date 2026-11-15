"""The exporter against a real Postgres with pgvector (US-012 acceptance criteria)."""

import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from export_helpers import alert, write_export
from rr_export.loader import LOCK_KEY, load_kb, schema_exists
from rr_export.manifest import ExportError

pytestmark = pytest.mark.integration

IDS = [
    {"case_number": "SR/00001/26", "kind": "gtin", "value_norm": "04006381333931"},
    {"case_number": "SR/00001/26", "kind": "brand_model", "value_norm": "acme|tx100"},
]
IMAGES = [
    {
        "case_number": "SR/00001/26",
        "sha256": "a" * 64,
        "ordinal": 1,
        "is_main": True,
        "source_url": "https://ec.europa.eu/image/1",
    }
]


def _count(conn, table):
    return conn.execute(f"SELECT count(*) FROM kb.{table}").fetchone()[0]  # noqa: S608


def test_first_load_goes_live_with_matching_counts(pg_conn, tmp_path):
    folder = write_export(tmp_path, [alert("SR/00001/26"), alert("SR/00002/26")], IDS, IMAGES)
    result = load_kb(pg_conn, folder)
    assert result.rows == {"alerts": 2, "alert_identifiers": 2, "alert_images": 1}
    assert (_count(pg_conn, "alerts"), _count(pg_conn, "alert_identifiers")) == (2, 2)
    assert not schema_exists(pg_conn, "kb_staging") and not schema_exists(pg_conn, "kb_old")
    info = pg_conn.execute("SELECT export_id, row_counts FROM kb.export_info").fetchone()
    assert info == ("20261115T120000Z", {"alerts": 2, "alert_identifiers": 2, "alert_images": 1})


def test_exact_and_keyword_search_work_after_load(pg_conn, tmp_path):
    load_kb(pg_conn, write_export(tmp_path, [alert("SR/00001/26")], IDS, IMAGES))
    exact = pg_conn.execute(
        "SELECT case_number FROM kb.alert_identifiers WHERE kind = 'gtin' AND value_norm = %s",
        ("04006381333931",),
    ).fetchall()
    assert exact == [("SR/00001/26",)]
    english = pg_conn.execute(
        "SELECT case_number FROM kb.alerts WHERE search_en @@ plainto_tsquery('english', 'choking')"
    ).fetchall()
    german = pg_conn.execute(
        "SELECT case_number FROM kb.alerts "
        "WHERE search_de @@ plainto_tsquery('german', 'Erstickungsgefahr')"
    ).fetchall()
    assert english == german == [("SR/00001/26",)]


def test_reload_replaces_the_live_data(pg_conn, tmp_path):
    load_kb(pg_conn, write_export(tmp_path / "a", [alert("SR/00001/26"), alert("SR/00002/26")]))
    load_kb(pg_conn, write_export(tmp_path / "b", [alert("SR/00003/26")], export_id="second"))
    assert pg_conn.execute("SELECT case_number FROM kb.alerts").fetchall() == [("SR/00003/26",)]
    assert pg_conn.execute("SELECT export_id FROM kb.export_info").fetchone() == ("second",)


def test_count_mismatch_is_rejected_and_kb_stays_unchanged(pg_conn, tmp_path):
    load_kb(pg_conn, write_export(tmp_path / "good", [alert("SR/00001/26")]))
    bad = write_export(
        tmp_path / "bad",
        [alert("SR/00002/26"), alert("SR/00003/26")],
        rows_override={"alerts": 5},
        export_id="bad",
    )
    with pytest.raises(ExportError, match="2 rows loaded, manifest says 5"):
        load_kb(pg_conn, bad)
    assert pg_conn.execute("SELECT case_number FROM kb.alerts").fetchall() == [("SR/00001/26",)]


def test_broken_reference_is_rejected_and_kb_stays_unchanged(pg_conn, tmp_path):
    load_kb(pg_conn, write_export(tmp_path / "good", [alert("SR/00001/26")]))
    orphan = [{"case_number": "SR/99999/26", "kind": "gtin", "value_norm": "04006381333931"}]
    with pytest.raises(ExportError, match="ForeignKeyViolation"):
        load_kb(pg_conn, write_export(tmp_path / "bad", [alert("SR/00002/26")], orphan))
    assert _count(pg_conn, "alerts") == 1
    assert pg_conn.execute("SELECT export_id FROM kb.export_info").fetchone() == (
        "20261115T120000Z",
    )


def test_invalid_value_is_rejected(pg_conn, tmp_path):
    bad = write_export(tmp_path, [alert("SR/00001/26", risk_level="deadly")])
    with pytest.raises(ExportError, match="CheckViolation"):
        load_kb(pg_conn, bad)
    assert not schema_exists(pg_conn, "kb")


def test_only_one_export_at_a_time(pg_conn, tmp_path):
    folder = write_export(tmp_path, [alert("SR/00001/26")])
    info = conninfo_to_dict(os.environ["RR_TEST_POSTGRES_DSN"]) | {"dbname": pg_conn.info.dbname}
    with psycopg.connect(**info, autocommit=True) as other:  # a second exporter
        other.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        with pytest.raises(ExportError, match="another kb export is running"):
            load_kb(pg_conn, folder)
    load_kb(pg_conn, folder)  # works once the other export has finished
