"""Tests for typed settings per environment (US-003)."""

import pytest
from pydantic import ValidationError
from rr_core.config import Settings, get_settings

FAKE_KEY = "sk-test-not-a-real-key-123"


def test_defaults_load_as_dev() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "dev"
    assert settings.service_name == "api"
    assert settings.log_level == "INFO"


def test_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RR_APP_ENV", "test")
    monkeypatch.setenv("RR_SERVICE_NAME", "worker")
    settings = Settings(_env_file=None)
    assert settings.app_env == "test"
    assert settings.service_name == "worker"


def test_unknown_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RR_APP_ENV", "staging")
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    assert "app_env" in str(excinfo.value)


def test_prod_without_llm_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RR_APP_ENV", "prod")
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    assert "mistral_api_key" in str(excinfo.value)


def test_prod_with_llm_key_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RR_APP_ENV", "prod")
    monkeypatch.setenv("RR_MISTRAL_API_KEY", FAKE_KEY)
    settings = Settings(_env_file=None)
    assert settings.mistral_api_key is not None
    assert settings.mistral_api_key.get_secret_value() == FAKE_KEY


def test_secret_never_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RR_MISTRAL_API_KEY", FAKE_KEY)
    settings = Settings(_env_file=None)
    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings)
    assert FAKE_KEY not in settings.model_dump_json()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
