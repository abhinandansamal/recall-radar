"""GPSR legal text (Regulation (EU) 2023/988) from the EU Publications Office (Cellar).

EUR-Lex answers scripts with a bot challenge (HTTP 202, empty body, header
``x-amzn-waf-action: challenge``). Cellar is the Publications Office's interface for
programs: a document is requested by its CELEX number, and the format and language are
chosen with the ``Accept`` and ``Accept-Language`` headers.

Each download is stored as one JSON "envelope": the unchanged XHTML text plus where and
when it was retrieved. Bronze reads these envelopes.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime

CELLAR_URL = "https://publications.europa.eu/resource/celex/{celex}"
ACCEPT = "application/xhtml+xml"
LANGUAGES = {"en": "eng", "de": "deu"}  # our code -> ISO 639-3 code used by Cellar
LICENCE = "European Union, EUR-Lex / Publications Office; reuse with attribution"

# Article headings: "oj-ti-art" in the Official Journal text, "title-article-norm" in the
# consolidated text. GPSR has 52 articles.
_ARTICLE_HEADING = re.compile(rb'class="(?:oj-ti-art|title-article-norm)"')
MIN_ARTICLES = 50


class InvalidDocumentError(ValueError):
    """Raised when downloaded bytes are not the expected legal text."""


@dataclass(frozen=True)
class GpsrDocument:
    """One version of the regulation.

    Attributes:
        celex: CELEX number in Cellar, for example ``02023R0988-20260529``.
        version: Our label for the version, used in file names and in bronze.
    """

    celex: str
    version: str


DOCUMENTS = (
    GpsrDocument("32023R0988", "original-2023-05-23"),
    GpsrDocument("02023R0988-20260529", "consolidated-2026-05-29"),
)


def request_for(document: GpsrDocument, language: str) -> tuple[str, dict[str, str]]:
    """Return the Cellar URL and headers for one document in one language.

    Args:
        document: The document version.
        language: ``en`` or ``de``.

    Returns:
        The URL and the content-negotiation headers.

    Raises:
        ValueError: If the language is not supported.
    """
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language {language!r}")
    url = CELLAR_URL.format(celex=document.celex)
    return url, {"Accept": ACCEPT, "Accept-Language": LANGUAGES[language]}


def count_articles(content: bytes) -> int:
    """Check that the bytes are the regulation's XHTML and count the article headings.

    Args:
        content: A downloaded document.

    Returns:
        Number of article headings.

    Raises:
        InvalidDocumentError: If the content is empty, not HTML, not the regulation, or has
            too few articles (for example a challenge or error page).
    """
    if b"<html" not in content[:2000].lower():
        raise InvalidDocumentError("not an HTML document")
    if b"2023/988" not in content:
        raise InvalidDocumentError("regulation number 2023/988 not found")
    articles = len(_ARTICLE_HEADING.findall(content))
    if articles < MIN_ARTICLES:
        raise InvalidDocumentError(f"only {articles} article headings (expected >= {MIN_ARTICLES})")
    return articles


def envelope(
    document: GpsrDocument,
    language: str,
    source_url: str,
    content: bytes,
    articles: int,
    retrieved_at: datetime,
) -> tuple[str, bytes]:
    """Build the landing file name and JSON envelope for one download.

    The name contains a hash of the XHTML content, so the same text is stored once and a
    changed text is stored as a new version.

    Args:
        document: The document version.
        language: ``en`` or ``de``.
        source_url: The Cellar URL that was requested.
        content: The XHTML bytes, stored unchanged as text.
        articles: Number of article headings found.
        retrieved_at: When the download happened (UTC).

    Returns:
        The file name and the JSON bytes.
    """
    sha256 = hashlib.sha256(content).hexdigest()
    record = {
        "celex": document.celex,
        "version": document.version,
        "language": language,
        "source_url": source_url,
        "accept_language": LANGUAGES[language],
        "retrieved_at": retrieved_at.isoformat(),
        "sha256": sha256,
        "size_bytes": len(content),
        "article_count": articles,
        "licence": LICENCE,
        "content": content.decode("utf-8"),
    }
    name = f"CELEX_{document.celex}_{sha256[:12]}.json"
    return name, json.dumps(record, ensure_ascii=False).encode("utf-8")
