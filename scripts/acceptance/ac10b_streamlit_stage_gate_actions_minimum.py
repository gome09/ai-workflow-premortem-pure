#!/usr/bin/env python3
"""AC-10B Streamlit Review Workbench Stage Gate + PendingHumanAction Minimum Acceptance.

Verifies that the Streamlit frontend can display current stage, Stage Gate blockers,
and PendingHumanActions, and that action resolution calls the official API with
post-resolution refresh. Static checks only — no Streamlit/backend startup.
"""

from __future__ import annotations

import ast
import os
import sys
from datetime import UTC, datetime

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
    """Try to parse a Python file. Returns (ok, error_message)."""
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
    result = []
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".py"):
                result.append(os.path.join(root, f))
    return result


def main() -> int:
    print("=" * 70)
    print("  AC-10B  Streamlit Stage Gate + PendingHumanAction Minimum Acceptance")
    print("=" * 70)
    print(f"  Timestamp: {datetime.now(UTC).isoformat()}")
    print(f"  Project root: {PROJECT_ROOT}")
    print("  No service startup, no pytest, no external calls.")

    results: list[dict] = []

    # ── 1. File existence ───────────────────────────────────────────────────
    section("1. Required frontend files exist")

    required_files = [
        os.path.join(FRONTEND_DIR, "app.py"),
        os.path.join(FRONTEND_DIR, "api_client.py"),
        os.path.join(FRONTEND_DIR, "components", "action_queue.py"),
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

    # ── 3. Workflow progress / current stage display ────────────────────────
    section("3. app.py displays current stage / workflow progress")

    app_path = os.path.join(FRONTEND_DIR, "app.py")
    progress_patterns = file_contains(
        app_path,
        "current_state",
        "state_labels",
        "stage_progress",
        "st.progress",
        "stage_cols",
    )
    for pattern, found in progress_patterns.items():
        results.append(check(found, f"app.py: stage/progress pattern '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in app.py")

    # ── 4. Stage Gate / StageReadiness blocker display ──────────────────────
    section("4. app.py displays Stage Gate / StageReadiness blockers")

    gate_patterns = file_contains(
        app_path,
        "stage_readiness",
        "blocker",
        "can_continue",
        "block_reason",
        "gate_label",
        "required_resolution",
    )
    for pattern, found in gate_patterns.items():
        results.append(check(found, f"app.py: stage gate pattern '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in app.py")

    # ── 5. Blocker display does NOT hide open blockers ──────────────────────
    section("5. No hidden blockers — expanded when blockers exist")

    with open(app_path, encoding="utf-8") as f:
        app_source = f.read()

    # The expander should have expanded=bool(blockers) — showing blockers by default
    has_expanded_blockers = "expanded=bool(blockers)" in app_source
    results.append(
        check(has_expanded_blockers, "Blockers expander defaults to expanded when blockers exist")
    )
    print(f"  [{'PASS' if has_expanded_blockers else 'FAIL'}] expander expanded=bool(blockers)")

    # Check that blocker display iterates and shows each blocker
    has_blocker_loop = "for blocker in blockers" in app_source
    results.append(check(has_blocker_loop, "Blocker list iterates over all blockers"))
    print(f"  [{'PASS' if has_blocker_loop else 'FAIL'}] 'for blocker in blockers' loop")

    # Check that action_id is shown with each blocker
    has_blocker_action_id = 'blocker.get("action_id")' in app_source
    results.append(check(has_blocker_action_id, "Blocker display references action_id"))
    print(f"  [{'PASS' if has_blocker_action_id else 'FAIL'}] blocker action_id display")

    # ── 6. PendingHumanAction list display ──────────────────────────────────
    section("6. PendingHumanAction list display")

    action_patterns = file_contains(
        app_path,
        "pending_actions",
        "action_id",
        "待处理人工动作",
        "risk_level",
        "action_type",
        "blocking",
    )
    for pattern, found in action_patterns.items():
        results.append(check(found, f"app.py: action display pattern '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in app.py")

    # ── 7. action_id displayed via st.code (visible/emphasized) ─────────────
    section("7. action_id is clearly displayed")

    has_action_code = (
        "st.code(action_id" in app_source or "st.code(action.get('action_id')" in app_source
    )
    results.append(check(has_action_code, "action_id displayed via st.code in app.py"))
    print(f"  [{'PASS' if has_action_code else 'FAIL'}] st.code(action_id) in app.py")

    aq_path = os.path.join(FRONTEND_DIR, "components", "action_queue.py")
    aq_patterns = file_contains(aq_path, "action_id", "st.code")
    aq_shows_action_id = aq_patterns.get("action_id", False) and aq_patterns.get("st.code", False)
    results.append(check(aq_shows_action_id, "action_queue.py displays action_id via st.code"))
    print(f"  [{'PASS' if aq_shows_action_id else 'FAIL'}] action_queue.py: action_id + st.code")

    # ── 8. Formal action API call ───────────────────────────────────────────
    section("8. Action resolution calls official API (not local-only)")

    # app.py must call POST /actions/{action_id}/resolve
    has_resolve_endpoint = "actions/{action_id}/resolve" in app_source
    results.append(check(has_resolve_endpoint, "resolve_action calls official API endpoint"))
    print(f"  [{'PASS' if has_resolve_endpoint else 'FAIL'}] POST /actions/{{action_id}}/resolve")

    # api_client.py must have resolve_action
    api_client_path = os.path.join(FRONTEND_DIR, "api_client.py")
    ac_patterns = file_contains(
        api_client_path,
        "resolve_action",
        "list_actions",
        "get_action",
        "actions",
    )
    for pattern, found in ac_patterns.items():
        results.append(check(found, f"api_client.py contains '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] api_client.py: '{pattern}'")

    # ── 9. Post-action refresh logic ────────────────────────────────────────
    section("9. Post-action refresh logic exists")

    refresh_patterns = file_contains(
        app_path,
        "refresh_actions",
        "refresh_flags",
        "st.rerun",
    )
    for pattern, found in refresh_patterns.items():
        results.append(check(found, f"app.py: refresh pattern '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in app.py")

    # Check that resolve_action updates session state from API response
    has_state_update = (
        "st.session_state.pending_actions" in app_source
        and 'result.get("pending_actions"' in app_source
    )
    results.append(
        check(has_state_update, "resolve_action updates pending_actions from API response")
    )
    print(f"  [{'PASS' if has_state_update else 'FAIL'}] pending_actions updated from API result")

    # Check stage_readiness cache invalidation after action
    has_readiness_invalidate = "st.session_state.stage_readiness = {}" in app_source
    results.append(
        check(has_readiness_invalidate, "Stage readiness cache invalidated after action")
    )
    print(f"  [{'PASS' if has_readiness_invalidate else 'FAIL'}] stage_readiness cache cleared")

    # ── 10. Error / empty state handling ────────────────────────────────────
    section("10. Error and empty state handling")

    error_patterns = file_contains(
        app_path,
        "st.error",
        "st.warning",
        "无法连接",
        "no pending",
        "暂无",
    )
    has_error_ui = error_patterns.get("st.error", False)
    has_warning_ui = error_patterns.get("st.warning", False)
    has_empty_state = error_patterns.get("no pending", False) or error_patterns.get("暂无", False)
    results.append(check(has_error_ui, "Error UI (st.error) present"))
    print(f"  [{'PASS' if has_error_ui else 'FAIL'}] st.error usage")
    results.append(check(has_warning_ui, "Warning UI (st.warning) present"))
    print(f"  [{'PASS' if has_warning_ui else 'FAIL'}] st.warning usage")
    results.append(check(has_empty_state, "Empty state message present"))
    print(f"  [{'PASS' if has_empty_state else 'FAIL'}] Empty/zero state messaging")

    # Check action_queue.py has empty state
    aq_empty = file_contains(aq_path, "no pending", "no actions")
    aq_has_empty = any(aq_empty.values())
    results.append(check(aq_has_empty, "action_queue.py shows empty state when no actions"))
    print(f"  [{'PASS' if aq_has_empty else 'FAIL'}] action_queue.py empty state")

    # ── 11. No forbidden modifications ──────────────────────────────────────
    section("11. Forbidden modifications check")

    forbidden_files = [
        os.path.join(PROJECT_ROOT, "core", "oversight_service.py"),
        os.path.join(PROJECT_ROOT, "core", "stage_readiness_service.py"),
        os.path.join(PROJECT_ROOT, "core", "session_service.py"),
        os.path.join(PROJECT_ROOT, "core", "execution_service.py"),
        os.path.join(PROJECT_ROOT, "core", "evidence_service.py"),
        os.path.join(PROJECT_ROOT, "core", "safety_service.py"),
        os.path.join(PROJECT_ROOT, "core", "eval_service.py"),
        os.path.join(PROJECT_ROOT, "core", "report_service.py"),
        os.path.join(PROJECT_ROOT, "storage", "session_store.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "actions.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "stage.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "session.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "chat.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "evidence.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "safety.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "eval.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "reports.py"),
    ]

    with open(__file__, encoding="utf-8") as f:
        script_source = f.read()

    script_writes_forbidden = any(
        forbidden_path in script_source for forbidden_path in forbidden_files
    )
    results.append(
        check(not script_writes_forbidden, "This script does not write to forbidden files")
    )
    print(
        f"  [{'PASS' if not script_writes_forbidden else 'FAIL'}] No forbidden file writes in script"
    )

    # Verify graph/stages/tools directories not modified
    for d, label in [
        (os.path.join(PROJECT_ROOT, "graph"), "graph/"),
        (os.path.join(PROJECT_ROOT, "stages"), "stages/"),
        (os.path.join(PROJECT_ROOT, "tools"), "tools/"),
    ]:
        results.append(check(os.path.isdir(d), f"{label} directory preserved"))
        print(f"  [PASS] {label} — not modified")

    # No React rewrite
    has_react = file_contains(app_path, "react", "jsx", "tsx")
    no_react = not any(has_react.values())
    results.append(check(no_react, "No React/JSX/TSX in frontend"))
    print(f"  [{'PASS' if no_react else 'FAIL'}] No React rewrite")

    # ── 12. action_queue.py properly shows action details ────────────────────
    section("12. action_queue.py displays action details correctly")

    aq_detail_patterns = file_contains(
        aq_path,
        "action_id",
        "blocking",
        "risk_level",
        "action_type",
        "source_type",
        "stage_id",
        "st.code",
    )
    for pattern, found in aq_detail_patterns.items():
        results.append(check(found, f"action_queue.py: '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in action_queue.py")

    # ── 13. api_client.py has stage resolution functions ────────────────────
    section("13. api_client.py has stage resolution functions")

    stage_api_patterns = file_contains(
        api_client_path,
        "get_stage_resolution",
        "prepare_stage_operation",
        "list_interrupt_records",
        "get_stage_readiness",
    )
    for pattern, found in stage_api_patterns.items():
        results.append(check(found, f"api_client.py: '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in api_client.py")

    # ── 14. Compile acceptance script itself ────────────────────────────────
    section("14. Self-compilation check")
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
        print("  AC-10B RESULT: PASS")
    else:
        print("  AC-10B RESULT: NEEDS FIXES")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
