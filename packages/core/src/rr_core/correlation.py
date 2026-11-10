"""Correlation IDs: one ID that follows a request through every log line.

The ID is stored in the structlog context, which is built on Python's
``contextvars``. Each asyncio task therefore keeps its own ID, even when many
requests are handled at the same time.
"""

import uuid
from collections.abc import Generator
from contextlib import contextmanager

import structlog

_KEY = "correlation_id"


def new_correlation_id() -> str:
    """Create a new random correlation ID.

    Returns:
        A 32-character hexadecimal string.
    """
    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    """Return the correlation ID of the current context.

    Returns:
        The bound ID, or ``None`` if no ID is bound.
    """
    value = structlog.contextvars.get_contextvars().get(_KEY)
    return value if isinstance(value, str) else None


def bind_correlation_id(cid: str | None = None) -> str:
    """Bind a correlation ID to the current context.

    Args:
        cid: The ID to bind, for example from an incoming request header.
            A new ID is created when it is ``None``.

    Returns:
        The bound ID.
    """
    value = cid or new_correlation_id()
    structlog.contextvars.bind_contextvars(**{_KEY: value})
    return value


@contextmanager
def correlation_scope(cid: str | None = None) -> Generator[str, None, None]:
    """Bind a correlation ID for a block of code, then restore the previous state.

    Args:
        cid: The ID to bind. A new ID is created when it is ``None``.

    Yields:
        The ID that is bound inside the block.
    """
    value = cid or new_correlation_id()
    tokens = structlog.contextvars.bind_contextvars(**{_KEY: value})
    try:
        yield value
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
