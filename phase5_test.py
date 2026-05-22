"""
Phase 5 test — assembles a full multi-block digest and emails it.

Run from the project root with the venv activated:
    python phase5_test.py

Required env vars (PowerShell example):
    $env:ANTHROPIC_API_KEY     = "sk-ant-..."
    $env:SMTP_HOST             = "smtp.gmail.com"
    $env:SMTP_PORT             = "587"
    $env:SMTP_USERNAME         = "your-sender@gmail.com"
    $env:SMTP_PASSWORD         = "your-app-password"
    $env:RECIPIENT_PAWEL_EMAIL = "you@example.com"

Notes:
  - We forecast for TOMORROW (target_date = today + 1 day) so the email
    matches the future evening-run pattern. To force a creche day for
    visibility into the baby block, override TARGET_DATE below.
  - Each block runs independently; one failure won't break the others.
"""

import os
import sys
from datetime import date, timedelta

from agent.config import load_config
from agent.blocks.cycling import build_cycling_block
from agent.blocks.running import build_running_block
from agent.blocks.baby import build_baby_block
from agent.blocks.swimming import build_swimming_block
from agent.render import render_digest
from agent.dispatch.email import send as send_email


# To exercise the baby block on a non-creche day, set this to a Tue-Fri date:
TARGET_DATE = date(2026, 5, 22)   # Tuesday
#TARGET_DATE = None  # None → tomorrow


def main():
    cfg = load_config()

    target = TARGET_DATE or (date.today() + timedelta(days=1))
    print(f"Building digest for {target.strftime('%A, %d %B %Y')}")
    print("-" * 60)

    # Build each block independently — keep partial success on errors.
    blocks = {}

    print("Baby block...")
    try:
        blocks["baby"] = build_baby_block(cfg, target)
        print("  done" if blocks["baby"] else "  skipped (not a creche day)")
    except Exception as e:
        print(f"  FAILED: {e}")
        blocks["baby"] = None

    print("Cycling block...")
    try:
        blocks["cycling"] = build_cycling_block(cfg, target)
        print("  done" if blocks["cycling"] else "  no data")
    except Exception as e:
        print(f"  FAILED: {e}")
        blocks["cycling"] = None

    print("Running block...")
    try:
        blocks["running"] = build_running_block(cfg, target)
        print("  done" if blocks["running"] else "  no data")
    except Exception as e:
        print(f"  FAILED: {e}")
        blocks["running"] = None

    print("Swimming block...")
    try:
        blocks["swimming"] = build_swimming_block(cfg, target)
        if blocks["swimming"]:
            print("  done")
        else:
            print("  skipped (water below threshold or missing)")
    except Exception as e:
        print(f"  FAILED: {e}")
        blocks["swimming"] = None

    print("-" * 60)
    body = render_digest(blocks, target)
    print(body)
    print("-" * 60)

    # Send the digest.
    to_addr = os.environ.get("RECIPIENT_PAWEL_EMAIL")
    if not to_addr:
        print("RECIPIENT_PAWEL_EMAIL not set — skipping email send.")
        sys.exit(0)

    subject = f"Morning Briefing — {target.strftime('%a %d %b %Y')}"
    print(f"Sending email to {to_addr}...")
    send_email(to=to_addr, subject=subject, body=body)
    print("Sent.")


if __name__ == "__main__":
    main()