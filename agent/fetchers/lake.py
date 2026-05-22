"""
Lake water-temperature fetcher.

Source: https://www.badi-info.ch/_temp/zuerichsee-thalwil.htm
This page is a tiny static HTML wrapper around Eawag's Alplakes model output
for the Thalwil station (Seebäder Bürger I/II, ~0.65m depth). It's updated
daily and is much easier to consume than the Alplakes REST API directly
(which has no public docs).

Future work (Phase 10 — morning vs. evening editions):
  - Add a separate boat24 scraper for the next-day FORECAST (used in evening run).
  - Keep this badi-info source for current MEASUREMENT (used in morning run).

Returns degrees Celsius as a float, or None if anything fails.
"""

import re
import html as html_lib
import requests

# Module-level constants — easy to swap if the source changes.
THALWIL_URL = "https://www.badi-info.ch/_temp/zuerichsee-thalwil.htm"
REQUEST_TIMEOUT_S = 10

# Some sites (badi-info included) reject the default python-requests UA with 403.
# A standard browser UA is sufficient — we're just reading a public page.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}


def fetch_lake_temp_thalwil():
    """
    Fetch the current Lake Zurich water temperature at Thalwil.

    Returns:
        float: temperature in °C, e.g. 16.5
        None : on any failure (network, parse, etc.)

    Per the spec (§6.3), fetchers never raise — they return None on failure
    so the digest can still be sent with a "missing" marker.
    """
    try:
        resp = requests.get(THALWIL_URL, headers=_HEADERS, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[lake] HTTP error fetching badi-info: {e}")
        return None

    # The page wraps the temperature in HTML tags like:  <strong>16.5</strong>°C
    # Strip tags first so the regex can match cleanly on plain text.

    page = html_lib.unescape(resp.text)   # &deg; → °, &amp; → & etc.
    plain = re.sub(r"<[^>]+>", "", page)
    match = re.search(r"(\d+(?:\.\d+)?)\s*°\s*C", plain)
    if not match:
        print(f"[lake] couldn't find a temperature in the page text")
        return None

    try:
        return float(match.group(1))
    except ValueError:
        print(f"[lake] couldn't parse '{match.group(1)}' as a float")
        return None


if __name__ == "__main__":
    # Manual smoke test: `python -m agent.fetchers.lake`
    temp = fetch_lake_temp_thalwil()
    print(f"Lake Zurich @ Thalwil: {temp}°C" if temp is not None else "Lake fetch failed")