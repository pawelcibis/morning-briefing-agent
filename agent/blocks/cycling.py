from datetime import date

from agent.fetchers.weather import fetch_hourly, degrees_to_compass
from agent.fetchers.alerts import fetch_meteoswiss_alerts, format_alert_line


def _extract_slot(raw: list, target_date: date, slot_time: str) -> dict | None:
    hour = int(slot_time.split(":")[0])
    target_key = f"{target_date}T{hour:02d}:00"
    for record in raw:
        if record["time"] == target_key:
            return {
                "time":      slot_time,
                "temp_c":    record["temperature_c"],
                "wind_ms":   round(record["windspeed_ms"], 1),
                "wind_dir":  degrees_to_compass(record["winddirection_deg"]),
                "rain_pct":  record["precipitation_probability_pct"],
                "cloud_pct": record["cloudcover_pct"],
            }
    return None


def _cloud_label(cloud_pct: int, labels_cfg: dict) -> str:
    for label, bounds in labels_cfg.items():
        lo, hi = bounds
        if lo <= cloud_pct <= hi:
            return label
    return "Unknown"


def _find_band(temp_c: float, bands: list) -> dict:
    """Return the first band whose max_c >= temp_c (coldest-to-warmest order)."""
    for band in bands:
        if temp_c <= band["max_c"]:
            return band
    return bands[-1]


def _alerts_for_slots(raw_alerts: list[dict], slot_times: list[str]) -> list[str]:
    """
    Filter MeteoSwiss alerts to those whose window overlaps any slot time.

    We do a simple check: if an alert has no start/end, include it (be safe).
    If it has both, include it only if the alert window covers one of the
    workout slots.

    Returns formatted alert strings.
    """
    if not raw_alerts:
        return []

    result = []
    for alert in raw_alerts:
        start = alert.get("start")
        end   = alert.get("end")

        # If no timing info, include the alert — better safe than silent.
        if not start and not end:
            result.append(format_alert_line(alert))
            continue

        # Check if any slot time falls within (or near) the alert window.
        # Slot times are "06:30", "16:30" etc.; alert times are "HH:MM".
        # Simple heuristic: extract HH from slot and alert start/end.
        for slot_time in slot_times:
            slot_h = int(slot_time.split(":")[0])
            try:
                start_h = int(start[11:13]) if start and len(start) >= 13 else 0
                end_h   = int(end[11:13])   if end   and len(end)   >= 13 else 23
                if start_h <= slot_h <= end_h:
                    result.append(format_alert_line(alert))
                    break  # one match per alert is enough
            except (ValueError, TypeError):
                # Unparseable times → include the alert (be safe)
                result.append(format_alert_line(alert))
                break

    return result


def build_cycling_block(cfg: dict, target_date: date) -> dict:
    from agent.llm import cycling_clothing_recommendation

    cc  = cfg["workouts"]["cycling"]
    loc = cc["location"]

    raw = fetch_hourly(latitude=loc["lat"], longitude=loc["lon"])

    slots = []
    bands = []
    for slot_time in cc["times"]:
        data = _extract_slot(raw, target_date, slot_time)
        if data is None:
            slots.append({"time": slot_time, "error": "data missing from API response"})
            bands.append(None)
            continue
        data["cloud_label"] = _cloud_label(data["cloud_pct"], cfg["cloud_cover_labels"])
        slots.append(data)
        bands.append(_find_band(data["temp_c"], cc["clothing_bands"]))

    # Phase 11: MeteoSwiss icing/frost alerts for the cycling postcode.
    alert_cfg     = cfg.get("alerts", {}).get("meteoswiss", {})
    postcode      = str(loc.get("postcode", "8001"))
    severity_min  = alert_cfg.get("severity_min", 2)
    raw_alerts    = fetch_meteoswiss_alerts(postcode, severity_min)
    alerts        = _alerts_for_slots(raw_alerts, cc["times"])

    # LLM recommendation requires both slots
    clothing = {"wear": "n/a", "pack": "n/a"}
    if (
        len(slots) >= 2
        and "error" not in slots[0]
        and "error" not in slots[1]
        and bands[0] is not None
        and bands[1] is not None
    ):
        clothing = cycling_clothing_recommendation(
            slots[0], slots[1],
            bands[0], bands[1],
            cc.get("wet_threshold_pct", 30),
        )

    return {
        "location": f"{loc['city']} {loc['postcode']}",
        "date":     str(target_date),
        "slots":    slots,
        "alerts":   alerts,   # list[str], [] if none
        "clothing": clothing,
    }