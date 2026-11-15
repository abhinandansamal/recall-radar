"""Build small gold export folders for tests (same layout as the gold notebook writes)."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from rr_export.kb_schema import LOAD_COLUMNS, SCHEMA_VERSION

_TYPES = {
    "published_at": pa.date32(),
    "is_withdrawn": pa.bool_(),
    "valid_from": pa.timestamp("us", tz="UTC"),
    "ordinal": pa.int32(),
    "is_main": pa.bool_(),
}


def alert(case: str, title_en: str = "Toy car", **values: Any) -> dict[str, Any]:
    """One row of ``alerts`` with sensible defaults."""
    row: dict[str, Any] = dict.fromkeys(LOAD_COLUMNS["alerts"])
    row.update(
        case_number=case,
        risk_level="serious",
        title_en=title_en,
        title_de="Spielzeugauto",
        category_en="Toys",
        category_de="Spielzeug",
        brand="Acme",
        model="TX-100",
        danger_en="The product poses a risk of choking.",
        danger_de="Das Produkt birgt Erstickungsgefahr.",
        published_at=date(2026, 11, 1),
        is_withdrawn=False,
        source_url=f"https://ec.europa.eu/alert/{case}",
        valid_from=datetime(2026, 11, 1, tzinfo=UTC),
    )
    row.update(values)
    return row


def write_export(
    folder: Path,
    alerts: list[dict[str, Any]],
    identifiers: list[dict[str, Any]] | None = None,
    images: list[dict[str, Any]] | None = None,
    export_id: str = "20261115T120000Z",
    rows_override: dict[str, int] | None = None,
) -> Path:
    """Write Parquet folders plus ``manifest.json`` like the gold notebook does."""
    tables = {
        "alerts": alerts,
        "alert_identifiers": identifiers or [],
        "alert_images": images or [],
    }
    manifest: dict[str, Any] = {
        "export_id": export_id,
        "schema_version": SCHEMA_VERSION,
        "created_at": "2026-11-15T12:00:00+00:00",
        "tables": {},
    }
    for name, rows in tables.items():
        columns = LOAD_COLUMNS[name]
        schema = pa.schema([(c, _TYPES.get(c, pa.string())) for c in columns])
        data = pa.Table.from_pylist([{c: r.get(c) for c in columns} for r in rows], schema=schema)
        (folder / name).mkdir(parents=True, exist_ok=True)
        pq.write_table(data, folder / name / "part-00000.parquet")
        (folder / name / "_SUCCESS").write_text("")  # Spark marker file, must be ignored
        count = (rows_override or {}).get(name, len(rows))
        manifest["tables"][name] = {"rows": count, "columns": list(columns)}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder
