#!/usr/bin/env python3
"""AC-10F Streamlit Review Workbench Runtime Smoke Minimum Acceptance.

Verifies that FastAPI starts and /health returns OK, and that Streamlit
starts headless and serves the root page at 200. Checks logs for fatal
errors. Does NOT run workflow, chat, LLM, Tavily, pytest, or Docker.
"""

from __future__ import annotations

import ast
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMPDIR = Path(os.environ.get("TMPDIR", "/tmp"))
UVICORN_LOG = TMPDIR / "ac10f_uvicorn.log"
STREAMLIT_LOG = TMPDIR / "ac10f_streamlit.log"
UVICORN_PID_FILE = TMPDIR / "ac10f_uvicorn.pid"
STREAMLIT_PID_FILE = TMPDIR / "ac10f_streamlit.pid"

PASS = "PASS"
FAIL = "FAIL"


def check(condition: bool, label: str) -> dict:
    return {"label": label, "result": PASS if condition else FAIL}


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def compile_file(path: str) -> tuple[bool, str]:
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)
        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, str(e)


def read_pid(pf: Path) -> int | None:
    try:
        return int(pf.read_text().strip())
    except Exception:
        return None


def kill_pid(pf: Path) -> None:
    pid = read_pid(pf)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def main() -> int:
    print("=" * 70)
    print("  AC-10F  Streamlit Review Workbench Runtime Smoke Acceptance")
    print("=" * 70)
    print(f"  Timestamp: {datetime.now(UTC).isoformat()}")
    print(f"  Project root: {PROJECT_ROOT}")
    print("  WORKFLOW_EXECUTION_MODE=single_step (no LangGraph interrupt)")
    print("  LLM_PROVIDER=disabled (no real LLM)")
    print("  TAVILY_API_KEY= (no real Tavily)")
    print("  No pytest, no Docker, no full workflow execution.")

    results: list[dict] = []

    # ── 1. Compilation checks ───────────────────────────────────────────────
    section("1. Compilation checks")

    compile_targets = [
        os.path.join(PROJECT_ROOT, "api", "main.py"),
        os.path.join(PROJECT_ROOT, "core", "config.py"),
        os.path.join(PROJECT_ROOT, "frontend", "app.py"),
        os.path.join(PROJECT_ROOT, "frontend", "api_client.py"),
    ]
    all_ok = True
    for path in compile_targets:
        ok, err = compile_file(path)
        rel = os.path.relpath(path, PROJECT_ROOT)
        if ok:
            print(f"  [PASS] {rel}")
        else:
            all_ok = False
            print(f"  [FAIL] {rel} — {err}")
    results.append(check(all_ok, "All key files compile"))
    if not all_ok:
        print("\n  Compilation failed — cannot proceed.")
        return 1

    # ── 2. FastAPI startup + /health ────────────────────────────────────────
    section("2. FastAPI startup and /health")

    env = os.environ.copy()
    env["WORKFLOW_EXECUTION_MODE"] = "single_step"
    env["LLM_PROVIDER"] = "disabled"
    env["TAVILY_API_KEY"] = ""

    uvicorn_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        stdout=UVICORN_LOG.open("w"),
        stderr=subprocess.STDOUT,
        cwd=PROJECT_ROOT,
        env=env,
    )
    UVICORN_PID_FILE.write_text(str(uvicorn_proc.pid))
    print(f"  Uvicorn PID: {uvicorn_proc.pid}")
    time.sleep(3)

    # Check /health
    health_ok = False
    health_body = ""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as resp:
            health_body = resp.read().decode()
            health_ok = resp.status == 200
    except Exception as exc:
        health_body = str(exc)
    results.append(check(health_ok, "/health returns 200"))
    print(f"  [{'PASS' if health_ok else 'FAIL'}] /health -> {health_body[:120]}")

    # ── 3. Streamlit headless startup ───────────────────────────────────────
    section("3. Streamlit headless startup and root page")

    env["API_BASE"] = "http://127.0.0.1:8000"
    streamlit_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "frontend/app.py",
            "--server.headless",
            "true",
            "--server.port",
            "8501",
            "--browser.gatherUsageStats",
            "false",
        ],
        stdout=STREAMLIT_LOG.open("w"),
        stderr=subprocess.STDOUT,
        cwd=PROJECT_ROOT,
        env=env,
    )
    STREAMLIT_PID_FILE.write_text(str(streamlit_proc.pid))
    print(f"  Streamlit PID: {streamlit_proc.pid}")
    time.sleep(8)

    # Check root page
    streamlit_ok = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8501", timeout=5) as resp:
            streamlit_ok = resp.status == 200
    except Exception:
        pass
    results.append(check(streamlit_ok, "Streamlit root returns 200"))
    print(f"  [{'PASS' if streamlit_ok else 'FAIL'}] Streamlit root page reachable")

    # ── 4. Log sanity ───────────────────────────────────────────────────────
    section("4. Log sanity — no fatal markers")

    fatal_markers = [
        "Traceback",
        "ModuleNotFoundError",
        "ImportError",
        "SyntaxError",
        "NameError",
        "AttributeError",
    ]

    for name, log_path in [("uvicorn", UVICORN_LOG), ("streamlit", STREAMLIT_LOG)]:
        try:
            text = log_path.read_text(errors="ignore")
            hits = [m for m in fatal_markers if m in text]
            ok = len(hits) == 0
            results.append(check(ok, f"{name} log — no fatal markers"))
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {hits if hits else 'clean'}")
        except Exception as exc:
            results.append(check(False, f"{name} log readable"))
            print(f"  [FAIL] {name} log not readable: {exc}")

    # ── 5. Stop services ────────────────────────────────────────────────────
    section("5. Service teardown")

    kill_pid(STREAMLIT_PID_FILE)
    kill_pid(UVICORN_PID_FILE)
    time.sleep(1)
    print("  Services stopped.")

    # ── 6. Compile this acceptance script ───────────────────────────────────
    section("6. Self-compilation check")
    ok, err = compile_file(__file__)
    results.append(check(ok, "This acceptance script compiles"))
    print(f"  [{'PASS' if ok else 'FAIL'}] Self-compilation: {err if err else 'OK'}")

    # ── SUMMARY ─────────────────────────────────────────────────────────────
    section("SUMMARY")
    passed = sum(1 for r in results if r["result"] == PASS)
    failed = sum(1 for r in results if r["result"] == FAIL)
    total = len(results)
    print(f"  Total checks : {total}")
    print(f"  Passed       : {passed}")
    print(f"  Failed       : {failed}")
    print(f"  Pass rate    : {passed / total * 100:.1f}%")

    if failed:
        print("\n  FAILED CHECKS:")
        for r in results:
            if r["result"] == FAIL:
                print(f"    - {r['label']}")

    print("\n" + "=" * 70)
    if failed == 0:
        print("  AC-10F RESULT: PASS  — Runtime smoke verified")
    else:
        print("  AC-10F RESULT: NEEDS FIXES")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
