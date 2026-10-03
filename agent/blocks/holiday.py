"""
agent/blocks/holiday.py — Holiday mode (Phase 14).

During a configured holiday period the normal baby / cycling / running /
swimming blocks are switched off (see main._build_all_blocks) and replaced by
four holiday blocks for the period's location. Stocks and the Wednesday event
are unaffected.

    holiday_weather   ONE shared table: temp / wind / rain / cloud at the slot
                      times, plus rain and thunderstorm alerts. Everyone gets it.
    holiday_baby      LLM clothing advice for a day out with the pushchair.
    holiday_running   running clothing per slot, from running_clothing.yaml.
    holiday_swimming  water temperature — only if the period has `swimming`.

Periods live in config.yaml under `holiday.periods` and are matched against the
digest's TARGET date (inclusive). The 20:00 run builds the next day, so the
evening before a period starts is already in holiday mode, and the evening
before it ends is already back to normal.

Slot times are LOCAL time at the holiday location: every fetch passes the
period's IANA timezone to Open-Meteo, so "06:00" on Kos means 06:00 Athens time.

Conventions shared with every other block:
  * build_*(cfg, target_date) → dict, or None when not applicable / no data.
  * Expected failures never raise; main._safe_build is only the last net.

Weather is fetched ONCE per run per location (memoised in _hourly): the shared
table, the baby advice and the running clothing all read the same snapshot, and
an Open-Meteo outage costs one retry cycle instead of three.
"""

import datetime as _dt

from agent.fetchers.weather import fetch_hourly, filter_hours, degrees_to_compass
from agent.fetchers.marine import fetch_marine_hourly
from agent.llm import baby_holiday_clothing_recommendation

DEFAULT_SLOT_TIMES = ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
DEFAULT_ALERT_WINDOW = ["06:00", "21:00"]
DEFAULT_RAIN_ALERT_PCT = 40
_STORM_CODE_MIN = 95          # WMO weather code: 95 thunderstorm, 96/99 with hail


# ---------------------------------------------------------------------------
# Period lookup
# ---------------------------------------------------------------------------

def _as_date(value) -> _dt.date:
    """YAML gives datetime.date for an unquoted 2026-10-04; accept strings too."""
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    return _dt.date.fromisoformat(str(value).strip())


def active_period(cfg: dict, target_date, warn: bool = True) -> dict | None:
    """
    Return the holiday period covering target_date (inclusive), else None.

    The result is a shallow copy with start/end normalised to datetime.date.
    Malformed periods are skipped with a printed warning (warn=True) — a config
    typo must never abort a run. If periods overlap, the first match wins.
    """
    holiday_cfg = (cfg or {}).get("holiday") or {}
    for i, period in enumerate(holiday_cfg.get("periods") or [], start=1):
        try:
            start = _as_date(period["start"])
            end   = _as_date(period["end"])
            loc   = period["location"]
            for key in ("city", "lat", "lon", "timezone"):
                if loc.get(key) in (None, ""):
                    raise KeyError(f"location.{key}")
        except Exception as exc:
            if warn:
                print(f"[holiday] ignoring malformed period #{i}: {exc!r}")
            continue
        if start <= target_date <= end:
            return {**period, "start": start, "end": end}
    return None


def location_label(period: dict) -> str:
    """'Wrocław, PL' — city plus optional country code."""
    loc = period["location"]
    country = loc.get("country")
    return f"{loc['city']}, {country}" if country else str(loc["city"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_HOURLY_CACHE: dict = {}


def _reset_cache() -> None:
    """Forget memoised weather. Tests only — each GHA run is a fresh process."""
    _HOURLY_CACHE.clear()


def _hourly(loc: dict) -> list | None:
    """
    Hourly Open-Meteo rows for the holiday location, in the location's timezone.

    Memoised for the life of the process, failures included: if Open-Meteo is
    down, the first caller spends the retry budget and the other holiday blocks
    skip at once instead of repeating it.
    """
    key = (float(loc["lat"]), float(loc["lon"]), str(loc["timezone"]))
    if key not in _HOURLY_CACHE:
        try:
            _HOURLY_CACHE[key] = fetch_hourly(
                latitude=loc["lat"], longitude=loc["lon"], timezone=loc["timezone"],
            )
        except Exception as exc:
            print(f"[holiday] weather fetch failed: {exc}")
            _HOURLY_CACHE[key] = None
    return _HOURLY_CACHE[key]


def _hhmm(value) -> str:
    """Normalise a configured time. YAML 1.1 reads an unquoted 06:00 as the
    base-60 integer 360, so turn that form back into "06:00"."""
    if isinstance(value, int):
        return f"{value // 60:02d}:{value % 60:02d}"
    return str(value).strip()


def _hour(hhmm) -> int:
    return int(_hhmm(hhmm).split(":")[0])


def _slot_times(cfg: dict) -> list[str]:
    times = ((cfg.get("holiday") or {}).get("slot_times")) or DEFAULT_SLOT_TIMES
    return [_hhmm(t) for t in times]


def _cloud_label(cloud_pct, labels_cfg) -> str:
    if cloud_pct is None:
        return "unknown"
    for label, (lo, hi) in labels_cfg.items():
        if lo <= cloud_pct <= hi:
            return label
    return "unknown"


def _select_band(temp_c, bands):
    """Same rule as running.py: first band where temp_c < max_c."""
    for band in bands:
        if temp_c < band["max_c"]:
            return band
    return bands[-1]


def _age_in_months(birthdate, target_date) -> float:
    """Approximate age in months — good enough for clothing decisions."""
    if isinstance(birthdate, str):
        birthdate = _dt.date.fromisoformat(birthdate)
    return round((target_date - birthdate).days / 30.44, 1)


def _weather_slots(rows, target_date, slot_times, labels_cfg) -> list[dict]:
    """One dict per slot time; {"time", "error"} when the API has no such hour."""
    slots = []
    for t in slot_times:
        hits = filter_hours(rows, target_date, [_hour(t)])
        if not hits:
            slots.append({"time": t, "error": "data missing from API response"})
            continue
        r = hits[0]
        wind = r.get("windspeed_ms")
        direction = r.get("winddirection_deg")
        slots.append({
            "time":        t,
            "temp_c":      r.get("temperature_c"),
            "wind_ms":     round(wind, 1) if wind is not None else None,
            "wind_dir":    degrees_to_compass(direction) if direction is not None else "",
            "rain_pct":    r.get("precipitation_probability_pct"),
            "cloud_label": _cloud_label(r.get("cloudcover_pct"), labels_cfg),
        })
    return slots


def _span(hours: list[int]) -> str:
    hours = sorted(hours)
    if hours[0] == hours[-1]:
        return f"{hours[0]:02d}:00"
    return f"{hours[0]:02d}:00–{hours[-1]:02d}:00"


def _alerts(rows, target_date, holiday_cfg: dict) -> list[str]:
    """
    Hard-rule alerts over EVERY hour of the alert window (not only the slots):
      * rain probability ≥ threshold (default 40%, as for the crèche block)
      * thunderstorm: WMO weather code ≥ 95
    The span runs from the first to the last flagged hour.
    """
    window = holiday_cfg.get("alert_window") or DEFAULT_ALERT_WINDOW
    threshold = holiday_cfg.get("rain_alert_threshold_pct", DEFAULT_RAIN_ALERT_PCT)
    day = filter_hours(rows, target_date,
                       list(range(_hour(window[0]), _hour(window[1]) + 1)))

    alerts = []
    wet = [r for r in day
           if r.get("precipitation_probability_pct") is not None
           and r["precipitation_probability_pct"] >= threshold]
    if wet:
        peak = max(r["precipitation_probability_pct"] for r in wet)
        alerts.append(
            f"Rain likely {_span([int(r['time'][11:13]) for r in wet])} (peak {peak}%)")

    storm = [r for r in day if (r.get("weather_code") or 0) >= _STORM_CODE_MIN]
    if storm:
        alerts.append(
            f"Thunderstorm possible {_span([int(r['time'][11:13]) for r in storm])}")
    return alerts


def _base(period: dict, target_date) -> dict:
    """Fields every holiday block carries. `date` is an ISO string so it compares
    equal after the JSON round trip through state/last_run.json (see diff.py)."""
    loc = period["location"]
    return {
        "place":    location_label(period),
        "date":     target_date.isoformat(),
        "location": {
            "city":     loc["city"],
            "country":  loc.get("country"),
            "lat":      loc["lat"],
            "lon":      loc["lon"],
            "timezone": loc["timezone"],
        },
    }


def _water_temp(rows, target_date, slot_times) -> float | None:
    """Day average of the water temperature: mean over the slot hours, falling
    back to every non-null hour of the day if the slot hours are null."""
    day = target_date.isoformat()
    hours = {_hour(t) for t in slot_times}
    on_day = [r for r in rows
              if r["time"].startswith(day) and r.get("sea_temp_c") is not None]
    at_slots = [r["sea_temp_c"] for r in on_day if int(r["time"][11:13]) in hours]
    values = at_slots or [r["sea_temp_c"] for r in on_day]
    return round(sum(values) / len(values), 1) if values else None


# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------

def build_holiday_weather_block(cfg, target_date) -> dict | None:
    """
    Shared weather table for the holiday location.

    Shape:
        {"place": "Tigaki, GR", "date": "2026-10-11", "location": {...},
         "slots": [{"time": "06:00", "temp_c": 19.8, "wind_ms": 3.2,
                    "wind_dir": "N", "rain_pct": 0, "cloud_label": "Sunny"}, ...],
         "alerts": ["Rain likely 14:00–16:00 (peak 55%)", ...]}
    """
    period = active_period(cfg, target_date, warn=False)
    if period is None:
        return None
    rows = _hourly(period["location"])
    if rows is None:
        return None
    slots = _weather_slots(rows, target_date, _slot_times(cfg), cfg["cloud_cover_labels"])
    if all("error" in s for s in slots):
        print(f"[holiday_weather] no rows for {target_date} in the API response")
        return None
    return {
        **_base(period, target_date),
        "slots":  slots,
        "alerts": _alerts(rows, target_date, cfg.get("holiday") or {}),
    }


def build_holiday_baby_block(cfg, target_date) -> dict | None:
    """
    Baby clothing for a day out (LLM). Weather itself lives in holiday_weather.

    Shape:
        {"place": ..., "date": ..., "location": {...}, "baby_age_months": 9.2,
         "clothing": {"outfit": "...", "adjustments": "...", "extras": "..."}}
    """
    period = active_period(cfg, target_date, warn=False)
    if period is None:
        return None
    rows = _hourly(period["location"])
    if rows is None:
        return None
    slots = [s for s in _weather_slots(rows, target_date, _slot_times(cfg),
                                       cfg["cloud_cover_labels"])
             if "error" not in s]
    if not slots:
        return None

    age_months = _age_in_months(cfg["baby"]["birthdate"], target_date)
    alerts = _alerts(rows, target_date, cfg.get("holiday") or {})
    try:
        clothing = baby_holiday_clothing_recommendation(
            age_months=age_months, slots=slots, alerts=alerts,
            place=location_label(period),
        )
    except Exception as exc:          # the LLM helper never raises; belt and braces
        print(f"[holiday_baby] LLM clothing call failed: {exc}")
        clothing = {
            "outfit": "(LLM unavailable — dress for the temperatures above; "
                      "sun hat if sunny and warm)",
            "adjustments": "",
            "extras": "",
        }
    return {**_base(period, target_date),
            "baby_age_months": age_months,
            "clothing": clothing}


def build_holiday_running_block(cfg, target_date) -> dict | None:
    """
    Running clothing per slot from running_clothing.yaml (same table and wet
    rule as the normal running block). The renderer groups consecutive slots
    with identical clothing.

    Shape:
        {"place": ..., "date": ..., "location": {...},
         "slots": [{"time": "06:00", "temp_c": 12.1, "rain_pct": 10,
                    "dry": "...", "wet": "cap", "wet_active": False}, ...]}
    """
    period = active_period(cfg, target_date, warn=False)
    if period is None:
        return None
    run_cfg = (cfg.get("workouts") or {}).get("running") or {}
    bands = run_cfg.get("clothing_bands")
    if not bands:
        print("[holiday_running] running clothing table not loaded — skipping")
        return None
    wet_threshold = run_cfg.get("wet_threshold_pct", 30)

    rows = _hourly(period["location"])
    if rows is None:
        return None

    slots = []
    for s in _weather_slots(rows, target_date, _slot_times(cfg), cfg["cloud_cover_labels"]):
        if "error" in s or s.get("temp_c") is None:
            slots.append({"time": s["time"], "error": s.get("error", "temperature missing")})
            continue
        band = _select_band(s["temp_c"], bands)
        rain = s["rain_pct"]
        slots.append({
            "time":       s["time"],
            "temp_c":     s["temp_c"],
            "rain_pct":   rain,
            "dry":        band["dry"],
            "wet":        band.get("wet", ""),
            "wet_active": rain is not None and rain >= wet_threshold,
        })
    if all("error" in s for s in slots):
        return None
    return {**_base(period, target_date), "slots": slots}


def build_holiday_swimming_block(cfg, target_date) -> dict | None:
    """
    Water temperature at the period's swim spot (Open-Meteo Marine API).

    None if the period has no `swimming`, or if the water is known to be below
    workouts.swimming.min_water_temp_to_show_c (same rule as the normal block).
    A failed fetch still renders, with "missing" (same as the normal block).

    Shape:
        {"place": ..., "date": ..., "location": {...},
         "spot": "Tigaki beach", "water": "sea", "water_temp_c": 24.2}
    """
    period = active_period(cfg, target_date, warn=False)
    if period is None or not period.get("swimming"):
        return None
    swim = period["swimming"]
    loc = period["location"]

    rows = fetch_marine_hourly(swim.get("lat", loc["lat"]), swim.get("lon", loc["lon"]),
                               timezone=loc["timezone"])
    water = _water_temp(rows, target_date, _slot_times(cfg)) if rows else None

    threshold = ((cfg.get("workouts") or {}).get("swimming") or {}).get(
        "min_water_temp_to_show_c", 10)
    if water is not None and water < threshold:
        print(f"[holiday_swimming] water {water}°C below {threshold}°C — omitting block")
        return None

    return {
        **_base(period, target_date),
        "spot":         swim.get("name") or loc["city"],
        "water":        swim.get("water", "sea"),
        "water_temp_c": water,
    }