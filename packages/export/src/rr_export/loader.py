"""Load an export into ``kb_staging``, check it, then swap it live in one transaction.

Steps (design section 7.4)::

    1  check the export folder (manifest, contract)       -> fail before touching the DB
    2  rebuild kb_staging and COPY the rows                -> live kb untouched
    3  build the indexes on staging                        -> the slow part, off the live tables
    4  check row counts and the schema contract            -> any mismatch: stop, kb untouched
    5  one transaction: kb -> kb_old, kb_staging -> kb, drop kb_old

Readers always see the complete old version or the complete new one, never a half-load.
A Postgres advisory lock makes sure only one export runs at a time.
"""

from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from rr_export.kb_schema import (
    CONTRACT,
    INDEXES,
    LIVE,
    LOAD_COLUMNS,
    OLD,
    SCHEMA_VERSION,
    STAGING,
    create_statements,
    index_statements,
)
from rr_export.manifest import ExportError, Manifest, read_manifest, read_rows

LOCK_KEY = 4_204_202_611  # any constant; identifies "kb export" for pg_advisory_lock


@dataclass(frozen=True)
class LoadResult:
    """What was loaded.

    Attributes:
        export_id: Id of the loaded export.
        rows: Rows loaded per table.
    """

    export_id: str
    rows: dict[str, int]


def schema_exists(conn: psycopg.Connection, schema: str) -> bool:
    """Whether a schema exists."""
    row = conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)).fetchone()
    return row is not None


def contract_errors(conn: psycopg.Connection, schema: str) -> list[str]:
    """Compare the tables and indexes in ``schema`` with the contract.

    Args:
        conn: Open connection.
        schema: Schema to check (``kb_staging`` before the swap, ``kb`` after it).

    Returns:
        Human-readable differences; empty if the schema matches exactly.
    """
    errors: list[str] = []
    for table, expected in CONTRACT.items():
        actual = conn.execute(
            """SELECT a.attname, format_type(a.atttypid, a.atttypmod)
               FROM pg_attribute a
               JOIN pg_class c ON c.oid = a.attrelid
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
               ORDER BY a.attnum""",
            (schema, table),
        ).fetchall()
        if tuple(actual) != expected:
            errors.append(f"{schema}.{table}: columns {actual} != contract {list(expected)}")
    present = {
        name
        for (name,) in conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = %s", (schema,)
        ).fetchall()
    }
    errors.extend(f"{schema}: index {i} missing" for i in INDEXES if i not in present)
    return errors


def _prepare_staging(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(STAGING)))
        for statement in create_statements(STAGING):
            conn.execute(statement)  # built from constants only


def _copy(conn: psycopg.Connection, folder: Path, table: str) -> int:
    columns = LOAD_COLUMNS[table]
    query = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(STAGING),
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    count = 0
    with conn.transaction(), conn.cursor() as cursor, cursor.copy(query) as copy:
        for row in read_rows(folder, table):
            copy.write_row(row)
            count += 1
    return count


def _verify(conn: psycopg.Connection, manifest: Manifest) -> None:
    errors = contract_errors(conn, STAGING)
    for table, expected in manifest.rows.items():
        (actual,) = conn.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(STAGING), sql.Identifier(table)
            )
        ).fetchone() or (0,)
        if actual != expected:
            errors.append(f"{table}: {actual} rows loaded, manifest says {expected}")
    if errors:
        raise ExportError("; ".join(errors))


def _swap(conn: psycopg.Connection) -> None:
    live, staging, old = (sql.Identifier(s) for s in (LIVE, STAGING, OLD))
    with conn.transaction():
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(old))
        if schema_exists(conn, LIVE):
            conn.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(live, old))
        conn.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(staging, live))
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(old))


def load_kb(conn: psycopg.Connection, folder: Path) -> LoadResult:
    """Run the whole export: staging, indexes, checks, atomic swap.

    Args:
        conn: Connection in autocommit mode (each step opens its own transaction).
        folder: Export folder with ``manifest.json``.

    Returns:
        Export id and loaded row counts.

    Raises:
        ExportError: If the export is invalid, another export runs, or a check fails.
            In every case the live ``kb`` schema is unchanged.
    """
    manifest = read_manifest(folder)
    (locked,) = conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone() or (False,)
    if not locked:
        raise ExportError("another kb export is running")
    try:
        try:
            _load_and_check(conn, folder, manifest)
            _swap(conn)
        except psycopg.Error as error:  # constraint, type or connection problem
            raise ExportError(f"{type(error).__name__}: {error}") from error
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return LoadResult(manifest.export_id, manifest.rows)


def _load_and_check(conn: psycopg.Connection, folder: Path, manifest: Manifest) -> None:
    """Steps 2-4: staging, COPY, indexes, checks. Leaves ``kb`` untouched."""
    _prepare_staging(conn)
    rows = {table: _copy(conn, folder, table) for table in LOAD_COLUMNS}
    with conn.transaction():
        conn.execute(
            sql.SQL(
                "INSERT INTO {}.export_info "
                "(export_id, schema_version, gold_created_at, row_counts) "
                "VALUES (%s, %s, %s, %s)"
            ).format(sql.Identifier(STAGING)),
            (manifest.export_id, SCHEMA_VERSION, manifest.created_at, Jsonb(rows)),
        )
        for statement in index_statements(STAGING):
            conn.execute(statement)  # built from constants
    for table in CONTRACT:
        conn.execute(
            sql.SQL("ANALYZE {}.{}").format(sql.Identifier(STAGING), sql.Identifier(table))
        )
    _verify(conn, manifest)
