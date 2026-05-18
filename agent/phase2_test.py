"""
Phase 2 test: print tomorrow morning's cycling forecast (Zurich 8001).
Run from repo root: python -m agent.phase2_test
"""

from datetime import date, timedelta
from agent.fetchers.weather import fetch_hourly, filter_hours

# Zurich 8001 — cycling commute location
LAT, LON = 47.3769, 8.5417

# Target: tomorrow at 06:30 and 16:30 (cycling times from spec)
tomorrow = date.today() + timedelta(days=1)
target_hours = [6, 16]

print(f"Fetching forecast for Zurich 8001 on {tomorrow}...")
all_hours = fetch_hourly(LAT, LON)
morning_hours = filter_hours(all_hours, tomorrow, target_hours)

print(f"\n{'Time':<10} {'Temp (°C)':>10} {'Wind (m/s)':>10} {'Direction':>10} {'Rain %':>8} {'Cloud %':>8}")
print("-" * 62)
for row in morning_hours:
    print(
        f"{row['time'][11:16]:<10}"           # "06:00"
        f"{row['temperature_c']:>10.1f}"
        f"{row['windspeed_ms']:>10.1f}"
        f"{row['winddirection_deg']:>10.0f}°"
        f"{row['precipitation_probability_pct']:>8}"
        f"{row['cloudcover_pct']:>8}"
    )