"""PostgreSQL persistence layer for stock price data."""

import logging
import os
import psycopg2

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS prices (
    symbol     TEXT        NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    field      TEXT        NOT NULL,
    value      NUMERIC,
    PRIMARY KEY (symbol, fetched_at, field)
);
"""


def _conn_str() -> str:
    """Build a PostgreSQL connection string from environment variables.

    Returns:
        A ``postgresql://`` connection string using the ``POSTGRES_*``
        environment variables.
    """
    return (
        f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}:{os.environ['POSTGRES_PORT']}/{os.environ['POSTGRES_DB']}"
    )


def ensure_schema() -> None:
    """Create the ``prices`` table if it does not already exist.

    Safe to call multiple times — uses ``CREATE TABLE IF NOT EXISTS``.
    Intended to be called once at application startup before the scheduler
    begins dispatching fetch jobs.

    Raises:
        psycopg2.Error: If the database connection or DDL execution fails.
    """
    with psycopg2.connect(_conn_str()) as conn, conn.cursor() as cur:
        cur.execute(_CREATE_TABLE)


def upsert(symbol: str, data: dict) -> None:
    """Persist a fetched data snapshot for a ticker to the ``prices`` table.

    Each key-value pair in ``data`` becomes one row. Values are coerced to
    native Python ``float`` before binding to avoid psycopg2 serialising
    numpy scalar types as their repr string.

    If ``data`` is empty the call is a no-op and a warning is logged.

    Args:
        symbol: The ticker symbol (e.g. ``"AAPL"``).
        data: A mapping of field name to numeric value as returned by
            :func:`fetcher.fetch`. ``None`` values are stored as SQL ``NULL``.

    Raises:
        psycopg2.Error: If the database connection or any insert fails.
    """
    if not data:
        logger.warning("[%s] no data to upsert", symbol)
        return

    with psycopg2.connect(_conn_str()) as conn, conn.cursor() as cur:
        for field, value in data.items():
            native = float(value) if value is not None else None
            cur.execute(
                """
                INSERT INTO prices (symbol, field, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol, fetched_at, field) DO UPDATE SET value = EXCLUDED.value
                """,
                (symbol, field, native),
            )
    logger.info("[%s] upserted %d field(s)", symbol, len(data))
