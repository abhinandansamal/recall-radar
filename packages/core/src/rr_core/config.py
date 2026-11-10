"""Typed, validated settings for every Recall Radar service.

Values come from environment variables with the prefix ``RR_`` (for example
``RR_APP_ENV=prod``) or from a local ``.env`` file. A wrong value stops the
service at startup instead of failing later in production.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings of a service.

    Attributes:
        app_env: Deployment environment: ``dev``, ``test`` or ``prod``.
        service_name: Name of the running service, written into every log line.
        log_level: Lowest log level that is written.
        mistral_api_key: API key for the LLM provider. Required in ``prod``.
        postgres_host: Database host name.
        postgres_port: Database port.
        postgres_db: Database name.
        postgres_user: Database user.
        postgres_password: Database password.
        redis_url: Connection URL of the Redis cache and queue.
    """

    model_config = SettingsConfigDict(
        env_prefix="RR_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    service_name: str = "api"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    mistral_api_key: SecretStr | None = None

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "rr_dev"
    postgres_user: str = "rr_app"
    postgres_password: SecretStr | None = None

    redis_url: str = "redis://localhost:6379/0"

    @model_validator(mode="after")
    def _require_secrets_in_prod(self) -> Self:
        """Fail fast when production runs without the secrets it needs.

        Returns:
            The validated settings.

        Raises:
            ValueError: If ``app_env`` is ``prod`` and ``mistral_api_key`` is missing.
        """
        if self.app_env == "prod" and self.mistral_api_key is None:
            raise ValueError("mistral_api_key is required when app_env is 'prod'")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the settings, loaded once per process.

    Returns:
        The cached ``Settings`` instance.
    """
    return Settings()
