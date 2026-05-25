import json
import os

import requests
#from anthropic import Anthropic  # already imported at top of llm.py — don't duplicate

_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL   = "claude-haiku-4-5-20251001"

_CYCLING_SYSTEM = """\
You are a practical cycling commuter clothing advisor.
Given morning and afternoon weather forecasts and clothing sets, output two things:
1. What to WEAR leaving home in the morning (full outfit)
2. What to PACK in the bag for the afternoon return trip

Rules:
- Apply morning wet_add items if morning rain_pct >= wet_threshold.
  "replaces medium jacket" in wet_add means: remove medium jacket, wear rain jacket instead.
  Thick winter jacket is never replaced by rain jacket — add rain jacket on top if needed.
- For afternoon pack: only list items genuinely needed for worse afternoon conditions.
  If afternoon is simply warmer, note which morning layers to skip on the return (pack nothing).
- Be specific — list actual items, not categories.
- Respond ONLY with a JSON object, no markdown, no commentary:
  {"wear": "...", "pack": "..."}
"""


def cycling_clothing_recommendation(
    morning: dict,
    afternoon: dict,
    morning_band: dict,
    afternoon_band: dict,
    wet_threshold: int,
) -> dict:
    """
    Ask Claude Haiku what to wear in the morning and what to pack for the return.
    Returns {"wear": "...", "pack": "..."}.
    Falls back gracefully if the API key is missing or the call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "wear": morning_band["dry"],
            "pack": "(ANTHROPIC_API_KEY not set — LLM skipped)",
        }

    user_msg = (
        f"Morning ({morning['time']}): {morning['temp_c']:.1f}°C, "
        f"{morning['wind_ms']} m/s {morning['wind_dir']}, "
        f"{morning['rain_pct']}% rain, {morning['cloud_label']}\n"
        f"Morning dry set:     {morning_band['dry']}\n"
        f"Morning wet add-ons: {morning_band.get('wet_add', '')}\n"
        f"\n"
        f"Afternoon ({afternoon['time']}): {afternoon['temp_c']:.1f}°C, "
        f"{afternoon['wind_ms']} m/s {afternoon['wind_dir']}, "
        f"{afternoon['rain_pct']}% rain, {afternoon['cloud_label']}\n"
        f"Afternoon dry set:     {afternoon_band['dry']}\n"
        f"Afternoon wet add-ons: {afternoon_band.get('wet_add', '')}\n"
        f"\n"
        f"Wet threshold: {wet_threshold}%"
    )

    try:
        resp = requests.post(
            _API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": _MODEL,
                "max_tokens": 300,
                "system": _CYCLING_SYSTEM,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"].strip()
        # Strip markdown fences if the model adds them despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as exc:
        return {"wear": morning_band["dry"], "pack": f"(LLM error: {exc})"}
    
# If the existing file doesn't already have a module-level _client, reuse the
# pattern it has. The skeleton below assumes you create the client per call;
# adjust to match your existing style.
_BABY_SYSTEM = """\
You are advising on what to dress a young baby in for daycare.
The baby travels in a pushchair, so they are NOT self-warming through movement —
cold air and wind chill matter more than for an active toddler.
Respond ONLY with a JSON object, no markdown, no commentary:
{"outfit": "...", "pushchair_extras": "...", "pick_up_note": "..."}
"""


def baby_clothing_recommendation(
    age_months: float,
    drop_off_weather: dict,
    pickup_weather: dict,
    midday_alerts: list | None = None,
    language: str = "en",
) -> dict:
    """
    Ask Claude Haiku what to dress the baby in for drop-off, what to put
    in the pushchair, and whether pick-up conditions need adjustment.
    Falls back gracefully if the API key is missing or the call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "outfit": "(ANTHROPIC_API_KEY not set — LLM skipped)",
            "pushchair_extras": "",
            "pick_up_note": "",
        }

# Format midday alerts for the prompt (empty string if none).
    midday_section = ""
    if midday_alerts:
        alert_lines = "\n".join(f"  - {a}" for a in midday_alerts)
        midday_section = (
            f"\nMidday conditions (between drop-off and pick-up):\n"
            f"{alert_lines}\n"
            f"Factor this into pushchair_extras (e.g. rain cover) "
            f"and pick_up_note if relevant.\n"
        )

    user_msg = (
        f"Baby age: {age_months} months. Language: {language}.\n"
        f"\n"
        f"Drop-off (08:00): {drop_off_weather['temp_c']:.1f}°C, "
        f"{drop_off_weather['wind_ms']} m/s {drop_off_weather['wind_dir']}, "
        f"{drop_off_weather['rain_pct']}% rain, {drop_off_weather['cloud_label']}\n"
        f"\n"
        f"Pick-up (16:15): {pickup_weather['temp_c']:.1f}°C, "
        f"{pickup_weather['wind_ms']} m/s {pickup_weather['wind_dir']}, "
        f"{pickup_weather['rain_pct']}% rain, {pickup_weather['cloud_label']}\n"
        f"{midday_section}"
        f"\n"
        f"Fields to fill:\n"
        f"  outfit           — full outfit for drop-off\n"
        f"  pushchair_extras — items for/over the pushchair (rain cover, blanket, etc.)\n"
        f"  pick_up_note     — one sentence on pick-up adjustment, or empty string\n"
    )

    try:
        resp = requests.post(
            _API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": _MODEL,
                "max_tokens": 400,
                "system": _BABY_SYSTEM,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        return {
            "outfit": data.get("outfit", ""),
            "pushchair_extras": data.get("pushchair_extras", ""),
            "pick_up_note": data.get("pick_up_note", ""),
        }
    except Exception as exc:
        return {
            "outfit": f"(LLM error: {exc})",
            "pushchair_extras": "",
            "pick_up_note": "",
        }