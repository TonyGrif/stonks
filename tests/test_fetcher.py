import pandas as pd
import pytest

import fetcher


@pytest.fixture
def mock_ticker(mocker):
    ticker = mocker.MagicMock()
    mocker.patch("fetcher.yf.Ticker", return_value=ticker)
    return ticker


_TS = pd.Timestamp("2026-06-23 16:00:00", tz="UTC")


def _history(open=100.0, high=105.0, low=99.0, close=103.0, volume=1_000_000, ts=_TS):
    return pd.DataFrame(
        {"Open": [open], "High": [high], "Low": [low], "Close": [close], "Volume": [volume]},
        index=pd.DatetimeIndex([ts]),
    )


class TestOHLCV:
    def test_returns_all_ohlcv_fields(self, mock_ticker):
        mock_ticker.history.return_value = _history()

        result = fetcher.fetch("AAPL", ["open", "high", "low", "close", "volume"])

        assert len(result) == 1
        ts, fields = result[0]
        assert fields["open"] == 100.0
        assert fields["high"] == 105.0
        assert fields["low"] == 99.0
        assert fields["close"] == 103.0
        assert fields["volume"] == 1_000_000

    def test_bar_timestamp_preserved(self, mock_ticker):
        mock_ticker.history.return_value = _history(ts=_TS)
        result = fetcher.fetch("AAPL", ["close"])
        assert result[0][0] == _TS

    def test_defaults_to_1d_period_and_interval(self, mock_ticker):
        mock_ticker.history.return_value = _history()
        fetcher.fetch("AAPL", ["close"])
        mock_ticker.history.assert_called_once_with(period="1d", interval="1d")

    def test_custom_period_and_interval_passed_through(self, mock_ticker):
        mock_ticker.history.return_value = _history()
        fetcher.fetch("AAPL", ["close"], period="5d", interval="1h")
        mock_ticker.history.assert_called_once_with(period="5d", interval="1h")

    def test_multiple_bars_returns_one_entry_per_bar(self, mock_ticker):
        ts1 = pd.Timestamp("2026-06-23 09:30:00", tz="UTC")
        ts2 = pd.Timestamp("2026-06-23 09:35:00", tz="UTC")
        ts3 = pd.Timestamp("2026-06-23 09:40:00", tz="UTC")
        mock_ticker.history.return_value = pd.DataFrame(
            {"Open": [100.0, 101.0, 102.0], "Close": [103.0, 104.0, 105.0],
             "High": [106.0, 107.0, 108.0], "Low": [99.0, 100.0, 101.0],
             "Volume": [1000, 1100, 1200]},
            index=pd.DatetimeIndex([ts1, ts2, ts3]),
        )
        result = fetcher.fetch("SPY", ["close"], period="1d", interval="5m")
        assert len(result) == 3
        assert result[0][0] == ts1
        assert result[1][0] == ts2
        assert result[2][0] == ts3

    def test_empty_history_returns_empty_list(self, mock_ticker):
        mock_ticker.history.return_value = pd.DataFrame()
        result = fetcher.fetch("AAPL", ["close"])
        assert result == []

    def test_history_exception_returns_empty_list(self, mock_ticker):
        mock_ticker.history.side_effect = Exception("network error")
        result = fetcher.fetch("AAPL", ["close"])
        assert result == []


class TestInfoFields:
    def test_returns_market_cap_and_pe(self, mock_ticker):
        mock_ticker.info = {"marketCap": 3_000_000_000_000, "trailingPE": 32.5}
        result = fetcher.fetch("AAPL", ["market_cap", "pe_ratio"])
        assert len(result) == 1
        _, fields = result[0]
        assert fields["market_cap"] == 3_000_000_000_000
        assert fields["pe_ratio"] == 32.5

    def test_missing_info_key_excluded(self, mock_ticker):
        mock_ticker.info = {}
        result = fetcher.fetch("AAPL", ["pe_ratio"])
        assert result == []

    def test_info_exception_returns_empty_list(self, mock_ticker):
        mock_ticker.info = mocker_raises(Exception("timeout"))
        result = fetcher.fetch("AAPL", ["market_cap"])
        assert result == []


class TestDividends:
    def test_returns_latest_dividend(self, mock_ticker):
        div_ts = pd.Timestamp("2026-05-15", tz="UTC")
        mock_ticker.dividends = pd.Series(
            [0.22, 0.23, 0.24],
            index=pd.DatetimeIndex([
                pd.Timestamp("2026-02-15", tz="UTC"),
                pd.Timestamp("2026-03-15", tz="UTC"),
                div_ts,
            ]),
        )
        result = fetcher.fetch("AAPL", ["dividends"])
        assert len(result) == 1
        ts, fields = result[0]
        assert fields["dividends"] == pytest.approx(0.24)
        assert ts == div_ts

    def test_empty_dividends_returns_none(self, mock_ticker):
        mock_ticker.dividends = pd.Series([], dtype=float)
        result = fetcher.fetch("AAPL", ["dividends"])
        assert len(result) == 1
        _, fields = result[0]
        assert fields["dividends"] is None


class TestUnknownFields:
    def test_unknown_field_excluded_from_result(self, mock_ticker):
        mock_ticker.history.return_value = _history()
        result = fetcher.fetch("AAPL", ["close", "not_a_real_field"])
        assert len(result) == 1
        _, fields = result[0]
        assert "not_a_real_field" not in fields
        assert "close" in fields

    def test_unknown_field_logs_warning(self, mock_ticker, caplog):
        import logging
        mock_ticker.history.return_value = _history()
        with caplog.at_level(logging.WARNING, logger="fetcher"):
            fetcher.fetch("AAPL", ["bad_field"])
        assert "bad_field" in caplog.text


# helper — raises on attribute access (simulates a broken .info property)
class mocker_raises:
    def __init__(self, exc):
        self._exc = exc

    def __getitem__(self, _):
        raise self._exc

    def get(self, *_):
        raise self._exc

    def __contains__(self, _):
        raise self._exc
