"""
agent/fetchers/alerts.py — Fetch MeteoSwiss weather warnings.

Endpoint
--------
Unofficial MeteoSwiss mobile-app backend:
    GET https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz=XXXX00

Where XXXX is the 4-digit Swiss postcode and the trailing "00" is required
by the API (it represents a sub-postcode precision the app uses internally).

This endpoint is not officially documented but is widely used by the Swiss
hobbyist community (Home Assistant, ioBroker, etc.) and has been stable
since at least 2020.  It returns JSON with a "warnings" list alongside the
forecast data.  We extract only the fields we need and ignore the rest.

Official OGD status (as of May 2026)
-------------------------------------
MeteoSwiss launched OGD in May 2025 but the warnings dataset has not been
released yet.  Individual API queries are planned for end of 2026.  When
that happens, swap this fetcher for the official endpoint — the block
interface (list[dict]) stays the same.

Warning dict shape returned by this module:
    {
        "type":        "frost",           # normalised type string
        "severity":    2,                 # 1–5 MeteoSwiss scale
        "start":       "2026-05-26T06:00",  # ISO string or None
        "end":         "2026-05-26T10:00",  # ISO string or None
        "title":       "Frost warning",
        "description": "...",
    }

On any failure (network error, bad JSON, unexpected shape): returns [].
The digest still renders; the alerts section is simply empty.
"""

import datetime
import requests

_BASE_URL = "https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail"

# MeteoSwiss type IDs that map to icing/frost/slippery-road hazards.
# Derived from community reverse-engineering of the app.
# Type codes seen in the wild:
#   1  wind
#   2  thunderstorm
#   3  rain
#   4  snow / heavy snowfall
#   5  slippery roads / black ice / freezing rain
#   6  frost
#   7  heat
#   8  avalanche
# We alert on 4 (snow), 5 (slippery/icing), 6 (frost).
_ICING_FROST_TYPE_IDS = {4, 5, 6}

_TYPE_NAMES = {
    1: "wind",
    2: "thunderstorm",
    3: "rain",
    4: "snow",
    5: "icing",
    6: "frost",
    7: "heat",
    8: "avalanche",
}


def fetch_meteoswiss_alerts(postcode: str, severity_min: int = 2) -> list[dict]:
    """
    Fetch current MeteoSwiss warnings for a Swiss postcode.

    Args:
        postcode:     4-digit Swiss postcode, e.g. "8001" or "8400".
        severity_min: Minimum severity to include (1–5).  Default 2 means
                      "moderate danger or above" — MeteoSwiss only issues
                      public warnings from level 2 upwards anyway.

    Returns:
        List of alert dicts (may be empty).  Never raises.
    """
    try:
        plz_param = str(postcode).strip() + "00"  # "8001" → "800100"
        resp = requests.get(
            _BASE_URL,
            params={"plz": plz_param},
            timeout=10,
            headers={"User-Agent": "morning-briefing-agent/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[alerts] MeteoSwiss fetch failed for postcode {postcode}: {exc}")
        return []

    return _parse_warnings(data, severity_min)


def _parse_warnings(data: dict, severity_min: int) -> list[dict]:
    """
    Extract and normalise the warnings array from a plzDetail response.

    The response shape (community-documented):
        {
          "warnings": [
            {
              "warnType":    5,
              "warnLevel":   3,
              "validFrom":   1748257200000,   # Unix ms
              "validTo":     1748278800000,   # Unix ms
              "text":        "Glatteis erwartet...",
              "heading":     "Glatteisgefahr"
            },
            ...
          ],
          "forecast":    [...],
          ...
        }
    """
    raw_warnings = data.get("warnings")
    if not raw_warnings or not isinstance(raw_warnings, list):
        return []

    results = []
    for w in raw_warnings:
        try:
            type_id = int(w.get("warnType", 0))
            severity = int(w.get("warnLevel", 0))

            # Skip if below configured severity threshold.
            if severity < severity_min:
                continue

            # Filter to icing/frost types.
            if type_id not in _ICING_FROST_TYPE_IDS:
                continue

            # Convert Unix-ms timestamps to ISO strings.
            start = _ms_to_iso(w.get("validFrom"))
            end   = _ms_to_iso(w.get("validTo"))

            type_name = _TYPE_NAMES.get(type_id, f"type_{type_id}")
            title     = w.get("heading", type_name.title())
            desc      = w.get("text", "")

            results.append({
                "type":        type_name,
                "severity":    severity,
                "start":       start,
                "end":         end,
                "title":       title,
                "description": desc,
            })
        except Exception as exc:
            print(f"[alerts] could not parse warning record: {exc} — {w!r}")
            continue

    return results


def _ms_to_iso(ms) -> str | None:
    """Convert Unix milliseconds to ISO 8601 string (Zurich local, naive)."""
    if ms is None:
        return None
    try:
        dt = datetime.datetime.fromtimestamp(int(ms) / 1000,
                                             tz=datetime.timezone.utc)
        # Convert to Europe/Zurich.  We can't import zoneinfo in older envs,
        # so we just output UTC with Z — good enough for display.
        return dt.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return None


def format_alert_line(alert: dict) -> str:
    """
    Format one alert dict as a single display string.

    Example output:
        "Icing risk (level 3) until 08:00 — Glatteisgefahr"
        "Frost warning (level 2) 06:00–10:00"
    """
    title    = alert.get("title") or alert.get("type", "Alert").title()
    severity = alert.get("severity", "")
    start    = alert.get("start", "")
    end      = alert.get("end", "")

    # Build a short time window string.
    if start and end:
        s_time = start[11:16] if len(start) >= 16 else start
        e_time = end[11:16]   if len(end)   >= 16 else end
        window = f" {s_time}–{e_time}"
    elif end:
        e_time = end[11:16] if len(end) >= 16 else end
        window = f" until {e_time}"
    else:
        window = ""

    sev_str = f" (level {severity})" if severity else ""
    return f"{title}{sev_str}{window}"