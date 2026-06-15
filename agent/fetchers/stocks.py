"""
agent/fetchers/stocks.py

Fetches daily closing price and previous-day close from Yahoo Finance.

Yahoo Finance covers the Warsaw Stock Exchange under the ".WA" ticker suffix
(KRU → KRU.WA). No API key required.

The STOOQ_API_KEY secret is no longer needed and can be deleted from
GitHub Secrets → Settings → Secrets and variables → Actions.

Return shape (identical to old Stooq fetcher — no downstream changes needed):
    {
        "ticker":     "KRU",
        "date":       "2026-06-12",
        "close":      412.0,
        "prev_close": 405.0,   # None when unavailable
        "change_pct": 1.73,    # None when prev_close is None
    }
or None on complete failure.
"""

import datetime
import requests
from agent.retry import with_retries

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Map our exchange identifiers to Yahoo Finance ticker suffixes.
_EXCHANGE_SUFFIX = {
    "WSE": ".WA",   # Warsaw Stock Exchange / Giełda Papierów Wartościowych
}

# Yahoo Finance requires a browser-like User-Agent; a bare Python requests
# user-agent is sometimes rejected with a 401 or empty result.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_stock_quote(ticker: str, exchange: str) -> dict | None:
    """
    Return the latest closing price and day-over-day change for *ticker*.

    Args:
        ticker:    Ticker symbol as stored in config.yaml, e.g. "KRU".
        exchange:  Exchange code, e.g. "WSE".

    Returns:
        Dict with ticker/date/close/prev_close/change_pct, or None on failure.
        change_pct is None when prev_close is unavailable (market just opened,
        etc.) — the render layer handles this with "(change: —)".
    """
    suffix = _EXCHANGE_SUFFIX.get(exchange.upper(), "")
    symbol = f"{ticker.upper()}{suffix}"   # e.g. "KRU.WA"
    url    = _URL.format(symbol=symbol)

    try:
        def _do_request():
            r = requests.get(
                url,
                params={"interval": "1d", "range": "5d"},
                headers=_HEADERS,
                timeout=10,
            )
            r.raise_for_status()
            return r

        resp = with_retries(
            _do_request, attempts=3, base_delay=0.5,
            exceptions=(requests.RequestException,), label="stocks",
        )

        data   = resp.json()
        result = data.get("chart", {}).get("result")

        if not result:
            err = data.get("chart", {}).get("error")
            print(f"[stocks] Yahoo Finance returned no result for {symbol}: {err}")
            return None

        meta       = result[0]["meta"]
        close      = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")

        if close is None:
            print(f"[stocks] Yahoo Finance: no close price in response for {symbol}")
            return None

        # Prefer the exchange's local trading date; fall back to today.
        market_ts = meta.get("regularMarketTime")
        if market_ts:
            date_str = datetime.datetime.fromtimestamp(market_ts).strftime("%Y-%m-%d")
        else:
            date_str = datetime.date.today().strftime("%Y-%m-%d")

        change_pct = None
        if prev_close and prev_close != 0:
            change_pct = round((close - prev_close) / prev_close * 100, 2)

        return {
            "ticker":     ticker.upper(),
            "date":       date_str,
            "close":      close,
            "prev_close": prev_close,
            "change_pct": change_pct,
        }

    except Exception as exc:
        print(f"[stocks] unexpected error for {symbol}: {exc!r}")
        return None