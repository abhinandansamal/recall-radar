"""Shared fixtures for the rr_core unit tests."""

from collections.abc import Iterator

import pytest
import structlog

from rr_core.config import get_settings


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give every test a clean environment, log context and settings cache."""
    for name in ("RR_APP_ENV", "RR_MISTRAL_API_KEY", "RR_LOG_LEVEL", "RR_SERVICE_NAME"):
        monkeypatch.delenv(name, raising=False)
    structlog.contextvars.clear_contextvars()
    get_settings.cache_clear()
    yield
    structlog.contextvars.clear_contextvars()
    get_settings.cache_clear()
