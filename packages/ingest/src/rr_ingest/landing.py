"""Write files into the landing zone exactly once."""

from pathlib import Path


def write_once(root: Path, relative_path: str, content: bytes) -> bool:
    """Write a file unless a file with that path already exists.

    Because landing file names contain a content hash, an existing path means the same
    content is already stored.

    Args:
        root: Landing zone root folder.
        relative_path: Path below the root, using ``/`` as separator.
        content: The bytes to write.

    Returns:
        ``True`` if the file was written, ``False`` if it already existed.
    """
    target = root / relative_path
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    temporary.write_bytes(content)
    temporary.replace(target)  # atomic: readers never see a half-written file
    return True
