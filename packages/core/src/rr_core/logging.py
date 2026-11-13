"""Structured JSON logging for every Recall Radar service.

Every log line is one JSON object with a UTC timestamp, the log level, the
event name, the environment, the service name and the correlation ID.
Values of sensitive fields (keys, passwords, e-mail addresses) are replaced
before the line is written.
"""

import logging
import sys
from collections.abc import Mapping
from typing import TextIO, cast

import structlog
from structlog.typing import EventDict, FilteringBoundLogger, WrappedLogger

from rr_core.config import Settings

REDACTED = "***REDACTED***"

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"api_key", "password", "authorization", "email", "token", "secret"}
)


def _is_sensitive(key: str) -> bool:
    """Check whether a field name must be redacted.

    Args:
        key: The field name, in any letter case.

    Returns:
        ``True`` if the lower-case key is in ``SENSITIVE_KEYS``.
    """
    return key.lower() in SENSITIVE_KEYS


def _redact_value(value: object) -> object:
    """Redact sensitive keys inside nested dictionaries.

    Args:
        value: Any logged value.

    Returns:
        The value, with sensitive entries of nested mappings replaced.
    """
    if isinstance(value, Mapping):
        return {
            k: REDACTED if _is_sensitive(str(k)) else _redact_value(v) for k, v in value.items()
        }
    return value


def redact_sensitive(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor that hides sensitive values.

    Args:
        logger: The wrapped logger (unused, required by structlog).
        method_name: The log method name (unused, required by structlog).
        event_dict: The log event being built.

    Returns:
        The event with sensitive values replaced by ``REDACTED``.
    """
    for key in list(event_dict):
        event_dict[key] = REDACTED if _is_sensitive(key) else _redact_value(event_dict[key])
    return event_dict


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Configure structlog to write JSON lines.

    Call this once at service startup.

    Args:
        settings: Provides environment, service name and log level.
        stream: Where to write. Defaults to standard output; tests pass a
            ``StringIO``.
    """

    def add_service_fields(
        logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        event_dict.setdefault("env", settings.app_env)
        event_dict.setdefault("service", settings.service_name)
        event_dict.setdefault("correlation_id", None)
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            add_service_fields,
            redact_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """Return a structured logger.

    Args:
        name: Optional logger name, added to each line as ``logger_name``.

    Returns:
        A structlog bound logger.
    """
    # Initial values keep the logger lazy: the configuration is looked up at the first log
    # call, so module-level loggers created before configure_logging() still write JSON.
    # (Calling .bind() here would build the logger immediately with the default config.)
    initial = {"logger_name": name} if name else {}
    return cast(FilteringBoundLogger, structlog.get_logger(**initial))
