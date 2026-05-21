"""
phase4_test.py

Phase 4 end-to-end test: fetch weather, build cycling block, send by email.

Required environment variables:
    ANTHROPIC_API_KEY       for the clothing recommendation
    SMTP_HOST               e.g. smtp.gmail.com
    SMTP_PORT               e.g. 587
    SMTP_USERNAME           sender Gmail address
    SMTP_PASSWORD           Gmail App Password
    RECIPIENT_PAWEL_EMAIL   destination address
"""

import os
from datetime import date, timedelta

from agent.config import load_config
from agent.blocks.cycling import build_cycling_block
from agent.render import render_cycling_block
from agent.dispatch.email import send


def main():
    # Target date: tomorrow (same as phase3_test)
    target_date = date.today() + timedelta(days=1)

    # Load config
    cfg = load_config()

    # Build the cycling block
    print("Fetching weather and building cycling block...")
    block = build_cycling_block(cfg, target_date)

    # Render to plain text
    body = render_cycling_block(block)

    # Resolve recipient address from environment (mirrors how GitHub Secrets work)
    recipient = os.environ.get("RECIPIENT_PAWEL_EMAIL")
    if not recipient:
        raise EnvironmentError(
            "RECIPIENT_PAWEL_EMAIL is not set. "
            "Run: $env:RECIPIENT_PAWEL_EMAIL = 'you@gmail.com'"
        )

    # Send
    subject = f"Morning briefing — cycling forecast {target_date.strftime('%A %d %B')}"
    print(f"Sending to {recipient}...")
    send(to=recipient, subject=subject, body=body)
    print("Done. Check your inbox.")


if __name__ == "__main__":
    main()