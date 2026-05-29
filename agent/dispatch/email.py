"""
agent/dispatch/email.py

Sends a plain-text email via SMTP (Gmail or any STARTTLS-capable provider).

All credentials are read from environment variables — never hardcoded:
    SMTP_HOST       e.g. smtp.gmail.com
    SMTP_PORT       e.g. 587
    SMTP_USERNAME   sender address
    SMTP_PASSWORD   App Password (Gmail) or SMTP password

Usage:
    from agent.dispatch.email import send
    ok, error = send(to="you@example.com", subject="Morning briefing", body="...")

Contract (Phase 13, item B): returns (ok: bool, error: str | None), matching
telegram.send_telegram(). It never raises for SMTP/network problems — those are
caught, retried (SPEC §6.3), and reported via the return value so the
orchestrator can log them uniformly.
"""

import os
import smtplib
from email.message import EmailMessage

from agent.retry import with_retries

_REQUIRED = ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD")


def send(to: str, subject: str, body: str) -> tuple[bool, str | None]:
    """
    Send a plain-text email, retrying transient SMTP/network failures.

    Args:
        to:      Recipient email address.
        subject: Email subject line.
        body:    Plain-text body.

    Returns:
        (True, None)        on success.
        (False, reason)     on a config problem (missing/invalid env) or after
                            all retry attempts are exhausted.
    """
    # --- Config validation: a missing secret is NOT transient — fail fast. ---
    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        msg = f"missing env var(s): {', '.join(missing)}"
        print(f"[email] {msg}")
        return (False, msg)

    host     = os.environ["SMTP_HOST"]
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    try:
        port = int(os.environ["SMTP_PORT"])
    except ValueError:
        msg = f"SMTP_PORT is not an integer: {os.environ['SMTP_PORT']!r}"
        print(f"[email] {msg}")
        return (False, msg)

    # --- Build the message ---
    msg = EmailMessage()
    msg["From"]    = username
    msg["To"]      = to
    msg["Subject"] = subject
    msg.set_content(body)

    # --- Connect, authenticate, send (retried on transient failure) ---
    # STARTTLS (port 587): starts unencrypted, then upgrades to TLS before
    # credentials are ever transmitted. Standard for Gmail.
    def _do_send():
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()           # introduce ourselves to the server
            smtp.starttls()       # upgrade the connection to encrypted
            smtp.ehlo()           # re-introduce after TLS handshake
            smtp.login(username, password)
            smtp.send_message(msg)

    try:
        # OSError covers socket/connection errors; SMTPException covers the
        # protocol-level ones. (A bad-password SMTPAuthenticationError will be
        # retried too — wasteful but harmless for a personal tool.)
        with_retries(
            _do_send, attempts=3, base_delay=1.0,
            exceptions=(smtplib.SMTPException, OSError), label="email",
        )
        return (True, None)
    except Exception as exc:
        return (False, str(exc))
