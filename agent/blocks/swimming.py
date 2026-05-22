"""
Swimming block.

07:00 at Thalwil (Lake Zurich). Water temperature from agent.fetchers.lake.

Conditional rendering rules (SPEC §3.4 + §6.3):
  - If water temp < min_water_temp_to_show_c → return None (block omitted).
  - If water temp fetch fails (None) → still render the block; renderer shows
    "missing" for the temp field. The user sees we tried and failed.
  - Otherwise render normally.

Block return shape:
    {
        "location":     {"postcode": ..., "city": ..., "lake": "zurich"},
        "date":         "Tuesday, 26 May 2026",
        "swim_time":    "07:00",
        "water_temp_c": 16.5,      # or None if fetch failed
        "air": {"temp_c": ..., "wind_ms": ..., "rain_pct": ..., "cloud_label": ...},
    }
"""

from agent.fetchers.weather import fetch_hourly, filter_hours, degrees_to_compass
from agent.fetchers.lake import fetch_lake_temp_thalwil


def _cloud_label(cloud_pct, labels_cfg):
    if cloud_pct is None:
        return "unknown"
    for label, (lo, hi) in labels_cfg.items():
        if lo <= cloud_pct <= hi:
            return label
    return "unknown"


# def _truncate_to_hour(hhmm):
#     return hhmm.split(":")[0] + ":00"


def build_swimming_block(cfg, target_date):
    swim_cfg = cfg["workouts"]["swimming"]
    loc = swim_cfg["location"]
    threshold = swim_cfg.get("min_water_temp_to_show_c", 10)
    swim_time = swim_cfg["times"][0]  # e.g. "07:00"
    cloud_labels_cfg = cfg["cloud_cover_labels"]

    # 1. Fetch lake temperature first — drives the keep/skip decision.
    water_temp = fetch_lake_temp_thalwil()

    # Skip rule: only skip when we KNOW the temp is below threshold.
    # If fetch failed (water_temp is None) we still render with "missing".
    if water_temp is not None and water_temp < threshold:
        print(f"[swimming] water temp {water_temp}°C below threshold {threshold}°C — omitting block")
        return None

    # 2. Fetch air weather at swim time.
    try:
        hourly = fetch_hourly(latitude=loc["lat"], longitude=loc["lon"])
        swim_hour = int(swim_time.split(":")[0])            # "07:00" → 7
        rows = filter_hours(hourly, target_date, [swim_hour])
        if rows:
            w = rows[0]
            air = {
                "temp_c": w["temperature_c"],
                "wind_ms": w["windspeed_ms"],
                "wind_dir": degrees_to_compass(w["winddirection_deg"]),
                "rain_pct": w["precipitation_probability_pct"],
                "cloud_label": _cloud_label(w["cloudcover_pct"], cloud_labels_cfg),
            }
        else:
            air = None
    except Exception as e:
        print(f"[swimming] air-weather fetch failed: {e}")
        air = None

    return {
        "location": {
            "postcode": loc["postcode"],
            "city": loc["city"],
            "lake": swim_cfg.get("lake", "zurich"),
        },
        "date": target_date.strftime("%A, %d %B %Y"),
        "swim_time": swim_time,
        "water_temp_c": water_temp,
        "air": air,
    }