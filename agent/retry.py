"""
agent/retry.py — a tiny, dependency-free retry helper.

Most fetch/dispatch failures are *transient*: a single dropped connection, a
brief 5xx, a timeout. The right response is not to give up immediately, nor to
hammer the server, but to wait a moment and try again — waiting longer after
each failure (exponential backoff) so a struggling service gets room to recover.

We use this in two places (SPEC §6.3):
  * Fetchers — Open-Meteo / lake / Stooq HTTP calls.
  * Dispatch — SMTP and Telegram sends, "up to 3 times with exponential backoff".

Design notes
------------
* `with_retries(fn, ...)` is the workhorse: it calls `fn()` and retries on the
  listed exception types. On the final failure it re-raises, so the caller's
  own error handling (return None / return (False, err)) still applies.
* Backoff is `base_delay * 2**(attempt-1)`, capped at `max_delay`, plus a little
  random "jitter" so retries from different blocks don't all fire in lockstep.
* `time.sleep` is called directly — tests patch it (or pass base_delay=0) to run
  instantly.
"""

import random
import time


def with_retries(
    fn,
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    exceptions: tuple = (Exception,),
    label: str = "",
):
    """
    Call ``fn()`` and retry on transient failure.

    Args:
        fn:         zero-argument callable (use a lambda or functools.partial to
                    bind arguments, e.g. ``with_retries(lambda: requests.get(...))``).
        attempts:   total tries, including the first (so 3 = 1 try + 2 retries).
        base_delay: seconds to wait before the first retry; doubles each time.
        max_delay:  upper bound on any single wait.
        exceptions: exception types that count as transient and trigger a retry.
                    Anything else propagates immediately.
        label:      short tag for log lines, e.g. "weather" → "[retry weather]".

    Returns:
        Whatever ``fn()`` returns on the first success.

    Raises:
        The last exception, if all attempts fail.
    """
    tag = f"[retry {label}]" if label else "[retry]"
    last_exc = None

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except exceptions as exc:          # noqa: B902 — caller picks the types
            last_exc = exc
            if attempt == attempts:
                print(f"{tag} attempt {attempt}/{attempts} failed: {exc!r} — giving up")
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay += random.uniform(0, delay * 0.1)   # up to 10% jitter
            print(f"{tag} attempt {attempt}/{attempts} failed: {exc!r} — "
                  f"retrying in {delay:.1f}s")
            time.sleep(delay)

    # Exhausted — re-raise so the caller's None / (False, err) path runs.
    raise last_exc


def retries(*, attempts: int = 3, base_delay: float = 0.5,
            max_delay: float = 8.0, exceptions: tuple = (Exception,),
            label: str = ""):
    """
    Decorator form of :func:`with_retries`.

    Example:
        @retries(attempts=3, label="weather")
        def fetch_hourly(...):
            ...
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            return with_retries(
                lambda: fn(*args, **kwargs),
                attempts=attempts, base_delay=base_delay,
                max_delay=max_delay, exceptions=exceptions,
                label=label or fn.__name__,
            )
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator
