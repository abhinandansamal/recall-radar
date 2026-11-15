"""Shared fixtures. Database tests run only when ``RR_TEST_POSTGRES_DSN`` is set.

Each database test gets its own throw-away database, so tests never touch ``rr_dev``:

    RR_TEST_POSTGRES_DSN=postgresql://rr_app:<password>@localhost:5432/postgres make test
"""

import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).parent))  # makes tests/export_helpers.py importable

DSN_VARIABLE = "RR_TEST_POSTGRES_DSN"


@pytest.fixture
def pg_conn() -> Iterator[psycopg.Connection]:
    """An autocommit connection to a fresh, empty database (dropped afterwards)."""
    dsn = os.environ.get(DSN_VARIABLE)
    if not dsn:
        pytest.skip(f"{DSN_VARIABLE} not set: no test database")
    name = f"rr_it_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        info = conninfo_to_dict(dsn)
        info["dbname"] = name
        with psycopg.connect(**info, autocommit=True) as conn:  # type: ignore[arg-type]
            yield conn
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
