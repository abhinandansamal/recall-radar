"""GTIN rules. Inputs are real values from the bronze profile (Q5) unless noted."""

import pytest

from rr_transform.gtin import extract_gtins, has_valid_check_digit, to_gtin14


@pytest.mark.parametrize(
    "digits",
    [
        "5054298241091",  # EAN-13 from Report-2026-45
        "4099979071513",  # EAN-13 from Report-2026-45
        "4006381333931",  # EAN-13, GS1 example
        "96385074",  # EAN-8, GS1 example
        "036000291452",  # UPC-A (12)
        "10012345678902",  # GTIN-14
    ],
)
def test_valid_check_digits(digits):
    assert has_valid_check_digit(digits)


@pytest.mark.parametrize("digits", ["5054298241092", "96385075", "123", "1234567890", "abcdefgh"])
def test_invalid_check_digits_or_lengths(digits):
    assert not has_valid_check_digit(digits)


def test_gtin14_pads_with_zeros():
    assert to_gtin14("4006381333931") == "04006381333931"
    assert to_gtin14("96385074") == "00000096385074"


def test_spaces_inside_one_code_are_joined():
    assert extract_gtins("4 006381 333931").gtins == ["04006381333931"]


def test_prefix_characters_are_ignored():
    assert extract_gtins("*4006381333931").gtins == ["04006381333931"]
    assert extract_gtins("'036000291452").gtins == ["00036000291452"]


def test_semicolon_list():
    result = extract_gtins("2000000011967; 2000000012032; 2000000012216")
    assert result.gtins == ["02000000011967", "02000000012032", "02000000012216"]
    assert result.rejected == []


def test_numbered_list():
    result = extract_gtins("1) 4006381333931, 2) 5054298241091")
    assert result.gtins == ["04006381333931", "05054298241091"]
    assert result.rejected == []  # "1" and "2" are numbering, not candidates


def test_labels_between_codes():
    raw = "4 006381 333931  (on the label)5 054298 241091 (on the packaging)"
    assert extract_gtins(raw).gtins == ["04006381333931", "05054298241091"]


def test_glued_codes_are_split_when_every_piece_is_valid():
    glued = "4006381333931" + "5054298241091" + "4099979071513"
    assert extract_gtins(glued).gtins == ["04006381333931", "05054298241091", "04099979071513"]


def test_glued_codes_are_not_guessed_when_one_piece_is_invalid():
    glued = "4006381333931" + "5054298241092"  # second check digit wrong
    result = extract_gtins(glued)
    assert result.gtins == []
    assert [r.reason for r in result.rejected] == ["glued_unsplittable"]


def test_two_codes_separated_by_space_with_other_lengths():
    # 12 + 13 digits: joined (25) is no GTIN, so each run is checked on its own
    result = extract_gtins("036000291452 4006381333931")
    assert result.gtins == ["00036000291452", "04006381333931"]


def test_dash_separated_prefix_is_rejected_alone():
    result = extract_gtins("044\u20134006381333931")  # profile shape: "044\u2013" + 13 digits
    assert result.gtins == ["04006381333931"]
    assert result.rejected == []  # "044" is shorter than a candidate


def test_wrong_check_digit_is_rejected_with_reason():
    result = extract_gtins("5054298241092")
    assert result.gtins == []
    assert [(r.candidate, r.reason) for r in result.rejected] == [("5054298241092", "check_digit")]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("*13765*", "not_gtin_length"),  # profile: 5 digits
        ("0009380002", "not_gtin_length"),  # profile: 10 digits
        ("0000000000000", "placeholder"),
    ],
)
def test_other_rejections(raw, reason):
    result = extract_gtins(raw)
    assert result.gtins == []
    assert [r.reason for r in result.rejected] == [reason]


@pytest.mark.parametrize("raw", [None, "", "-", "n/a", "   "])
def test_empty_or_placeholder_text_gives_nothing(raw):
    result = extract_gtins(raw)
    assert result.gtins == []
    assert result.rejected == []


def test_duplicates_are_removed():
    assert extract_gtins("4006381333931, 4 006381 333931").gtins == ["04006381333931"]


def test_non_latin_text_is_a_separator():
    result = extract_gtins("4006381333931, \u2116 \u041c\u041e0292")  # "No. MO0292" in Cyrillic
    assert result.gtins == ["04006381333931"]
    assert [r.reason for r in result.rejected] == ["not_gtin_length"]
