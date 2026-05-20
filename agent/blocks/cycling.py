from datetime import date

from agent.fetchers.weather import fetch_hourly, degrees_to_compass


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
        "clothing": clothing,
    }