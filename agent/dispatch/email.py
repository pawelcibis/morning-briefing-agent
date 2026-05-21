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
    send(to="you@example.com", subject="Morning briefing", body="...")
"""

import os
import smtplib
from email.message import EmailMessage


def send(to: str, subject: str, body: str) -> None:
    """
    Send a plain-text email.

    Args:
        to:      Recipient email address.
        subject: Email subject line.
        body:    Plain-text body.

    Raises:
        EnvironmentError: if any required env var is missing.
        smtplib.SMTPException: on any SMTP-level failure.
    """
    # --- Read credentials from environment ---
    host     = _require_env("SMTP_HOST")
    port     = int(_require_env("SMTP_PORT"))
    username = _require_env("SMTP_USERNAME")
    password = _require_env("SMTP_PASSWORD")

    # --- Build the message ---
    msg = EmailMessage()
    msg["From"]    = username
    msg["To"]      = to
    msg["Subject"] = subject
    msg.set_content(body)

    # --- Connect, authenticate, send ---
    # STARTTLS (port 587): starts an unencrypted connection, then upgrades
    # to TLS before credentials are ever transmitted. Standard for Gmail.
    with smtplib.SMTP(host, port) as smtp:
        smtp.ehlo()           # introduce ourselves to the server
        smtp.starttls()       # upgrade the connection to encrypted
        smtp.ehlo()           # re-introduce after TLS handshake
        smtp.login(username, password)
        smtp.send_message(msg)


def _require_env(name: str) -> str:
    """Return the value of an env var, or raise a clear error if missing."""
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            "Set it in your terminal before running, or add it to GitHub Secrets."
        )
    return value
