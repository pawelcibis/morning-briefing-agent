"""
Fetches daily stock price data from Stooq.pl (free, requires API key).

Stooq returns Polish column headers:
  Data, Otwarcie, Najwyzszy, Najnizszy, Zamkniecie, Wolumen
  (Date, Open,    High,      Low,       Close,       Volume)

API key obtained once from: https://stooq.pl/q/d/?s=kru&get_apikey
Store as environment variable STOOQ_API_KEY (and GitHub Secret of same name).
"""

import csv
import io
import os

import requests


STOOQ_URL = "https://stooq.pl/q/d/l/"

# Polish → English column mapping
COL_DATE  = "Data"
COL_CLOSE = "Zamkniecie"


def fetch_stock_quote(ticker: str, exchange: str) -> dict | None:
    """
    Fetch the latest closing price for a stock from Stooq.pl.

    Args:
        ticker:   e.g. "KRU"
        exchange: e.g. "WSE" (unused in the URL, kept for block metadata)

    Returns:
        {
            "ticker":     "KRU",
            "date":       "2026-05-22",
            "close":      12.34,
            "prev_close": 11.98,
            "change_pct": 3.01,
        }
    or None on any failure.
    """
    api_key = os.environ.get("STOOQ_API_KEY", "")
    if not api_key:
        # §6.3: fetchers never raise — they return None so the digest still
        # sends with a "missing" marker. (Previously this raised, which crashed
        # the whole run if the secret was absent.)
        print(
            "[stocks] STOOQ_API_KEY not set — skipping stock fetch. "
            "Get a key at https://stooq.pl/q/d/?s=kru&get_apikey"
        )
        return None

    symbol = ticker.lower()   # Stooq uses bare ticker: "kru"

    # Note: d1/d2 date-range params cause a 404 with the free API key tier —
    # Stooq doesn't support range queries through this endpoint+key combination.
    # Without them Stooq may return just 1 row (the latest close); we handle
    # that gracefully below by returning prev_close=None.

    try:
        from agent.retry import with_retries

        def _do_request():
            r = requests.get(
                STOOQ_URL,
                params={"s": symbol, "i": "d", "apikey": api_key},
                timeout=10,
            )
            r.raise_for_status()
            return r

        resp = with_retries(
            _do_request, attempts=3, base_delay=0.5,
            exceptions=(requests.RequestException,), label="stocks",
        )

        text = resp.text.strip()

        # Guard: Stooq returns a Polish error page if the key/ticker is wrong.
        # Valid CSV always starts with "Data" (Polish for Date).
        if not text.startswith("Data"):
            print(f"[stocks] unexpected Stooq response for {ticker} "
                  f"(first 200 chars): {text[:200]!r}")
            return None

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            print(f"[stocks] Stooq returned 0 data rows for {ticker}")
            return None

        latest = rows[-1]
        close  = float(latest[COL_CLOSE])

        # If we got at least 2 rows, compute the day-over-day change.
        # If Stooq returns only 1 row (latest close only), we surface the
        # price without a % change rather than silently dropping the block.
        if len(rows) >= 2:
            prev_close = float(rows[-2][COL_CLOSE])
            change_pct = round((close - prev_close) / prev_close * 100, 2)
        else:
            print(f"[stocks] only 1 row returned for {ticker}; "
                  f"showing close price without change")
            prev_close = None
            change_pct = None

        latest   = rows[-1]   # most-recent trading day
        previous = rows[-2]

        close      = float(latest[COL_CLOSE])
        prev_close = float(previous[COL_CLOSE])
        change_pct = round((close - prev_close) / prev_close * 100, 2)

        return {
            "ticker":     ticker.upper(),
            "date":       latest[COL_DATE],
            "close":      close,
            "prev_close": prev_close,   # None when Stooq returned only 1 row
            "change_pct": change_pct,   # None when prev_close unavailable
        }

    except Exception:
        return None