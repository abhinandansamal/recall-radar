"""The ``kb`` schema in Postgres: the contract between the gold notebook and the exporter.

One module, no database or Spark imports, so three places use the same definition:

- the gold notebook selects exactly :data:`LOAD_COLUMNS` and writes :data:`SCHEMA_VERSION`
  into the export manifest;
- the exporter creates the tables with :func:`create_statements` and refuses exports with
  another version or other columns;
- the contract tests compare the live database with :data:`CONTRACT`.

Change the schema only together with ``SCHEMA_VERSION`` (ADR-0004, section 7).
"""

from typing import Final

SCHEMA_VERSION: Final = 1
LIVE: Final = "kb"
STAGING: Final = "kb_staging"
OLD: Final = "kb_old"

# Columns filled from the export files, in file order. Tables are loaded in this order
# (parents before children, because of the foreign keys).
LOAD_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "alerts": (
        "case_number",
        "risk_level",
        "title_en",
        "title_de",
        "category_en",
        "category_de",
        "risk_type_en",
        "risk_type_de",
        "brand",
        "model",
        "description_en",
        "description_de",
        "danger_en",
        "danger_de",
        "measures_en",
        "measures_de",
        "notifying_country",
        "country_of_origin",
        "published_at",
        "is_withdrawn",
        "source_url",
        "valid_from",
    ),
    "alert_identifiers": ("case_number", "kind", "value_norm"),
    "alert_images": ("case_number", "sha256", "ordinal", "is_main", "source_url"),
}

# Every column of every table as Postgres reports it (``format_type``), in table order.
# Columns after the loaded ones are generated (search) or filled later (embeddings, E3/E4).
CONTRACT: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "alerts": (
        ("case_number", "text"),
        ("risk_level", "text"),
        ("title_en", "text"),
        ("title_de", "text"),
        ("category_en", "text"),
        ("category_de", "text"),
        ("risk_type_en", "text"),
        ("risk_type_de", "text"),
        ("brand", "text"),
        ("model", "text"),
        ("description_en", "text"),
        ("description_de", "text"),
        ("danger_en", "text"),
        ("danger_de", "text"),
        ("measures_en", "text"),
        ("measures_de", "text"),
        ("notifying_country", "text"),
        ("country_of_origin", "text"),
        ("published_at", "date"),
        ("is_withdrawn", "boolean"),
        ("source_url", "text"),
        ("valid_from", "timestamp with time zone"),
        ("search_en", "tsvector"),
        ("search_de", "tsvector"),
        ("text_embedding", "halfvec(1024)"),
        ("embedding_model", "text"),
    ),
    "alert_identifiers": (
        ("case_number", "text"),
        ("kind", "text"),
        ("value_norm", "text"),
    ),
    "alert_images": (
        ("case_number", "text"),
        ("sha256", "text"),
        ("ordinal", "integer"),
        ("is_main", "boolean"),
        ("source_url", "text"),
        ("image_embedding", "halfvec(512)"),
        ("embedding_model", "text"),
    ),
    "export_info": (
        ("export_id", "text"),
        ("schema_version", "integer"),
        ("gold_created_at", "timestamp with time zone"),
        ("loaded_at", "timestamp with time zone"),
        ("row_counts", "jsonb"),
    ),
}


def _search(config: str, lang: str) -> str:
    """Weighted full-text vector: title, brand and model count more than the long texts."""
    strong = (
        f"coalesce(title_{lang}, '') || ' ' || coalesce(brand, '') || ' ' || coalesce(model, '')"
    )
    weak = (
        f"coalesce(category_{lang}, '') || ' ' || coalesce(description_{lang}, '') || ' ' "
        f"|| coalesce(danger_{lang}, '')"
    )
    return (
        f"setweight(to_tsvector('{config}', {strong}), 'A') "
        f"|| setweight(to_tsvector('{config}', {weak}), 'B')"
    )


def create_statements(schema: str) -> list[str]:
    """SQL that creates the empty tables in ``schema`` (no secondary indexes yet).

    Args:
        schema: Target schema, normally :data:`STAGING`.

    Returns:
        Statements in execution order.
    """
    s = schema
    return [
        f"CREATE SCHEMA {s}",
        f"""CREATE TABLE {s}.alerts (
            case_number text PRIMARY KEY,
            risk_level text NOT NULL
                CHECK (risk_level IN ('serious', 'other_risk', 'other_alert', 'unknown')),
            title_en text, title_de text,
            category_en text, category_de text,
            risk_type_en text, risk_type_de text,
            brand text, model text,
            description_en text, description_de text,
            danger_en text, danger_de text,
            measures_en text, measures_de text,
            notifying_country text, country_of_origin text,
            published_at date NOT NULL,
            is_withdrawn boolean NOT NULL,
            source_url text,
            valid_from timestamptz NOT NULL,
            search_en tsvector GENERATED ALWAYS AS ({_search("english", "en")}) STORED,
            search_de tsvector GENERATED ALWAYS AS ({_search("german", "de")}) STORED,
            text_embedding halfvec(1024),
            embedding_model text
        )""",
        f"""CREATE TABLE {s}.alert_identifiers (
            case_number text NOT NULL REFERENCES {s}.alerts (case_number),
            kind text NOT NULL CHECK (kind IN ('gtin', 'brand_model')),
            value_norm text NOT NULL CHECK (kind <> 'gtin' OR value_norm ~ '^[0-9]{{14}}$'),
            PRIMARY KEY (case_number, kind, value_norm)
        )""",
        f"""CREATE TABLE {s}.alert_images (
            case_number text NOT NULL REFERENCES {s}.alerts (case_number),
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
            ordinal integer NOT NULL CHECK (ordinal >= 1),
            is_main boolean NOT NULL,
            source_url text NOT NULL,
            image_embedding halfvec(512),
            embedding_model text,
            PRIMARY KEY (case_number, sha256)
        )""",
        f"""CREATE TABLE {s}.export_info (
            export_id text PRIMARY KEY,
            schema_version integer NOT NULL,
            gold_created_at timestamptz NOT NULL,
            loaded_at timestamptz NOT NULL DEFAULT now(),
            row_counts jsonb NOT NULL
        )""",
    ]


def index_statements(schema: str) -> list[str]:
    """Secondary indexes, built after loading (faster than updating them row by row).

    Args:
        schema: Target schema, normally :data:`STAGING`.

    Returns:
        Statements in execution order (index choices: design section 7.2).
    """
    s = schema
    return [
        # Exact keys first (D7): GTIN or brand+model lookup in microseconds.
        f"CREATE INDEX alert_identifiers_lookup ON {s}.alert_identifiers (kind, value_norm)",
        f"CREATE INDEX alert_images_sha256 ON {s}.alert_images (sha256)",
        f"CREATE INDEX alerts_published ON {s}.alerts (published_at DESC)",
        # Keyword search (hybrid retrieval): brands and model numbers match exactly.
        f"CREATE INDEX alerts_search_en ON {s}.alerts USING gin (search_en)",
        f"CREATE INDEX alerts_search_de ON {s}.alerts USING gin (search_de)",
        # Vector search; the columns are filled by the embedding jobs (E3/E4).
        f"CREATE INDEX alerts_text_embedding ON {s}.alerts "
        "USING hnsw (text_embedding halfvec_cosine_ops)",
        f"CREATE INDEX alert_images_embedding ON {s}.alert_images "
        "USING hnsw (image_embedding halfvec_cosine_ops)",
    ]


INDEXES: Final = tuple(
    name.split()[2] for name in index_statements(STAGING)
)  # index names, for the contract test
