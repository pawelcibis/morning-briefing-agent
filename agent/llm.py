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
You are advising on what to dress a young baby in for a very short pushchair journey to daycare.

Key context (read carefully before answering):
- The journey is ONLY 5 minutes long — brief cold exposure.
- The pushchair is WELL-PROTECTED from wind (good canopy and footmuff shield the baby).
- Therefore: do NOT over-layer and do NOT worry about wind chill.
- Recommend ONE simple outfit appropriate for the temperature. Two items only if the
  temperature genuinely demands it (e.g. a base layer + warm suit below 5 °C).
  NEVER recommend three or more layers.
- pushchair_extras: "Add rain cover" if rain probability is ≥ 40%. Empty string "" otherwise.
  Do not mention footmuffs, blankets, or other pushchair items.
- pick_up_note: always return empty string "". Spare clothes are kept at daycare.

Respond ONLY with a JSON object — no markdown, no commentary:
{"outfit": "...", "pushchair_extras": "...", "pick_up_note": ""}
"""


def baby_clothing_recommendation(
    age_months: float,
    drop_off_weather: dict,
    pickup_weather: dict,
    midday_alerts: list | None = None,
    language: str = "en",
) -> dict:
    """
    Ask Claude Haiku what to dress the baby in for drop-off.

    The revised prompt (Phase 14) focuses on a 5-minute, wind-protected pushchair
    journey: minimal outfit, rain cover only when needed, pick_up_note always empty
    (spare clothes are kept at crèche).

    Falls back gracefully if the API key is missing or the call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "outfit": "(ANTHROPIC_API_KEY not set — LLM skipped)",
            "pushchair_extras": "",
            "pick_up_note": "",
        }

    # Only temperature and rain matter — pushchair blocks wind and the journey
    # is 5 minutes, so pick-up weather and midday alerts are not relevant here.
    user_msg = (
        f"Baby age: {age_months} months.\n"
        f"Drop-off (08:00): {drop_off_weather['temp_c']:.1f}°C, "
        f"{drop_off_weather['rain_pct']}% rain probability.\n"
        f"What should the baby wear for the short pushchair journey to daycare?"
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
                "max_tokens": 200,
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