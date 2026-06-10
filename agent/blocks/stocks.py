"""
Builds the stocks block.
Reads tickers from config; reads shareholdings from environment (GitHub Secrets).
"""

import os

from agent.fetchers.stocks import fetch_stock_quote


def build_stocks_block(cfg: dict) -> dict:
    """
    Build the stocks block from config.

    cfg["stocks"] is a list of entries like:
        {ticker, exchange, shares_secret, currency}

    Shareholdings are read from os.environ[entry["shares_secret"]].

    Returns:
        {
            "tickers": [
                {
                    "ticker":          "KRU",
                    "exchange":        "WSE",
                    "currency":        "PLN",
                    "date":            "2026-05-22",
                    "close":           12.34,
                    "prev_close":      11.98,
                    "change_pct":      3.01,
                    "shares":          250,
                    "portfolio_value":  3085.0,
                    "portfolio_change":  90.0,
                    "error":           None,    # or error string
                },
                ...
            ]
        }
    """
    tickers = []

    for entry in cfg.get("stocks", []):
        ticker   = entry["ticker"]
        exchange = entry["exchange"]
        currency = entry.get("currency", "")

        # Read shareholding from environment variable
        shares_secret = entry["shares_secret"]
        shares_raw = os.environ.get(shares_secret, "")
        if not shares_raw:
            tickers.append({
                "ticker":          ticker,
                "exchange":        exchange,
                "currency":        currency,
                "date":            None,
                "close":           None,
                "prev_close":      None,
                "change_pct":      None,
                "shares":          None,
                "portfolio_value": None,
                "portfolio_change": None,
                "error":           f"Secret {shares_secret!r} not set in environment",
            })
            continue

        try:
            shares = int(shares_raw)
        except ValueError:
            tickers.append({
                "ticker":          ticker,
                "exchange":        exchange,
                "currency":        currency,
                "date":            None,
                "close":           None,
                "prev_close":      None,
                "change_pct":      None,
                "shares":          None,
                "portfolio_value": None,
                "portfolio_change": None,
                "error":           f"Secret {shares_secret!r} is not an integer: {shares_raw!r}",
            })
            continue

        # Fetch price data
        quote = fetch_stock_quote(ticker, exchange)

        if quote is None:
            tickers.append({
                "ticker":          ticker,
                "exchange":        exchange,
                "currency":        currency,
                "date":            None,
                "close":           None,
                "prev_close":      None,
                "change_pct":      None,
                "shares":          shares,
                "portfolio_value": None,
                "portfolio_change": None,
                "error":           "Price fetch failed (Stooq unavailable or bad response)",
            })
            continue

        portfolio_value  = round(quote["close"]      * shares, 2)
        portfolio_change = round((quote["close"] - quote["prev_close"]) * shares, 2)

        tickers.append({
            "ticker":          ticker,
            "exchange":        exchange,
            "currency":        currency,
            "date":            quote["date"],
            "close":           quote["close"],
            "prev_close":      quote["prev_close"],
            "change_pct":      quote["change_pct"],
            "shares":          shares,
            "portfolio_value":  portfolio_value,
            "portfolio_change": portfolio_change,
            "error":           None,
        })

    return {"tickers": tickers}