"""Extract GTINs (EAN/UPC barcodes) from the free-text ``barcode`` field.

Profile Q5 showed the field is free text: prefixes (``*``, ``'``), spaces inside one code,
labels, numbering (``1) … 2) …``) and several 13-digit codes glued together without a
separator. The rules, in order:

1. Split the text into **parts** at strong separators: anything that is not a digit, a space
   or a dash (letters, ``,``, ``;``, ``/``, ``)``, ``*`` …).
2. Inside a part, spaces and dashes are weak: first try the part's digits **joined**
   (``"0 000011 283867"`` is one code). If that is no GTIN, try each digit run on its own.
3. A digit string is accepted if its length is 8, 12, 13 or 14 and its check digit is right.
4. A string whose length is a multiple of 13 (26, 39, 52 …) is split into 13-digit pieces
   **only if every piece** has a valid check digit. Nothing is guessed.
5. Everything else is rejected with a reason (rule A: the identifier is quarantined, the
   alert stays).
"""

import re
from dataclasses import dataclass, field

GTIN_LENGTHS = frozenset({8, 12, 13, 14})
MIN_CANDIDATE_DIGITS = 4  # shorter runs are numbering ("1)") or noise, not identifiers

_STRONG_SEPARATOR = re.compile(r"[^0-9 \-\u2010-\u2015\u00a0]+")  # weak: space, dashes, NBSP
_DIGIT_RUN = re.compile(r"\d+")


@dataclass(frozen=True)
class Rejected:
    """A digit string from the barcode field that is not a usable GTIN.

    Attributes:
        candidate: The digits that were checked.
        reason: ``check_digit``, ``glued_unsplittable``, ``placeholder`` or ``not_gtin_length``.
    """

    candidate: str
    reason: str


@dataclass(frozen=True)
class GtinExtraction:
    """Result of reading one barcode field.

    Attributes:
        gtins: Valid GTINs, zero-padded to 14 digits, in source order, no duplicates.
        rejected: Candidates that failed, with the reason.
    """

    gtins: list[str] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)


def has_valid_check_digit(digits: str) -> bool:
    """Check the GS1 mod-10 check digit of a GTIN-8, -12, -13 or -14.

    The code is padded to 14 digits; from the left, weights alternate 3, 1, 3, …

    Args:
        digits: Digits only.

    Returns:
        ``True`` if the length is a GTIN length and the last digit is correct.
    """
    if len(digits) not in GTIN_LENGTHS or not digits.isdigit():
        return False
    padded = digits.zfill(14)
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(padded[:13]))
    return (10 - total % 10) % 10 == int(padded[13])


def to_gtin14(digits: str) -> str:
    """Return the GTIN in its 14-digit form, the exact-match key (ADR-0004, D7).

    Args:
        digits: A valid GTIN of 8, 12, 13 or 14 digits.

    Returns:
        The digits left-padded with zeros to 14.
    """
    return digits.zfill(14)


def _check(digits: str) -> tuple[list[str], Rejected | None]:
    """Accept one digit string as GTIN(s) or explain why not.

    Args:
        digits: Digits only, at least ``MIN_CANDIDATE_DIGITS`` long.

    Returns:
        The accepted 14-digit GTINs, and a rejection when nothing was accepted.
    """
    if set(digits) == {"0"}:
        return [], Rejected(digits, "placeholder")
    if len(digits) in GTIN_LENGTHS:
        if has_valid_check_digit(digits):
            return [to_gtin14(digits)], None
        return [], Rejected(digits, "check_digit")
    if len(digits) % 13 == 0:
        pieces = [digits[i : i + 13] for i in range(0, len(digits), 13)]
        if all(has_valid_check_digit(p) and set(p) != {"0"} for p in pieces):
            return [to_gtin14(p) for p in pieces], None
        return [], Rejected(digits, "glued_unsplittable")
    return [], Rejected(digits, "not_gtin_length")


def extract_gtins(raw: str | None) -> GtinExtraction:
    """Read all GTINs from a free-text barcode field.

    Args:
        raw: ``barcode`` as stored in bronze.

    Returns:
        Valid GTINs (14 digits) and rejected candidates. Empty field: both lists empty.

    Examples:
        >>> extract_gtins("2000000011967; 2000000012032").gtins
        ['02000000011967', '02000000012032']
    """
    result = GtinExtraction()
    for part in _STRONG_SEPARATOR.split(raw or ""):
        runs = _DIGIT_RUN.findall(part)
        joined = "".join(runs)
        if len(joined) < MIN_CANDIDATE_DIGITS:
            continue
        accepted, rejected = _check(joined)
        if not accepted and len(runs) > 1:
            # The weak separators may separate codes after all: "044-8434482288540".
            singles = [_check(r) for r in runs if len(r) >= MIN_CANDIDATE_DIGITS]
            found = [g for ok, _ in singles for g in ok]
            if found:
                accepted = found
                rejected = None
                result.rejected.extend(r for _, r in singles if r is not None)
        for gtin in accepted:
            if gtin not in result.gtins:
                result.gtins.append(gtin)
        if rejected is not None:
            result.rejected.append(rejected)
    return result
