import json
from datetime import UTC, datetime

import httpx
import pytest

from rr_ingest import gpsr_job
from rr_ingest.gpsr import (
    DOCUMENTS,
    MIN_ARTICLES,
    GpsrDocument,
    InvalidDocumentError,
    count_articles,
    envelope,
    request_for,
)
from rr_ingest.gpsr_job import download_gpsr, main

ORIGINAL, CONSOLIDATED = DOCUMENTS
NOW = datetime(2026, 11, 13, 17, 0, tzinfo=UTC)


def legal_text(marker="oj-ti-art", articles=52, number="2023/988"):
    """A small XHTML document shaped like the real Cellar texts."""
    heads = "".join(f'<p class="{marker}">Article {i}</p>' for i in range(1, articles + 1))
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f"<head><title>Regulation (EU) {number}</title></head><body>{heads}</body></html>"
    ).encode()


# The EUR-Lex bot challenge: HTTP 202 with an empty body.
CHALLENGE = b""


def test_request_uses_cellar_and_content_negotiation():
    url, headers = request_for(CONSOLIDATED, "de")

    assert url == "https://publications.europa.eu/resource/celex/02023R0988-20260529"
    assert headers == {"Accept": "application/xhtml+xml", "Accept-Language": "deu"}


def test_request_rejects_unknown_language():
    with pytest.raises(ValueError, match="unsupported language"):
        request_for(ORIGINAL, "fr")


@pytest.mark.parametrize("marker", ["oj-ti-art", "title-article-norm"])
def test_count_articles_in_both_text_formats(marker):
    assert count_articles(legal_text(marker=marker)) == 52


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (CHALLENGE, "not an HTML"),
        (b"<html><body>Access denied</body></html>", "2023/988"),
        (legal_text(number="2019/1020"), "2023/988"),
        (legal_text(articles=MIN_ARTICLES - 1), "article headings"),
    ],
)
def test_count_articles_rejects_wrong_content(content, reason):
    with pytest.raises(InvalidDocumentError, match=reason):
        count_articles(content)


def test_envelope_keeps_text_and_records_source_and_date():
    content = legal_text()
    name, data = envelope(ORIGINAL, "en", "https://src", content, 52, NOW)
    record = json.loads(data)

    assert name.startswith("CELEX_32023R0988_") and name.endswith(".json")
    assert record["content"].encode() == content
    assert record["source_url"] == "https://src"
    assert record["retrieved_at"] == "2026-11-13T17:00:00+00:00"
    assert record["version"] == "original-2023-05-23" and record["language"] == "en"
    assert record["article_count"] == 52 and record["size_bytes"] == len(content)


def test_envelope_name_depends_only_on_content():
    later = datetime(2027, 1, 1, tzinfo=UTC)

    same = envelope(ORIGINAL, "en", "u", legal_text(), 52, NOW)[0]
    assert same == envelope(ORIGINAL, "en", "u", legal_text(), 52, later)[0]
    assert same != envelope(ORIGINAL, "en", "u", legal_text(articles=53), 53, NOW)[0]


def cellar(blocked=()):
    """Fake Cellar: answers by Accept-Language; listed CELEX numbers get the bot challenge."""
    requested = []

    def handler(request):
        requested.append(request)
        if any(c in str(request.url) for c in blocked):
            return httpx.Response(202, content=CHALLENGE)
        marker = "title-article-norm" if "02023" in str(request.url) else "oj-ti-art"
        return httpx.Response(200, content=legal_text(marker=marker))

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def run(client, out):
    return download_gpsr(client, out, sleep=lambda s: None, now=lambda: NOW)


def test_downloads_two_versions_in_two_languages(tmp_path):
    client, requested = cellar()

    summary = run(client, tmp_path)

    assert summary.written == 4 and summary.failed == []
    assert sorted(r.headers["Accept-Language"] for r in requested) == ["deu", "deu", "eng", "eng"]
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.json"))
    assert [f.split("/")[1] for f in files] == ["lang=de", "lang=de", "lang=en", "lang=en"]


def test_second_run_writes_nothing_new(tmp_path):
    client, _ = cellar()
    run(client, tmp_path)

    summary = run(client, tmp_path)

    assert summary.written == 0 and summary.unchanged == 4


def test_challenge_page_is_recorded_not_stored(tmp_path):
    client, _ = cellar(blocked=("02023R0988",))

    summary = run(client, tmp_path)

    assert summary.written == 2
    assert summary.failed == ["02023R0988-20260529/en", "02023R0988-20260529/de"]


def test_main_exit_codes(tmp_path, monkeypatch):
    good, _ = cellar()
    monkeypatch.setattr(gpsr_job, "make_client", lambda: good)
    assert main(["--out", str(tmp_path / "a"), "--pause", "0"]) == 0

    bad, _ = cellar(blocked=("32023R0988",))
    monkeypatch.setattr(gpsr_job, "make_client", lambda: bad)
    assert main(["--out", str(tmp_path / "b"), "--pause", "0"]) == 1


def test_documents_are_the_original_and_the_consolidated_text():
    assert [d.celex for d in DOCUMENTS] == ["32023R0988", "02023R0988-20260529"]
    assert all(isinstance(d, GpsrDocument) for d in DOCUMENTS)
