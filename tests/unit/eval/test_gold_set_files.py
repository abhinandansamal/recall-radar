"""Every gold-set file in ``evals/data`` must load, validate and keep its holdout separate."""

from pathlib import Path

import pytest

from rr_eval.datasets import check_holdout_is_separate, load_dataset
from rr_eval.schemas import AdversarialCase, LegalCase, MatchingCase, RoutingCase

DATA = Path(__file__).resolve().parents[3] / "evals" / "data"
MODELS = {
    "matching": MatchingCase,
    "legal": LegalCase,
    "adversarial": AdversarialCase,
    "routing": RoutingCase,
}
MAIN_FILES = sorted(p for p in DATA.glob("*/v*.jsonl") if ".holdout." not in p.name)


@pytest.mark.parametrize("path", MAIN_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_gold_set_file_is_valid(path):
    model = MODELS[path.parent.name]
    main = load_dataset(path, model)
    holdout_path = path.with_name(path.name.replace(".jsonl", ".holdout.jsonl"))
    if holdout_path.is_file():
        check_holdout_is_separate(main, load_dataset(holdout_path, model))


def test_every_set_folder_is_known():
    assert {p.parent.name for p in DATA.glob("*/*.jsonl")} <= set(MODELS)
