import os
import pytest
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def _conn_kwargs(dbname: str | None = None) -> dict:
    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", 5432)),
        "user": os.environ.get("POSTGRES_USER", "stocks"),
        "password": os.environ.get("POSTGRES_PASSWORD", "stocks"),
        "dbname": dbname or os.environ.get("POSTGRES_DB", "stocks_test"),
    }


@pytest.fixture(scope="session")
def test_database():
    """Create the test database and schema once per test session."""
    test_db = os.environ.get("POSTGRES_DB", "stocks_test")

    conn = psycopg2.connect(**_conn_kwargs(dbname="postgres"))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{test_db}"')
    conn.close()

    import db
    db.ensure_schema()


@pytest.fixture
def clean_prices():
    """Truncate prices after each test that touches the DB."""
    yield
    conn = psycopg2.connect(**_conn_kwargs())
    with conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE prices")
    conn.close()
