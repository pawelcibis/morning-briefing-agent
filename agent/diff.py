"""
agent/diff.py — Compute per-field deltas for the morning update.

The morning run reads the previous evening's state, calls diff_blocks(),
and passes the result to the renderers. Each renderer annotates numeric
fields that changed by more than the configured threshold.

Return format — flat dict of {dot-path: delta_float}:
    {
        "baby.drop_off.temp_c":    2.1,
        "baby.pick_up.rain_pct":  -10.0,
        "cycling.06:30.temp_c":   -0.5,
        "cycling.16:30.wind_ms":   1.2,
        "running.07:00.temp_c":    0.8,
        "swimming.water_temp_c":   0.3,
        "swimming.air.temp_c":     1.0,
    }

Dot-path keys use the slot *time string* as the middle segment for
blocks that have named time slots (cycling, running). This keeps the
renderer look-up simple: f"cycling.{slot['time']}.temp_c".

Stocks are intentionally skipped (per Phase 10 spec notes).
"""


def diff_blocks(current: dict, previous_state: dict) -> dict:
    """
    Compute per-field numeric deltas (current − previous).

    Args:
        current:         Full blocks dict from this run
                         {"baby": ..., "cycling": ..., ...}.
        previous_state:  Dict loaded from state/last_run.json.
                         Expected shape: {"target_date": "...", "blocks": {...}}.
                         Pass {} (or read_state() result) if no prior state.

    Returns:
        Flat {dot-path: float} dict.  Empty dict when no previous state,
        or when blocks are structurally incompatible (None in either side).
    """
    if not previous_state:
        return {}

    prev = previous_state.get("blocks", {})
    deltas: dict = {}

    _diff_baby(current.get("baby"),       prev.get("baby"),       deltas)
    _diff_cycling(current.get("cycling"), prev.get("cycling"),    deltas)
    _diff_running(current.get("running"), prev.get("running"),    deltas)
    _diff_swimming(current.get("swimming"), prev.get("swimming"), deltas)
    # Stocks: skip (see module docstring).

    return deltas


# ---------------------------------------------------------------------------
# Per-block helpers
# ---------------------------------------------------------------------------

def _delta(prefix: str, field: str, cur_val, prev_val, out: dict) -> None:
    """
    Compute cur_val − prev_val and store under key f"{prefix}.{field}".

    Silently skips if either value is None or non-numeric.
    """
    if cur_val is None or prev_val is None:
        return
    try:
        d = round(float(cur_val) - float(prev_val), 4)
        out[f"{prefix}.{field}"] = d
    except (TypeError, ValueError):
        pass


def _diff_baby(cur: dict | None, prev: dict | None, out: dict) -> None:
    if cur is None or prev is None:
        return
    for slot_key in ("drop_off", "pick_up"):
        c_slot = cur.get(slot_key)  or {}
        p_slot = prev.get(slot_key) or {}
        for field in ("temp_c", "wind_ms", "rain_pct"):
            _delta(f"baby.{slot_key}", field, c_slot.get(field), p_slot.get(field), out)


def _diff_cycling(cur: dict | None, prev: dict | None, out: dict) -> None:
    if cur is None or prev is None:
        return
    # Index slots by time string; skip error slots.
    c_slots = {s["time"]: s for s in cur.get("slots",  []) if "error" not in s}
    p_slots = {s["time"]: s for s in prev.get("slots", []) if "error" not in s}
    for time_key, c_slot in c_slots.items():
        p_slot = p_slots.get(time_key)
        if p_slot is None:
            continue
        for field in ("temp_c", "wind_ms", "rain_pct"):
            _delta(f"cycling.{time_key}", field, c_slot.get(field), p_slot.get(field), out)


def _diff_running(cur: dict | None, prev: dict | None, out: dict) -> None:
    if cur is None or prev is None:
        return
    c_slot = cur.get("slot")  or {}
    p_slot = prev.get("slot") or {}
    time_key = c_slot.get("time", "07:00")
    for field in ("temp_c", "wind_ms", "rain_pct"):
        _delta(f"running.{time_key}", field, c_slot.get(field), p_slot.get(field), out)


def _diff_swimming(cur: dict | None, prev: dict | None, out: dict) -> None:
    if cur is None or prev is None:
        return
    _delta("swimming", "water_temp_c",
           cur.get("water_temp_c"), prev.get("water_temp_c"), out)
    c_air = cur.get("air")  or {}
    p_air = prev.get("air") or {}
    for field in ("temp_c", "wind_ms", "rain_pct"):
        _delta("swimming.air", field, c_air.get(field), p_air.get(field), out)