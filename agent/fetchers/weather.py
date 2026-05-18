"""
Fetches hourly weather forecast from Open-Meteo (no API key required).
Returns a list of dicts, one per hour, for the requested date range.
"""

import requests
from datetime import date, timedelta

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_hourly(latitude: float, longitude: float, timezone: str = "Europe/Zurich") -> list[dict]:
    """
    Fetch hourly forecast for the next 2 days.
    Returns a list of dicts with keys:
        time, temperature_c, windspeed_ms, winddirection_deg,
        precipitation_probability_pct, cloudcover_pct
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": [
            "temperature_2m",
            "windspeed_10m",
            "winddirection_10m",
            "precipitation_probability",
            "cloudcover",
        ],
        "wind_speed_unit": "ms",          # metres per second (spec uses m/s)
        "timezone": timezone,
        "forecast_days": 2,               # today + tomorrow
    }

    response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    response.raise_for_status()           # raises if HTTP 4xx/5xx
    data = response.json()

    hourly = data["hourly"]
    rows = []
    for i, time_str in enumerate(hourly["time"]):
        rows.append({
            "time": time_str,                                          # "2026-05-19T06:00"
            "temperature_c": hourly["temperature_2m"][i],
            "windspeed_ms": hourly["windspeed_10m"][i],
            "winddirection_deg": hourly["winddirection_10m"][i],
            "precipitation_probability_pct": hourly["precipitation_probability"][i],
            "cloudcover_pct": hourly["cloudcover"][i],
        })
    return rows


def filter_hours(rows: list[dict], target_date: date, hours: list[int]) -> list[dict]:
    """
    Filter rows to a specific date and list of hours (0–23).
    E.g. filter_hours(rows, tomorrow, [6, 7, 8])
    """
    date_str = target_date.isoformat()   # "2026-05-19"
    return [
        r for r in rows
        if r["time"].startswith(date_str)
        and int(r["time"][11:13]) in hours
    ]

def degrees_to_compass(degrees: float) -> str:
    """
    Convert wind direction from degrees (0–360) to compass label.
    16-point compass: N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW
    """
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    ]
    # Normalize to 0–360, then map to 16 sectors (each sector = 22.5°)
    idx = round((degrees % 360) / 22.5) % 16
    return directions[idx]