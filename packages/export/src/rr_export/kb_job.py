"""Load a gold export folder into the Postgres knowledge base (``kb``).

Usage (dev, against the local Docker Postgres from ``.env``)::

    uv run python -m rr_export.kb_job --export-dir data/local/exports/kb/<export_id>
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

import psycopg

from rr_core.config import Settings, get_settings
from rr_core.logging import configure_logging, get_logger
from rr_export.loader import load_kb
from rr_export.manifest import ExportError

log = get_logger(__name__)


def connect(settings: Settings) -> psycopg.Connection:
    """Open an autocommit connection with the ``RR_POSTGRES_*`` settings.

    Args:
        settings: Service settings.

    Returns:
        The connection.
    """
    password = settings.postgres_password.get_secret_value() if settings.postgres_password else None
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=password,
        autocommit=True,
        application_name="rr_export.kb_job",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point.

    Args:
        argv: Arguments (default: from the command line).

    Returns:
        Exit code: 0 if the export is live, 1 if it was rejected (``kb`` unchanged).
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings)
    try:
        with connect(settings) as conn:
            result = load_kb(conn, args.export_dir)
    except ExportError as error:
        log.error("export_rejected", reason=str(error), kb_unchanged=True)
        return 1
    log.info("export_live", export_id=result.export_id, **result.rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
