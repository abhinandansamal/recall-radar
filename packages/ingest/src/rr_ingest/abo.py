"""Amazon Berkeley Objects (ABO): the marketplace-catalogue side of Recall Radar (US-008).

ABO is a static public dataset on S3 (no account needed). We copy the listing metadata and the
image metadata unchanged into the landing volume, then select the product types that overlap
with Safety Gate categories (see ``docs/data/data-sources.md``, section 2).

This module holds the pure parts: bucket listing, download checks, landing paths, licence and
the keyword rules that *propose* a Safety Gate category for an ABO product type. The final
mapping is a Product Owner decision, committed as ``pipelines/reference/abo_category_map.csv``.
"""

from dataclasses import dataclass

from defusedxml import ElementTree

BUCKET_URL = "https://amazon-berkeley-objects.s3.amazonaws.com"
LISTINGS_PREFIX = "listings/metadata/"
IMAGES_PREFIX = "images/metadata/"

LICENCE = (
    "Amazon Berkeley Objects (Collins et al., CVPR 2022), CC BY 4.0 per bucket README and "
    "LICENSE-CC-BY-4.0.txt (2023 relicense); the AWS registry still states CC BY-NC 4.0. "
    "Used non-commercially with attribution."
)

_GZIP_MAGIC = b"\x1f\x8b"


@dataclass(frozen=True)
class S3Object:
    """One file in the public bucket.

    Attributes:
        key: Path in the bucket, e.g. ``listings/metadata/listings_0.json.gz``.
        size: Size in bytes, used to check the download.
        etag: S3 entity tag (content fingerprint), stored for lineage.
    """

    key: str
    size: int
    etag: str


def listing_url(prefix: str) -> str:
    """URL of the public S3 listing (ListObjectsV2) for a prefix."""
    return f"{BUCKET_URL}/?list-type=2&prefix={prefix}"


def parse_bucket_listing(xml: bytes) -> list[S3Object]:
    """Read an S3 ListObjectsV2 response.

    Args:
        xml: The response body.

    Returns:
        The objects, sorted by key; folder markers (keys ending in ``/``) are skipped.

    Raises:
        ValueError: If the listing is truncated (more than one page), which would mean
            files are missing; ABO has 17 metadata files, far below the 1,000 per page.
    """
    root = ElementTree.fromstring(xml)
    if (root.findtext("{*}IsTruncated") or "false").lower() == "true":
        raise ValueError("bucket listing is truncated: files would be missing")
    objects = [
        S3Object(
            key=item.findtext("{*}Key") or "",
            size=int(item.findtext("{*}Size") or 0),
            etag=(item.findtext("{*}ETag") or "").strip('"'),
        )
        for item in root.iterfind("{*}Contents")
    ]
    return sorted((o for o in objects if o.key and not o.key.endswith("/")), key=lambda o: o.key)


def download_error(data: bytes, expected: S3Object) -> str | None:
    """Check a downloaded metadata file before it is stored.

    Args:
        data: The downloaded bytes.
        expected: The object from the bucket listing.

    Returns:
        ``None`` if the file is complete; otherwise ``size_mismatch`` or ``not_gzip``.
    """
    if len(data) != expected.size:
        return "size_mismatch"
    if not data.startswith(_GZIP_MAGIC):
        return "not_gzip"
    return None


def landing_path(key: str) -> str:
    """Path below the landing volume: the bucket path, unchanged, under ``abo/``."""
    return f"abo/{key}"


# Keyword rules for the *proposal* only, matched against whole words of the product type
# ("LIGHT_BULB" -> {"LIGHT", "BULB"}), so "FAN" never matches "INFANT". First match wins.
# Second element: a word that appears in the Safety Gate category name (English).
PROPOSAL_RULES: tuple[tuple[frozenset[str], str], ...] = (
    (
        frozenset(
            {
                "RING",
                "EARRING",
                "NECKLACE",
                "BRACELET",
                "PENDANT",
                "JEWELRY",
                "ANKLET",
                "BROOCH",
                "CHARM",
            }
        ),
        "Jewellery",
    ),
    (
        frozenset({"BABY", "INFANT", "TODDLER", "NURSERY", "CRIB", "STROLLER", "PACIFIER"}),
        "Childcare",
    ),
    (frozenset({"TOY", "TOYS", "GAME", "GAMES", "PUZZLE", "DOLL"}), "Toys"),
    (
        frozenset(
            {"LIGHT", "LIGHTING", "LAMP", "BULB", "LANTERN", "FLASHLIGHT", "CHANDELIER", "SCONCE"}
        ),
        "Lighting",
    ),
    (
        frozenset(
            {
                "ADAPTER",
                "CHARGER",
                "CABLE",
                "BATTERY",
                "POWER",
                "FAN",
                "HEATER",
                "KETTLE",
                "TOASTER",
                "BLENDER",
                "MIXER",
                "VACUUM",
                "IRON",
                "DRYER",
                "SHAVER",
                "ELECTRONIC",
                "ELECTRIC",
                "APPLIANCE",
                "SPEAKER",
                "HEADPHONES",
                "PLUG",
                "OUTLET",
            }
        ),
        "Electrical",
    ),
    (
        frozenset(
            {
                "SKIN",
                "BEAUTY",
                "COSMETIC",
                "MAKEUP",
                "LOTION",
                "SHAMPOO",
                "HAIR",
                "NAIL",
                "FRAGRANCE",
                "SUNSCREEN",
            }
        ),
        "Cosmetics",
    ),
    (
        frozenset(
            {"SPORT", "SPORTING", "FITNESS", "EXERCISE", "YOGA", "BICYCLE", "HELMET", "CAMPING"}
        ),
        "Sport",
    ),
    (frozenset({"KITCHEN", "COOKWARE", "BAKEWARE", "CUP", "BOTTLE", "UTENSIL"}), "Kitchen"),
    (
        frozenset(
            {
                "CHAIR",
                "SOFA",
                "TABLE",
                "DESK",
                "BED",
                "SHELF",
                "CABINET",
                "DRESSER",
                "FURNITURE",
                "STOOL",
                "BENCH",
            }
        ),
        "Furniture",
    ),
    (
        frozenset(
            {
                "SHOES",
                "BOOT",
                "SANDAL",
                "SHIRT",
                "DRESS",
                "PANTS",
                "JACKET",
                "COAT",
                "HAT",
                "SOCKS",
                "APPAREL",
                "CLOTHING",
            }
        ),
        "Clothing",
    ),
)


def propose_category(product_type: str | None, sg_categories: list[str]) -> str | None:
    """Propose the Safety Gate category for an ABO product type.

    Args:
        product_type: ABO ``product_type`` value, e.g. ``"LIGHT_BULB"``.
        sg_categories: Safety Gate category names (English) present in silver.

    Returns:
        The first Safety Gate category whose name contains the keyword of the first matching
        rule, or ``None`` if no rule matches (the product type is not proposed).
    """
    words = set((product_type or "").upper().split("_"))
    for keywords, word in PROPOSAL_RULES:
        if words & keywords:
            return next((c for c in sorted(sg_categories) if word.lower() in c.lower()), None)
    return None
