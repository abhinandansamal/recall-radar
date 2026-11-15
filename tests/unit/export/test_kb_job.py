"""Command-line wrapper of the exporter (database replaced by fakes)."""

import contextlib
import io

import pytest

from rr_core.logging import configure_logging
from rr_export import kb_job
from rr_export.loader import LoadResult
from rr_export.manifest import ExportError


@pytest.fixture
def logs(monkeypatch):
    """Send the job's JSON logs to a buffer that stays open after the test."""
    buffer = io.StringIO()
    monkeypatch.setattr(kb_job, "configure_logging", lambda s: configure_logging(s, buffer))
    monkeypatch.setattr(kb_job, "connect", lambda settings: contextlib.nullcontext("conn"))
    return buffer


def test_live_export_returns_0(monkeypatch, tmp_path, logs):
    monkeypatch.setattr(kb_job, "load_kb", lambda conn, folder: LoadResult("x1", {"alerts": 3}))
    assert kb_job.main(["--export-dir", str(tmp_path)]) == 0
    assert '"event": "export_live"' in logs.getvalue()


def test_rejected_export_returns_1(monkeypatch, tmp_path, logs):
    def reject(conn, folder):
        raise ExportError("2 rows loaded, manifest says 5")

    monkeypatch.setattr(kb_job, "load_kb", reject)
    assert kb_job.main(["--export-dir", str(tmp_path)]) == 1
    assert '"kb_unchanged": true' in logs.getvalue()
