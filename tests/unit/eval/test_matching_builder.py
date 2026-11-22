"""Building the matching gold set from repeat alerts and safe listings."""

import json
from collections import Counter

from rr_eval.matching_builder import (
    AlertRecord,
    SafeListing,
    build_matching_cases,
    product_groups,
    split_files,
    split_for,
)
from rr_eval.schemas import MatchingCase

SHA = "a" * 64


def alert(case_number, **kw):
    defaults = {
        "title_en": "Baby soother holder - Sunny Clip",
        "title_de": "Schnullerhalter - Sunny Clip",
        "description_en": "Plastic soother holder with a metal clip. Brand Sunny, model SC-100.",
        "description_de": "Schnullerhalter aus Kunststoff mit Metallclip.",
        "category_en": "Childcare articles and children's equipment",
        "brand": "Sunny",
        "model": "SC-100",
    }
    defaults.update(kw)
    return AlertRecord(case_number=case_number, **defaults)


ALERTS = [
    # one product, joined by a shared GTIN (A1-A2) and a shared brand + model (A2-A3)
    alert("SR/00001/26", gtins=("04006381333931",), image_sha256=(SHA,)),
    alert("SR/00002/26", gtins=("04006381333931",), brand_models=("sunny|sc100",)),
    alert("SR/00003/26", brand_models=("sunny|sc100",), image_sha256=("b" * 64,)),
    # a single alert: not a repeat, so no case
    alert("SR/00004/26", brand="Other", model="ZZ-9", brand_models=("other|zz9",)),
]
SAFE = [
    SafeListing("B07ABC", "Silicone soother clip, pink", "en", "Childcare articles", "Acme"),
    SafeListing("B07DEF", "Schnullerkette aus Holz", "de", "Childcare articles"),
]


def test_groups_join_transitively_and_drop_singletons():
    groups = product_groups(ALERTS)
    assert groups == [("bm:sunny|sc100", ("SR/00001/26", "SR/00002/26", "SR/00003/26"))]


def test_split_is_stable_and_roughly_60_30_10():
    assert split_for("gtin:1") == split_for("gtin:1")
    counts = Counter(split_for(f"gtin:{i}") for i in range(3000))
    assert 0.55 < counts["dev"] / 3000 < 0.65
    assert 0.25 < counts["test"] / 3000 < 0.35
    assert 0.07 < counts["holdout"] / 3000 < 0.13


def test_every_built_case_is_a_valid_gold_case():
    cases = build_matching_cases(ALERTS, SAFE)
    models = [MatchingCase.model_validate(c) for c in cases]
    assert [m.case_id for m in models] == [f"M-{i:04d}" for i in range(1, len(models) + 1)]
    variants = Counter(m.slices[0] for m in models)
    assert variants == {
        "exact_key": 1,
        "no_identifier": 1,
        "cross_language": 1,
        "image_only": 1,
        "evasion": 1,
        "look_alike": 2,
    }


def test_leave_one_out_and_one_split_per_product():
    product_cases = [c for c in build_matching_cases(ALERTS, SAFE) if c["expected"] == "match"]
    (source,) = {c["exclude_ids"][0] for c in product_cases}
    assert all(source not in c["relevant"] for c in product_cases)
    assert all(len(c["relevant"]) == 2 for c in product_cases)
    assert len({c["split"] for c in product_cases}) == 1


def test_variants_hide_what_they_should():
    cases = {c["slices"][0]: c for c in build_matching_cases(ALERTS, SAFE)}
    exact = cases["exact_key"]["query"]
    assert exact["brand"] == "Sunny" and exact["model"] == "SC-100"
    if "gtin" in exact:  # only a barcode another alert shares, shown as EAN-13
        assert exact["gtin"] == "4006381333931"
    for name in ("no_identifier", "cross_language", "evasion"):
        query = cases[name]["query"]
        text = (query["title"] + query.get("description", "")).lower()
        assert "sunny" not in text and "sc-100" not in text
        assert "brand" not in query and "gtin" not in query
    assert (
        cases["no_identifier"]["query"]["description"]
        == "Plastic soother holder with a metal clip."
    )
    assert cases["cross_language"]["query"]["language"] == "de"
    assert cases["evasion"]["query"]["model"] != "SC-100"
    photo = cases["image_only"]["query"]
    assert photo["image_sha256"] and "title" not in photo


def test_look_alikes_are_clear_and_attributed():
    looks = [c for c in build_matching_cases(ALERTS, SAFE) if c["slices"] == ["look_alike"]]
    assert {c["source"] for c in looks} == {"abo:B07ABC", "abo:B07DEF"}
    assert all(c["expected"] == "clear" and c["relevant"] == {} for c in looks)
    assert build_matching_cases(ALERTS, SAFE, max_look_alikes=1)[-1]["slices"] == ["look_alike"]


def test_output_is_deterministic_and_limits_apply():
    assert build_matching_cases(ALERTS, SAFE) == build_matching_cases(list(reversed(ALERTS)), SAFE)
    only_safe = build_matching_cases(ALERTS, SAFE, max_groups=0)
    assert all(c["expected"] == "clear" for c in only_safe)


def test_missing_texts_skip_variants():
    bare = [
        AlertRecord("SR/00010/26", gtins=("00000000000017",)),
        AlertRecord("SR/00011/26", gtins=("00000000000017",)),
    ]
    assert build_matching_cases(bare, []) == []  # a listing without any text is not realistic
    titled = [AlertRecord(c.case_number, title_en="Lamp", gtins=c.gtins) for c in bare]
    cases = build_matching_cases(titled, [])
    assert [c["slices"][0] for c in cases] == ["exact_key", "no_identifier", "evasion"]
    assert cases[0]["query"]["gtin"] == "0000000000017"
    for case in cases:
        MatchingCase.model_validate(case)


def test_files_separate_holdout():
    cases = build_matching_cases(ALERTS, SAFE)
    main, holdout = split_files(cases)
    main_rows = [json.loads(line) for line in main.splitlines()]
    holdout_rows = [json.loads(line) for line in holdout.splitlines()]
    assert len(main_rows) + len(holdout_rows) == len(cases)
    assert all(r["split"] != "holdout" for r in main_rows)
    assert all(r["split"] == "holdout" for r in holdout_rows)
