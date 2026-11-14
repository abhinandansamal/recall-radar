"""Check downloaded photos and give each one a content-addressed path (ADR-0004, D4).

A photo is stored once per SHA-256 of its bytes, so the same photo used by several alerts
(or downloaded twice) takes space once. The file type is decided from the bytes, not from
the server's ``Content-Type`` header (the EC sends ``image/png;charset=UTF-8``).

Only the standard library and Pillow are used, so the module also runs on Databricks.
"""

import hashlib
import io
import warnings
from dataclasses import dataclass

from PIL import Image

MAX_BYTES = 20 * 1024 * 1024  # larger files are not product photos
MAX_PIXELS = 50_000_000  # protects against decompression bombs

# (magic bytes at offset 0, file extension, MIME type)
_SIGNATURES = (
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
)


@dataclass(frozen=True)
class PhotoCheck:
    """Result of checking one downloaded photo.

    Attributes:
        sha256: Hex SHA-256 of the bytes (also for rejected photos, for tracing).
        size_bytes: Number of bytes.
        ext: File extension (``jpg``, ``png``, ``gif``, ``webp``), ``None`` if unknown.
        mime: MIME type from the bytes, ``None`` if unknown.
        width: Width in pixels, ``None`` if not decodable.
        height: Height in pixels, ``None`` if not decodable.
        dhash: 64-bit difference hash as 16 hex digits (near-duplicate detection).
        error: ``None`` if usable; else ``empty``, ``too_large``, ``unknown_type``,
            ``undecodable`` or ``too_many_pixels``.
    """

    sha256: str
    size_bytes: int
    ext: str | None = None
    mime: str | None = None
    width: int | None = None
    height: int | None = None
    dhash: str | None = None
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        """Whether the photo can be stored."""
        return self.error is None

    @property
    def path(self) -> str:
        """Content-addressed path below the images volume: ``sha256/ab/cd/<sha>.<ext>``."""
        return content_path(self.sha256, self.ext or "bin")


def content_path(sha256: str, ext: str) -> str:
    """Build the storage path for a photo.

    Two folder levels (256 x 256) keep folders small even with 330,000 photos.

    Args:
        sha256: Hex SHA-256 of the bytes.
        ext: File extension without dot.

    Returns:
        For example ``sha256/9f/86/9f86…08.png``.
    """
    return f"sha256/{sha256[:2]}/{sha256[2:4]}/{sha256}.{ext}"


def sniff_type(data: bytes) -> tuple[str, str] | None:
    """Detect the image type from the first bytes.

    Args:
        data: The file content.

    Returns:
        ``(extension, mime)`` or ``None`` for anything else (HTML error pages, PDFs …).
    """
    for magic, ext, mime in _SIGNATURES:
        if data.startswith(magic):
            return ext, mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def difference_hash(image: Image.Image) -> str:
    """Compute a 64-bit difference hash (dHash).

    The photo is shrunk to 9 x 8 grey pixels; each bit says whether a pixel is brighter
    than its right neighbour. Re-encoded or resized copies of a photo get the same or a
    very close hash.

    Args:
        image: A decoded image.

    Returns:
        16 hex digits.
    """
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left, right = pixels[row * 9 + col], pixels[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def check_photo(data: bytes, *, max_bytes: int = MAX_BYTES) -> PhotoCheck:
    """Check that downloaded bytes are a usable photo and describe it.

    Args:
        data: The downloaded bytes.
        max_bytes: Upper size limit.

    Returns:
        The check result; ``error`` says why a photo is rejected.
    """
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    if size == 0:
        return PhotoCheck(sha, size, error="empty")
    if size > max_bytes:
        return PhotoCheck(sha, size, error="too_large")
    kind = sniff_type(data)
    if kind is None:
        return PhotoCheck(sha, size, error="unknown_type")
    ext, mime = kind
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                width, height = probe.size
                if width * height > MAX_PIXELS:
                    return PhotoCheck(sha, size, ext, mime, width, height, error="too_many_pixels")
                probe.load()  # decodes the whole file: truncated files fail here
                dhash = difference_hash(probe)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return PhotoCheck(sha, size, ext, mime, error="too_many_pixels")
    except (OSError, ValueError, SyntaxError):
        return PhotoCheck(sha, size, ext, mime, error="undecodable")
    return PhotoCheck(sha, size, ext, mime, width, height, dhash)
