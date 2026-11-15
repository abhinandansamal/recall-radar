"""Export folder checks and schema definitions (no database needed)."""

import json

import pytest

from export_helpers import alert, write_export
from rr_export.kb_schema import CONTRACT, INDEXES, LOAD_COLUMNS, create_statements
from rr_export.manifest import ExportError, read_manifest, read_rows


def test_valid_export(tmp_path):
    write_export(tmp_path, [alert("SR/00001/26"), alert("SR/00002/26")])
    manifest = read_manifest(tmp_path)
    assert manifest.export_id == "20261115T120000Z"
    assert manifest.rows == {"alerts": 2, "alert_identifiers": 0, "alert_images": 0}


def test_rows_come_in_contract_order_and_marker_files_are_ignored(tmp_path):
    write_export(tmp_path, [alert("SR/00001/26")])
    (row,) = list(read_rows(tmp_path, "alerts"))
    assert len(row) == len(LOAD_COLUMNS["alerts"])
    assert row[0] == "SR/00001/26"
    assert row[LOAD_COLUMNS["alerts"].index("risk_level")] == "serious"


def test_missing_manifest(tmp_path):
    with pytest.raises(ExportError, match="no manifest"):
        read_manifest(tmp_path)


def _edit_manifest(folder, change):
    path = folder / "manifest.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda m: m.update(schema_version=99), "schema version 99"),
        (lambda m: m["tables"].pop("alert_images"), "export tables"),
        (lambda m: m["tables"]["alerts"]["columns"].reverse(), "columns of alerts"),
        (lambda m: m["tables"]["alerts"].update(rows=-1), "negative row count"),
        (lambda m: m.pop("export_id"), "invalid manifest"),
    ],
)
def test_manifest_must_match_the_contract(tmp_path, change, message):
    write_export(tmp_path, [alert("SR/00001/26")])
    _edit_manifest(tmp_path, change)
    with pytest.raises(ExportError, match=message):
        read_manifest(tmp_path)


def test_missing_data_folder(tmp_path):
    write_export(tmp_path, [alert("SR/00001/26")])
    for file in (tmp_path / "alert_images").iterdir():
        file.unlink()
    (tmp_path / "alert_images").rmdir()
    with pytest.raises(ExportError, match="missing data folder"):
        read_manifest(tmp_path)


def test_loaded_columns_come_first_in_the_contract():
    for table, columns in LOAD_COLUMNS.items():
        contract_names = tuple(name for name, _ in CONTRACT[table])
        assert contract_names[: len(columns)] == columns


def test_create_statements_mention_every_contract_column():
    ddl = "\n".join(create_statements("kb_staging"))
    for table, columns in CONTRACT.items():
        assert f"kb_staging.{table}" in ddl
        for name, _ in columns:
            assert name in ddl


def test_index_names_are_unique():
    assert len(INDEXES) == len(set(INDEXES))
