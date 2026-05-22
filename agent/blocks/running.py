"""
Running block.

One slot per day at the configured time (default 07:00) and location
(default Winterthur 8400). Rule-based clothing recommendation pulled from
running_clothing.yaml (inlined into config under workouts.running.clothing_bands).

Block return shape:
    {
        "location":   {"postcode": ..., "city": ...},
        "date":       "Tuesday, 26 May 2026",
        "slot": {
            "time":         "07:00",
            "temp_c":       12.3,
            "wind_ms":      2.1,
            "wind_dir":     "NE",
            "rain_pct":     15,
            "cloud_label":  "Partially sunny",
        },
        "clothing": {
            "dry":         "long-sleeved top, shorts, standard socks",
            "wet":         "cap",          # may be ""
            "wet_active":  False,          # True if precip >= wet_threshold
        },
    }

Returns None only if the weather fetch fails completely (failure resilience).
"""

from datetime import datetime
from agent.fetchers.weather import fetch_hourly, filter_hours, degrees_to_compass


def _cloud_label(cloud_pct, labels_cfg):
    """Map 0–100% cloud cover to a 4-level human label using config thresholds."""
    if cloud_pct is None:
        return "unknown"
    for label, (lo, hi) in labels_cfg.items():
        if lo <= cloud_pct <= hi:
            return label
    return "unknown"


def _select_band(temp_c, bands):
    """Find the first band where temp_c < band['max_c']. Falls back to last band."""
    for band in bands:
        if temp_c < band["max_c"]:
            return band
    return bands[-1]


# def _truncate_to_hour(hhmm):
#     """'07:00' -> '07:00'; '07:30' -> '07:00'. Open-Meteo serves hourly data at :00."""
#     return hhmm.split(":")[0] + ":00"


def build_running_block(cfg, target_date):
    """
    Build the structured running block for `target_date` (a datetime.date).

    Args:
        cfg: full loaded config dict (with clothing_bands inlined under
             cfg['workouts']['running']['clothing_bands']).
        target_date: datetime.date — the day we're forecasting for.

    Returns:
        dict (block) or None on fetch failure.
    """
    run_cfg = cfg["workouts"]["running"]
    loc = run_cfg["location"]
    bands = run_cfg["clothing_bands"]
    cloud_labels_cfg = cfg["cloud_cover_labels"]
    wet_threshold = cfg.get("wet_threshold_pct", 30)
    #slot_time = _truncate_to_hour(run_cfg["times"][0])  # e.g. "07:00"

    # Fetch hourly weather for the location.
    try:
        hourly = fetch_hourly(latitude=loc["lat"], longitude=loc["lon"])
    except Exception as e:
        print(f"[running] weather fetch failed: {e}")
        return None

    # Pick the hour matching slot_time on target_date.
    slot_hour = int(run_cfg["times"][0].split(":")[0])  # "07:00" → 7
    rows = filter_hours(hourly, target_date, [slot_hour])
    if not rows:
        print(f"[running] no weather row for hour {slot_hour} on {target_date}")
        return None
    w = rows[0]

    temp_c = w["temperature_c"]
    rain_pct = w["precipitation_probability_pct"]
    band = _select_band(temp_c, bands)
    wet_active = rain_pct is not None and rain_pct >= wet_threshold

    return {
        "location": {"postcode": loc["postcode"], "city": loc["city"]},
        "date": target_date.strftime("%A, %d %B %Y"),
        "slot": {
            "time": run_cfg["times"][0],
            "temp_c": temp_c,
            "wind_ms": w["windspeed_ms"],
            "wind_dir": degrees_to_compass(w["winddirection_deg"]),
            "rain_pct": rain_pct,
            "cloud_label": _cloud_label(w["cloudcover_pct"], cloud_labels_cfg),
        },
        "clothing": {
            "dry": band["dry"],
            "wet": band.get("wet", ""),
            "wet_active": wet_active,
        },
    }