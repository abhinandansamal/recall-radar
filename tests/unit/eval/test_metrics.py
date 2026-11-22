"""Ranking metrics against hand-computed examples."""

import math

import pytest

from rr_eval.metrics import (
    clean_ranking,
    hit_at_k,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

RANKED = ["a", "b", "c", "d", "e"]
RELEVANT = {"b": 2, "e": 1, "z": 2}  # z is never found


def test_recall_counts_found_relevant_ids():
    assert recall_at_k(RANKED, RELEVANT, 5) == pytest.approx(2 / 3)
    assert recall_at_k(RANKED, RELEVANT, 1) == 0.0
    assert recall_at_k(RANKED, {}, 5) is None


def test_precision_divides_by_k_even_for_short_rankings():
    assert precision_at_k(RANKED, RELEVANT, 5) == pytest.approx(2 / 5)
    assert precision_at_k(["b"], RELEVANT, 5) == pytest.approx(1 / 5)


def test_reciprocal_rank_uses_first_relevant():
    assert reciprocal_rank(RANKED, RELEVANT) == pytest.approx(1 / 2)
    assert reciprocal_rank(["x", "y"], RELEVANT) == 0.0


def test_ndcg_matches_hand_computation():
    # DCG  = 2/log2(3) + 1/log2(6)              = 1.26186 + 0.38685 = 1.64871
    # IDCG = 2/log2(2) + 2/log2(3) + 1/log2(4)  = 2 + 1.26186 + 0.5 = 3.76186
    assert ndcg_at_k(RANKED, RELEVANT, 5) == pytest.approx(0.43827, abs=1e-4)
    assert ndcg_at_k(["b", "z", "e"], RELEVANT, 3) == pytest.approx(1.0)
    assert ndcg_at_k(RANKED, {}, 5) is None


def test_ndcg_rewards_same_product_more_than_similar():
    same_first = ndcg_at_k(["s", "m"], {"s": 2, "m": 1}, 2)
    similar_first = ndcg_at_k(["m", "s"], {"s": 2, "m": 1}, 2)
    assert same_first is not None and similar_first is not None
    assert same_first > similar_first
    assert same_first == pytest.approx(1.0)
    assert similar_first == pytest.approx((1 + 2 / math.log2(3)) / (2 + 1 / math.log2(3)))


def test_hit_at_k():
    assert hit_at_k(RANKED, RELEVANT, 2)
    assert not hit_at_k(RANKED, RELEVANT, 1)


def test_clean_ranking_drops_excluded_and_repeated_ids():
    assert clean_ranking(["a", "b", "a", "c"], exclude=["b"]) == ["a", "c"]


@pytest.mark.parametrize("func", [recall_at_k, precision_at_k, ndcg_at_k, hit_at_k])
def test_k_must_be_positive(func):
    with pytest.raises(ValueError, match="k must be at least 1"):
        func(RANKED, RELEVANT, 0)


def test_mean_ignores_undefined_values():
    assert mean([1.0, None, 0.0]) == pytest.approx(0.5)
    assert mean([None]) is None
