"""
agent/fetchers/stocks.py

Fetches the latest closing price and previous-day close from Twelve Data.

Twelve Data (twelvedata.com) covers the Warsaw Stock Exchange (WSE) and is
designed for server-to-server use — unlike Yahoo Finance it does not block
cloud-runner IP addresses.  The free tier provides 800 API calls/day; this
agent uses roughly 20/month (one weekday evening run per weekday).

Required secret:
    TWELVEDATA_API_KEY   — free key from https://twelvedata.com/pricing
    (STOOQ_API_KEY can be deleted from GitHub Secrets — no longer used)

Return shape (unchanged from previous Stooq/Yahoo fetcher):
    {
        "ticker":     "KRU",
        "date":       "2026-06-12",
        "close":      412.0,
        "prev_close": 405.0,   # None when unavailable
        "change_pct": 1.73,    # None when prev_close is None
    }
or None on complete failure.
"""

import os
import requests
from agent.retry import with_retries

_URL = "https://api.twelvedata.com/quote"


def fetch_stock_quote(ticker: str, exchange: str) -> dict | None:
    """
    Return the latest closing price and day-over-day change for *ticker*.

    Args:
        ticker:    Symbol as in config.yaml, e.g. "KRU".
        exchange:  Exchange code, e.g. "WSE".

    Returns:
        Dict with ticker/date/close/prev_close/change_pct, or None on failure.
        change_pct is None when prev_close is unavailable; the render layer
        displays "(change: —)" in that case.
    """
    api_key = os.environ.get("TWELVEDATA_API_KEY", "")
    if not api_key:
        print("[stocks] TWELVEDATA_API_KEY not set — skipping stock fetch. "
              "Get a free key at https://twelvedata.com/pricing")
        return None

    try:
        def _do_request():
            r = requests.get(
                _URL,
                params={
                    "symbol":   ticker.upper(),
                    "exchange": exchange.upper(),   # e.g. "WSE"
                    "apikey":   api_key,
                },
                timeout=10,
            )
            r.raise_for_status()
            return r

        resp = with_retries(
            _do_request, attempts=3, base_delay=1.0,
            exceptions=(requests.RequestException,), label="stocks",
        )

        data = resp.json()

        # Twelve Data signals errors in the JSON body (not always via HTTP status).
        if data.get("status") == "error" or "code" in data:
            print(f"[stocks] Twelve Data error for {ticker}.{exchange}: "
                  f"{data.get('message', data)}")
            return None

        close_str = data.get("close")
        prev_str  = data.get("previous_close")
        date_str  = data.get("datetime")          # "YYYY-MM-DD"

        if close_str is None:
            print(f"[stocks] Twelve Data: no close price for {ticker}.{exchange}")
            return None

        close = float(close_str)

        prev_close = float(prev_str) if prev_str else None
        change_pct = None
        if prev_close and prev_close != 0:
            change_pct = round((close - prev_close) / prev_close * 100, 2)

        return {
            "ticker":     ticker.upper(),
            "date":       date_str or "",
            "close":      close,
            "prev_close": prev_close,
            "change_pct": change_pct,
        }

    except Exception as exc:
        print(f"[stocks] unexpected error for {ticker}.{exchange}: {exc!r}")
        return None