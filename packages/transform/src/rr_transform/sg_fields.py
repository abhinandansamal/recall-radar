"""Field rules for Safety Gate alerts: case number, date, risk level, pictures.

Each function takes the raw bronze text and returns a clean value or a reason why the value
is unusable. Reasons are short, stable codes; they are counted in ``ops.dq_results`` and
stored in ``ops.quarantine_*``.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# The 10 valid formats found in 20 years of reports (profile Q3), as one expression.
CASE_NUMBER = re.compile(r"(?:A\d{2}|SR|INFO|OR|EM)/\d{4,5}/\d{2}|\d{3,4}/\d{2}")
_HTML_TAG = re.compile(r"<[^>]*>")
_DATE_FORMAT = "%d-%m-%Y"  # profile Q4: the only format in publicationDate

# Profile Q7: 3 levels, translated per language.
RISK_LEVELS = {
    "serious risk": "serious",
    "ernstes risiko": "serious",
    "other risk levels": "other_risk",
    "sonstige risikoniveaus": "other_risk",
    "other types of alerts": "other_alert",
    "sonstige warnungen": "other_alert",
}
UNKNOWN_LEVEL = "unknown"

_PICTURE = re.compile(r"<picture>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</picture>", re.DOTALL)


# Plain classes instead of one generic class: the notebook may run on Python 3.10/3.11
# (Databricks serverless environment versions), where PEP 695 generics do not exist.
@dataclass(frozen=True)
class CheckedText:
    """A cleaned text value, or the reason it could not be cleaned.

    Attributes:
        value: The clean value; ``None`` when the check failed.
        error: A short reason code; ``None`` when the check passed.
    """

    value: str | None
    error: str | None = None


@dataclass(frozen=True)
class CheckedDate:
    """A parsed date, or the reason it could not be parsed.

    Attributes:
        value: The date; ``None`` when the check failed.
        error: A short reason code; ``None`` when the check passed.
    """

    value: date | None
    error: str | None = None


def clean_case_number(raw: str | None) -> CheckedText:
    """Repair and validate a case number.

    Only repairs that need no guessing are made: HTML tags and a trailing dot are removed
    (``"1150/09<br></br>"`` and ``"0806/10."``). Everything else must already match one of
    the known formats.

    Args:
        raw: ``caseNumber`` as stored in bronze.

    Returns:
        The case number, or the error ``case_number_missing`` / ``case_number_format``.
    """
    text = _HTML_TAG.sub("", raw or "").strip().rstrip(".").strip()
    if not text:
        return CheckedText(None, "case_number_missing")
    if not CASE_NUMBER.fullmatch(text):
        return CheckedText(None, "case_number_format")
    return CheckedText(text)


def parse_publication_date(raw: str | None, today: date) -> CheckedDate:
    """Parse ``dd-MM-yyyy`` and reject empty, invalid and future dates.

    One day of tolerance covers time zones: the EC publishes in Brussels time.

    Args:
        raw: ``publicationDate`` as stored in bronze.
        today: The run date; dates after ``today + 1 day`` are rejected.

    Returns:
        The date, or ``publication_date_missing`` / ``_invalid`` / ``_future``.
    """
    text = (raw or "").strip()
    if not text:
        return CheckedDate(None, "publication_date_missing")
    try:
        parsed = datetime.strptime(text, _DATE_FORMAT).date()
    except ValueError:
        return CheckedDate(None, "publication_date_invalid")
    if parsed > today + timedelta(days=1):
        return CheckedDate(None, "publication_date_future")
    return CheckedDate(parsed)


def risk_level_code(raw: str | None) -> str:
    """Map the translated risk level to one language-neutral code.

    An unknown label does **not** remove the alert: a new label from the EC must never hide
    a dangerous product. It becomes ``unknown`` and is counted as a data-quality failure.

    Args:
        raw: ``level`` as stored in bronze, in English or German.

    Returns:
        ``serious``, ``other_risk``, ``other_alert`` or ``unknown``.
    """
    return RISK_LEVELS.get(" ".join((raw or "").split()).lower(), UNKNOWN_LEVEL)


def parse_pictures(raw: str | None) -> list[str]:
    """Extract picture URLs from the raw ``<picture>`` list (profile Q8).

    Args:
        raw: ``pictures`` as stored in bronze, e.g. ``"<picture>https://…</picture> …"``.

    Returns:
        The http(s) URLs in source order without duplicates; the first is the main photo.
    """
    urls: list[str] = []
    for url in _PICTURE.findall(raw or ""):
        if url.startswith(("https://", "http://")) and url not in urls:
            urls.append(url)
    return urls
