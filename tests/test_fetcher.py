import pandas as pd
import pytest

import fetcher


@pytest.fixture
def mock_ticker(mocker):
    ticker = mocker.MagicMock()
    mocker.patch("fetcher.yf.Ticker", return_value=ticker)
    return ticker


def _history(open=100.0, high=105.0, low=99.0, close=103.0, volume=1_000_000):
    return pd.DataFrame(
        {"Open": [open], "High": [high], "Low": [low], "Close": [close], "Volume": [volume]}
    )


class TestOHLCV:
    def test_returns_all_ohlcv_fields(self, mock_ticker):
        mock_ticker.history.return_value = _history()

        result = fetcher.fetch("AAPL", ["open", "high", "low", "close", "volume"])

        assert result["open"] == 100.0
        assert result["high"] == 105.0
        assert result["low"] == 99.0
        assert result["close"] == 103.0
        assert result["volume"] == 1_000_000

    def test_requests_one_day_period(self, mock_ticker):
        mock_ticker.history.return_value = _history()
        fetcher.fetch("AAPL", ["close"])
        mock_ticker.history.assert_called_once_with(period="1d")

    def test_empty_history_returns_no_ohlcv(self, mock_ticker):
        mock_ticker.history.return_value = pd.DataFrame()
        result = fetcher.fetch("AAPL", ["close"])
        assert "close" not in result

    def test_history_exception_returns_empty(self, mock_ticker):
        mock_ticker.history.side_effect = Exception("network error")
        result = fetcher.fetch("AAPL", ["close"])
        assert "close" not in result


class TestInfoFields:
    def test_returns_market_cap_and_pe(self, mock_ticker):
        mock_ticker.info = {"marketCap": 3_000_000_000_000, "trailingPE": 32.5}
        result = fetcher.fetch("AAPL", ["market_cap", "pe_ratio"])
        assert result["market_cap"] == 3_000_000_000_000
        assert result["pe_ratio"] == 32.5

    def test_missing_info_key_excluded(self, mock_ticker):
        mock_ticker.info = {}
        result = fetcher.fetch("AAPL", ["pe_ratio"])
        assert "pe_ratio" not in result

    def test_info_exception_returns_empty(self, mock_ticker):
        mock_ticker.info = mocker_raises(Exception("timeout"))
        result = fetcher.fetch("AAPL", ["market_cap"])
        assert "market_cap" not in result


class TestDividends:
    def test_returns_latest_dividend(self, mock_ticker, mocker):
        import pandas as pd
        mock_ticker.dividends = pd.Series([0.22, 0.23, 0.24])
        result = fetcher.fetch("AAPL", ["dividends"])
        assert result["dividends"] == pytest.approx(0.24)

    def test_empty_dividends_returns_none(self, mock_ticker):
        import pandas as pd
        mock_ticker.dividends = pd.Series([], dtype=float)
        result = fetcher.fetch("AAPL", ["dividends"])
        assert result["dividends"] is None


class TestUnknownFields:
    def test_unknown_field_excluded_from_result(self, mock_ticker):
        mock_ticker.history.return_value = _history()
        result = fetcher.fetch("AAPL", ["close", "not_a_real_field"])
        assert "not_a_real_field" not in result
        assert "close" in result

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
