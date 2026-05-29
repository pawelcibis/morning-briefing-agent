"""
agent/log.py — structured run logging + rendered-message retention.

SPEC §6.4 (as resolved in Phase 13): logs are NOT committed to the repo. The
`main` branch stays code-only and the morning run stays read-only. Instead, the
runner writes everything under ``logs/`` and the workflow uploads that directory
as a GitHub Actions artifact at 90-day retention (≈ the "~3 months" the spec
asked for). Retention/cleanup is therefore handled by the platform, not by us —
``prune_old()`` below only tidies a *local* dev machine, where logs accumulate
on disk run after run.

Two things get written each run:
  * logs/YYYY-MM.log
        one structured, greppable block per run — timestamp, run type, the
        per-block build status, the per-channel dispatch status, and any error
        text. Appended, so a month's runs live in one file.
  * logs/messages/YYYY-MM-DD-{evening|morning}.txt
        the full rendered digest body, for archive/retrieval.

Design rule: **logging must never break the run.** Every file operation is
wrapped so a logging failure degrades to a printed warning, never an exception
that would abort dispatch.
"""

import datetime
import os
import traceback

LOGS_DIR = "logs"
MESSAGES_SUBDIR = "messages"


def _utc_stamp() -> str:
    """ISO-8601 UTC timestamp, e.g. '2026-05-28T20:00:03Z'.

    Uses only zero-padded format codes (no %-d / %-H) so it behaves the same on
    Windows PowerShell and Linux.
    """
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunLog:
    """
    Accumulates one run's events, then writes a single structured entry.

    Usage (from main.py):
        rl = RunLog(run_type, target_date)
        rl.block("baby", "built")
        rl.block("stocks", "failed", error="...")
        rl.dispatch("Pawel", "email", "ok")
        rl.dispatch("Liliana", "email", "skipped", error="no content for role")
        rl.finish(ok=3, fail=0)        # writes logs/YYYY-MM.log
    """

    def __init__(self, run_type: str, target_date, logs_dir: str = LOGS_DIR):
        self.run_type = run_type
        self.target_date = target_date
        self.logs_dir = logs_dir
        self.started = _utc_stamp()
        self._blocks: list[tuple[str, str, str | None]] = []
        self._dispatch: list[tuple[str, str, str, str | None]] = []
        self._notes: list[str] = []

    # --- recording -------------------------------------------------------
    def block(self, name: str, status: str, error: str | None = None) -> None:
        """status ∈ {'built', 'skipped', 'failed'}."""
        self._blocks.append((name, status, error))

    def dispatch(self, recipient: str, channel: str, status: str,
                 error: str | None = None) -> None:
        """status ∈ {'ok', 'failed', 'skipped', 'dry-run'}."""
        self._dispatch.append((recipient, channel, status, error))

    def note(self, msg: str) -> None:
        self._notes.append(msg)

    # --- rendering + writing --------------------------------------------
    def _format_entry(self, ok: int, fail: int) -> str:
        target = getattr(self.target_date, "isoformat", lambda: str(self.target_date))()
        lines = [
            "=" * 64,
            f"{self.started}  run={self.run_type}  target={target}",
            "  blocks:",
        ]
        for name, status, error in self._blocks:
            tail = f" — {error}" if error else ""
            lines.append(f"    {name:<9}: {status}{tail}")
        lines.append("  dispatch:")
        if self._dispatch:
            for recipient, channel, status, error in self._dispatch:
                tail = f" — {error}" if error else ""
                lines.append(f"    {recipient:<9}{channel:<9}: {status}{tail}")
        else:
            lines.append("    (none)")
        for n in self._notes:
            lines.append(f"  note: {n}")
        lines.append(f"  result: {ok} ok, {fail} error(s)")
        return "\n".join(lines) + "\n"

    def finish(self, ok: int, fail: int) -> str:
        """Write the structured entry to logs/YYYY-MM.log. Returns the text."""
        entry = self._format_entry(ok, fail)
        month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
        path = os.path.join(self.logs_dir, f"{month}.log")
        try:
            os.makedirs(self.logs_dir, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"[log] appended run summary → {path}")
        except Exception as exc:                       # logging must never abort
            print(f"[log] WARNING: could not write {path}: {exc!r}")
            traceback.print_exc()
        return entry


def write_message(target_date, run_type: str, body: str,
                  logs_dir: str = LOGS_DIR) -> None:
    """
    Archive the full rendered digest to logs/messages/YYYY-MM-DD-{run_type}.txt.

    Never raises — a write failure prints a warning and returns.
    """
    date_str = getattr(target_date, "strftime", None)
    date_str = target_date.strftime("%Y-%m-%d") if date_str else str(target_date)
    msg_dir = os.path.join(logs_dir, MESSAGES_SUBDIR)
    path = os.path.join(msg_dir, f"{date_str}-{run_type}.txt")
    try:
        os.makedirs(msg_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"[log] archived message → {path}")
    except Exception as exc:
        print(f"[log] WARNING: could not write {path}: {exc!r}")


def prune_old(days: int = 90, logs_dir: str = LOGS_DIR) -> int:
    """
    Delete local log + message files older than `days` (LOCAL dev tidiness only).

    In GitHub Actions the runner is ephemeral so logs/ starts empty and this is
    a no-op; artifact retention (90 days) is the real retention mechanism there.

    Returns the number of files deleted. Never raises.
    """
    cutoff = datetime.datetime.now().timestamp() - days * 86400
    deleted = 0
    for root, _dirs, files in os.walk(logs_dir):
        for name in files:
            fpath = os.path.join(root, name)
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    deleted += 1
            except OSError:
                continue
    if deleted:
        print(f"[log] pruned {deleted} local file(s) older than {days} days")
    return deleted
