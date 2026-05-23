"""
phase7_test.py

Phase 7 end-to-end test: build the full digest and send it via both
email and Telegram.

Required env vars (set in PowerShell before running):
    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD
    RECIPIENT_PAWEL_EMAIL
    STOOQ_API_KEY
    STOCKS_KRU_SHARES
    TELEGRAM_BOT_TOKEN
    RECIPIENT_PAWEL_TELEGRAM

Run:
    python phase7_test.py
"""

import datetime
import os
import sys

# ---------------------------------------------------------------------------
# Path fix so local imports work without installing the package
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

from agent.config import load_config
from agent.blocks.baby import build_baby_block
from agent.blocks.cycling import build_cycling_block
from agent.blocks.running import build_running_block
from agent.blocks.swimming import build_swimming_block
from agent.blocks.stocks import build_stocks_block
from agent.render import render_digest
from agent.dispatch.email import send
from agent.dispatch.telegram import send_telegram


def main():
    cfg = load_config()
    target_date = datetime.date.today() + datetime.timedelta(days=1)



    # ------------------------------------------------------------------
    # Build blocks
    # ------------------------------------------------------------------
    baby_block     = build_baby_block(cfg, target_date)
    cycling_block  = build_cycling_block(cfg, target_date)
    running_block  = build_running_block(cfg, target_date)
    swimming_block = build_swimming_block(cfg, target_date)
    stocks_block   = build_stocks_block(cfg)

    blocks = {
        "baby":     baby_block,
        "cycling":  cycling_block,
        "running":  running_block,
        "swimming": swimming_block,
        "stocks":   stocks_block,
    }

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    digest = render_digest(blocks, target_date)
    print("=" * 60)
    print(digest)
    print("=" * 60)
    print(f"\nDigest length: {len(digest)} characters")

    # ------------------------------------------------------------------
    # Dispatch — email
    # ------------------------------------------------------------------
    email_address = os.environ.get("RECIPIENT_PAWEL_EMAIL", "")
    if not email_address:
        print("\n[email] RECIPIENT_PAWEL_EMAIL not set — skipping email.")
    else:
        subject = f"Morning Briefing — {target_date.strftime('%A, %d %B %Y')}"
        try:
            send(to=email_address, subject=subject, body=digest)
            print(f"\n[email] ✅  Sent to {email_address}")
        except Exception as exc:
            print(f"\n[email] ❌  Failed: {exc}")

    # ------------------------------------------------------------------
    # Dispatch — Telegram
    # ------------------------------------------------------------------
    chat_id = os.environ.get("RECIPIENT_PAWEL_TELEGRAM", "")
    if not chat_id:
        print("[telegram] RECIPIENT_PAWEL_TELEGRAM not set — skipping Telegram.")
    else:
        ok = send_telegram(chat_id=chat_id, text=digest)
        if ok:
            print(f"[telegram] ✅  Sent to chat_id {chat_id}")
        else:
            print(f"[telegram] ❌  Failed (see error above)")


if __name__ == "__main__":
    main()