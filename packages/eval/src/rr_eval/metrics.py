"""Ranking metrics for one query, as plain functions.

All functions take the ranked result ids (best first) and the graded relevance of the case
(``{alert_id: grade}``, grade 2 = same product, 1 = similar). Ids in ``exclude`` are removed
from the ranking first, so leave-one-out cases are scored on the remaining alerts.

Definitions (k is a cut-off, ranks start at 1):

- recall@k: share of relevant ids found in the top k.
- precision@k: relevant ids in the top k divided by k.
- reciprocal rank: 1 / rank of the first relevant id, 0 if none is found.
- nDCG@k: DCG with linear gain ``grade / log2(rank + 1)``, divided by the DCG of the ideal
  ranking. Linear gain keeps "same product" twice as valuable as "similar".
"""

import math
from collections.abc import Iterable, Mapping, Sequence


def clean_ranking(ranked: Sequence[str], exclude: Iterable[str] = ()) -> list[str]:
    """Drop excluded ids and repeated ids, keeping the first position of each id."""
    skip = set(exclude)
    seen: set[str] = set()
    result: list[str] = []
    for item in ranked:
        if item in skip or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def recall_at_k(ranked: Sequence[str], relevant: Mapping[str, int], k: int) -> float | None:
    """Share of relevant ids in the top ``k``; ``None`` when the case has no relevant ids."""
    _check_k(k)
    if not relevant:
        return None
    found = sum(1 for item in ranked[:k] if item in relevant)
    return found / len(relevant)


def precision_at_k(ranked: Sequence[str], relevant: Mapping[str, int], k: int) -> float:
    """Relevant ids in the top ``k`` divided by ``k`` (a short ranking is not rewarded)."""
    _check_k(k)
    found = sum(1 for item in ranked[:k] if item in relevant)
    return found / k


def reciprocal_rank(ranked: Sequence[str], relevant: Mapping[str, int]) -> float:
    """``1 / rank`` of the first relevant id, ``0.0`` if none is in the ranking."""
    for rank, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: Mapping[str, int], k: int) -> float | None:
    """Normalised discounted cumulative gain at ``k``; ``None`` without relevant ids."""
    _check_k(k)
    if not relevant:
        return None
    dcg = sum(
        relevant.get(item, 0) / math.log2(rank + 1) for rank, item in enumerate(ranked[:k], start=1)
    )
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum(grade / math.log2(rank + 1) for rank, grade in enumerate(ideal, start=1))
    return dcg / idcg


def hit_at_k(ranked: Sequence[str], relevant: Mapping[str, int], k: int) -> bool:
    """``True`` if at least one relevant id is in the top ``k``."""
    _check_k(k)
    return any(item in relevant for item in ranked[:k])


def mean(values: Iterable[float | None]) -> float | None:
    """Mean of the defined values; ``None`` if there are none."""
    defined = [value for value in values if value is not None]
    if not defined:
        return None
    return sum(defined) / len(defined)


def _check_k(k: int) -> None:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
