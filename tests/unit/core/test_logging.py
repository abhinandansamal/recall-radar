"""Tests for JSON logging with redaction (US-002)."""

import io
import json
from typing import Any

from rr_core.logging import REDACTED, configure_logging, get_logger

from rr_core.config import Settings
from rr_core.correlation import correlation_scope


def _setup(log_level: str = "INFO") -> io.StringIO:
    stream = io.StringIO()
    settings = Settings(_env_file=None, app_env="test", service_name="unit", log_level=log_level)
    configure_logging(settings, stream=stream)
    return stream


def _lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_writes_one_json_line_with_required_fields() -> None:
    stream = _setup()
    with correlation_scope("cid-1"):
        get_logger().info("listing_checked", listing_id="L01")
    [line] = _lines(stream)
    assert line["event"] == "listing_checked"
    assert line["level"] == "info"
    assert line["env"] == "test"
    assert line["service"] == "unit"
    assert line["correlation_id"] == "cid-1"
    assert line["listing_id"] == "L01"
    assert "timestamp" in line


def test_timestamp_is_utc_iso8601() -> None:
    stream = _setup()
    get_logger().info("tick")
    [line] = _lines(stream)
    assert line["timestamp"].endswith(("Z", "+00:00"))


def test_correlation_id_is_null_when_not_bound() -> None:
    stream = _setup()
    get_logger().info("no_request")
    [line] = _lines(stream)
    assert line["correlation_id"] is None


def test_sensitive_values_are_redacted() -> None:
    stream = _setup()
    get_logger().info(
        "login",
        api_key="secret-1",
        Password="secret-2",  # noqa: S106 (fake value to test redaction)
        authorization="Bearer secret-3",
        email="person@example.com",
        nested={"token": "secret-4", "safe": "visible"},
    )
    output = stream.getvalue()
    for value in ("secret-1", "secret-2", "secret-3", "person@example.com", "secret-4"):
        assert value not in output
    [line] = _lines(stream)
    assert line["api_key"] == REDACTED
    assert line["nested"]["safe"] == "visible"


def test_debug_is_hidden_at_info_level() -> None:
    stream = _setup("INFO")
    get_logger().debug("too_detailed")
    assert stream.getvalue() == ""


def test_debug_is_written_at_debug_level() -> None:
    stream = _setup("DEBUG")
    get_logger().debug("detail")
    assert _lines(stream)[0]["event"] == "detail"
