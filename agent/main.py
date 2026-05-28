"""
agent/main.py — Orchestrator for the morning briefing agent.

Runs the full pipeline end-to-end:
  1. Load config + previous state
  2. Build all five blocks (baby, cycling, running, swimming, stocks)
  3. (Morning only) Compute deltas vs previous state
  4. Render per recipient role + dispatch via each configured channel
  5. (Evening only) Write new state to state/last_run.json

CLI:
    python -m agent.main --run-type {evening|morning} [--dry-run]

--dry-run skips dispatch but everything else runs (including state write).
Useful for local pre-deploy testing without spamming yourself or Liliana.

Exit code is always 0 — partial failures are reported to stdout but never
cause GHA to mark the run red. The only way to exit non-zero is via an
unhandled exception in the orchestrator itself, which would indicate a
real bug rather than a normal degraded run.
"""

import argparse
import datetime
import os
import sys
import traceback

from agent.config import load_config
from agent.state  import read_state, write_state, STATE_PATH
from agent.diff   import diff_blocks
from agent.render import render_for_recipient, ROLE_BLOCKS

from agent.blocks.baby     import build_baby_block
from agent.blocks.cycling  import build_cycling_block
from agent.blocks.running  import build_running_block
from agent.blocks.swimming import build_swimming_block
from agent.blocks.stocks   import build_stocks_block

from agent.dispatch.email    import send as send_email
from agent.dispatch.telegram import send_telegram


# ---------------------------------------------------------------------------
# Block building — per-block exception isolation
# ---------------------------------------------------------------------------

def _safe_build(name: str, fn, *args):
    """
    Call build_*_block with isolation.

    On exception: log full traceback, return None.
    On normal None return: log "skipped".
    On success:           log "built".

    A single fetcher failure must not abort the digest — every block is
    independently optional. render_for_recipient already skips None blocks.
    """
    try:
        block = fn(*args)
    except Exception as exc:
        print(f"[main] [{name:<10}] FAILED: {exc!r}")
        traceback.print_exc()
        return None

    if block is None:
        print(f"[main] [{name:<10}] None (skipped — non-creche day, cold lake, etc.)")
    else:
        print(f"[main] [{name:<10}] built")
    return block


def _build_all_blocks(cfg, target_date):
    print(f"\n[main] Building blocks for target_date={target_date.isoformat()}")
    return {
        "baby":     _safe_build("baby",     build_baby_block,     cfg, target_date),
        "cycling":  _safe_build("cycling",  build_cycling_block,  cfg, target_date),
        "running":  _safe_build("running",  build_running_block,  cfg, target_date),
        "swimming": _safe_build("swimming", build_swimming_block, cfg, target_date),
        "stocks":   _safe_build("stocks",   build_stocks_block,   cfg),
    }


# ---------------------------------------------------------------------------
# Dispatch — per-channel exception isolation
# ---------------------------------------------------------------------------

def _dispatch_email(channel: dict, subject: str, body: str,
                    dry_run: bool, log_prefix: str):
    """Returns (ok: bool, error: str | None)."""
    secret_name = channel.get("address_secret")
    if not secret_name:
        print(f"{log_prefix} skipped — channel missing 'address_secret'")
        return (False, "channel missing 'address_secret'")

    address = os.environ.get(secret_name, "")
    if not address:
        print(f"{log_prefix} skipped — env var {secret_name} not set")
        return (False, f"env var {secret_name} not set")

    if dry_run:
        print(f"{log_prefix} DRY-RUN would send to {address} ({len(body)} chars)")
        return (True, "dry-run")

    try:
        send_email(to=address, subject=subject, body=body)
        print(f"{log_prefix} sent → {address}")
        return (True, None)
    except Exception as exc:
        print(f"{log_prefix} FAILED → {address}: {exc!r}")
        return (False, str(exc))


def _dispatch_telegram(channel: dict, body: str,
                       dry_run: bool, log_prefix: str):
    """Returns (ok: bool, error: str | None)."""
    secret_name = channel.get("chat_id_secret")
    if not secret_name:
        print(f"{log_prefix} skipped — channel missing 'chat_id_secret'")
        return (False, "channel missing 'chat_id_secret'")

    chat_id = os.environ.get(secret_name, "")
    if not chat_id:
        print(f"{log_prefix} skipped — env var {secret_name} not set")
        return (False, f"env var {secret_name} not set")

    if dry_run:
        print(f"{log_prefix} DRY-RUN would send to chat {chat_id} ({len(body)} chars)")
        return (True, "dry-run")

    ok = send_telegram(chat_id=chat_id, text=body)
    if ok:
        print(f"{log_prefix} sent → chat {chat_id}")
        return (True, None)
    print(f"{log_prefix} FAILED → chat {chat_id} (send_telegram returned False)")
    return (False, "send_telegram returned False")


def _dispatch_to_recipient(recipient: dict, body: str, subject: str,
                           dry_run: bool):
    """
    Dispatch body to all of recipient's channels.

    Returns (n_ok, n_fail) so the orchestrator can build the summary.
    """
    n_ok, n_fail = 0, 0
    name = recipient.get("name", "?")
    for channel in recipient.get("channels", []):
        ctype  = channel.get("type", "?")
        prefix = f"  [{name:<10} {ctype:<8}]"
        if ctype == "email":
            ok, _ = _dispatch_email(channel, subject, body, dry_run, prefix)
        elif ctype == "telegram":
            ok, _ = _dispatch_telegram(channel, body, dry_run, prefix)
        else:
            print(f"{prefix} unknown channel type {ctype!r} — skipping")
            ok = False
        n_ok  += int(ok)
        n_fail += int(not ok)
    return n_ok, n_fail


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main(run_type: str, dry_run: bool = False) -> int:
    """
    Run the full pipeline once.

    Args:
        run_type: "evening" or "morning".
        dry_run:  if True, skip all dispatch but build blocks and write state.

    Returns:
        Always 0. Errors are logged, never raised.
    """
    print(f"[main] === START run_type={run_type} dry_run={dry_run} ===")

    cfg   = load_config()
    today = datetime.date.today()
    if run_type == "evening":
        target_date = today + datetime.timedelta(days=1)
    else:
        target_date = today
    print(f"[main] today={today.isoformat()}  target_date={target_date.isoformat()}")

    # State — read always (morning needs it for diff; evening just logs it)
    previous_state = read_state()
    if previous_state:
        prev_date = previous_state.get("target_date", "?")
        print(f"[main] previous state: target_date={prev_date}")
    else:
        print(f"[main] previous state: empty (first run, or state file missing)")

    # Build blocks
    blocks = _build_all_blocks(cfg, target_date)

    # Compute deltas (morning only)
    deltas = None
    if run_type == "morning":
        deltas = diff_blocks(blocks, previous_state)
        print(f"[main] computed {len(deltas)} field delta(s)")

    thresholds = cfg.get("diff_thresholds")

    # Subject line — distinguishable per run type
    date_str = target_date.strftime("%a %d %b")
    if run_type == "evening":
        subject = f"Morning briefing — {date_str}"
    else:
        subject = f"Morning update — {date_str}"

    # Dispatch per recipient
    recipients = cfg.get("recipients", [])
    print(f"\n[main] Dispatching to {len(recipients)} recipient(s)  subject={subject!r}")
    total_ok, total_fail = 0, 0
    for recipient in recipients:
        name = recipient.get("name", "?")
        role = recipient.get("role", "full")

        # Skip entirely if every block this role would receive is None.
        # e.g. Liliana (baby_only) on a non-crèche day — no content to send.
        allowed_blocks = ROLE_BLOCKS.get(role, set())
        if not any(blocks.get(k) is not None for k in allowed_blocks):
            print(f"  [{name:<10}] skipping — no content for role {role!r}")
            continue

        body = render_for_recipient(
            blocks, target_date, role,
            deltas=deltas, thresholds=thresholds,
        )
        ok, fail = _dispatch_to_recipient(recipient, body, subject, dry_run)
        total_ok  += ok
        total_fail += fail

    # State write (evening only — even on partial block failures)
    if run_type == "evening":
        try:
            write_state(STATE_PATH, blocks, target_date)
        except Exception as exc:
            print(f"[main] state write FAILED: {exc!r}")
            traceback.print_exc()

    # Summary
    n_recip = len(recipients)
    n_chan  = total_ok + total_fail
    print(f"\n[main] === DONE — {n_recip} recipient(s), "
          f"{n_chan} channel attempts, {total_ok} ok, {total_fail} error(s) ===")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv=None):
    p = argparse.ArgumentParser(prog="agent")
    p.add_argument("--run-type", required=True, choices=["evening", "morning"])
    p.add_argument("--dry-run", action="store_true",
                   help="Skip dispatch but build blocks and write state normally.")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(main(run_type=args.run_type, dry_run=args.dry_run))