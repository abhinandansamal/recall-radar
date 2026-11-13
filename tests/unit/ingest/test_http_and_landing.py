import httpx
import pytest

from rr_ingest.http import USER_AGENT, fetch, make_client
from rr_ingest.landing import write_once


def client_with(responses):
    """An httpx client that answers with the given responses in order (no network)."""
    calls = []

    def handler(request):
        calls.append(request)
        item = responses[len(calls) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_fetch_returns_body():
    client, _ = client_with([httpx.Response(200, content=b"ok")])

    assert fetch(client, "https://x", sleep=lambda s: None) == b"ok"


def test_fetch_retries_server_errors_with_backoff():
    client, calls = client_with(
        [httpx.Response(503), httpx.Response(500), httpx.Response(200, content=b"ok")]
    )
    waits = []

    assert fetch(client, "https://x", backoff_s=1.0, sleep=waits.append) == b"ok"
    assert len(calls) == 3
    assert waits == [1.0, 2.0]


def test_fetch_retries_network_errors():
    client, calls = client_with([httpx.ConnectError("down"), httpx.Response(200, content=b"ok")])

    assert fetch(client, "https://x", sleep=lambda s: None) == b"ok"
    assert len(calls) == 2


def test_fetch_does_not_retry_404():
    client, calls = client_with([httpx.Response(404)])

    with pytest.raises(httpx.HTTPStatusError):
        fetch(client, "https://x", sleep=lambda s: None)
    assert len(calls) == 1


def test_fetch_gives_up_after_last_attempt():
    client, calls = client_with([httpx.Response(503)] * 3)

    with pytest.raises(httpx.HTTPStatusError):
        fetch(client, "https://x", attempts=3, sleep=lambda s: None)
    assert len(calls) == 3


def test_fetch_gives_up_on_repeated_network_errors():
    client, _ = client_with([httpx.ConnectError("down")] * 2)

    with pytest.raises(httpx.ConnectError):
        fetch(client, "https://x", attempts=2, sleep=lambda s: None)


def test_client_identifies_the_project():
    with make_client() as client:
        assert client.headers["User-Agent"] == USER_AGENT


def test_write_once_writes_then_skips(tmp_path):
    assert write_once(tmp_path, "a/b/file.xml", b"one") is True
    assert write_once(tmp_path, "a/b/file.xml", b"two") is False

    assert (tmp_path / "a/b/file.xml").read_bytes() == b"one"
    assert not list(tmp_path.rglob("*.part"))
