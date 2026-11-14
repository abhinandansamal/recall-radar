"""All silver rules for one Safety Gate alert, in one call.

The silver notebook calls :func:`clean_sg_alert` once per bronze row inside a Spark UDF.
Keeping the combination here (not in the notebook) means CI tests it.
"""

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from rr_transform.gtin import extract_gtins
from rr_transform.keys import model_keys, normalise_key
from rr_transform.sg_fields import (
    UNKNOWN_LEVEL,
    clean_case_number,
    parse_pictures,
    parse_publication_date,
    risk_level_code,
)

# Spark schema of :meth:`CleanAlert.as_row`, as DDL. Keep both in the same order.
SPARK_SCHEMA = (
    "case_number STRING, publication_date DATE, risk_level STRING, brand_key STRING, "
    "model_keys ARRAY<STRING>, gtins ARRAY<STRING>, "
    "rejected_gtins ARRAY<STRUCT<candidate: STRING, reason: STRING>>, "
    "picture_urls ARRAY<STRING>, errors ARRAY<STRING>"
)


@dataclass(frozen=True)
class CleanAlert:
    """The cleaned, typed values of one alert.

    Attributes:
        case_number: Repaired case number, or ``None`` if invalid.
        publication_date: Parsed date, or ``None`` if invalid.
        risk_level: ``serious``, ``other_risk``, ``other_alert`` or ``unknown``.
        brand_key: Normalised brand, or ``None``.
        model_keys: Normalised models.
        gtins: Valid GTINs, 14 digits.
        rejected_gtins: Barcode candidates that failed, as ``{candidate, reason}``.
        picture_urls: Photo URLs; the first is the main photo.
        errors: Alert-level errors. Any error sends the whole alert to quarantine.
    """

    case_number: str | None
    publication_date: date | None
    risk_level: str
    brand_key: str | None
    model_keys: list[str]
    gtins: list[str]
    rejected_gtins: list[dict[str, str]]
    picture_urls: list[str]
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        """Whether the alert can go to silver (no alert-level error)."""
        return not self.errors

    def as_row(self) -> dict[str, Any]:
        """Return the values as a dict for a Spark struct (see ``SPARK_SCHEMA``)."""
        return asdict(self)


def clean_sg_alert(
    *,
    case_number: str | None,
    publication_date: str | None,
    level: str | None,
    brand: str | None,
    model: str | None,
    barcode: str | None,
    pictures: str | None,
    today: date,
) -> CleanAlert:
    """Apply every silver rule to one bronze alert.

    Rule A (PO decision, 2026-11-14): an invalid barcode never removes the alert; only the
    identifier is rejected. An invalid case number or publication date does remove it,
    because silver cannot key or date such a row.

    Args:
        case_number: ``caseNumber``.
        publication_date: ``publicationDate`` (``dd-MM-yyyy``).
        level: ``level`` (EN or DE text).
        brand: ``brand``.
        model: ``type_numberOfModel``.
        barcode: ``barcode`` (free text).
        pictures: ``pictures`` (raw ``<picture>`` list).
        today: The run date, for the future-date check.

    Returns:
        The cleaned alert.
    """
    case = clean_case_number(case_number)
    published = parse_publication_date(publication_date, today)
    extraction = extract_gtins(barcode)
    return CleanAlert(
        case_number=case.value,
        publication_date=published.value,
        risk_level=risk_level_code(level),
        brand_key=normalise_key(brand),
        model_keys=model_keys(model),
        gtins=extraction.gtins,
        rejected_gtins=[
            {"candidate": r.candidate, "reason": r.reason} for r in extraction.rejected
        ],
        picture_urls=parse_pictures(pictures),
        errors=[e for e in (case.error, published.error) if e is not None],
    )


__all__ = ["SPARK_SCHEMA", "UNKNOWN_LEVEL", "CleanAlert", "clean_sg_alert"]
