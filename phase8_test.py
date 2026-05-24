"""
phase8_test.py

Phase 8 end-to-end test: build the full digest, then dispatch per-recipient
using each recipient's role and configured channels.

Recipients and roles come from config.yaml.
Personal identifiers (email addresses, chat IDs) are read from env vars
whose names are listed in config.yaml under address_secret / chat_id_secret.

Required env vars:
    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD
    STOOQ_API_KEY, STOCKS_KRU_SHARES
    TELEGRAM_BOT_TOKEN
    RECIPIENT_PAWEL_EMAIL
    RECIPIENT_PAWEL_TELEGRAM
    RECIPIENT_LILIANA_EMAIL          ← set to pawel@cibis.pl for now

Run:
    python phase8_test.py
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
    blocks = {
        "baby":     build_baby_block(cfg, target_date),
        "cycling":  build_cycling_block(cfg, target_date),
        "running":  build_running_block(cfg, target_date),
        "swimming": build_swimming_block(cfg, target_date),
        "stocks":   build_stocks_block(cfg),
    }

    # ------------------------------------------------------------------
    # Dispatch per recipient
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