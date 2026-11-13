"""EU Safety Gate weekly reports: read the index, build URLs, check and name report files.

The index lists every weekly report since 2005. Each entry has a ``URL`` to the report's
detail XML. One detail file holds all alerts of that week as ``<notifications>`` elements.

All XML is parsed with ``defusedxml`` because the files come from the internet.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from xml.etree.ElementTree import Element  # type only; parsing always uses defusedxml

from defusedxml import ElementTree

ROOT_TAG = "Safety-Gate"
ALERT_TAG = "notifications"
_LANGUAGE_PARAM = re.compile(r"(?<=[?&])language=[a-z]{2}(?=&|$)")


class InvalidReportError(ValueError):
    """Raised when downloaded bytes are not a Safety Gate report (e.g. an HTML error page)."""


@dataclass(frozen=True)
class WeeklyReport:
    """One entry of the weekly report index.

    Attributes:
        reference: Report code, for example ``Report-2026-45``.
        publication_date: Day the report was published.
        detail_url: URL of the report's detail XML (English), exactly as in the index.
    """

    reference: str
    publication_date: date
    detail_url: str


def _child_text(element: Element, tag: str) -> str:
    """Return the stripped text of a required child element.

    Args:
        element: The parent element.
        tag: Name of the child element.

    Returns:
        The child's text without surrounding whitespace.

    Raises:
        InvalidReportError: If the child is missing or empty.
    """
    child = element.find(tag)
    if child is None or not (child.text or "").strip():
        raise InvalidReportError(f"index entry has no <{tag}>")
    return (child.text or "").strip()


def parse_index(xml_bytes: bytes) -> list[WeeklyReport]:
    """Parse the weekly report index.

    Args:
        xml_bytes: The raw index XML.

    Returns:
        All reports, newest first.

    Raises:
        InvalidReportError: If the bytes are not a Safety Gate index.
    """
    root = ElementTree.fromstring(xml_bytes)
    if root.tag != ROOT_TAG:
        raise InvalidReportError(f"unexpected root element <{root.tag}>")
    reports = [
        WeeklyReport(
            reference=_child_text(entry, "reference"),
            publication_date=datetime.strptime(
                _child_text(entry, "publicationDate"), "%d/%m/%Y"
            ).date(),
            detail_url=_child_text(entry, "URL"),
        )
        for entry in root.iter("weeklyReport")
    ]
    return sorted(reports, key=lambda r: r.publication_date, reverse=True)


def detail_url_for(report: WeeklyReport, language: str) -> str:
    """Return the detail URL for one language, changing only the ``language`` parameter.

    The rest of the URL is kept byte for byte, because the server is sensitive to it.

    Args:
        report: The index entry.
        language: Two-letter language code, for example ``de``.

    Returns:
        The detail URL in the requested language.

    Raises:
        ValueError: If the language code is not two lower-case letters or the URL has no
            ``language`` parameter.
    """
    if not re.fullmatch(r"[a-z]{2}", language):
        raise ValueError(f"invalid language code {language!r}")
    url, count = _LANGUAGE_PARAM.subn(f"language={language}", report.detail_url)
    if count != 1:
        raise ValueError(f"no language parameter in {report.detail_url!r}")
    return url


def count_alerts(xml_bytes: bytes) -> int:
    """Check that the bytes are a Safety Gate report and count its alerts.

    Args:
        xml_bytes: A downloaded detail file.

    Returns:
        Number of ``<notifications>`` elements (may be 0).

    Raises:
        InvalidReportError: If the bytes are not XML or not a Safety Gate report.
    """
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise InvalidReportError(f"not XML: {exc}") from exc
    if root.tag != ROOT_TAG:
        raise InvalidReportError(f"unexpected root element <{root.tag}>")
    return len(root.findall(ALERT_TAG))


def _canonical(element: Element) -> list[object]:
    """Reduce an element to its tag and text, ignoring attributes and empty-value styles.

    ``<a/>``, ``<a><![CDATA[]]></a>`` and ``<a xsi:nil="true"/>`` all become ``["a", ""]``.
    """
    children = list(element)
    if not children:
        return [element.tag, (element.text or "").strip()]
    return [element.tag, [_canonical(child) for child in children]]


def content_fingerprint(xml_bytes: bytes) -> str:
    """Return a SHA-256 over the meaning of an XML document, not its exact bytes.

    The Safety Gate server sometimes serves the same report with a different XML
    declaration and a different style for empty fields (empty CDATA vs ``xsi:nil``).
    Those variants get the same fingerprint; a changed value or a changed alert does not.

    Args:
        xml_bytes: A downloaded XML file.

    Returns:
        The fingerprint as a hex string.
    """
    canonical = _canonical(ElementTree.fromstring(xml_bytes))
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def landing_name(reference: str, xml_bytes: bytes) -> str:
    """Build the file name for the landing zone: the reference plus a short fingerprint.

    The same content always gets the same name (stored once); changed content gets a new
    name (stored as a new version).

    Args:
        reference: Report code, for example ``Report-2026-45``.
        xml_bytes: The file content.

    Returns:
        A name like ``Report-2026-45_3f2a9c1b7d4e.xml``.
    """
    return f"{reference}_{content_fingerprint(xml_bytes)[:12]}.xml"
