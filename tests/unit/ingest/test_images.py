"""Photo checks and content-addressed paths (US-011)."""

import hashlib
import io

import pytest
from PIL import Image

from rr_ingest.images import check_photo, content_path, difference_hash, sniff_type


def _photo(fmt: str, size: tuple[int, int] = (64, 48), stripes: bool = False) -> bytes:
    image = Image.new("RGB", size, (200, 30, 30))
    if stripes:
        for x in range(0, size[0], 8):
            for y in range(size[1]):
                image.putpixel((x, y), (255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("fmt", "ext", "mime"),
    [
        ("PNG", "png", "image/png"),
        ("JPEG", "jpg", "image/jpeg"),
        ("GIF", "gif", "image/gif"),
        ("WEBP", "webp", "image/webp"),
    ],
)
def test_valid_photos(fmt, ext, mime):
    data = _photo(fmt)
    result = check_photo(data)
    assert result.is_valid
    assert (result.ext, result.mime) == (ext, mime)
    assert (result.width, result.height) == (64, 48)
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert result.size_bytes == len(data)
    assert len(result.dhash or "") == 16
    assert result.path == content_path(result.sha256, ext)


def test_content_path_has_two_folder_levels():
    sha = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert content_path(sha, "png") == f"sha256/9f/86/{sha}.png"


def test_type_comes_from_bytes_not_header():
    assert sniff_type(b"<!DOCTYPE html><html>error</html>") is None
    assert sniff_type(b"%PDF-1.7") is None


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"", "empty"),
        (b"<html>Service unavailable</html>", "unknown_type"),
        (b"\x89PNG\r\n\x1a\n" + b"garbage" * 10, "undecodable"),
    ],
)
def test_rejected_photos(data, error):
    result = check_photo(data)
    assert not result.is_valid
    assert result.error == error
    assert result.sha256 == hashlib.sha256(data).hexdigest()


def test_truncated_photo_is_undecodable():
    data = _photo("JPEG", (200, 200), stripes=True)
    assert check_photo(data[: len(data) // 2]).error == "undecodable"


def test_too_large():
    assert check_photo(_photo("PNG"), max_bytes=10).error == "too_large"


def test_too_many_pixels(monkeypatch):
    monkeypatch.setattr("rr_ingest.images.MAX_PIXELS", 100)
    result = check_photo(_photo("PNG"))
    assert result.error == "too_many_pixels"
    assert (result.width, result.height) == (64, 48)


def test_dhash_survives_reencoding_and_separates_different_photos():
    png = Image.open(io.BytesIO(_photo("PNG", (128, 96), stripes=True)))
    jpg = Image.open(io.BytesIO(_photo("JPEG", (128, 96), stripes=True)))
    plain = Image.open(io.BytesIO(_photo("PNG", (128, 96))))
    assert difference_hash(png) == difference_hash(jpg)
    assert difference_hash(png) != difference_hash(plain)
