"""Normalised brand and model keys for exact matching (ADR-0004, D7).

Silver does the normalisation once, so the app never guesses: ``"EP-TA200"`` → ``"epta200"``,
``" Jojo Maman Bébé "`` → ``"jojomamanbebe"``. Values that mean "no value" (``"unknown"``,
``"-"``) become ``None``; a key built from them would match unrelated products.
"""

import re
import unicodedata

_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
_MODEL_SEPARATOR = re.compile(r"[,;\n\r]+")
MIN_MODEL_KEY = 3  # "a1" or "s" would match far too many listings

# Compared after normalisation, so spaces, case and accents do not matter.
PLACEHOLDERS = frozenset(
    {
        "",
        "na",
        "nd",
        "none",
        "null",
        "unknown",
        "unbekannt",
        "notknown",
        "nichtbekannt",
        "noname",
        "nobrand",
        "withoutbrand",
        "ohnemarke",
        "keinemarke",
        "notspecified",
        "nichtangegeben",
        "various",
        "diverse",
    }
)

_SPECIAL = str.maketrans({"ß": "ss", "æ": "ae", "ø": "o", "œ": "oe", "đ": "d", "ł": "l"})


def normalise_key(raw: str | None) -> str | None:
    """Turn a brand or model text into an exact-match key.

    Lower case, accents removed, special letters spelled out, then only ``a-z`` and ``0-9``
    kept.

    Args:
        raw: Brand or model text from the source.

    Returns:
        The key, or ``None`` if nothing usable is left or the text is a placeholder.
    """
    text = (raw or "").lower().translate(_SPECIAL)
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    key = _NOT_ALNUM.sub("", ascii_text)
    return None if key in PLACEHOLDERS else key


def model_keys(raw: str | None) -> list[str]:
    """Split the model field into separate models and normalise each.

    Only ``,``, ``;`` and line breaks separate models; ``/``, ``.`` and ``-`` appear inside
    real model numbers (``"10.2.17.25.271"``), so they are kept as part of one model.

    Args:
        raw: ``type_numberOfModel`` as stored in bronze.

    Returns:
        Model keys in source order, without duplicates and without keys shorter than
        ``MIN_MODEL_KEY``.
    """
    keys: list[str] = []
    for piece in _MODEL_SEPARATOR.split(raw or ""):
        key = normalise_key(piece)
        if key is not None and len(key) >= MIN_MODEL_KEY and key not in keys:
            keys.append(key)
    return keys
