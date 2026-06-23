"""Fetches stock data from Yahoo Finance via yfinance."""

import logging
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


def fetch(symbol: str, fields: list[str]) -> dict:
    """Fetch the requested fields for a ticker from Yahoo Finance.

    Partitions ``fields`` into the three underlying yfinance API calls
    (history, info, dividends), executes only the calls that are needed,
    and merges the results. Each API call is isolated so a failure in one
    does not prevent the others from running.

    Unknown field names are logged as warnings and excluded from the result.
    Missing values (e.g. a fundamental not reported for this ticker) are
    also excluded rather than returning ``None``, except for ``dividends``
    where ``None`` is returned explicitly when no history is available.

    Args:
        symbol: The ticker symbol to query (e.g. ``"AAPL"``).
        fields: List of field names to fetch. Supported values are the keys
            of ``_HISTORY_FIELDS``, ``_INFO_FIELDS``, and ``_DIVIDEND_FIELDS``.

    Returns:
        A dict mapping each successfully fetched field name to its value.
        Fields that could not be fetched are omitted.
    """
    ticker = yf.Ticker(symbol)
    result = {}

    history_needed = [f for f in fields if f in _HISTORY_FIELDS]
    info_needed = [f for f in fields if f in _INFO_FIELDS]
    dividend_needed = [f for f in fields if f in _DIVIDEND_FIELDS]
    unknown = [f for f in fields if f not in _HISTORY_FIELDS and f not in _INFO_FIELDS and f not in _DIVIDEND_FIELDS]

    for f in unknown:
        logger.warning("[%s] unknown field '%s', skipping", symbol, f)

    if history_needed:
        try:
            hist = ticker.history(period="1d")
            if hist.empty:
                logger.warning("[%s] history returned no data", symbol)
            else:
                row = hist.iloc[-1]
                for f in history_needed:
                    result[f] = row[f.capitalize()]
        except Exception as e:
            logger.error("[%s] failed to fetch history: %s", symbol, e)

    if info_needed:
        try:
            info = ticker.info
            for f in info_needed:
                key = _INFO_FIELDS[f]
                if key in info:
                    result[f] = info[key]
                else:
                    logger.warning("[%s] info key '%s' not available", symbol, key)
        except Exception as e:
            logger.error("[%s] failed to fetch info: %s", symbol, e)

    if dividend_needed:
        try:
            divs = ticker.dividends
            result["dividends"] = float(divs.iloc[-1]) if not divs.empty else None
        except Exception as e:
            logger.error("[%s] failed to fetch dividends: %s", symbol, e)

    return result
