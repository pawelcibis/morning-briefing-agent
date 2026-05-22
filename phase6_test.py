"""
Phase 6 end-to-end test.

Builds all blocks (baby, cycling, running, swimming, stocks),
renders the digest, and sends it to RECIPIENT_PAWEL_EMAIL.

Run from the repo root:
    python phase6_test.py

Required environment variables (set before running):
    ANTHROPIC_API_KEY
    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD
    RECIPIENT_PAWEL_EMAIL
    STOCKS_KRU_SHARES          ← new for Phase 6
"""

import os
import smtplib
from datetime import date, timedelta
from email.mime.text import MIMEText

from agent.config import load_config
from agent.blocks.cycling import build_cycling_block
from agent.blocks.running import build_running_block
from agent.blocks.baby import build_baby_block
from agent.blocks.swimming import build_swimming_block
from agent.blocks.stocks import build_stocks_block
from agent.render import render_digest


def send_email(subject: str, body: str) -> None:
    host     = os.environ["SMTP_HOST"]
    port     = int(os.environ["SMTP_PORT"])
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    to_addr  = os.environ["RECIPIENT_PAWEL_EMAIL"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = username
    msg["To"]      = to_addr

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(username, password)
        server.sendmail(username, [to_addr], msg.as_string())

    print(f"Email sent to {to_addr}")


def main() -> None:
    cfg = load_config()

    # The digest covers tomorrow morning
    target_date = date.today() + timedelta(days=1)
    print(f"Building digest for {target_date}")

    # ── Build all blocks ────────────────────────────────────────────────────
    print("Building cycling block...")
    cycling = build_cycling_block(cfg, target_date)

    print("Building running block...")
    running = build_running_block(cfg, target_date)

    print("Building baby block...")
    baby = build_baby_block(cfg, target_date)

    print("Building swimming block...")
    swimming = build_swimming_block(cfg, target_date)

    print("Building stocks block...")
    stocks = build_stocks_block(cfg)

    # ── Render ──────────────────────────────────────────────────────────────
    blocks = {
        "baby":     baby,
        "cycling":  cycling,
        "running":  running,
        "swimming": swimming,
        "stocks":   stocks,
    }

    digest = render_digest(blocks, target_date)

    print("\n" + "=" * 60)
    print(digest)
    print("=" * 60 + "\n")

    # ── Send ────────────────────────────────────────────────────────────────
    subject = f"Morning Briefing (Phase 6 test) — {target_date}"
    send_email(subject, digest)


if __name__ == "__main__":
    main()