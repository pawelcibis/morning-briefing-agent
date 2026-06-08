"""
agent/blocks/wednesday_event.py

Wednesday outdoor evening event block (June–September only).

Appears in:
  * Tuesday evening briefing  → target_date is Wednesday → included
  * Wednesday morning update  → target_date is Wednesday → included
  Any other day               → returns None

What we check for the 18:00–22:00 window at Zurich 8001:

  a) TEMPERATURE (18:00–22:00)
       green  — all hours ≥ 20 °C
       amber  — ≥ 18 °C at 18:00 AND all hours ≥ 15 °C
       red    — anything colder

  b) RAIN RISK (18:00–21:00)
       green  — max probability = 0 %
       amber  — max probability 1–20 %  (+ intensity label)
       red    — max probability > 20 %  (+ intensity label)
     Intensity derived from Open-Meteo precipitation (mm/h):
       < 0.5  → light,  0.5–2.5 → moderate,  > 2.5 → heavy

  c) THUNDERSTORM (18:00–21:00)
       green  — no WMO weather_code ≥ 95 in the window
       red    — any code ≥ 95 (slight/moderate: 95, with hail: 96/99)

  overall_status = worst of (a, b, c): red > amber > green

Block return shape:
  {
      "location":     {"postcode": 8001, "city": "Zurich"},
      "date":         "Wednesday, 04 June 2026",
      "status":       "green" | "amber" | "red",
      "temperature":  {
          "slots":    [{"time": "18:00", "temp_c": 21.3}, …],  # 18–22 h
          "status":   "green" | "amber" | "red",
      },
      "rain":         {
          "slots":    [{"time": "18:00", "rain_pct": 10, "precip_mm_h": 0.2}, …],
          "status":   "green" | "amber" | "red",
          "max_pct":  10,
          "max_precip_mm_h": 0.2,
          "intensity_label":  "light" | "moderate" | "heavy" | "none",
      },
      "thunderstorm": {
          "present":  False,
          "status":   "green" | "red",
          "hours":    [],   # time strings ("18:00") where code ≥ 95
      },
  }
"""

from agent.fetchers.weather import fetch_hourly, filter_hours

# Eligibility window
_MONTHS = {6, 7, 8, 9}          # June–September
_WEEKDAY = 2                     # Wednesday (Mon=0)

# Time windows
_TEMP_HOURS  = [18, 19, 20, 21, 22]   # temperature check
_EVENT_HOURS = [18, 19, 20, 21]       # rain + thunderstorm check (finish by 21)

_STATUS_RANK = {"green": 0, "amber": 1, "red": 2}


def _worst(*statuses: str) -> str:
    return max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))


def _intensity_label(precip_mm_h: float | None) -> str:
    if precip_mm_h is None or precip_mm_h == 0:
        return "none"
    if precip_mm_h < 0.5:
        return "light"
    if precip_mm_h <= 2.5:
        return "moderate"
    return "heavy"


def build_wednesday_event_block(cfg, target_date) -> dict | None:
    """
    Build the Wednesday event block for a given target_date.

    Returns None if:
      * target_date is not a Wednesday, or
      * target_date.month is outside June–September, or
      * the weather fetch fails.
    """
    if target_date.weekday() != _WEEKDAY or target_date.month not in _MONTHS:
        return None

    event_cfg = cfg.get("wednesday_event", {})
    loc = event_cfg.get("location", {})

    lat = loc.get("lat")
    lon = loc.get("lon")
    if lat is None or lon is None:
        print("[wednesday_event] missing lat/lon in config.wednesday_event.location")
        return None

    try:
        hourly = fetch_hourly(latitude=lat, longitude=lon)
    except Exception as exc:
        print(f"[wednesday_event] weather fetch failed: {exc}")
        return None

    # --- Temperature (18–22h) ------------------------------------------------
    temp_rows = filter_hours(hourly, target_date, _TEMP_HOURS)
    temp_slots = [
        {"time": f"{int(r['time'][11:13]):02d}:00", "temp_c": r["temperature_c"]}
        for r in temp_rows
    ]
    temps = [s["temp_c"] for s in temp_slots if s["temp_c"] is not None]
    if temps:
        first_temp = temps[0]
        min_temp   = min(temps)
        if all(t >= 20 for t in temps):
            temp_status = "green"
        elif first_temp >= 18 and min_temp >= 15:
            temp_status = "amber"
        else:
            temp_status = "red"
    else:
        temp_status = "red"   # no data = assume worst

    # --- Rain risk (18–21h) --------------------------------------------------
    rain_rows = filter_hours(hourly, target_date, _EVENT_HOURS)
    rain_slots = [
        {
            "time":          f"{int(r['time'][11:13]):02d}:00",
            "rain_pct":      r["precipitation_probability_pct"],
            "precip_mm_h":   r.get("precipitation_mm_h"),
        }
        for r in rain_rows
    ]
    rain_probs  = [s["rain_pct"] for s in rain_slots if s["rain_pct"] is not None]
    precip_vals = [s["precip_mm_h"] or 0 for s in rain_slots]

    max_pct     = max(rain_probs,  default=0)
    max_precip  = max(precip_vals, default=0.0)
    intensity   = _intensity_label(max_precip) if max_pct > 0 else "none"

    if max_pct == 0:
        rain_status = "green"
    elif max_pct <= 20:
        rain_status = "amber"
    else:
        rain_status = "red"

    # --- Thunderstorm (18–21h) -----------------------------------------------
    thunder_hours = [
        f"{int(r['time'][11:13]):02d}:00"
        for r in rain_rows
        if r.get("weather_code") is not None and r["weather_code"] >= 95
    ]
    thunder_status  = "red" if thunder_hours else "green"

    # --- Overall -------------------------------------------------------------
    overall = _worst(temp_status, rain_status, thunder_status)

    return {
        "location":    {"postcode": loc.get("postcode"), "city": loc.get("city")},
        "date":        target_date.strftime("%A, %d %B %Y"),
        "status":      overall,
        "temperature": {
            "slots":  temp_slots,
            "status": temp_status,
        },
        "rain": {
            "slots":         rain_slots,
            "status":        rain_status,
            "max_pct":       max_pct,
            "max_precip_mm_h": max_precip,
            "intensity_label": intensity,
        },
        "thunderstorm": {
            "present": bool(thunder_hours),
            "status":  thunder_status,
            "hours":   thunder_hours,
        },
    }