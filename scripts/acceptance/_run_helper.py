"""Helper to run acceptance scripts with correct PYTHONPATH.

Usage (inside Docker):
    python scripts/acceptance/_run_helper.py scripts/acceptance/ac09a_report_artifact_export.py
"""

import sys
from pathlib import Path

# Ensure /app is on sys.path so project imports work
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python _run_helper.py <script_path>", file=sys.stderr)
        sys.exit(1)
    script = Path(sys.argv[1])
    if not script.exists():
        print(f"Script not found: {script}", file=sys.stderr)
        sys.exit(1)
    exec(script.read_text(encoding="utf-8"))
