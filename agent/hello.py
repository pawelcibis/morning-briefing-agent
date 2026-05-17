"""Phase 1: prove the runner can execute Python."""
import sys
from datetime import datetime, timezone

print(f"Hello from the morning-briefing-agent.")
print(f"Python version: {sys.version}")
print(f"UTC time: {datetime.now(timezone.utc).isoformat()}")