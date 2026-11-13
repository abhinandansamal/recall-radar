"""Polite HTTP downloads with timeouts and retries."""

import time
from collections.abc import Callable, Mapping

import httpx

USER_AGENT = "recall-radar/0.1 (+https://github.com/abhinandansamal/recall-radar)"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def make_client(timeout_s: float = 30.0) -> httpx.Client:
    """Create an HTTP client that identifies the project and follows redirects."""
    return httpx.Client(
        timeout=timeout_s, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )


def fetch(
    client: httpx.Client,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    attempts: int = 3,
    backoff_s: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Download a URL, retrying network errors and temporary server errors.

    Retries wait ``backoff_s``, then twice as long, and so on. Client errors such as 404
    are not retried, because repeating the request cannot fix them.

    Args:
        client: The HTTP client.
        url: The URL to download.
        headers: Extra request headers, for example ``Accept`` for content negotiation.
        attempts: Total number of tries.
        backoff_s: Wait before the first retry, in seconds.
        sleep: Wait function (replaced in tests).

    Returns:
        The response body.

    Raises:
        httpx.HTTPError: When the last attempt fails or the error cannot be retried.
    """
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRY_STATUS or attempt == attempts:
                raise
        except httpx.TransportError:
            if attempt == attempts:
                raise
        sleep(backoff_s * 2 ** (attempt - 1))
    raise AssertionError("unreachable")  # pragma: no cover
