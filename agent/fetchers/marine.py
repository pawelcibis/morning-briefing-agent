"""
agent/fetchers/marine.py — sea surface temperature from the Open-Meteo Marine API.

Used by holiday mode for sea swimming spots (e.g. Tigaki, Kos). Same provider
as the weather fetcher: free, no API key, coordinate-based, so any coast works
without writing a new scraper per location.

    GET https://marine-api.open-meteo.com/v1/marine
        ?latitude=..&longitude=..&hourly=sea_surface_temperature
        &timezone=Europe/Athens&forecast_days=2

The marine endpoint picks the nearest SEA grid cell by default, so a point on
or just off the beach is fine. Values are hourly, in °C, in the requested
timezone. Some hours can be null (the underlying SST model is coarser than
hourly); callers must tolerate None values.

Contract (SPEC §6.3 invariant, applied properly to new code):
  * Returns a list of {"time": "2026-10-11T06:00", "sea_temp_c": 24.1 | None}
  * Returns None on ANY failure. Never raises.
  * 4xx (bad parameters) fails fast — retrying a deterministic error is pointless.
    Transient failures (timeouts, 5xx, connection resets) are retried 3x.
"""

import requests

from agent.retry import with_retries

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
REQUEST_TIMEOUT_S = 10


def fetch_marine_hourly(latitude: float, longitude: float,
                        timezone: str = "Europe/Zurich") -> list[dict] | None:
    """
    Hourly sea surface temperature for today + tomorrow at (latitude, longitude).

    Returns:
        list[dict]: [{"time": "YYYY-MM-DDTHH:MM", "sea_temp_c": float | None}, ...]
        None:       on any failure (network, HTTP error, unexpected payload).
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "sea_surface_temperature",
        "timezone": timezone,
        "forecast_days": 2,
    }

    def _do_request():
        resp = requests.get(MARINE_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        if 400 <= resp.status_code < 500:
            # Deterministic client error (e.g. bad timezone or coordinates).
            # ValueError is NOT in the retry list below, so with_retries
            # re-raises it immediately instead of retrying.
            raise ValueError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()          # 5xx → HTTPError → retried
        return resp.json()

    try:
        data = with_retries(
            _do_request, attempts=3, base_delay=0.5,
            exceptions=(requests.RequestException,), label="marine",
        )
        hourly = data["hourly"]
        times = hourly["time"]
        sst = hourly.get("sea_surface_temperature") or [None] * len(times)
        return [{"time": t, "sea_temp_c": sst[i]} for i, t in enumerate(times)]
    except Exception as exc:
        print(f"[marine] fetch failed: {exc}")
        return None


if __name__ == "__main__":
    # Manual smoke test (needs internet):  python -m agent.fetchers.marine
    # Tigaki beach, Kos — the configured holiday swim point.
    rows = fetch_marine_hourly(36.9000, 27.1823, timezone="Europe/Athens")
    if rows is None:
        print("Marine fetch failed")
    else:
        filled = [r for r in rows if r["sea_temp_c"] is not None]
        print(f"{len(rows)} hourly rows, {len(filled)} with a sea temperature")
        for r in rows[::6]:
            print(f"  {r['time']}  sea {r['sea_temp_c']} °C")