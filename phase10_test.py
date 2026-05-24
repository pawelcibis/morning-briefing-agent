"""
phase10_test.py

Phase 10 end-to-end test — proves state read/write and diff rendering
work correctly, entirely locally (no git, no state branch, no dispatch).

What this does:
  1. Build blocks for tomorrow  →  the "evening run" snapshot.
  2. Write them to state/last_run.json.
  3. Read the state back (simulating what the morning run would do).
  4. Build blocks again for the same date  →  identical values initially.
  5. Manually perturb a few fields to make visible deltas.
  6. Call diff_blocks() to compute what changed.
  7. Render the digest WITHOUT deltas  →  "evening" view.
  8. Render the digest WITH deltas     →  "morning" view.
  9. Print both side-by-side to the console.

Required env vars (same as phase9_test.py):
  ANTHROPIC_API_KEY, SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
  TELEGRAM_BOT_TOKEN, RECIPIENT_PAWEL_EMAIL, RECIPIENT_PAWEL_TELEGRAM,
  RECIPIENT_LILIANA_EMAIL, STOCKS_KRU_SHARES

Run:
  python phase10_test.py
"""

import copy
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agent.config import load_config
from agent.blocks.baby     import build_baby_block
from agent.blocks.cycling  import build_cycling_block
from agent.blocks.running  import build_running_block
from agent.blocks.swimming import build_swimming_block
from agent.blocks.stocks   import build_stocks_block
from agent.state  import read_state, write_state
from agent.diff   import diff_blocks
from agent.render import render_for_recipient

STATE_PATH = "state/last_run.json"


def _perturb(blocks: dict) -> dict:
    """
    Return a deep copy of blocks with some numeric fields nudged.
    These values are large enough to clear DEFAULT_THRESHOLDS in render.py,
    so the delta annotations will be visible in the output.

    Adjust as you like to test edge cases.
    """
    b = copy.deepcopy(blocks)

    # Cycling morning slot: +3 °C, +15% rain
    if b.get("cycling") and b["cycling"].get("slots"):
        for slot in b["cycling"]["slots"]:
            if slot.get("time") == "06:30" and "error" not in slot:
                slot["temp_c"]   = round(slot["temp_c"]   + 3.0, 1)
                slot["rain_pct"] = min(100, (slot["rain_pct"] or 0) + 15)

    # Running: -2 °C, wind +2 m/s
    if b.get("running") and b["running"].get("slot"):
        b["running"]["slot"]["temp_c"]  = round(b["running"]["slot"]["temp_c"]  - 2.0, 1)
        b["running"]["slot"]["wind_ms"] = round((b["running"]["slot"]["wind_ms"] or 0) + 2.0, 1)

    # Baby drop-off: +2 °C, pick-up +20% rain
    if b.get("baby"):
        if b["baby"].get("drop_off"):
            b["baby"]["drop_off"]["temp_c"] = round(b["baby"]["drop_off"]["temp_c"] + 2.0, 1)
        if b["baby"].get("pick_up"):
            b["baby"]["pick_up"]["rain_pct"] = min(100, (b["baby"]["pick_up"]["rain_pct"] or 0) + 20)

    # Swimming: +1.5 °C water
    if b.get("swimming") and b["swimming"].get("water_temp_c") is not None:
        b["swimming"]["water_temp_c"] = round(b["swimming"]["water_temp_c"] + 1.5, 1)

    return b


def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    cfg         = load_config()
    target_date = datetime.date.today() + datetime.timedelta(days=1)
    thresholds  = cfg.get("diff_thresholds")   # may be None if not yet in config.yaml

    # ------------------------------------------------------------------
    # Step 1 — Build "evening" blocks
    # ------------------------------------------------------------------
    _section("Step 1 — Building evening blocks")

    evening_blocks = {
        "baby":     build_baby_block(cfg, target_date),
        "cycling":  build_cycling_block(cfg, target_date),
        "running":  build_running_block(cfg, target_date),
        "swimming": build_swimming_block(cfg, target_date),
        "stocks":   build_stocks_block(cfg),
    }
    print(f"  target_date : {target_date}")
    for k, v in evening_blocks.items():
        status = "None (skipped)" if v is None else "built"
        print(f"  {k:<10} : {status}")

    # ------------------------------------------------------------------
    # Step 2 — Write state
    # ------------------------------------------------------------------
    _section("Step 2 — Writing state")
    write_state(STATE_PATH, evening_blocks, target_date)

    # ------------------------------------------------------------------
    # Step 3 — Read state back
    # ------------------------------------------------------------------
    _section("Step 3 — Reading state back")
    previous_state = read_state(STATE_PATH)
    print(f"  state target_date : {previous_state.get('target_date')}")
    print(f"  state block keys  : {list(previous_state.get('blocks', {}).keys())}")

    # ------------------------------------------------------------------
    # Step 4+5 — "Morning" blocks: same data, then perturbed
    # ------------------------------------------------------------------
    _section("Step 4+5 — Building morning blocks (perturbed)")
    morning_blocks = _perturb(evening_blocks)
    print("  Applied perturbations:")
    print("    cycling 06:30: temp_c +3.0, rain_pct +15")
    print("    running 07:00: temp_c -2.0, wind_ms  +2.0")
    print("    baby drop_off: temp_c +2.0")
    print("    baby pick_up:  rain_pct +20")
    print("    swimming:      water_temp_c +1.5")

    # ------------------------------------------------------------------
    # Step 6 — Compute deltas
    # ------------------------------------------------------------------
    _section("Step 6 — Diff")
    deltas = diff_blocks(morning_blocks, previous_state)
    if deltas:
        for k, v in sorted(deltas.items()):
            print(f"  {k:<40} {v:+.4f}")
    else:
        print("  (no deltas — previous state missing or all values identical)")

    # ------------------------------------------------------------------
    # Step 7 — Evening rendering (no deltas)
    # ------------------------------------------------------------------
    _section("Step 7 — Evening render (NO deltas)")
    evening_text = render_for_recipient(
        evening_blocks, target_date, role="full",
        deltas=None, thresholds=thresholds,
    )
    print(evening_text)

    # ------------------------------------------------------------------
    # Step 8 — Morning rendering (with deltas)
    # ------------------------------------------------------------------
    _section("Step 8 — Morning render (WITH deltas)")
    morning_text = render_for_recipient(
        morning_blocks, target_date, role="full",
        deltas=deltas, thresholds=thresholds,
    )
    print(morning_text)

    # ------------------------------------------------------------------
    # Step 9 — Summary
    # ------------------------------------------------------------------
    _section("Summary")
    print(f"  Evening digest : {len(evening_text)} chars")
    print(f"  Morning digest : {len(morning_text)} chars")
    print(f"  Deltas found   : {len(deltas)}")
    print()
    print("  Phase 10 complete. No dispatch was performed.")
    print("  Next: create the 'state' branch on GitHub (see SPEC §6.2 / Phase 10 notes).")


if __name__ == "__main__":
    main()