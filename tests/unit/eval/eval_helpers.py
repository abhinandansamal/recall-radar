"""Small builders for gold-set cases used by the evaluation tests."""

from typing import Any

from rr_eval.schemas import MatchingCase

A1, A2, A3 = "SR/00001/26", "SR/00002/26", "SR/00003/26"


def matching(case_id: str = "M-0001", **overrides: Any) -> MatchingCase:
    data: dict[str, Any] = {
        "case_id": case_id,
        "split": "dev",
        "slices": ["re_upload"],
        "query": {"title": "Baby soother holder", "language": "en"},
        "expected": "match",
        "relevant": {A1: 2},
        "source": "test",
    }
    data.update(overrides)
    return MatchingCase.model_validate(data)
