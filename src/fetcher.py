"""Fetches stock data from Yahoo Finance via yfinance."""

import logging
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_HISTORY_FIELDS = {"open", "high", "low", "close", "volume"}

_INFO_FIELDS = {
    "market_cap": "marketCap",
    "pe_ratio": "trailingPE",
    "forward_pe": "forwardPE",
    "dividend_yield": "dividendYield",
    "beta": "beta",
    "eps": "trailingEps",
    "52_week_high": "fiftyTwoWeekHigh",
    "52_week_low": "fiftyTwoWeekLow",
}

_DIVIDEND_FIELDS = {"dividends"}


def fetch(
    symbol: str,
    fields: list[str],
    period: str = "1d",
    interval: str = "1d",
) -> list[tuple[pd.Timestamp, dict]]:
    """Fetch the requested fields for a ticker from Yahoo Finance.

    Partitions ``fields`` into the three underlying yfinance API calls
    (history, info, dividends) and executes only the calls that are needed.

    OHLCV fields produce one result tuple per bar returned by
    ``Ticker.history()``, so intraday intervals yield multiple entries.
    Info (fundamental) fields produce a single tuple timestamped at the
    current UTC time, since fundamentals are not bar-aligned. Dividend
    fields produce a single tuple at the most recent dividend payment date.

    Each API call is isolated — a failure in one does not prevent the
    others from running. Unknown field names are logged as warnings and
    excluded from the result.

    Args:
        symbol: The ticker symbol to query (e.g. ``"AAPL"``).
        fields: List of field names to fetch. Supported values are the keys
            of ``_HISTORY_FIELDS``, ``_INFO_FIELDS``, and ``_DIVIDEND_FIELDS``.
        period: How far back to fetch data (e.g. ``"1d"``, ``"5d"``, ``"1mo"``).
            Passed directly to ``Ticker.history()``. Defaults to ``"1d"``.
        interval: Bar size (e.g. ``"1m"``, ``"5m"``, ``"1h"``, ``"1d"``).
            Passed directly to ``Ticker.history()``. Defaults to ``"1d"``.
            Note that yfinance enforces limits — ``"1m"`` is only available
            for the last 7 days.

    Returns:
        A list of ``(timestamp, field_dict)`` tuples ordered by arrival.
        OHLCV entries carry the bar's exchange timestamp. Info entries carry
        the current UTC time. Dividend entries carry the payment date.
        Returns an empty list if nothing could be fetched.
    """
    ticker = yf.Ticker(symbol)
    results: list[tuple[pd.Timestamp, dict]] = []

    history_needed = [f for f in fields if f in _HISTORY_FIELDS]
    info_needed = [f for f in fields if f in _INFO_FIELDS]
    dividend_needed = [f for f in fields if f in _DIVIDEND_FIELDS]
    unknown = [
        f for f in fields
        if f not in _HISTORY_FIELDS and f not in _INFO_FIELDS and f not in _DIVIDEND_FIELDS
    ]

    for f in unknown:
        logger.warning("[%s] unknown field '%s', skipping", symbol, f)

    if history_needed:
        try:
            hist = ticker.history(period=period, interval=interval)
            if hist.empty:
                logger.warning("[%s] history returned no data", symbol)
            else:
                for ts, row in hist.iterrows():
                    bar_data = {f: row[f.capitalize()] for f in history_needed}
                    results.append((ts, bar_data))
        except Exception as e:
            logger.error("[%s] failed to fetch history: %s", symbol, e)

    if info_needed:
        try:
            info = ticker.info
            info_data = {}
            for f in info_needed:
                key = _INFO_FIELDS[f]
                if key in info:
                    info_data[f] = info[key]
                else:
                    logger.warning("[%s] info key '%s' not available", symbol, key)
            if info_data:
                results.append((pd.Timestamp.now(tz="UTC"), info_data))
        except Exception as e:
            logger.error("[%s] failed to fetch info: %s", symbol, e)

    if dividend_needed:
        try:
            divs = ticker.dividends
            if not divs.empty:
                results.append((divs.index[-1], {"dividends": float(divs.iloc[-1])}))
            else:
                results.append((pd.Timestamp.now(tz="UTC"), {"dividends": None}))
        except Exception as e:
            logger.error("[%s] failed to fetch dividends: %s", symbol, e)

    return results
