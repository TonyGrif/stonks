"""PostgreSQL persistence layer for stock price data."""

import logging
import os
import psycopg2

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS prices (
    symbol     TEXT        NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
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


def upsert(symbol: str, rows: list[tuple]) -> None:
    """Persist a list of bar snapshots for a ticker to the ``prices`` table.

    Each element of ``rows`` is a ``(timestamp, field_dict)`` pair as
    returned by :func:`fetcher.fetch`. The timestamp is the bar's exchange
    time (or current UTC time for non-bar data such as fundamentals), making
    it meaningful for time-series queries rather than reflecting fetch time.

    Values are coerced to native Python ``float`` before binding to prevent
    psycopg2 from serialising numpy scalar types as their repr string.

    If ``rows`` is empty the call is a no-op and a warning is logged.

    Args:
        symbol: The ticker symbol (e.g. ``"AAPL"``).
        rows: A list of ``(timestamp, field_dict)`` tuples as returned by
            :func:`fetcher.fetch`. ``None`` values are stored as SQL ``NULL``.

    Raises:
        psycopg2.Error: If the database connection or any insert fails.
    """
    if not rows:
        logger.warning("[%s] no data to upsert", symbol)
        return

    total = 0
    with psycopg2.connect(_conn_str()) as conn, conn.cursor() as cur:
        for ts, data in rows:
            for field, value in data.items():
                native = float(value) if value is not None else None
                cur.execute(
                    """
                    INSERT INTO prices (symbol, fetched_at, field, value)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (symbol, fetched_at, field) DO UPDATE SET value = EXCLUDED.value
                    """,
                    (symbol, ts, field, native),
                )
                total += 1
    logger.info("[%s] upserted %d field(s) across %d bar(s)", symbol, total, len(rows))
