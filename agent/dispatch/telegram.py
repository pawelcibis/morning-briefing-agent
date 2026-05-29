"""
agent/dispatch/telegram.py

Sends a message via the Telegram Bot API.

Credentials read from environment variables — never hardcoded:
    TELEGRAM_BOT_TOKEN   bot token from @BotFather

Usage:
    from agent.dispatch.telegram import send_telegram
    ok, error = send_telegram(chat_id="123456789", text="Good morning!")

Contract (Phase 13, item B): returns (ok: bool, error: str | None), matching
email.send(). Long messages are split on blank lines into <=4096-char chunks;
each chunk's POST is retried on transient failure (SPEC §6.3).
"""

import os
import requests

from agent.retry import with_retries

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LENGTH = 4096  # Telegram's hard limit per message


def send_telegram(chat_id: str, text: str) -> tuple[bool, str | None]:
    """
    Send a plain-text message to a Telegram chat.

    If the text exceeds 4096 characters it is split on blank lines and sent as
    sequential messages. Each chunk is retried on transient failure.

    Args:
        chat_id: Numeric chat ID as a string (e.g. "123456789").
        text:    Message body.

    Returns:
        (True, None)     if every chunk was sent successfully.
        (False, reason)  on a config problem or after retries are exhausted.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        msg = "TELEGRAM_BOT_TOKEN is not set"
        print(f"[telegram] {msg}")
        return (False, msg)

    url = TELEGRAM_API.format(token=token)
    chunks = _split(text)

    for i, chunk in enumerate(chunks, start=1):
        # Bind `chunk` as a default arg so the closure captures THIS iteration's
        # value, not the loop variable's final value.
        def _send_chunk(chunk=chunk):
            resp = requests.post(
                url, json={"chat_id": chat_id, "text": chunk}, timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                # API-level rejection (e.g. bad chat_id) — raise so with_retries
                # treats it like any other failure and the caller gets a reason.
                raise RuntimeError(f"Telegram API error: {data}")
            return data

        try:
            with_retries(
                _send_chunk, attempts=3, base_delay=1.0,
                exceptions=(requests.RequestException, RuntimeError, ValueError),
                label="telegram",
            )
        except Exception as exc:
            print(f"[telegram] chunk {i}/{len(chunks)} failed: {exc}")
            return (False, str(exc))

    return (True, None)


def _split(text: str) -> list[str]:
    """
    Split text into chunks of at most MAX_LENGTH characters.

    Tries to split on blank lines first (paragraph boundaries) so the digest
    blocks stay intact. Falls back to hard-splitting on MAX_LENGTH if a single
    paragraph exceeds the limit.
    """
    if len(text) <= MAX_LENGTH:
        return [text]

    chunks = []
    current = ""

    for paragraph in text.split("\n\n"):
        candidate = (current + "\n\n" + paragraph).lstrip("\n")
        if len(candidate) <= MAX_LENGTH:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # paragraph itself might exceed limit — hard-split it
            while len(paragraph) > MAX_LENGTH:
                chunks.append(paragraph[:MAX_LENGTH])
                paragraph = paragraph[MAX_LENGTH:]
            current = paragraph

    if current:
        chunks.append(current)

    return chunks
