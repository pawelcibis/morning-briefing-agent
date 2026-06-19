"""
agent/fetchers/stocks.py

Fetches daily closing price from Marketstack.

Marketstack (marketstack.com) covers the Warsaw Stock Exchange under the XWAR
MIC code (e.g. KRU → KRU.XWAR). The free tier provides 100 API calls/month
(we use ~20) but requires plain HTTP — HTTPS is a paid feature. The security
risk is minimal: the key only grants access to public stock price data.

Required secret:
    MARKETSTACK_API_KEY   — free key from https://marketstack.com

Return shape (unchanged throughout — no downstream changes needed):
    {"ticker": "KRU", "date": "2026-06-12", "close": 412.0,
     "prev_close": 405.0, "change_pct": 1.73}
    prev_close / change_pct are None when only 1 record is available.
    Returns None on complete failure.
"""

import os
import requests
from agent.retry import with_retries

# HTTP (not HTTPS) — free tier restriction on Marketstack.
_URL = "http://api.marketstack.com/v1/eod"

# Map our canonical exchange codes to Marketstack's MIC codes.
_EXCHANGE_MIC = {
    "WSE": "XWAR",   # Warsaw Stock Exchange / Giełda Papierów Wartościowych
}


def fetch_stock_quote(ticker: str, exchange: str) -> dict | None:
    """
    Fetch the two most recent EOD records for *ticker* and compute change%.

    Args:
        ticker:    Symbol as stored in config.yaml, e.g. "KRU".
        exchange:  Exchange code, e.g. "WSE" — mapped to MIC internally.

    Returns:
        Dict with ticker/date/close/prev_close/change_pct, or None on failure.
        change_pct is None when only 1 record is available; the render layer
        shows "(change: —)" in that case.
    """
    api_key = os.environ.get("MARKETSTACK_API_KEY", "")
    if not api_key:
        print("[stocks] MARKETSTACK_API_KEY not set — skipping stock fetch. "
              "Get a free key at https://marketstack.com")
        return None

    mic    = _EXCHANGE_MIC.get(exchange.upper(), exchange.upper())
    symbol = f"{ticker.upper()}.{mic}"   # e.g. "KRU.XWAR"

    try:
        def _do_request():
            r = requests.get(
                _URL,
                params={
                    "access_key": api_key,
                    "symbols":    symbol,
                    "limit":      2,      # latest + previous day for change%
                },
                timeout=10,
            )
            # 4xx = deterministic (bad key, symbol not found, plan limit).
            # Raise ValueError so with_retries lets it through immediately
            # without wasting retry attempts.
            if 400 <= r.status_code < 500:
                raise ValueError(
                    f"Marketstack {r.status_code} for {symbol}: {r.text[:300]}"
                )
            r.raise_for_status()   # 5xx → HTTPError → retried normally
            return r

        resp = with_retries(
            _do_request, attempts=3, base_delay=1.0,
            exceptions=(requests.RequestException,),   # ValueError → immediate fail
            label="stocks",
        )

        body = resp.json()

        # Marketstack signals errors in the JSON body too (HTTP 200 + error key).
        if "error" in body:
            print(f"[stocks] Marketstack error for {symbol}: {body['error']}")
            return None

        records = body.get("data", [])
        if not records:
            print(f"[stocks] Marketstack returned 0 records for {symbol}")
            return None

        # Records are returned newest-first.
        latest = records[0]
        close  = float(latest["close"])

        # Parse date: "2026-06-12T00:00:00+0000" → "2026-06-12"
        date_str = latest.get("date", "")[:10]

        if len(records) >= 2:
            prev_close = float(records[1]["close"])
            change_pct = round((close - prev_close) / prev_close * 100, 2)
        else:
            print(f"[stocks] only 1 record returned for {symbol}; "
                  "showing close price without day-over-day change")
            prev_close = None
            change_pct = None

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