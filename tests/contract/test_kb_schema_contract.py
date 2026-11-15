"""Schema contract: the live ``kb`` schema must match ``rr_export.kb_schema.CONTRACT``.

The app (search, agents) is written against this contract. If someone changes the DDL without
changing the contract (and ``SCHEMA_VERSION``), this test fails before anything is deployed.
"""

import pytest

from export_helpers import alert, write_export
from rr_export.kb_schema import CONTRACT
from rr_export.loader import contract_errors, load_kb

pytestmark = pytest.mark.integration


def test_live_kb_matches_the_contract(pg_conn, tmp_path):
    load_kb(pg_conn, write_export(tmp_path, [alert("SR/00001/26")]))
    assert contract_errors(pg_conn, "kb") == []


def test_a_changed_column_is_reported(pg_conn, tmp_path):
    load_kb(pg_conn, write_export(tmp_path, [alert("SR/00001/26")]))
    pg_conn.execute("ALTER TABLE kb.alerts ALTER COLUMN notifying_country TYPE varchar(80)")
    pg_conn.execute("DROP INDEX kb.alerts_search_de")
    errors = contract_errors(pg_conn, "kb")
    assert any("kb.alerts: columns" in e for e in errors)
    assert "kb: index alerts_search_de missing" in errors


def test_contract_covers_every_kb_table(pg_conn, tmp_path):
    load_kb(pg_conn, write_export(tmp_path, [alert("SR/00001/26")]))
    tables = {
        name
        for (name,) in pg_conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'kb'"
        ).fetchall()
    }
    assert tables == set(CONTRACT)
