"""
agent/dispatch/telegram.py

Sends a message via the Telegram Bot API.

Credentials read from environment variables — never hardcoded:
    TELEGRAM_BOT_TOKEN   bot token from @BotFather

Usage:
    from agent.dispatch.telegram import send_telegram
    ok = send_telegram(chat_id="123456789", text="Good morning!")
"""

import os
import requests


TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LENGTH = 4096  # Telegram's hard limit per message


def send_telegram(chat_id: str, text: str) -> bool:
    """
    Send a plain-text message to a Telegram chat.

    If the text exceeds 4096 characters, it is split on blank lines and
    sent as sequential messages.

    Args:
        chat_id: Numeric chat ID as a string (e.g. "123456789").
        text:    Message body.

    Returns:
        True if all messages were sent successfully, False on any failure.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("[telegram] ERROR: TELEGRAM_BOT_TOKEN is not set.")
        return False

    url = TELEGRAM_API.format(token=token)
    chunks = _split(text)

    for chunk in chunks:
        try:
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": chunk},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                print(f"[telegram] API error: {data}")
                return False
        except Exception as exc:
            print(f"[telegram] ERROR: {exc}")
            return False

    return True


def _split(text: str) -> list[str]:
    """
    Split text into chunks of at most MAX_LENGTH characters.

    Tries to split on blank lines first (paragraph boundaries) so the
    digest blocks stay intact. Falls back to hard-splitting on MAX_LENGTH
    if a single paragraph exceeds the limit.
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