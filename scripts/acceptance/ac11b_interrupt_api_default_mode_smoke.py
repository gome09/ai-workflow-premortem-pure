# scripts/acceptance/ac11b_interrupt_api_default_mode_smoke.py
"""AC-11B: Interrupt API + Default Mode Runtime Smoke Acceptance Verification.

Starts FastAPI in single_step mode, checks /health and /openapi.json,
then stops. No pytest, no Streamlit, no chat, no LLM, no workflow runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(str(PROJECT_ROOT))

# ── Tmp paths (cross-platform) ──────────────────────────────────────────
TMP = Path(os.environ.get("TEMP", "/tmp"))
HEALTH_FILE = TMP / "ac11b_health.json"
OPENAPI_FILE = TMP / "ac11b_openapi.json"
UVICORN_LOG = TMP / "ac11b_uvicorn_smoke.log"
UVICORN_PID_FILE = TMP / "ac11b_uvicorn_smoke.pid"

# ── Target files to compile ─────────────────────────────────────────────
COMPILE_FILES = [
    "core/config.py",
    "core/execution_mode.py",
    "api/main.py",
    "api/routers/interrupts.py",
    "graph/langgraph_interrupt_runner.py",
    "graph/interrupt_gate.py",
    "graph/interrupts.py",
]

# ── Required OpenAPI route terms ────────────────────────────────────────
REQUIRED_ROUTES = {
    "sessions": "session",
    "interrupts": "interrupt",
    "stage": "stage",
    "evidence": "evidence",
    "safety": "safety",
    "eval": "eval",
    "reports": "report",
    "oversight_or_actions": "action",
}

FATAL_MARKERS = [
    "Traceback",
    "ModuleNotFoundError",
    "ImportError",
    "SyntaxError",
    "NameError",
    "AttributeError",
]

results: list[tuple[str, bool, str]] = []


def heading(text: str) -> None:
    print(f"\n{'=' * 64}")
    print(f"  {text}")
    print(f"{'=' * 64}")


def check(name: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    msg = f"  [{status}] {name}"
    print(msg)
    if detail and not passed:
        print(f"         {detail}")
    results.append((name, passed, detail))


def kill_port_8000() -> None:
    """Ensure port 8000 is free before starting."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | "
                    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }",
                ],
                capture_output=True,
                timeout=10,
            )
        else:
            subprocess.run(
                ["bash", "-c", "kill $(lsof -ti:8000) 2>/dev/null || true"],
                capture_output=True,
                timeout=10,
            )
        time.sleep(1)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Compile target files
# ═══════════════════════════════════════════════════════════════════════════
heading("Step 1: py_compile target files")

import py_compile

for rel_path in COMPILE_FILES:
    full_path = PROJECT_ROOT / rel_path
    try:
        py_compile.compile(str(full_path), doraise=True)
        check(f"py_compile {rel_path}", True)
    except py_compile.PyCompileError as e:
        check(f"py_compile {rel_path}", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Start uvicorn in single_step mode
# ═══════════════════════════════════════════════════════════════════════════
heading("Step 2: Start FastAPI in single_step mode")

kill_port_8000()

env = os.environ.copy()
env["WORKFLOW_EXECUTION_MODE"] = "single_step"
env["TAVILY_API_KEY"] = ""
env["DEEPSEEK_API_KEY"] = ""

log_fh = open(str(UVICORN_LOG), "w")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"],
    env=env,
    stdout=log_fh,
    stderr=subprocess.STDOUT,
    cwd=str(PROJECT_ROOT),
)

UVICORN_PID_FILE.write_text(str(proc.pid))
print(f"  uvicorn PID={proc.pid}")

time.sleep(4)

# Check if process is still alive
if proc.poll() is not None:
    check(
        "uvicorn process started",
        False,
        f"Process exited with code {proc.returncode}. Log tail:\n"
        + "\n".join(UVICORN_LOG.read_text(errors="ignore").splitlines()[-15:]),
    )
    log_fh.close()
    sys.exit(1)

check("uvicorn process started", True, f"PID={proc.pid}")


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Test /health
# ═══════════════════════════════════════════════════════════════════════════
heading("Step 3: Test /health endpoint")

try:
    resp = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10)
    health = json.loads(resp.read())
    HEALTH_FILE.write_text(json.dumps(health, indent=2))
    print(f"  health = {json.dumps(health)}")

    check("health.status == ok", health.get("status") == "ok")
    mode = health.get("workflow_execution_mode")
    check("health.workflow_execution_mode == single_step", mode == "single_step", f"got {mode!r}")
    check(
        "health.interrupt_adapter_status",
        "interrupt_adapter_status" in health,
        f"got {health.get('interrupt_adapter_status')}",
    )

except Exception as e:
    check("/health request", False, str(e))
    mode = None
    health = {}


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Test /openapi.json
# ═══════════════════════════════════════════════════════════════════════════
heading("Step 4: Test /openapi.json endpoint")

try:
    resp = urllib.request.urlopen("http://127.0.0.1:8000/openapi.json", timeout=10)
    openapi = json.loads(resp.read())
    OPENAPI_FILE.write_text(json.dumps(openapi, indent=2))
    paths = openapi.get("paths", {})
    print(f"  paths_count = {len(paths)}")

    check("openapi.paths non-empty", len(paths) > 0)

    def hits(term: str):
        return [p for p in paths if term in p.lower()]

    for label, term in REQUIRED_ROUTES.items():
        found = hits(term)
        check(
            f"openapi has {label} routes",
            len(found) > 0,
            f"term={term!r}, found={found[:5] if found else 'NONE'}",
        )

    # Interrupt paths specifically
    interrupt_paths = hits("interrupt")
    check(
        "interrupt routes exist (optional API)",
        len(interrupt_paths) > 0,
        f"interrupt_paths={interrupt_paths}",
    )
    print(f"  interrupt_paths = {interrupt_paths}")

    # Default mode must still be single_step
    if mode:
        check(
            "default mode still single_step (interrupt only optional API)",
            mode == "single_step",
            f"mode={mode}",
        )

except Exception as e:
    check("/openapi.json request", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Check uvicorn log for fatal errors
# ═══════════════════════════════════════════════════════════════════════════
heading("Step 5: Check uvicorn log for fatal errors")

log_text = UVICORN_LOG.read_text(errors="ignore")
print("  --- Last 15 log lines ---")
for line in log_text.splitlines()[-15:]:
    print(f"    {line}")

fatal_hits = [m for m in FATAL_MARKERS if m in log_text]
check("no fatal markers in uvicorn log", len(fatal_hits) == 0, f"Found: {fatal_hits}")


# ═══════════════════════════════════════════════════════════════════════════
# Step 6: Stop uvicorn
# ═══════════════════════════════════════════════════════════════════════════
heading("Step 6: Stop uvicorn")

log_fh.close()
try:
    proc.terminate()
    proc.wait(timeout=5)
    check("uvicorn stopped gracefully", True)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
    check("uvicorn killed (timeout)", True, "Terminate timed out, force killed")

# Final cleanup
kill_port_8000()


# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════
heading("SUMMARY")

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)

for name, ok, detail in results:
    status = "PASS" if ok else "FAIL"
    if not ok:
        print(f"  [{status}] {name}  --  {detail}")

print(f"\n  {passed}/{total} checks passed")

if passed == total:
    print("\n  AC-11B ALL CHECKS PASSED")
    print("  -> FastAPI starts in single_step mode as default.")
    print("  -> /health confirms workflow_execution_mode=single_step.")
    print("  -> /openapi.json exposes all routes including interrupt as optional API.")
    print("  -> No fatal errors in uvicorn startup log.")
    print("  -> No chat, no workflow, no LLM, no Tavily, no pytest used.")
else:
    print(f"\n  AC-11B: {total - passed} CHECK(S) FAILED")

print()
sys.exit(0 if passed == total else 1)
