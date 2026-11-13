"""Download Safety Gate weekly reports (EN + DE) into the local landing zone.

Usage:
    uv run python -m rr_ingest.safety_gate_job --out data/local/landing --since 2025-01-01

Layout written below ``--out`` (see docs/architecture/data-storage-design.md, section 6.1)::

    safety_gate/index/fetched_date=<YYYY-MM-DD>/weekly_index_<sha12>.xml
    safety_gate/reports/lang=<en|de>/<Report-YYYY-WW>_<sha12>.xml
"""

import argparse
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from rr_core.config import get_settings
from rr_core.logging import configure_logging, get_logger
from rr_ingest.http import fetch, make_client
from rr_ingest.landing import write_once
from rr_ingest.safety_gate import (
    InvalidReportError,
    content_fingerprint,
    count_alerts,
    detail_url_for,
    landing_name,
    parse_index,
)

INDEX_URL = "https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/list/xml/en"
LANGUAGES = ("en", "de")

log = get_logger(__name__)


@dataclass
class Summary:
    """Counts of one run."""

    written: int = 0
    unchanged: int = 0
    alerts: int = 0
    failed: list[str] = field(default_factory=list)


def download_safety_gate(
    client: httpx.Client,
    out_root: Path,
    *,
    since: date,
    languages: Sequence[str] = LANGUAGES,
    pause_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    today: date | None = None,
) -> Summary:
    """Download the index and every report published on or after ``since``.

    A report that fails (network error or invalid content) is recorded and skipped, so one
    bad week does not stop the whole run.

    Args:
        client: The HTTP client.
        out_root: Landing zone root folder.
        since: First publication date to download.
        languages: Language codes to download.
        pause_s: Pause between requests, to be polite to the EC servers.
        sleep: Wait function (replaced in tests).
        today: Date used in the index folder name (default: today in UTC).

    Returns:
        Counts of written, unchanged and failed files.
    """
    summary = Summary()
    fetched_date = (today or datetime.now(UTC).date()).isoformat()

    index_bytes = fetch(client, INDEX_URL, sleep=sleep)
    reports = [r for r in parse_index(index_bytes) if r.publication_date >= since]
    write_once(
        out_root,
        f"safety_gate/index/fetched_date={fetched_date}/"
        f"weekly_index_{content_fingerprint(index_bytes)[:12]}.xml",
        index_bytes,
    )
    log.info("index_read", reports_selected=len(reports), since=since.isoformat())

    for report in reports:
        for language in languages:
            url = detail_url_for(report, language)
            try:
                sleep(pause_s)
                content = fetch(client, url, sleep=sleep)
                alerts = count_alerts(content)
            except (httpx.HTTPError, InvalidReportError) as exc:
                summary.failed.append(f"{report.reference}/{language}")
                log.warning("report_failed", report=report.reference, lang=language, error=str(exc))
                continue
            path = f"safety_gate/reports/lang={language}/{landing_name(report.reference, content)}"
            if write_once(out_root, path, content):
                summary.written += 1
                summary.alerts += alerts
                log.info("report_written", report=report.reference, lang=language, alerts=alerts)
            else:
                summary.unchanged += 1
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point.

    Args:
        argv: Arguments (default: from the command line).

    Returns:
        Exit code: 0 if every report was handled, 1 if any failed.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/local/landing"))
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--lang", action="append", choices=LANGUAGES, dest="languages")
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between requests")
    args = parser.parse_args(argv)

    configure_logging(get_settings())
    with make_client() as client:
        summary = download_safety_gate(
            client,
            args.out,
            since=args.since,
            languages=args.languages or LANGUAGES,
            pause_s=args.pause,
        )
    log.info(
        "run_finished",
        written=summary.written,
        unchanged=summary.unchanged,
        alerts=summary.alerts,
        failed=len(summary.failed),
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
