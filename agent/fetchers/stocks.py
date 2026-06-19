"""
agent/fetchers/stocks.py

Fetches daily closing price from Stooq.pl — a Polish financial data service
that provides GPW (Warsaw Stock Exchange) data via a free CSV download endpoint.
No API key or registration required for basic daily quotes.

History:
  Phase 6–12: Stooq with API key (free one-time key) — worked until key expired.
  Phase 13+:  Tried Yahoo Finance (429 rate-limit from GHA IPs) and Twelve Data
              (KRU only on paid Ultra plan). Returning to Stooq without API key:
              the public CSV endpoint works without authentication.

Return shape (unchanged throughout — no downstream changes needed):
    {
        "ticker":     "KRU",
        "date":       "2026-06-12",
        "close":      412.0,
        "prev_close": 405.0,   # None when Stooq returns only 1 row
        "change_pct": 1.73,    # None when prev_close is None
    }
or None on complete failure.
"""

import csv
import io
import requests
from agent.retry import with_retries

_URL = "https://stooq.pl/q/d/l/"

# Stooq returns CSV with Polish column headers.
COL_DATE  = "Data"
COL_CLOSE = "Zamkniecie"


def fetch_stock_quote(ticker: str, exchange: str) -> dict | None:
    """
    Fetch the latest closing price for *ticker* from Stooq.pl.

    Args:
        ticker:   Symbol as stored in config.yaml, e.g. "KRU".
        exchange: Not used for the request (Stooq is GPW-focused) but kept
                  in the signature for interface consistency.

    Returns:
        Dict with ticker/date/close/prev_close/change_pct, or None on failure.
        change_pct is None when only 1 row is returned (prev_close unavailable);
        the render layer shows "(change: —)" in that case.
    """
    symbol = ticker.lower()   # Stooq uses bare lowercase ticker: "kru"

    try:
        def _do_request():
            r = requests.get(
                _URL,
                params={"s": symbol, "i": "d"},
                timeout=10,
            )
            # 4xx is a deterministic rejection — don't retry.
            if 400 <= r.status_code < 500:
                raise ValueError(
                    f"Stooq {r.status_code} for {ticker}: {r.text[:300]}"
                )
            r.raise_for_status()   # 5xx → HTTPError → retried normally
            return r

        resp = with_retries(
            _do_request, attempts=3, base_delay=1.0,
            exceptions=(requests.RequestException,),   # ValueError not listed → no retry
            label="stocks",
        )

        text = resp.text.strip()

        # Valid CSV starts with "Data" (Polish for Date).
        # Any other response is an error page or redirect.
        if not text.startswith("Data"):
            print(f"[stocks] unexpected Stooq response for {ticker} "
                  f"(first 200 chars): {text[:200]!r}")
            return None

        rows = list(csv.DictReader(io.StringIO(text)))

        if not rows:
            print(f"[stocks] Stooq returned 0 data rows for {ticker}")
            return None

        latest = rows[-1]
        close  = float(latest[COL_CLOSE])

        # Stooq may return only 1 row (latest close only) depending on the
        # query.  Surface the price without a % change rather than failing.
        if len(rows) >= 2:
            prev_close = float(rows[-2][COL_CLOSE])
            change_pct = round((close - prev_close) / prev_close * 100, 2)
        else:
            print(f"[stocks] only 1 row returned for {ticker}; "
                  "showing close price without day-over-day change")
            prev_close = None
            change_pct = None

        return {
            "ticker":     ticker.upper(),
            "date":       latest[COL_DATE],
            "close":      close,
            "prev_close": prev_close,
            "change_pct": change_pct,
        }

    except Exception as exc:
        print(f"[stocks] unexpected error for {ticker}: {exc!r}")
        return None