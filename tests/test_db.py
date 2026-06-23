import os
from datetime import datetime, timezone
import pytest
import psycopg2

import db


@pytest.fixture(scope="module", autouse=True)
def setup_db(test_database):
    """Ensure schema exists before any test in this module."""
    pass


_TS = datetime(2026, 6, 23, 16, 0, 0, tzinfo=timezone.utc)
_TS2 = datetime(2026, 6, 23, 16, 5, 0, tzinfo=timezone.utc)


def _fetch_all():
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ.get("POSTGRES_DB", "stocks_test"),
        user=os.environ.get("POSTGRES_USER", "stocks"),
        password=os.environ.get("POSTGRES_PASSWORD", "stocks"),
    )
    with conn, conn.cursor() as cur:
        cur.execute("SELECT symbol, fetched_at, field, value FROM prices ORDER BY fetched_at, field")
        return cur.fetchall()


class TestEnsureSchema:
    def test_idempotent(self):
        db.ensure_schema()
        db.ensure_schema()  # second call must not raise


class TestUpsert:
    def test_inserts_rows(self, clean_prices):
        db.upsert("AAPL", [(_TS, {"close": 150.0, "volume": 1_000_000.0})])
        rows = _fetch_all()
        assert len(rows) == 2
        values = {r[2]: float(r[3]) for r in rows}
        assert values["close"] == pytest.approx(150.0)
        assert values["volume"] == pytest.approx(1_000_000.0)

    def test_bar_timestamp_stored(self, clean_prices):
        db.upsert("AAPL", [(_TS, {"close": 150.0})])
        rows = _fetch_all()
        stored_ts = rows[0][1].replace(tzinfo=timezone.utc)
        assert stored_ts == _TS

    def test_symbol_stored_correctly(self, clean_prices):
        db.upsert("GOOGL", [(_TS, {"close": 200.0})])
        rows = _fetch_all()
        assert rows[0][0] == "GOOGL"

    def test_none_value_stored_as_null(self, clean_prices):
        db.upsert("AAPL", [(_TS, {"pe_ratio": None})])
        rows = _fetch_all()
        assert rows[0][3] is None

    def test_empty_rows_skipped(self, clean_prices):
        db.upsert("AAPL", [])
        assert _fetch_all() == []

    def test_numpy_float64_coercion(self, clean_prices):
        """Regression: psycopg2 must not receive raw numpy types."""
        import numpy as np
        db.upsert("AAPL", [(_TS, {"open": np.float64(297.54)})])
        rows = _fetch_all()
        assert len(rows) == 1
        assert float(rows[0][3]) == pytest.approx(297.54, rel=1e-4)

    def test_multiple_bars_per_ticker(self, clean_prices):
        db.upsert("SPY", [
            (_TS,  {"close": 500.0}),
            (_TS2, {"close": 501.0}),
        ])
        rows = _fetch_all()
        assert len(rows) == 2
        closes = [float(r[3]) for r in rows]
        assert closes == [500.0, 501.0]

    def test_multiple_tickers_independent(self, clean_prices):
        db.upsert("AAPL", [(_TS, {"close": 150.0})])
        db.upsert("SPY",  [(_TS, {"close": 500.0})])
        rows = _fetch_all()
        symbols = {r[0] for r in rows}
        assert symbols == {"AAPL", "SPY"}
