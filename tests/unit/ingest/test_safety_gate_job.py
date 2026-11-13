from datetime import date
from pathlib import Path

import httpx
import pytest

from rr_ingest import safety_gate_job
from rr_ingest.safety_gate_job import INDEX_URL, download_safety_gate, main

FIXTURES = Path(__file__).parents[2] / "fixtures" / "safety_gate"
INDEX = (FIXTURES / "index_small.xml").read_bytes()
DETAIL = (FIXTURES / "detail_small.xml").read_bytes()


def fake_server(broken=()):
    """Serve the fixtures; URLs containing a text in ``broken`` return an HTML error page."""
    requested = []

    def handler(request):
        url = str(request.url)
        requested.append(url)
        if url == INDEX_URL:
            return httpx.Response(200, content=INDEX)
        if any(b in url for b in broken):
            return httpx.Response(200, content=b"<html><body>Oops!</body></html>")
        return httpx.Response(200, content=DETAIL)

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def run(client, out, since=date(2026, 11, 13)):
    return download_safety_gate(
        client, out, since=since, sleep=lambda s: None, today=date(2026, 11, 13)
    )


def test_downloads_index_and_both_languages(tmp_path):
    client, requested = fake_server()

    summary = run(client, tmp_path)

    assert summary.written == 2 and summary.unchanged == 0 and summary.failed == []
    assert summary.alerts == 4
    assert any("language=de" in u for u in requested)
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.xml"))
    assert files[0].startswith("safety_gate/index/fetched_date=2026-11-13/weekly_index_")
    assert files[1].startswith("safety_gate/reports/lang=de/Report-2026-45_")
    assert files[2].startswith("safety_gate/reports/lang=en/Report-2026-45_")


def test_second_run_writes_nothing_new(tmp_path):
    client, _ = fake_server()
    run(client, tmp_path)

    summary = run(client, tmp_path)

    assert summary.written == 0 and summary.unchanged == 2
    assert len(list(tmp_path.rglob("*.xml"))) == 3


def test_since_filters_old_reports(tmp_path):
    client, requested = fake_server()

    run(client, tmp_path, since=date(2026, 11, 6))

    assert sum("detail/xml" in u for u in requested) == 4


def test_error_page_is_recorded_not_stored(tmp_path):
    client, _ = fake_server(broken=("language=de",))

    summary = run(client, tmp_path)

    assert summary.failed == ["Report-2026-45/de"]
    assert not (tmp_path / "safety_gate/reports/lang=de").exists()


def test_main_returns_1_when_a_report_failed(tmp_path, monkeypatch):
    client, _ = fake_server(broken=("language=de",))
    monkeypatch.setattr(safety_gate_job, "make_client", lambda: client)

    code = main(["--out", str(tmp_path), "--since", "2026-11-13", "--pause", "0"])

    assert code == 1


def test_main_returns_0_on_success(tmp_path, monkeypatch):
    client, _ = fake_server()
    monkeypatch.setattr(safety_gate_job, "make_client", lambda: client)

    assert (
        main(["--out", str(tmp_path), "--since", "2026-11-13", "--lang", "en", "--pause", "0"]) == 0
    )


def test_main_requires_since(tmp_path):
    with pytest.raises(SystemExit):
        main(["--out", str(tmp_path)])
