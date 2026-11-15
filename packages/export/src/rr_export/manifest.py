"""Read and check a gold export folder before anything touches the database.

An export folder, written by ``pipelines/gold/kb_gold.py``, looks like this::

    <export_id>/
      manifest.json            export id, schema version, row count + columns per table
      alerts/part-….parquet
      alert_identifiers/…
      alert_images/…

Everything that can be checked without a database is checked here, so a broken export
fails in a second, before the staging schema is even created.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from rr_export.kb_schema import LOAD_COLUMNS, SCHEMA_VERSION


class ExportError(Exception):
    """The export cannot be loaded; the live ``kb`` schema stays unchanged."""


@dataclass(frozen=True)
class Manifest:
    """The content of ``manifest.json``.

    Attributes:
        export_id: Unique id of the export (UTC time of the gold run).
        schema_version: Must equal :data:`rr_export.kb_schema.SCHEMA_VERSION`.
        created_at: When gold wrote the export.
        rows: Expected row count per table.
        folder: The export folder.
    """

    export_id: str
    schema_version: int
    created_at: datetime
    rows: dict[str, int]
    folder: Path


def read_manifest(folder: Path) -> Manifest:
    """Read ``manifest.json`` and check it against the schema contract.

    Args:
        folder: The export folder.

    Returns:
        The manifest.

    Raises:
        ExportError: If the file is missing or does not match the contract.
    """
    path = folder / "manifest.json"
    if not path.is_file():
        raise ExportError(f"no manifest.json in {folder}")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        version = int(data["schema_version"])
        tables: dict[str, dict[str, Any]] = data["tables"]
        manifest = Manifest(
            export_id=str(data["export_id"]),
            schema_version=version,
            created_at=datetime.fromisoformat(data["created_at"]),
            rows={name: int(info["rows"]) for name, info in tables.items()},
            folder=folder,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ExportError(f"invalid manifest.json: {error!r}") from error

    if version != SCHEMA_VERSION:
        raise ExportError(f"export has schema version {version}, exporter expects {SCHEMA_VERSION}")
    if set(tables) != set(LOAD_COLUMNS):
        raise ExportError(f"export tables {sorted(tables)} != expected {sorted(LOAD_COLUMNS)}")
    for name, info in tables.items():
        if tuple(info.get("columns", ())) != LOAD_COLUMNS[name]:
            raise ExportError(f"columns of {name} do not match the contract")
        if manifest.rows[name] < 0:
            raise ExportError(f"negative row count for {name}")
        if not (folder / name).is_dir():
            raise ExportError(f"missing data folder {name}/")
    return manifest


def read_rows(folder: Path, table: str) -> Iterator[tuple[Any, ...]]:
    """Yield the rows of one exported table, columns in contract order.

    Parquet folders written by Spark contain marker files (``_SUCCESS``, ``_committed_…``);
    pyarrow ignores files that start with ``_`` or ``.``.

    Args:
        folder: The export folder.
        table: Table name (a key of ``LOAD_COLUMNS``).

    Yields:
        One tuple per row.

    Raises:
        ExportError: If a contract column is missing in the files.
    """
    columns = LOAD_COLUMNS[table]
    data = pq.read_table(folder / table)
    missing = [c for c in columns if c not in data.column_names]
    if missing:
        raise ExportError(f"{table}: columns missing in the files: {missing}")
    for batch in data.select(list(columns)).to_batches(max_chunksize=10_000):
        yield from zip(*(column.to_pylist() for column in batch.columns), strict=True)
