"""ABO bucket listing, download checks and category proposals (US-008)."""

import gzip

import pytest

from rr_ingest.abo import (
    S3Object,
    download_error,
    landing_path,
    listing_url,
    parse_bucket_listing,
    propose_category,
)

LISTING = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>amazon-berkeley-objects</Name><Prefix>listings/metadata/</Prefix>
  <KeyCount>3</KeyCount><MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>
  <Contents><Key>listings/metadata/listings_1.json.gz</Key><ETag>"bb"</ETag><Size>5350124</Size></Contents>
  <Contents><Key>listings/metadata/listings_0.json.gz</Key><ETag>"aa"</ETag><Size>5446000</Size></Contents>
  <Contents><Key>listings/metadata/</Key><ETag>"cc"</ETag><Size>0</Size></Contents>
</ListBucketResult>"""

SG = [
    "Toys",
    "Jewellery",
    "Lighting equipment",
    "Electrical appliances and equipment",
    "Cosmetics",
    "Childcare articles and children's equipment",
    "Clothing, textiles and fashion items",
]


def test_listing_is_parsed_sorted_and_without_folder_marker():
    objects = parse_bucket_listing(LISTING)
    assert objects == [
        S3Object("listings/metadata/listings_0.json.gz", 5446000, "aa"),
        S3Object("listings/metadata/listings_1.json.gz", 5350124, "bb"),
    ]


def test_truncated_listing_is_refused():
    with pytest.raises(ValueError, match="truncated"):
        parse_bucket_listing(LISTING.replace(b"<IsTruncated>false", b"<IsTruncated>true"))


def test_listing_url():
    assert listing_url("images/metadata/").endswith("?list-type=2&prefix=images/metadata/")


def test_download_checks():
    data = gzip.compress(b'{"item_id": "B000"}\n')
    expected = S3Object("listings/metadata/listings_0.json.gz", len(data), "aa")
    assert download_error(data, expected) is None
    assert download_error(data[:-1], expected) == "size_mismatch"
    html = b"<html>" + b"x" * (len(data) - 6)
    assert download_error(html, expected) == "not_gzip"


def test_landing_path_keeps_the_bucket_path():
    assert landing_path("images/metadata/images.csv.gz") == "abo/images/metadata/images.csv.gz"


@pytest.mark.parametrize(
    ("product_type", "category"),
    [
        ("RING", "Jewellery"),
        ("EARRING", "Jewellery"),
        ("LIGHT_BULB", "Lighting equipment"),
        ("LAMP", "Lighting equipment"),
        ("ELECTRONIC_ADAPTER", "Electrical appliances and equipment"),
        ("BATTERY", "Electrical appliances and equipment"),
        ("SKIN_CLEANING_AGENT", "Cosmetics"),
        ("BABY_PRODUCT", "Childcare articles and children's equipment"),
        ("SHOES", "Clothing, textiles and fashion items"),
        ("light_bulb", "Lighting equipment"),
    ],
)
def test_proposals(product_type, category):
    assert propose_category(product_type, SG) == category


@pytest.mark.parametrize("product_type", ["GROCERY", "PET_SUPPLIES", "", None])
def test_no_proposal(product_type):
    assert propose_category(product_type, SG) is None


def test_whole_words_only():
    assert propose_category("INFANT_CAR_SEAT", SG).startswith("Childcare")  # not "FAN"
    assert propose_category("SPRING_MATTRESS", SG) is None  # "RING" is only part of a word
    assert propose_category("BABY_LAMP", SG).startswith("Childcare")  # first rule wins


def test_rule_matches_but_category_absent_in_safety_gate():
    assert propose_category("YOGA_MAT", SG) is None  # "Sports" is not in this list
