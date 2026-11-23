"""Build the matching gold set (W1 screening) from alerts and safe catalogue listings.

The set is built from data, not invented:

- **Repeat alerts** (re-uploads): alerts that share an exact key (GTIN or brand + model) are
  the same product. For each such product one alert becomes the "listing" and is excluded
  from the search; the other alerts are the answer ("leave one out"). Each source gives up to
  five variants: with identifiers, without identifiers, German text, photo only, and an
  evasion variant (brand removed, model number disguised, title reworded).
- **Safe look-alikes**: ABO catalogue products of the same kinds as the alerts. They are not
  on any alert, so the expected result is "clear" (false-alarm cases).

Alerts in :data:`EXCLUDED_CATEGORIES` (motor vehicles) are left out: car models are recalled
again and again, so they would fill the set, and they are not sold as marketplace listings.

Splits are assigned per **product**, never per case, so variants of one product never sit in
both dev and test. The split comes from a hash of the product key: 60 % dev, 30 % test, 10 %
holdout; the same input always gives the same set.

Plain Python on purpose (no pydantic, no Spark): the Databricks notebook
``pipelines/eval/matching_gold_set.py`` calls it on collected rows, and the cases are
validated against :class:`rr_eval.schemas.MatchingCase` in the repository and in CI.
"""

import hashlib
import html
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

TITLE_MAX = 300
DESCRIPTION_MAX = 500
SOURCE_ALERT = "safety_gate"
SOURCE_ABO = "abo"  # Amazon Berkeley Objects, CC BY 4.0
VARIANTS = ("exact", "no_id", "german", "photo", "evasion")
EXCLUDED_CATEGORIES = ("motor vehicle",)  # matched in lower case inside category_en
SPOT_CHECK_SIZE = 30
_GENERIC_WORDS = ("New", "Premium", "2026", "Top quality", "Bestseller")
_PLACEHOLDER_PART = re.compile(
    r"\s*[-\u2013]\s*(unknown|unbekannt|not known|n/?a)\s*(?=[-\u2013,]|$)", flags=re.IGNORECASE
)
_EMPTY_LABEL = re.compile(
    r"\b(brand|model|type|marke|modell|typ)\b\s*:?\s*(?=[,.;]|$)", flags=re.IGNORECASE
)
_LOOKALIKE_DIGITS = str.maketrans({"0": "O", "1": "l", "5": "S", "8": "B"})


@dataclass(frozen=True)
class AlertRecord:
    """One alert as the gold tables hold it (``gold.kb_alerts`` + identifiers + photos)."""

    case_number: str
    title_en: str = ""
    title_de: str = ""
    description_en: str = ""
    description_de: str = ""
    category_en: str = ""
    brand: str | None = None
    model: str | None = None
    gtins: tuple[str, ...] = ()  # 14 digits, as in silver
    brand_models: tuple[str, ...] = ()  # "brandkey|modelkey"
    image_sha256: tuple[str, ...] = ()  # main photo first


@dataclass(frozen=True)
class SafeListing:
    """One ABO catalogue listing in a product kind that also appears in alerts."""

    item_id: str
    title: str
    language: str  # "en" or "de"
    category: str
    brand: str | None = None


@dataclass
class _Draft:
    sort_key: tuple[str, ...]
    data: dict[str, Any] = field(default_factory=dict)


def product_groups(alerts: Iterable[AlertRecord]) -> list[tuple[str, tuple[str, ...]]]:
    """Group alerts that share any exact key; keep groups of two or more.

    Keys connect transitively (A shares a GTIN with B, B shares brand + model with C: one
    product). Returns ``(product_key, case_numbers)`` sorted by product key, where the
    product key is the smallest exact key of the group (stable across runs).
    """
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[max(root_a, root_b)] = min(root_a, root_b)

    keys_of: dict[str, list[str]] = {}
    for alert in alerts:
        keys = [f"gtin:{g}" for g in alert.gtins] + [f"bm:{k}" for k in alert.brand_models]
        keys_of[alert.case_number] = keys
        for key in keys:
            union(f"case:{alert.case_number}", key)

    members: dict[str, set[str]] = {}
    for case_number, keys in keys_of.items():
        if keys:
            members.setdefault(find(f"case:{case_number}"), set()).add(case_number)
    groups = []
    for root, cases in members.items():
        if len(cases) < 2:
            continue
        group_keys = sorted(k for c in cases for k in keys_of[c])
        groups.append((group_keys[0] if group_keys else root, tuple(sorted(cases))))
    return sorted(groups)


def split_for(product_key: str) -> str:
    """Deterministic split from the product key: 60 % dev, 30 % test, 10 % holdout."""
    bucket = _bucket(product_key, 100)
    if bucket < 60:
        return "dev"
    if bucket < 90:
        return "test"
    return "holdout"


def build_matching_cases(
    alerts: Sequence[AlertRecord],
    safe_listings: Sequence[SafeListing],
    *,
    max_groups: int | None = None,
    max_look_alikes: int = 100,
) -> list[dict[str, Any]]:
    """Build all matching cases as plain dicts in :class:`~rr_eval.schemas.MatchingCase` shape.

    Args:
        alerts: All current alerts.
        safe_listings: ABO listings in the product kinds of the alerts.
        max_groups: Use at most this many repeat products (chosen by hash, not by order).
        max_look_alikes: Number of safe look-alike cases.

    Returns:
        Cases with ids ``M-0001``… in a stable order (products first, then look-alikes).
    """
    alerts = [a for a in alerts if not is_excluded(a)]
    by_case = {alert.case_number: alert for alert in alerts}
    groups = product_groups(alerts)
    if max_groups is not None:
        groups = sorted(groups, key=lambda g: _bucket(g[0], 1 << 30))[:max_groups]
        groups.sort()

    drafts: list[_Draft] = []
    for product_key, cases in groups:
        source = min((by_case[c] for c in cases), key=lambda a: _source_rank(a, product_key))
        relevant = {c: 2 for c in cases if c != source.case_number}
        others = [by_case[c] for c in relevant]
        shared_gtins = [g for g in source.gtins if any(g in o.gtins for o in others)]
        split = split_for(product_key)
        for variant in VARIANTS:
            data = _variant(variant, source, relevant, split, product_key, shared_gtins)
            if data is not None:
                drafts.append(_Draft(("0", product_key, str(VARIANTS.index(variant))), data))

    picked = sorted(safe_listings, key=lambda s: _bucket(s.item_id, 1 << 30))[:max_look_alikes]
    for listing in sorted(picked, key=lambda s: s.item_id):
        drafts.append(_Draft(("1", listing.item_id), _look_alike(listing)))

    cases_out = []
    for number, draft in enumerate(sorted(drafts, key=lambda d: d.sort_key), start=1):
        cases_out.append({"case_id": f"M-{number:04d}", **draft.data})
    return cases_out


def is_excluded(alert: AlertRecord) -> bool:
    """``True`` for alerts outside the marketplace scope (motor vehicles)."""
    category = alert.category_en.lower()
    return any(excluded in category for excluded in EXCLUDED_CATEGORIES)


def spot_check_sample(
    cases: Sequence[dict[str, Any]], size: int = SPOT_CHECK_SIZE
) -> list[dict[str, Any]]:
    """Pick cases for the Product Owner: every slice in turn, one case per product.

    Cases are taken in hash order (not file order), so the sample is spread over the whole
    set and the same input gives the same sample.
    """
    by_slice: dict[str, list[dict[str, Any]]] = {}
    for case in sorted(cases, key=lambda c: _bucket(c["case_id"], 1 << 30)):
        by_slice.setdefault(case["slices"][0], []).append(case)
    sample: list[dict[str, Any]] = []
    used_sources: set[str] = set()
    while len(sample) < size and any(by_slice.values()):
        for group in by_slice.values():
            while group and len(sample) < size:
                case = group.pop(0)
                if case["source"] not in used_sources:
                    used_sources.add(case["source"])
                    sample.append(case)
                    break
    return sorted(sample, key=lambda c: c["case_id"])


def to_jsonl(cases: Iterable[dict[str, Any]]) -> str:
    """One JSON object per line, keys sorted, so the file diffs cleanly in Git."""
    return "".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in cases)


def split_files(cases: Sequence[dict[str, Any]]) -> tuple[str, str]:
    """Return the text of ``v1.jsonl`` (dev + test) and ``v1.holdout.jsonl``."""
    main = [c for c in cases if c["split"] != "holdout"]
    holdout = [c for c in cases if c["split"] == "holdout"]
    return to_jsonl(main), to_jsonl(holdout)


# ---------- variants ----------


def _variant(
    variant: str,
    alert: AlertRecord,
    relevant: dict[str, int],
    split: str,
    product_key: str,
    shared_gtins: Sequence[str],
) -> dict[str, Any] | None:
    base = {
        "split": split,
        "expected": "match",
        "relevant": relevant,
        "exclude_ids": [alert.case_number],
        "source": f"{SOURCE_ALERT}:{alert.case_number}",
    }
    # A shared barcode if there is one; otherwise the group is joined by brand + model.
    gtin = _listing_gtin(shared_gtins[0]) if shared_gtins else None
    if variant == "exact":
        has_key = gtin or (alert.brand and alert.model and alert.brand_models)
        if not (has_key and alert.title_en):  # a real listing always has a title
            return None
        query = _query(alert.title_en, alert.description_en, "en")
        for name, value in (("brand", alert.brand), ("model", alert.model)):
            if value:
                query[name] = _clip_list(value, 100)
        if gtin:
            query["gtin"] = gtin
        return {**base, "slices": ["exact_key", "re_upload"], "query": query}
    if variant == "no_id":
        title = _strip_names(alert.title_en, alert)
        query = _query(title, _strip_names(alert.description_en, alert), "en")
        return {**base, "slices": ["no_identifier", "re_upload"], "query": query} if title else None
    if variant == "german":
        title = _strip_names(alert.title_de, alert)
        query = _query(title, _strip_names(alert.description_de, alert), "de")
        slices = ["cross_language", "no_identifier", "re_upload"]
        return {**base, "slices": slices, "query": query} if title else None
    if variant == "photo":
        if not alert.image_sha256:
            return None
        query = {"language": "en", "image_sha256": [alert.image_sha256[0]]}
        return {**base, "slices": ["image_only", "re_upload"], "query": query}
    title = _evasive_title(_strip_names(alert.title_en, alert), product_key)
    if not title:
        return None
    query = _query(title, "", "en")
    if alert.model:
        query["model"] = _disguise_model(_clip_list(alert.model, 90), product_key)
    note = "brand removed, model disguised, title reworded"
    return {**base, "slices": ["evasion", "re_upload"], "query": query, "notes": note}


def _look_alike(listing: SafeListing) -> dict[str, Any]:
    query = _query(listing.title, "", listing.language)
    if listing.brand:
        query["brand"] = listing.brand[:100]
    if listing.category:
        query["category"] = listing.category[:200]
    return {
        "split": split_for(f"abo:{listing.item_id}"),
        "slices": ["look_alike"],
        "query": query,
        "expected": "clear",
        "relevant": {},
        "exclude_ids": [],
        "source": f"{SOURCE_ABO}:{listing.item_id}",
        "notes": "safe catalogue product of an alerted kind; PO spot-check",
    }


# ---------- text helpers ----------


def _query(title: str, description: str, language: str) -> dict[str, Any]:
    query: dict[str, Any] = {"title": _clip(title, TITLE_MAX), "language": language}
    if description:
        query["description"] = _clip(description, DESCRIPTION_MAX)
    return query


def _clip(text: str, limit: int) -> str:
    text = html.unescape(text)  # alert texts contain "&amp;"; a seller writes "&"
    text = re.sub(r"\s+", " ", _PLACEHOLDER_PART.sub("", text)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
    return text.strip(" ,;-\u2013")


def _clip_list(text: str, limit: int) -> str:
    """Shorten a list like ``"A1, A2, A3"`` at a separator, so no model number is cut in half."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = max(text.rfind(sep, 0, limit) for sep in (",", ";"))
    return (text[:cut] if cut > 0 else text[:limit]).strip(" ,;")


def _strip_names(text: str, alert: AlertRecord) -> str:
    """Remove brand, model and barcodes from a text, so only the description can match."""
    text = html.unescape(text)
    for name in (alert.brand, alert.model):
        if name and len(name.strip()) >= 2:
            text = re.sub(re.escape(name.strip()), " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{8,14}\b", " ", text)
    text = _EMPTY_LABEL.sub("", text)  # "Brand , model ." left after removing the names
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"([,;:.])(?=[,.;:])", "", text)
    text = re.sub(r"\s*[-\u2013]\s*(?=[-\u2013]|$)", "", text)
    return _clip(re.sub(r"^[\s\-\u2013,;:]+", "", text), TITLE_MAX)


def _evasive_title(title: str, key: str) -> str:
    words = title.split()
    if not words:
        return ""
    shift = _bucket(key + "shift", len(words))
    words = words[shift:] + words[:shift]
    extra = _GENERIC_WORDS[_bucket(key + "word", len(_GENERIC_WORDS))]
    return _clip(f"{extra} {' '.join(words).lower()}", TITLE_MAX)


def _disguise_model(model: str, key: str) -> str:
    """Change a model number so the exact key no longer matches (O for 0, a suffix …)."""
    disguised = model.translate(_LOOKALIKE_DIGITS)
    if disguised == model:
        disguised = f"{model}-{('V2', 'Plus', 'X')[_bucket(key + 'model', 3)]}"
    return disguised[:100]


def _listing_gtin(gtin14: str) -> str:
    """Show a barcode as a seller would: EAN-13 when the 14-digit form starts with 0."""
    return gtin14[1:] if len(gtin14) == 14 and gtin14.startswith("0") else gtin14


def _source_rank(alert: AlertRecord, product_key: str) -> tuple[bool, bool, bool, int]:
    """Prefer the alert that gives the most variants (photo, both titles); hash breaks ties."""
    return (
        not alert.image_sha256,
        not alert.title_en,
        not alert.title_de,
        _bucket(product_key + alert.case_number, 1 << 30),
    )


def _bucket(text: str, size: int) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16) % size
