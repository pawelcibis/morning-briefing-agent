"""
Lake water-temperature fetcher.

*** TEMPORARY — LOCARNO / LAGO MAGGIORE VACATION OVERRIDE ***
Repointed from Lake Zurich (Thalwil, badi-info.ch) to Lago Maggiore for the
duration of a stay in Locarno. Revert this commit to restore the original
Thalwil source.

Source: https://www.boot24.ch/chde/service/temperaturen/
This is boot24.ch's overview page listing every larger Swiss lake with its
current "today" surface temperature (mean of the whole lake), updated daily
(data from MeteoNews). We read the Lago Maggiore row. The overview page is used
rather than the per-lake page because it is a single stable URL and reliably
served (the per-lake page intermittently 404s to non-browser clients).

NOTE: the public function name is kept as `fetch_lake_temp_thalwil` on purpose,
so agent/blocks/swimming.py needs no change and the whole switch reverts in one
commit.

Returns degrees Celsius as a float, or None if anything fails.
Per SPEC §6.3, fetchers never raise — they return None on failure so the digest
can still be sent with a "missing" marker.
"""

import re
import html as html_lib
import requests

# boot24.ch overview page — one stable URL that contains every lake's current
# temperature. We pick out the Lago Maggiore row by its per-lake link slug.
BOOT24_TEMPS_URL = "https://www.boot24.ch/chde/service/temperaturen/"
LAKE_ANCHOR = "lagomaggiore"     # appears in the row's <a href=".../lagomaggiore/">
REQUEST_TIMEOUT_S = 10

# boot24 (like badi-info) rejects the default python-requests UA. A standard
# browser UA is sufficient — we're just reading a public page.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}


def fetch_lake_temp_thalwil():
    """
    Fetch the current Lago Maggiore water temperature (see module note).

    Returns:
        float: temperature in °C, e.g. 26.0
        None : on any failure (network, parse, etc.)
    """
    from agent.retry import with_retries

    def _do_request():
        resp = requests.get(BOOT24_TEMPS_URL, headers=_HEADERS, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp

    try:
        resp = with_retries(
            _do_request, attempts=3, base_delay=0.5,
            exceptions=(requests.RequestException,), label="lake",
        )
    except requests.RequestException as e:
        print(f"[lake] HTTP error fetching boot24: {e}")
        return None

    page = html_lib.unescape(resp.text)   # &deg; → °, &#176; → °, &amp; → & etc.

    # Locate the Lago Maggiore row by its per-lake link slug, then read the first
    # temperature that follows it (the bold "today" cell, rendered like "26°").
    idx = page.lower().find(LAKE_ANCHOR)
    if idx == -1:
        print("[lake] Lago Maggiore row not found on boot24 page")
        return None

    # Bounded window after the anchor: prevents grabbing a later row's value if
    # this row's "today" cell is ever empty. The row's title/link text contains
    # no digits, so the first "<number>°" after the anchor is today's reading.
    window = re.sub(r"<[^>]+>", " ", page[idx: idx + 600])
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*°", window)
    if not match:
        print("[lake] couldn't find a temperature for Lago Maggiore")
        return None

    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        print(f"[lake] couldn't parse '{match.group(1)}' as a float")
        return None


if __name__ == "__main__":
    # Manual smoke test: `python -m agent.fetchers.lake`
    temp = fetch_lake_temp_thalwil()
    print(f"Lago Maggiore: {temp}°C" if temp is not None else "Lake fetch failed")