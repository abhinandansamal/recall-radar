"""Case number, date, level, pictures and key rules. Inputs come from the bronze profile."""

from datetime import date

import pytest

from rr_transform.keys import model_keys, normalise_key
from rr_transform.sg_alert import clean_sg_alert
from rr_transform.sg_fields import (
    clean_case_number,
    parse_pictures,
    parse_publication_date,
    risk_level_code,
)

TODAY = date(2026, 11, 14)


@pytest.mark.parametrize(
    "raw",
    [
        "A11/0001/14",
        "A11/00001/20",
        "0001/05",
        "SR/00001/25",
        "INFO/00001/19",
        "OR/00001/25",
        "INFO/0031/19",
        "197/05",
        "EM/00001/22",
        "EM/0002/14",
    ],
)
def test_all_ten_known_case_formats_are_valid(raw):
    assert clean_case_number(raw).value == raw


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1150/09<br></br>", "1150/09"), ("0806/10.", "0806/10"), ("  SR/03208/26 ", "SR/03208/26")],
)
def test_repairable_case_numbers(raw, expected):
    assert clean_case_number(raw).value == expected


@pytest.mark.parametrize("raw", ["0522/081", "0350/05 \u2013 0352/05", "0559.11", "49 0357/10"])
def test_malformed_case_numbers_are_rejected(raw):
    checked = clean_case_number(raw)
    assert checked.value is None
    assert checked.error == "case_number_format"


@pytest.mark.parametrize("raw", [None, "", "<br>"])
def test_missing_case_number(raw):
    assert clean_case_number(raw).error == "case_number_missing"


def test_date_is_parsed():
    assert parse_publication_date("10-11-2026", TODAY).value == date(2026, 11, 10)


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        (None, "publication_date_missing"),
        ("", "publication_date_missing"),
        ("10/11/2026", "publication_date_invalid"),
        ("31-02-2026", "publication_date_invalid"),
        ("16-11-2026", "publication_date_future"),
    ],
)
def test_bad_dates(raw, error):
    checked = parse_publication_date(raw, TODAY)
    assert checked.value is None
    assert checked.error == error


def test_tomorrow_is_tolerated():
    assert parse_publication_date("15-11-2026", TODAY).value == date(2026, 11, 15)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("Serious risk", "serious"),
        ("Ernstes Risiko", "serious"),
        ("Other risk levels", "other_risk"),
        ("Sonstige Risikoniveaus", "other_risk"),
        ("Other types of alerts", "other_alert"),
        ("Sonstige Warnungen", "other_alert"),
        ("  serious   RISK ", "serious"),
        ("Something new", "unknown"),
        (None, "unknown"),
    ],
)
def test_risk_levels(raw, code):
    assert risk_level_code(raw) == code


def test_pictures_from_profile_q8():
    raw = (
        "<picture>https://ec.europa.eu/safety-gate-alerts/public/api/notification/image/385875"
        "</picture> <picture>https://ec.europa.eu/safety-gate-alerts/public/api/notification/"
        "image/385876</picture>"
    )
    assert parse_pictures(raw) == [
        "https://ec.europa.eu/safety-gate-alerts/public/api/notification/image/385875",
        "https://ec.europa.eu/safety-gate-alerts/public/api/notification/image/385876",
    ]


def test_pictures_with_cdata_duplicates_and_junk():
    raw = (
        "<picture><![CDATA[https://x.eu/1]]></picture><picture>https://x.eu/1</picture>"
        "<picture>not a url</picture><picture></picture>"
    )
    assert parse_pictures(raw) == ["https://x.eu/1"]


@pytest.mark.parametrize("raw", [None, "", "<pictures/>"])
def test_no_pictures(raw):
    assert parse_pictures(raw) == []


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("EP-TA200", "epta200"),
        (" Samsung ", "samsung"),
        ("Jojo Maman Bébé", "jojomamanbebe"),
        ("Straße", "strasse"),
        ("s.Oliver", "soliver"),
        ("Unknown", None),
        ("unbekannt", None),
        ("No brand", None),
        ("-", None),
        ("n/a", None),
        (None, None),
    ],
)
def test_normalise_key(raw, key):
    assert normalise_key(raw) == key


def test_model_keys_split_on_commas_only():
    assert model_keys("10.2.17.25.271, 2175334.5906.ONE SIZE") == [
        "1021725271",
        "21753345906onesize",
    ]


def test_model_keys_drop_short_placeholder_and_duplicate_values():
    assert model_keys("A1; unknown; EP-TA200\nep ta200") == ["epta200"]


def test_clean_alert_valid_with_bad_barcode_keeps_the_alert():
    alert = clean_sg_alert(
        case_number="SR/03208/26",
        publication_date="10-11-2026",
        level="Serious risk",
        brand="Jojo Maman Bébé",
        model="C52-683-145-000161",
        barcode="5054298241091, 5054298241092",
        pictures="<picture>https://x.eu/1</picture>",
        today=TODAY,
    )
    assert alert.is_valid
    row = alert.as_row()
    assert row["case_number"] == "SR/03208/26"
    assert row["publication_date"] == date(2026, 11, 10)
    assert row["risk_level"] == "serious"
    assert row["brand_key"] == "jojomamanbebe"
    assert row["model_keys"] == ["c52683145000161"]
    assert row["gtins"] == ["05054298241091"]
    assert row["rejected_gtins"] == [{"candidate": "5054298241092", "reason": "check_digit"}]
    assert row["picture_urls"] == ["https://x.eu/1"]
    assert row["errors"] == []


def test_clean_alert_collects_alert_level_errors():
    alert = clean_sg_alert(
        case_number="0559.11",
        publication_date="",
        level=None,
        brand=None,
        model=None,
        barcode=None,
        pictures=None,
        today=TODAY,
    )
    assert not alert.is_valid
    assert alert.errors == ["case_number_format", "publication_date_missing"]
    assert alert.risk_level == "unknown"
