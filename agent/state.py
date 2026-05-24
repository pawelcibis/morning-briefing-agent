"""
agent/state.py — State persistence for the morning briefing agent.

The evening run serialises its blocks dict to state/last_run.json.
The morning run reads that file, computes deltas, and discards the file
(morning state is ephemeral — nothing is written back).

state/last_run.json lives on the `state` Git branch (not main).
The GitHub Actions workflow fetches it via `git show origin/state:…`
before the Python process starts; the Python process just does a
normal open() — it sees the file on the local disk.

JSON-safety rules enforced in write_state:
  * datetime.date  → ISO string ("2026-05-26")
  * float          → rounded to 4 dp
  * None / bool / int / str → passed through
  * anything else  → str() fallback (should not happen in practice)
"""

import json
import os
from datetime import date as date_cls


# Default path, relative to repo root (matches git show target).
STATE_PATH = "state/last_run.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_state(path: str = STATE_PATH) -> dict:
    """
    Load state/last_run.json.

    Returns {} in two normal cases:
      * File not found  — first-ever run, no previous state.
      * JSON corrupt    — should never happen, but safe fallback beats crash.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        print(f"[state] no state file at {path!r} — first run or morning-only run")
        return {}
    except json.JSONDecodeError as exc:
        print(f"[state] corrupt state file at {path!r}: {exc} — starting fresh")
        return {}


def write_state(path: str, blocks: dict, target_date: date_cls) -> None:
    """
    Serialise blocks dict to JSON at path.

    Creates the parent directory if it doesn't exist.
    The file format is:
        {
            "target_date": "2026-05-26",
            "blocks": { <block_name>: <block_dict_or_null>, ... }
        }
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    payload = {
        "target_date": target_date.isoformat(),
        "blocks": _serializable(blocks),
    }

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    print(f"[state] wrote state for {target_date} → {path!r}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serializable(obj):
    """Recursively convert obj into a JSON-safe type."""
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serializable(v) for v in obj]
    if isinstance(obj, date_cls):          # must come before bool check
        return obj.isoformat()
    if isinstance(obj, float):
        return round(obj, 4)
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    # Fallback: convert anything exotic (e.g. numpy types) to string.
    return str(obj)