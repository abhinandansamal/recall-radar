"""Building the matching gold set from repeat alerts and safe listings."""

import json
from collections import Counter

import pytest

from rr_eval.matching_builder import (
    AlertRecord,
    SafeListing,
    build_matching_cases,
    is_excluded,
    product_groups,
    product_links,
    same_product,
    split_files,
    split_for,
    spot_check_rows,
    spot_check_sample,
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


def test_groups_hold_linked_alerts_and_drop_singletons():
    groups = product_groups(ALERTS)
    assert groups == [("case:SR/00001/26", ("SR/00001/26", "SR/00002/26", "SR/00003/26"))]


def test_relevant_alerts_are_direct_links_only():
    links = product_links(ALERTS)
    assert links["SR/00002/26"] == {"SR/00001/26", "SR/00003/26"}
    assert links["SR/00001/26"] == {"SR/00002/26"}  # A1-A3 only via A2: no chain


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
    assert all(len(c["relevant"]) >= 1 for c in product_cases)
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


def test_long_model_lists_are_cut_at_a_separator():
    models = ", ".join(f"VD{i:04d}" for i in range(30))  # 178 characters
    long = [alert(c, model=models, brand_models=("sunny|vd0000",)) for c in ("0001/11", "0002/11")]
    exact = build_matching_cases(long, [])[0]
    assert exact["slices"][0] == "exact_key"
    assert len(exact["query"]["model"]) <= 100
    assert exact["query"]["model"].split(", ")[-1] == "VD0011"
    MatchingCase.model_validate(exact)


def test_motor_vehicles_are_left_out():
    cars = [
        alert(f"A12/0{i}00/18", category_en="Motor vehicles", brand_models=("fuso|canter",))
        for i in (1, 2)
    ]
    assert is_excluded(cars[0])
    assert build_matching_cases(cars, []) == []


def test_placeholders_and_dangling_dashes_are_removed():
    odd = [
        alert(
            c,
            title_en="Girls' bikini - Unknown",
            model="BK-77",
            brand_models=("sunny|bk77",),
        )
        for c in ("0001/10", "0002/10")
    ]
    titles = {c["slices"][0]: c["query"]["title"] for c in build_matching_cases(odd, [])}
    assert titles["exact_key"] == "Girls' bikini"
    assert all(not t.endswith(("-", " ")) and "Unknown" not in t for t in titles.values())


def test_spot_check_sample_covers_slices_once_per_product():
    many = [
        alert(f"SR/{i:05d}/26", brand_models=(f"b|m{i // 2:03d}",), image_sha256=(SHA,))
        for i in range(40)
    ]
    safe = [SafeListing(f"B0{i:04d}", f"Safe thing {i}", "en", "Toys") for i in range(10)]
    cases = build_matching_cases(many, safe)
    sample = spot_check_sample(cases)
    assert len(sample) == 30
    assert len({c["source"] for c in sample}) == 30
    assert {c["slices"][0] for c in sample} >= {"exact_key", "evasion", "look_alike"}
    assert sample == spot_check_sample(list(reversed(cases)))


def test_html_entities_are_decoded():
    pair = [
        alert(
            c,
            title_en="Hairspray - Fix &amp; Shine",
            title_de="Haarspray - Fix &amp; Shine",
            brand="Fix &amp; Shine",
            model="FS-1 &amp; FS-2",
        )
        for c in ("SR/00001/25", "SR/00002/25")
    ]
    pair = [AlertRecord(**{**a.__dict__, "brand_models": ("sunny|sc100",)}) for a in pair]
    titles = [c["query"].get("title", "") for c in build_matching_cases(pair, [])]
    assert titles and all("&amp" not in t for t in titles)
    assert "Hairspray - Fix & Shine" in titles
    exact = build_matching_cases(pair, [])[0]["query"]
    assert exact["brand"] == "Fix & Shine" and exact["model"] == "FS-1 & FS-2"


# The Product Owner's spot-check of 23 Nov 2026 (source alert vs relevant alert). The rule
# must reject every pair the PO marked as different. M-0136 and M-0214 were the same product
# but are rejected too: the names share no word (accepted loss; a wrong answer is worse).
PO_PAIRS = [
    (
        "M-0032",
        "Disposable electronic cigarette - 8 ADJUSTABLE FLAVORS, 8in1, 160000 puffs",
        "AiRMEZ",
        "Disposable electronic cigarette - 8 ADJUSTABLE FLAVORS 8in1 160000 PUFFS",
        "AiRMEZ",
        True,
    ),
    (
        "M-0106",
        "Deodorant - Neutro deodorante profumato",
        "Breeze",
        "Deodorant spray - Neutro",
        "Breeze",
        True,
    ),
    ("M-0118", "Fireworks - Colpo", "Bufalo", "Fireworks - Zanzara", "Bufalo", False),
    (
        "M-0136",
        "Skin-lightening product - Crème éclaircissante 3 en 1",
        "Carotone - LIGHT AND NATURAL",
        "Skin lightening product - Light &amp; Natural brightening cream",
        "Carotone",
        False,
    ),
    (
        "M-0214",
        "Tattoo ink - Dynamic Tattoo Ink Grey 30 ml lotto 111224-DP",
        "Dynamic Platinum",
        "Tattoo ink - Platinum",
        "Dynamic",
        False,
    ),
    (
        "M-0231",
        "Perfume - Amethyste",
        "Elementi di Byblos",
        "Cosmetic set - Fiori di Essenza Divina",
        "Renato Balestra",
        False,
    ),
    (
        "M-0280",
        "Shower gel - ACTIV &amp; PURE, značka Fa MEN",
        "Fa MEN",
        "Shower gel - 3i1 shower gel ACTIVE &amp; PURE MEN",
        "Fa MEN",
        True,
    ),
    (
        "M-0339",
        "Fireworks - Burst Blow",
        "Grand Prix",
        "Fireworks - G-Force Glitter",
        "Grand Prix",
        False,
    ),
    (
        "M-0376",
        "USB charger - Smart USB charger",
        "hoco.",
        "USB Charger - Smart USB Charger",
        "hoco.",
        True,
    ),
    (
        "M-0454",
        "Earrings - 3 pairs earrings",
        "Kik",
        "Earrings - 4 pairs of ear studs",
        "Kik",
        False,
    ),
    (
        "M-0476",
        "Disposable electronic cigarette - 5 % NICOTINE, 110000 puffs",
        "LANA JOY TORNADO",
        "Disposable electronic cigarette - 5 % NICOTINE, 120000 puffs, volume: 40 ml",
        "LANA JOY TORNADO",
        False,
    ),
    (
        "M-0511",
        "Face cream - Nourishing Facial Cream with beeswax and vegetable oil",
        "Margarita",
        "Face cream - Moisturising Facial Cream with natural whey",
        "Margarita",
        False,
    ),
    (
        "M-0525",
        "Eau de toilette - VETIVER BOURBON",
        "Monotheme",
        "Aftershave",
        "Sergio Soldano",
        False,
    ),
    (
        "M-0564",
        "Deodorant - Protect &amp; Care",
        "Nivea",
        "Deodorant - Protect care",
        "Nivea",
        True,
    ),
    (
        "M-0675",
        "Shower gel - VIP GLAM ORCHID SCENT",
        "Playboy",
        "Shower gel - PLAYBOY VIP shower gel glam orchid scent",
        "Playboy VIP",
        True,
    ),
    (
        "M-0734",
        "Disposable electronic cigarette - 6in1 140000 PUFFS 2% NICOTINE",
        "RENdM TORNADO",
        "Disposable electronic cigarette - 120000 PUFFS 2% NICOTINE 38ml",
        "RENdM TORNADO",
        False,
    ),
    (
        "M-0849",
        "Hair dye - Palette professional mixing colors",
        "TESTANERA",
        "Hair dye - Palette professional mixing colors 4 - 86 Mix castano agata",
        "TESTANERA",
        True,
    ),
    (
        "M-0870",
        "USB charger - 25W PD Adapter",
        "TREQA",
        "USB charger - TRAVEL ADAPTER, 25W PD Adapter",
        "TREQA",
        True,
    ),
    (
        "M-0925",
        "Hairspray - Fix &amp; Shine",
        "L'OREAL PARIS",
        "Fixing spray - Studio line  Fix &amp; Shine",
        "L'OREAL PARIS",
        True,
    ),
    (
        "M-0971",
        "Lighting chain - 210CM X 210CM LED",
        None,
        "Lighting chain - 210 cm x 210 cm LED",
        None,
        True,
    ),
    ("M-0975", "Lighting chain", None, "Lighting chain - LED", None, True),
    (
        "M-1025",
        "Perfume - Right Starlight",
        "Comin parfum",
        "Eau de toilette - Right Starlight",
        "Comin parfum",
        True,
    ),
    (
        "M-1060",
        "Shower gel - Fresia di Lanzarote",
        "Perlier",
        "Shower gel - Fresia di Lanzarote",
        "Perlier",
        True,
    ),
    (
        "M-1100",
        "Eau de toilette - Blue club",
        "Prady Parfums",
        "Eau de toilette - Blueberry's woman",
        "Prady Parfums",
        False,
    ),
    ("M-1204", "Hair dye - Brown Henna", "Topline", "Hair dye - Brown Henna", "Royal", False),
]


@pytest.mark.parametrize(("case_id", "title_a", "brand_a", "title_b", "brand_b", "same"), PO_PAIRS)
def test_same_product_agrees_with_po_spot_check(case_id, title_a, brand_a, title_b, brand_b, same):
    a = AlertRecord("1/11", title_en=title_a, brand=brand_a)
    b = AlertRecord("2/11", title_en=title_b, brand=brand_b)
    assert same_product(a, b) is same, case_id


def test_keys_on_many_alerts_and_flavour_lists_do_not_link():
    shared_cert = [alert(f"SR/{i:05d}/26", brand_models=("bufalo|0163p15178",)) for i in range(11)]
    assert product_links(shared_cert) == {}
    flavours = tuple(f"vape|flavour{i}" for i in range(4))
    vapes = [alert(c, brand_models=flavours) for c in ("SR/00001/26", "SR/00002/26")]
    assert product_links(vapes) == {}


def test_spot_check_rows_show_both_sides():
    cases = build_matching_cases(ALERTS, SAFE)
    rows = spot_check_rows(spot_check_sample(cases), ALERTS, SAFE)
    match = next(r for r in rows if r["expected"] == "match")
    assert match["source_title"] == "Baby soother holder - Sunny Clip"
    assert match["relevant_title"] == "Baby soother holder - Sunny Clip"
    assert match["relevant_brand"] == "Sunny" and match["ok?"] == ""
    clear = next(r for r in rows if r["expected"] == "clear")
    assert clear["source_title"] in {"Silicone soother clip, pink", "Schnullerkette aus Holz"}
    assert clear["relevant"] == "" and clear["relevant_title"] == ""
