"""
Running block.

One slot per day at the configured time (default 07:00) and location
(default Winterthur 8400). Rule-based clothing recommendation pulled from
running_clothing.yaml (inlined into config under workouts.running.clothing_bands).

Phase 11 addition: MeteoSwiss icing/frost alerts for the running postcode,
filtered to the workout time window.

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
        "alerts":  ["Frost warning (level 2) 04:00–09:00"],  # [] if none
        "clothing": {
            "dry":         "long-sleeved top, shorts, standard socks",
            "wet":         "cap",
            "wet_active":  False,
        },
    }

Returns None only if the weather fetch fails completely.
"""

from agent.fetchers.weather import fetch_hourly, filter_hours, degrees_to_compass
from agent.fetchers.alerts import fetch_meteoswiss_alerts, format_alert_line


def _cloud_label(cloud_pct, labels_cfg):
    if cloud_pct is None:
        return "unknown"
    for label, (lo, hi) in labels_cfg.items():
        if lo <= cloud_pct <= hi:
            return label
    return "unknown"


def _select_band(temp_c, bands):
    for band in bands:
        if temp_c < band["max_c"]:
            return band
    return bands[-1]


def _alerts_for_slot(raw_alerts: list[dict], slot_time: str) -> list[str]:
    """Filter MeteoSwiss alerts to those covering the workout time slot."""
    if not raw_alerts:
        return []

    result = []
    slot_h = int(slot_time.split(":")[0])

    for alert in raw_alerts:
        start = alert.get("start")
        end   = alert.get("end")

        if not start and not end:
            result.append(format_alert_line(alert))
            continue

        try:
            start_h = int(start[11:13]) if start and len(start) >= 13 else 0
            end_h   = int(end[11:13])   if end   and len(end)   >= 13 else 23
            if start_h <= slot_h <= end_h:
                result.append(format_alert_line(alert))
        except (ValueError, TypeError):
            result.append(format_alert_line(alert))

    return result


def build_running_block(cfg, target_date):
    run_cfg = cfg["workouts"]["running"]
    loc     = run_cfg["location"]
    bands   = run_cfg["clothing_bands"]
    cloud_labels_cfg = cfg["cloud_cover_labels"]
    wet_threshold    = cfg.get("wet_threshold_pct", 30)

    try:
        hourly = fetch_hourly(latitude=loc["lat"], longitude=loc["lon"])
    except Exception as e:
        print(f"[running] weather fetch failed: {e}")
        return None

    slot_hour = int(run_cfg["times"][0].split(":")[0])
    rows = filter_hours(hourly, target_date, [slot_hour])
    if not rows:
        print(f"[running] no weather row for hour {slot_hour} on {target_date}")
        return None
    w = rows[0]

    temp_c   = w["temperature_c"]
    rain_pct = w["precipitation_probability_pct"]
    band     = _select_band(temp_c, bands)
    wet_active = rain_pct is not None and rain_pct >= wet_threshold

    # Phase 11: MeteoSwiss icing/frost alerts for running postcode.
    alert_cfg    = cfg.get("alerts", {}).get("meteoswiss", {})
    postcode     = str(loc.get("postcode", "8400"))
    severity_min = alert_cfg.get("severity_min", 2)
    raw_alerts   = fetch_meteoswiss_alerts(postcode, severity_min)
    slot_time    = run_cfg["times"][0]
    alerts       = _alerts_for_slot(raw_alerts, slot_time)

    return {
        "location": {"postcode": loc["postcode"], "city": loc["city"]},
        "date":     target_date.strftime("%A, %d %B %Y"),
        "slot": {
            "time":        slot_time,
            "temp_c":      temp_c,
            "wind_ms":     w["windspeed_ms"],
            "wind_dir":    degrees_to_compass(w["winddirection_deg"]),
            "rain_pct":    rain_pct,
            "cloud_label": _cloud_label(w["cloudcover_pct"], cloud_labels_cfg),
        },
        "alerts":  alerts,   # list[str], [] if quiet
        "clothing": {
            "dry":        band["dry"],
            "wet":        band.get("wet", ""),
            "wet_active": wet_active,
        },
    }