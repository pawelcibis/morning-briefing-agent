"""
phase11_test.py

Phase 11 end-to-end test — alert detection, MeteoSwiss fetcher, and rendering.

Flags:
  --mock-alerts   Inject fake icing/frost/rain alert strings into the finished
                  blocks (tests the RENDERING path only — LLM already ran).

  --mock-rain     Patch fetch_hourly to return 70% rain for every hour BEFORE
                  build_baby_block() runs. This forces _build_midday_alerts()
                  to fire AND passes the alerts into the LLM call, so you can
                  verify the full pipeline (tests the LLM path).

No dispatch — console only.

Run:
  python phase11_test.py                  # real data
  python phase11_test.py --mock-alerts   # verify alert rendering (no LLM re-call)
  python phase11_test.py --mock-rain     # verify LLM sees rain alert
"""

import copy
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agent.config import load_config
from agent.blocks.cycling  import build_cycling_block
from agent.blocks.running  import build_running_block
from agent.blocks.swimming import build_swimming_block
from agent.blocks.stocks   import build_stocks_block
from agent.render import render_for_recipient

MOCK_ALERTS = "--mock-alerts" in sys.argv
MOCK_RAIN   = "--mock-rain"   in sys.argv


# ---------------------------------------------------------------------------
# --mock-rain: patch fetch_hourly for the baby block only
# ---------------------------------------------------------------------------

def _build_baby_block_with_rain(cfg, target_date):
    """
    Build the baby block with fetch_hourly monkey-patched so every hour
    returns 70% precipitation probability. This triggers _build_midday_alerts()
    and passes the resulting alerts into the LLM call — testing the full path.

    Only the baby block uses the patched fetcher; we restore before returning.
    """
    import agent.blocks.baby as baby_mod          # ← patch the consumer
    from agent.blocks.baby import build_baby_block

    _real_fetch = baby_mod.fetch_hourly

    def _rainy_fetch(latitude, longitude, **kw):
        rows = _real_fetch(latitude, longitude, **kw)
        for r in rows:
            r["precipitation_probability_pct"] = 70
        return rows

    baby_mod.fetch_hourly = _rainy_fetch
    try:
        block = build_baby_block(cfg, target_date)
    finally:
        baby_mod.fetch_hourly = _real_fetch

    return block

# ---------------------------------------------------------------------------
# --mock-alerts: inject alert strings into already-built blocks
# ---------------------------------------------------------------------------

def _inject_mock_alerts(blocks: dict) -> dict:
    """
    Inject fake alert strings into finished blocks.
    Tests the rendering path only — the LLM clothing recommendation
    was already computed and is NOT re-run.
    """
    b = copy.deepcopy(blocks)
    if b.get("cycling"):
        b["cycling"]["alerts"] = ["Icing risk (level 3) 05:00–09:00 — Glatteisgefahr"]
    if b.get("running"):
        b["running"]["alerts"] = ["Frost warning (level 2) 04:00–08:00 — Frostgefahr"]
    if b.get("baby"):
        b["baby"]["alerts"] = ["Rain likely 09:00–16:00 (peak 70%)"]
    return b


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    from agent.blocks.baby import build_baby_block

    cfg         = load_config()
    target_date = datetime.date.today() + datetime.timedelta(days=1)
    thresholds  = cfg.get("diff_thresholds")

    if MOCK_RAIN:
        print("\n*** --mock-rain: fetch_hourly will return 70% rain for baby block ***")
        print("    LLM will be called with the rain alert — full pipeline test.")
    elif MOCK_ALERTS:
        print("\n*** --mock-alerts: alert strings injected after build ***")
        print("    LLM clothing was already computed — rendering path test only.")

    # ------------------------------------------------------------------
    # Step 1 — Build blocks
    # ------------------------------------------------------------------
    _section("Step 1 — Building blocks")

    if MOCK_RAIN:
        baby_block = _build_baby_block_with_rain(cfg, target_date)
    else:
        baby_block = build_baby_block(cfg, target_date)

    blocks = {
        "baby":     baby_block,
        "cycling":  build_cycling_block(cfg, target_date),
        "running":  build_running_block(cfg, target_date),
        "swimming": build_swimming_block(cfg, target_date),
        "stocks":   build_stocks_block(cfg),
    }
    print(f"  target_date : {target_date}")
    for k, v in blocks.items():
        status = "None (skipped)" if v is None else "built"
        print(f"  {k:<10} : {status}")

    # ------------------------------------------------------------------
    # Step 2 — Apply mock alerts if requested (rendering test only)
    # ------------------------------------------------------------------
    if MOCK_ALERTS:
        _section("Step 2 — Injecting mock alert strings")
        blocks = _inject_mock_alerts(blocks)
        print("  cycling : fake icing alert injected")
        print("  running : fake frost alert injected")
        print("  baby    : fake rain alert injected (clothing NOT re-computed)")
    elif MOCK_RAIN:
        _section("Step 2 — Mock rain was applied during build (Step 1)")
        print("  Baby block built with 70% rain across all hours.")
        print("  LLM was called with midday_alerts populated.")
    else:
        _section("Step 2 — Real data (no mock flags)")

    # ------------------------------------------------------------------
    # Step 3 — Print raw alerts per block
    # ------------------------------------------------------------------
    _section("Step 3 — Raw alerts per block")

    for key in ["baby", "cycling", "running"]:
        block = blocks.get(key)
        if block is None:
            print(f"  {key:<10} : None (block skipped)")
            continue
        alerts = block.get("alerts", [])
        if alerts:
            print(f"  {key:<10} : {len(alerts)} alert(s):")
            for a in alerts:
                print(f"              ⚠  {a}")
        else:
            print(f"  {key:<10} : no alerts")

    # ------------------------------------------------------------------
    # Step 4 — If --mock-rain, show the clothing the LLM produced
    # ------------------------------------------------------------------
    if MOCK_RAIN and blocks.get("baby"):
        _section("Step 4a — LLM clothing output (should reflect rain alert)")
        c = blocks["baby"].get("clothing", {})
        print(f"  outfit           : {c.get('outfit', '—')}")
        print(f"  pushchair_extras : {c.get('pushchair_extras', '—')}")
        print(f"  pick_up_note     : {c.get('pick_up_note', '—')}")
        found = any(
            word in str(c).lower()
            for word in ["rain", "cover", "waterproof", "umbrella", "wet"]
        )
        print()
        if found:
            print("  ✓ LLM mentioned rain/cover/waterproof — alert was picked up.")
        else:
            print("  ✗ No rain-related word found in clothing output.")
            print("    Check the prompt in llm.py and confirm midday_alerts was passed.")

    # ------------------------------------------------------------------
    # Step 5 — Render the full digest
    # ------------------------------------------------------------------
    _section("Step 5 — Full digest render")
    digest = render_for_recipient(
        blocks, target_date, role="full",
        deltas=None, thresholds=thresholds,
    )
    print(digest)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _section("Summary")
    total_alerts = sum(
        len(blocks.get(k, {}).get("alerts", []) or [])
        for k in ["baby", "cycling", "running"]
        if blocks.get(k)
    )
    print(f"  Total alerts : {total_alerts}")
    print(f"  Digest chars : {len(digest)}")
    print()
    if not MOCK_RAIN and not MOCK_ALERTS and total_alerts == 0:
        print("  No alerts active. Use --mock-rain to test the LLM path,")
        print("  or --mock-alerts to test the rendering path.")
    print()
    print("  Phase 11 complete. No dispatch performed.")


if __name__ == "__main__":
    main()