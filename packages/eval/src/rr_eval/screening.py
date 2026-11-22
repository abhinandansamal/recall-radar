"""Evaluate the W1 screening pipeline stage by stage on matching cases.

The screening service returns, for one listing, what each stage produced
(:class:`ScreeningRun`). This module checks every stage of every case, labels each wrong case
with its **first failing stage**, and computes the metrics the gates need, overall and per
slice.

Stages in pipeline order:

1. ``exact_keys``: exact GTIN or brand + model lookup. Fails when an exact-key case does not
   find a same-product alert, or when any exact hit is not a relevant alert (a false exact
   match is as bad as a missed one).
2. ``candidates``: hybrid text + photo search after RRF. Fails when no relevant alert is in
   the top ``candidate_k``.
3. ``rerank``: rerank / judge ordering. Fails when no relevant alert is in the top
   ``rerank_k``.
4. ``result``: the final label (match / similar / clear). Fails when it differs from the
   expected label.

A stage that did not run (``None`` in the run, e.g. no reranker yet) is skipped, so the
harness works from the first stage that exists.
"""

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from rr_eval.gates import MetricValue
from rr_eval.metrics import (
    clean_ranking,
    hit_at_k,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from rr_eval.schemas import Label, ListingQuery, MatchingCase

STAGES: tuple[str, ...] = ("exact_keys", "candidates", "rerank", "result")
DANGEROUS: frozenset[Label] = frozenset({"match", "similar"})


@dataclass(frozen=True)
class ScreeningRun:
    """What the screening pipeline produced for one listing.

    Attributes:
        exact_hits: Alert ids found by the exact-key step.
        candidates: Ranked alert ids after fusion (best first).
        reranked: Ranked alert ids after rerank / judge, or ``None`` if the stage is not built.
        label: Final label, or ``None`` if the stage is not built.
        latency_ms: Time for the whole call, if measured.
    """

    exact_hits: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()
    reranked: tuple[str, ...] | None = None
    label: Label | None = None
    latency_ms: float | None = None


Screener = Callable[[ListingQuery], ScreeningRun]
"""Anything that screens a listing: the real service, or a stub in tests."""


@dataclass(frozen=True)
class CaseResult:
    """Stage outcomes for one case."""

    case: MatchingCase
    run: ScreeningRun
    stages: dict[str, bool]  # stage -> passed; only stages that apply to this case
    first_failing_stage: str | None
    false_exact: bool = False  # an exact hit that is not a relevant alert


@dataclass
class ScreeningReport:
    """All case results and the metrics derived from them."""

    results: list[CaseResult]
    metrics: dict[tuple[str, str], MetricValue] = field(default_factory=dict)

    @property
    def failing_stage_counts(self) -> Counter[str]:
        """How many wrong cases failed first at each stage."""
        return Counter(r.first_failing_stage for r in self.results if r.first_failing_stage)


def evaluate_screening(
    cases: Sequence[MatchingCase],
    screener: Screener,
    candidate_k: int = 20,
    rerank_k: int = 5,
) -> ScreeningReport:
    """Screen every case and evaluate each stage.

    Args:
        cases: Matching cases (usually one split).
        screener: Function that screens one listing.
        candidate_k: Cut-off for the candidate stage check.
        rerank_k: Cut-off for the rerank stage check.

    Returns:
        The per-case results and the metrics per slice.
    """
    results = [_evaluate_case(case, screener(case.query), candidate_k, rerank_k) for case in cases]
    return ScreeningReport(results=results, metrics=compute_metrics(results))


def compute_metrics(results: Iterable[CaseResult]) -> dict[tuple[str, str], MetricValue]:
    """Compute every screening metric for the slice ``all`` and for each case slice."""
    by_slice: dict[str, list[CaseResult]] = {"all": []}
    for result in results:
        by_slice["all"].append(result)
        for case_slice in result.case.slices:
            by_slice.setdefault(case_slice, []).append(result)
    metrics: dict[tuple[str, str], MetricValue] = {}
    for slice_name, group in by_slice.items():
        for name, value in _slice_metrics(group).items():
            metrics[(slice_name, name)] = value
    return metrics


def _evaluate_case(
    case: MatchingCase, run: ScreeningRun, candidate_k: int, rerank_k: int
) -> CaseResult:
    exclude = case.exclude_ids
    stages: dict[str, bool] = {}

    exact = clean_ranking(run.exact_hits, exclude)
    same_product = {aid for aid, grade in case.relevant.items() if grade == 2}
    false_exact = any(aid not in case.relevant for aid in exact)
    if "exact_key" in case.slices or exact:
        found = bool(same_product & set(exact)) if "exact_key" in case.slices else True
        stages["exact_keys"] = found and not false_exact

    if case.relevant:
        candidates = clean_ranking(run.candidates, exclude)
        stages["candidates"] = bool(set(exact) & set(case.relevant)) or hit_at_k(
            candidates, case.relevant, candidate_k
        )
        if run.reranked is not None:
            reranked = clean_ranking(run.reranked, exclude)
            stages["rerank"] = hit_at_k(reranked, case.relevant, rerank_k)

    if run.label is not None:
        stages["result"] = run.label == case.expected

    first = next((s for s in STAGES if s in stages and not stages[s]), None)
    return CaseResult(
        case=case, run=run, stages=stages, first_failing_stage=first, false_exact=false_exact
    )


def _slice_metrics(group: list[CaseResult]) -> dict[str, MetricValue]:
    out: dict[str, MetricValue] = {}

    def put(name: str, values: list[float | None]) -> None:
        defined = [v for v in values if v is not None]
        value = mean(defined)
        if value is not None:
            out[name] = MetricValue(value=value, n=len(defined))

    exact_cases = [r for r in group if "exact_key" in r.case.slices]
    put("exact_key_recall", [float(r.stages.get("exact_keys", False)) for r in exact_cases])
    put(
        "false_exact_match_rate",
        [float(r.false_exact) for r in group if r.run.exact_hits],
    )

    with_relevant = [r for r in group if r.case.relevant]
    ranked = [(r, clean_ranking(r.run.candidates, r.case.exclude_ids)) for r in with_relevant]
    for k in (20, 50):
        put(f"recall@{k}", [recall_at_k(c, r.case.relevant, k) for r, c in ranked])
    put("mrr", [reciprocal_rank(c, r.case.relevant) for r, c in ranked])

    reranked = [
        (r, clean_ranking(r.run.reranked, r.case.exclude_ids))
        for r in with_relevant
        if r.run.reranked is not None
    ]
    put("precision@5", [precision_at_k(c, r.case.relevant, 5) for r, c in reranked])
    put("ndcg@10", [ndcg_at_k(c, r.case.relevant, 10) for r, c in reranked])

    labelled = [r for r in group if r.run.label is not None]
    put(
        "catch_rate",
        [float(r.run.label in DANGEROUS) for r in labelled if r.case.expected in DANGEROUS],
    )
    put(
        "false_alarm_rate",
        [float(r.run.label in DANGEROUS) for r in labelled if r.case.expected == "clear"],
    )
    put("label_accuracy", [float(r.run.label == r.case.expected) for r in labelled])

    latencies = sorted(r.run.latency_ms for r in group if r.run.latency_ms is not None)
    if latencies:
        index = max(0, -(-95 * len(latencies) // 100) - 1)  # nearest-rank p95
        out["latency_p95_ms"] = MetricValue(value=latencies[index], n=len(latencies))
    return out
