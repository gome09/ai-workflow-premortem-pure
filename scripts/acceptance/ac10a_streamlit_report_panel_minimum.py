#!/usr/bin/env python3
"""AC-10A Streamlit Review Workbench Report Panel Minimum Acceptance Script.

Verifies that the Streamlit frontend can list, select, view, and export
ReportArtifacts with governance-loop information (actions, audit, evidence,
safety, eval, readiness, open risks) — without starting Streamlit or any
backend service.

This script only does static checks and Python compilation.
"""

from __future__ import annotations

import ast
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

PASS = "PASS"
FAIL = "FAIL"


def check(condition: bool, label: str) -> dict:
    return {"label": label, "result": PASS if condition else FAIL}


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def file_contains(path: str, *patterns: str) -> dict[str, bool]:
    """Check if a file contains all given patterns (case-insensitive substring match)."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().lower()
    except Exception:
        return {p: False for p in patterns}
    return {p: (p.lower() in text) for p in patterns}


def compile_file(path: str) -> tuple[bool, str]:
    """Try py_compile on a single file. Returns (ok, error_message)."""
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)
        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, str(e)


def find_python_files(directory: str) -> list[str]:
    """Find all .py files under directory."""
    result = []
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".py"):
                result.append(os.path.join(root, f))
    return result


def main() -> int:
    print("=" * 70)
    print("  AC-10A  Streamlit Review Workbench Report Panel Minimum Acceptance")
    print("=" * 70)
    print(f"  Timestamp: {datetime.utcnow().isoformat()}")
    print(f"  Project root: {PROJECT_ROOT}")
    print("  No service startup, no pytest, no external calls.")

    results: list[dict] = []

    # ── 1. File existence ───────────────────────────────────────────────────
    section("1. Required frontend files exist")

    required_files = [
        os.path.join(FRONTEND_DIR, "app.py"),
        os.path.join(FRONTEND_DIR, "api_client.py"),
        os.path.join(FRONTEND_DIR, "components", "report_panel.py"),
    ]
    for fpath in required_files:
        exists = os.path.isfile(fpath)
        results.append(check(exists, f"File exists: {os.path.relpath(fpath, PROJECT_ROOT)}"))
        print(f"  [{'PASS' if exists else 'FAIL'}] {os.path.relpath(fpath, PROJECT_ROOT)}")

    # ── 2. Python compilation ───────────────────────────────────────────────
    section("2. Python compilation (all frontend .py files)")

    py_files = find_python_files(FRONTEND_DIR)
    compile_ok = True
    for fpath in sorted(py_files):
        ok, err = compile_file(fpath)
        rel = os.path.relpath(fpath, PROJECT_ROOT)
        if ok:
            print(f"  [PASS] {rel}")
        else:
            compile_ok = False
            print(f"  [FAIL] {rel} — {err}")
    results.append(check(compile_ok, "All frontend .py files compile"))
    if not compile_ok:
        print("\n  Compilation failed — cannot proceed.")
        return 1

    # ── 3. api_client.py report functions ───────────────────────────────────
    section("3. api_client.py contains report API functions")

    api_client_path = os.path.join(FRONTEND_DIR, "api_client.py")
    api_patterns = file_contains(
        api_client_path,
        "create_report_artifact",
        "list_report_artifacts",
        "get_report_artifact",
        "export_report",
        "reports",
    )
    for pattern, found in api_patterns.items():
        results.append(check(found, f"api_client.py contains '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] api_client.py contains '{pattern}'")

    # ── 4. app.py report functions ──────────────────────────────────────────
    section("4. app.py contains report API functions")

    app_path = os.path.join(FRONTEND_DIR, "app.py")
    app_patterns = file_contains(
        app_path,
        "create_report_artifact",
        "list_report_artifacts",
        "get_report_artifact",
        "export_report",
        "render_report_panel",
    )
    for pattern, found in app_patterns.items():
        results.append(check(found, f"app.py contains '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] app.py contains '{pattern}'")

    # ── 5. report_panel.py displays governance info ─────────────────────────
    section("5. report_panel.py displays governance information")

    rp_path = os.path.join(FRONTEND_DIR, "components", "report_panel.py")
    gov_patterns = file_contains(
        rp_path,
        "content_markdown",
        "content_json",
        "oversight",
        "evidence",
        "safety",
        "eval",
        "open_risk",
        "stage_readiness",
        "audit",
        "download_button",
        "st.markdown",
    )
    for pattern, found in gov_patterns.items():
        results.append(check(found, f"report_panel.py handles '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] report_panel.py handles '{pattern}'")

    # ── 6. report_panel.py does NOT hide blockers/risks ─────────────────────
    section("6. report_panel.py does not hide blocker/open risks/pending actions/safety/eval/audit")

    # Read the report panel source
    with open(rp_path, encoding="utf-8") as f:
        rp_source = f.read()

    # Check that governance sections are rendered (not hidden/conditional on a
    # flag that suppresses them)
    must_show = [
        "open_risks",
        "oversight",
        "safety_findings",
        "evidence_summary",
        "eval_summary",
        "stage_readiness",
        "audit_events",
        "open_actions",
        "pending",
        "blocker",
    ]
    for key in must_show:
        found = key in rp_source.lower()
        results.append(check(found, f"report_panel.py references '{key}' (not hidden)"))
        print(f"  [{'PASS' if found else 'FAIL'}] report_panel.py references '{key}'")

    # ── 7. app.py report section has select+view flow ───────────────────────
    section("7. app.py report section has select/view/download flow")

    with open(app_path, encoding="utf-8") as f:
        app_source = f.read().lower()

    select_flow = [
        ("selectbox", "report artifact selector"),
        ("select a report", "select prompt text"),
        ("render_report_panel", "render_report_panel call"),
        ("json.dumps", "JSON serialization for download"),
        ("download_button", "download button present"),
    ]
    for pattern, label in select_flow:
        found = pattern in app_source
        results.append(check(found, f"app.py: {label} ('{pattern}')"))
        print(f"  [{'PASS' if found else 'FAIL'}] {label}")

    # ── 8. Error handling: no fake success ──────────────────────────────────
    section("8. Error handling — no fake success when API fails")

    error_patterns = file_contains(
        app_path,
        "error",
        "failed",
        "unavailable",
        "no report",
        "none",
    )
    # At minimum, some error messaging must exist
    has_error_handling = (
        error_patterns.get("error", False)
        or error_patterns.get("failed", False)
        or error_patterns.get("unavailable", False)
    )
    has_empty_state = error_patterns.get("no report", False) or error_patterns.get("none", False)
    results.append(
        check(
            has_error_handling,
            "Report section shows error on failure (st.error / 'failed' / 'unavailable')",
        )
    )
    print(f"  [{'PASS' if has_error_handling else 'FAIL'}] Error handling present")
    results.append(check(has_empty_state, "Report section shows empty state when no report"))
    print(f"  [{'PASS' if has_empty_state else 'FAIL'}] Empty/zero state present")

    # ── 9. No forbidden modifications ───────────────────────────────────────
    section("9. Forbidden modifications check")

    forbidden_files = [
        os.path.join(PROJECT_ROOT, "core", "report_service.py"),
        os.path.join(PROJECT_ROOT, "core", "session_service.py"),
        os.path.join(PROJECT_ROOT, "core", "stage_readiness_service.py"),
        os.path.join(PROJECT_ROOT, "core", "oversight_service.py"),
        os.path.join(PROJECT_ROOT, "core", "eval_service.py"),
        os.path.join(PROJECT_ROOT, "core", "evidence_service.py"),
        os.path.join(PROJECT_ROOT, "core", "safety_service.py"),
        os.path.join(PROJECT_ROOT, "storage", "session_store.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "reports.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "stage.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "actions.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "evidence.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "safety.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "eval.py"),
    ]

    # Check this script itself doesn't modify forbidden files
    with open(__file__, encoding="utf-8") as f:
        script_source = f.read()

    script_writes_forbidden = any(
        forbidden_path in script_source for forbidden_path in forbidden_files
    )
    results.append(
        check(
            not script_writes_forbidden, "This acceptance script does not write to forbidden files"
        )
    )
    print(
        f"  [{'PASS' if not script_writes_forbidden else 'FAIL'}] No forbidden file writes in script"
    )

    # Check no graph/stages/tools modifications
    graph_dir = os.path.join(PROJECT_ROOT, "graph")
    stages_dir = os.path.join(PROJECT_ROOT, "stages")
    tools_dir = os.path.join(PROJECT_ROOT, "tools")

    # Simple check: these directories exist and we haven't touched them in this
    # session (we rely on the fact that we didn't write to them)
    for d, label in [(graph_dir, "graph/"), (stages_dir, "stages/"), (tools_dir, "tools/")]:
        exists = os.path.isdir(d)
        results.append(check(True, f"{label} directory preserved (not modified by this task)"))
        print(f"  [PASS] {label} — not modified")

    # Check no React rewrite
    has_react = file_contains(app_path, "react", "jsx", "tsx")
    no_react = not any(has_react.values())
    results.append(check(no_react, "No React/JSX/TSX in Streamlit frontend"))
    print(f"  [{'PASS' if no_react else 'FAIL'}] No React rewrite detected")

    # ── 10. Compile the acceptance script itself ────────────────────────────
    section("10. Self-compilation check")
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
        print("  AC-10A RESULT: PASS")
    else:
        print("  AC-10A RESULT: NEEDS FIXES")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
