"""Download the GPSR legal text (EN + DE, original and consolidated) into the landing zone.

Usage:
    uv run python -m rr_ingest.gpsr_job --out data/local/landing

Layout written below ``--out``::

    gpsr/lang=<en|de>/CELEX_<celex>_<sha12>.json
"""

import argparse
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from rr_core.config import get_settings
from rr_core.logging import configure_logging, get_logger
from rr_ingest.gpsr import (
    DOCUMENTS,
    LANGUAGES,
    GpsrDocument,
    InvalidDocumentError,
    count_articles,
    envelope,
    request_for,
)
from rr_ingest.http import fetch, make_client
from rr_ingest.landing import write_once

log = get_logger("rr_ingest.gpsr_job")


@dataclass
class Summary:
    """Counts of one run."""

    written: int = 0
    unchanged: int = 0
    failed: list[str] = field(default_factory=list)


def download_gpsr(
    client: httpx.Client,
    out_root: Path,
    *,
    documents: Sequence[GpsrDocument] = DOCUMENTS,
    languages: Sequence[str] = tuple(LANGUAGES),
    pause_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Summary:
    """Download every document in every language; skip texts that are already stored.

    Args:
        client: The HTTP client.
        out_root: Landing zone root folder.
        documents: The document versions to fetch.
        languages: Language codes to fetch.
        pause_s: Pause between requests.
        sleep: Wait function (replaced in tests).
        now: Clock (replaced in tests).

    Returns:
        Counts of written, unchanged and failed downloads.
    """
    summary = Summary()
    for document in documents:
        for language in languages:
            url, headers = request_for(document, language)
            label = f"{document.celex}/{language}"
            try:
                sleep(pause_s)
                content = fetch(client, url, headers=headers, sleep=sleep)
                articles = count_articles(content)
            except (httpx.HTTPError, InvalidDocumentError) as exc:
                summary.failed.append(label)
                log.warning("document_failed", document=label, error=str(exc))
                continue
            name, data = envelope(document, language, url, content, articles, now())
            if write_once(out_root, f"gpsr/lang={language}/{name}", data):
                summary.written += 1
                log.info("document_written", document=label, articles=articles, file=name)
            else:
                summary.unchanged += 1
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point.

    Args:
        argv: Arguments (default: from the command line).

    Returns:
        Exit code: 0 if every download worked, 1 if any failed.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/local/landing"))
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between requests")
    args = parser.parse_args(argv)

    configure_logging(get_settings())
    with make_client() as client:
        summary = download_gpsr(client, args.out, pause_s=args.pause)
    log.info(
        "run_finished",
        written=summary.written,
        unchanged=summary.unchanged,
        failed=len(summary.failed),
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
