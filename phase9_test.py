"""
phase9_test.py

Phase 9 end-to-end test — same as phase8_test.py but adds a console
printout of the LLM baby clothing recommendation before dispatching,
so you can inspect it before it hits email / Telegram.

Required env vars: same as phase8_test.py, plus ANTHROPIC_API_KEY.

Run:
    python phase9_test.py
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agent.config import load_config
from agent.blocks.baby import build_baby_block
from agent.blocks.cycling import build_cycling_block
from agent.blocks.running import build_running_block
from agent.blocks.swimming import build_swimming_block
from agent.blocks.stocks import build_stocks_block
from agent.render import render_for_recipient
from agent.dispatch.email import send as send_email
from agent.dispatch.telegram import send_telegram


def main():
    cfg = load_config()
    target_date = datetime.date.today() + datetime.timedelta(days=1)

    # ------------------------------------------------------------------
    # Build all blocks once — shared across all recipients
    # ------------------------------------------------------------------
    baby_block = build_baby_block(cfg, target_date)

    blocks = {
        "baby":     baby_block,
        "cycling":  build_cycling_block(cfg, target_date),
        "running":  build_running_block(cfg, target_date),
        "swimming": build_swimming_block(cfg, target_date),
        "stocks":   build_stocks_block(cfg),
    }

    # ------------------------------------------------------------------
    # Phase 9 addition: inspect baby clothing recommendation before sending
    # ------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print("BABY CLOTHING RECOMMENDATION (Claude Haiku)")
    print("=" * 60)
    if baby_block is None:
        print(f"  Baby block is None — {target_date.strftime('%A')} is not a creche day.")
    else:
        c = baby_block["clothing"]
        d = baby_block["drop_off"]
        p = baby_block["pick_up"]
        print(f"  Age:              {baby_block['baby_age_months']} months")
        print(f"  Drop-off:         {d['temp_c']:.1f}°C  {d['wind_ms']} m/s {d['wind_dir']}  {d['rain_pct']}% rain  {d['cloud_label']}")
        print(f"  Pick-up:          {p['temp_c']:.1f}°C  {p['wind_ms']} m/s {p['wind_dir']}  {p['rain_pct']}% rain  {p['cloud_label']}")
        print(f"  Outfit:           {c['outfit']}")
        print(f"  Pushchair extras: {c['pushchair_extras']}")
        print(f"  Pick-up note:     {c['pick_up_note']}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Dispatch per recipient — identical to phase8_test.py from here
    # ------------------------------------------------------------------
    for recipient in cfg.get("recipients", []):
        name     = recipient["name"]
        role     = recipient["role"]
        channels = recipient.get("channels", [])

        digest = render_for_recipient(blocks, target_date, role)

        print(f"\n{'=' * 60}")
        print(f"Recipient: {name}  |  Role: {role}")
        print(f"{'=' * 60}")
        print(digest)
        print(f"(length: {len(digest)} chars)")

        subject = f"Morning Briefing — {target_date.strftime('%A, %d %B %Y')}"

        for channel in channels:
            ch_type = channel["type"]

            if ch_type == "email":
                secret_name = channel.get("address_secret", "")
                address = os.environ.get(secret_name, "")
                if not address:
                    print(f"  [email] ⚠  {secret_name} not set — skipping")
                    continue
                try:
                    send_email(to=address, subject=subject, body=digest)
                    print(f"  [email] ✅  Sent to {address}")
                except Exception as exc:
                    print(f"  [email] ❌  Failed: {exc}")

            elif ch_type == "telegram":
                secret_name = channel.get("chat_id_secret", "")
                chat_id = os.environ.get(secret_name, "")
                if not chat_id:
                    print(f"  [telegram] ⚠  {secret_name} not set — skipping")
                    continue
                ok = send_telegram(chat_id=chat_id, text=digest)
                if ok:
                    print(f"  [telegram] ✅  Sent to chat_id {chat_id}")
                else:
                    print(f"  [telegram] ❌  Failed")

            else:
                print(f"  [{ch_type}] ⚠  Unknown channel type — skipping")


if __name__ == "__main__":
    main()