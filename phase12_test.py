"""
phase12_test.py

Phase 12 local pre-deploy test — drives agent.main twice (evening + morning)
in --dry-run mode. No dispatch happens, but the full pipeline runs:
  * load config
  * build all five blocks
  * compute deltas (morning only — diffs against state/last_run.json)
  * render per recipient + role
  * write state (evening only)

If both runs print "DONE — ... 0 error(s)" and no FAILED lines appear,
you're safe to deploy.

Run:
  python phase12_test.py

Note: this writes state/last_run.json locally on the evening pass.
That is the SAME file the GHA workflow manages — locally it just lives
on disk inside the repo. Safe to delete or commit-ignore.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agent.main import main


def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


if __name__ == "__main__":
    _section("Phase 12 — DRY-RUN: evening")
    rc1 = main(run_type="evening", dry_run=True)

    _section("Phase 12 — DRY-RUN: morning")
    rc2 = main(run_type="morning", dry_run=True)

    _section("Phase 12 test complete")
    print(f"  evening: exit {rc1}")
    print(f"  morning: exit {rc2}")
    print()
    print("  If both lines above say `exit 0` and no FAILED lines appeared,")
    print("  the orchestrator is ready.")
    print()
    print("  Next:")
    print("    1. Run a REAL evening (no --dry-run) to confirm email/Telegram fire.")
    print("    2. Verify all GitHub Secrets are set.")
    print("    3. Push .github/workflows/digest.yml and trigger via workflow_dispatch.")