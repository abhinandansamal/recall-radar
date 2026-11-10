# ADR-0002: Settings with pydantic-settings, logging with structlog

- Status: Accepted
- Date: 2026-11-10
- Feature: F01

## Context
Every service needs validated configuration per environment (dev, test, prod) and machine-readable logs
that can be followed across one request. Secrets must never appear in logs or error messages.

## Options considered
| Option | Pros | Cons |
|--------|------|------|
| **pydantic-settings** | Types and validation from pydantic, `SecretStr`, `.env` support, already a dependency | One more library to learn |
| `os.environ` by hand | No dependency | No types, no validation, typos found only at runtime |
| dynaconf | Many file formats, layered config | Heavier; weaker typing; not needed |
| **structlog** | JSON output, processor chain (easy redaction), contextvars for async | Different API from stdlib logging |
| stdlib `logging` + JSON formatter | Built in | Per-request context and redaction need custom code |
| loguru | Simple API | Global logger, weaker contextvars story for asyncio |

## Decision
pydantic-settings for configuration and structlog for logging, both inside the shared package `rr_core`.
Correlation IDs are stored in structlog's contextvars so each asyncio task keeps its own ID.

## Consequences
- A wrong setting stops the service at startup; production refuses to start without its LLM key.
- Every log line is JSON with timestamp (UTC), level, event, env, service and correlation_id.
- Sensitive field names are redacted centrally; new sensitive names are added to `SENSITIVE_KEYS`.
- Revisit if we need OpenTelemetry trace context: the correlation ID would then map to the trace ID.

## Proof
`tests/unit/core/` (21 tests, 100 % coverage on rr_core), `docs/proof/sprint1/gitleaks-fake-secret.txt`.
