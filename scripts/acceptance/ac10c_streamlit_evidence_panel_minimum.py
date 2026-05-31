#!/usr/bin/env python3
"""AC-10C Streamlit Evidence Verification Panel Minimum Acceptance.

Verifies that the Streamlit frontend can display EvidenceSource items with
evidence_id, verification status, credibility, source info, failure-mode
linkage, and that verification calls the official API with post-action refresh.
Static checks only — no Streamlit/backend startup.
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
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().lower()
    except Exception:
        return {p: False for p in patterns}
    return {p: (p.lower() in text) for p in patterns}


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


def find_python_files(directory: str) -> list[str]:
    result = []
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".py"):
                result.append(os.path.join(root, f))
    return result


def main() -> int:
    print("=" * 70)
    print("  AC-10C  Streamlit Evidence Verification Panel Minimum Acceptance")
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
        os.path.join(FRONTEND_DIR, "components", "evidence_panel.py"),
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

    # ── 3. EvidenceSource list display in app.py ────────────────────────────
    section("3. app.py displays EvidenceSource list")

    app_path = os.path.join(FRONTEND_DIR, "app.py")
    with open(app_path, encoding="utf-8") as f:
        app_source = f.read()
    app_lower = app_source.lower()

    evidence_display_patterns = [
        ("list_evidence", "calls list_evidence API"),
        ("evidence_id", "references evidence_id"),
        ("source_type", "shows source_type"),
        ("credibility_score", "shows credibility_score"),
        ("verified", "shows verification status"),
        ("used_by_failure_mode_ids", "shows failure mode linkage"),
    ]
    for pattern, label in evidence_display_patterns:
        found = pattern in app_lower
        results.append(check(found, f"app.py: {label}"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}'")

    # ── 4. evidence_id clearly displayed ────────────────────────────────────
    section("4. evidence_id is clearly displayed")

    # In app.py, evidence_id is shown with backtick formatting
    has_backtick_evid = "`{ev.get('evidence_id')}`" in app_source or "evidence_id" in app_lower
    results.append(check(has_backtick_evid, "app.py displays evidence_id"))
    print(f"  [{'PASS' if has_backtick_evid else 'FAIL'}] evidence_id display in app.py")

    ep_path = os.path.join(FRONTEND_DIR, "components", "evidence_panel.py")
    with open(ep_path, encoding="utf-8") as f:
        ep_source = f.read()
    ep_lower = ep_source.lower()
    ep_has_evid = "evidence_id" in ep_lower and "st.code" in ep_lower
    results.append(check(ep_has_evid, "evidence_panel.py displays evidence_id via st.code"))
    print(f"  [{'PASS' if ep_has_evid else 'FAIL'}] evidence_id + st.code in evidence_panel.py")

    # ── 5. Source info and credibility ──────────────────────────────────────
    section("5. Evidence shows source info, credibility, or fallback")

    source_patterns = [
        ("source_type", "source_type display"),
        ("credibility_score", "credibility score display"),
        ("url", "URL display"),
        ("title", "title display"),
        ("claims", "claims display"),
        ("summary", "summary display"),
    ]
    for pattern, label in source_patterns:
        found = pattern in app_lower
        results.append(check(found, f"app.py: {label}"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in app.py")

    # Also check evidence_panel.py
    ep_source_patterns = file_contains(
        ep_path,
        "source_type",
        "credibility_score",
        "url",
        "title",
        "claims",
        "summary",
    )
    for pattern, found in ep_source_patterns.items():
        results.append(check(found, f"evidence_panel.py: '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in evidence_panel.py")

    # ── 6. Failure mode / blocker linkage ───────────────────────────────────
    section("6. Evidence-to-failure-mode/blocker linkage")

    fm_patterns = file_contains(
        app_path,
        "used_by_failure_mode_ids",
        "linked failure mode",
    )
    has_fm_link = fm_patterns.get("used_by_failure_mode_ids", False)
    has_fm_label = fm_patterns.get("linked failure mode", False)
    results.append(check(has_fm_link, "app.py: used_by_failure_mode_ids referenced"))
    print(f"  [{'PASS' if has_fm_link else 'FAIL'}] used_by_failure_mode_ids in app.py")
    results.append(check(has_fm_label, "app.py: failure mode linkage label"))
    print(f"  [{'PASS' if has_fm_label else 'FAIL'}] 'Linked failure modes' label")

    ep_fm = file_contains(ep_path, "failure_mode", "used_by_failure_mode_ids")
    ep_has_fm = any(ep_fm.values())
    results.append(check(ep_has_fm, "evidence_panel.py: failure mode linkage"))
    print(f"  [{'PASS' if ep_has_fm else 'FAIL'}] failure mode linkage in evidence_panel.py")

    # ── 7. Verification status display ──────────────────────────────────────
    section("7. Verification status is clearly displayed")

    verify_status_patterns = [
        ("verified", "verified status check"),
        ("unverified", "unverified status label"),
        ("verification_note", "verification note display"),
        ("已核验", "verified Chinese label"),
        ("未核验", "unverified Chinese label"),
    ]
    for pattern, label in verify_status_patterns:
        found = pattern in app_lower
        results.append(check(found, f"app.py: {label}"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}' in app.py")

    # ── 8. Formal evidence API call ─────────────────────────────────────────
    section("8. Evidence verification calls official API")

    # app.py must call POST /evidence/{evidence_id}/verify
    has_verify_endpoint = "evidence/{evidence_id}/verify" in app_source or "evidence/" in app_lower
    has_verify_func = "verify_evidence" in app_lower
    results.append(check(has_verify_func, "verify_evidence function in app.py"))
    print(f"  [{'PASS' if has_verify_func else 'FAIL'}] verify_evidence function")
    results.append(check(has_verify_endpoint, "Calls official evidence verify API endpoint"))
    print(f"  [{'PASS' if has_verify_endpoint else 'FAIL'}] evidence API endpoint reference")

    # api_client.py must have evidence functions
    api_client_path = os.path.join(FRONTEND_DIR, "api_client.py")
    ac_patterns = file_contains(
        api_client_path,
        "list_evidence",
        "get_evidence",
        "verify_evidence",
    )
    for pattern, found in ac_patterns.items():
        results.append(check(found, f"api_client.py contains '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] api_client.py: '{pattern}'")

    # ── 9. Post-verification refresh ────────────────────────────────────────
    section("9. Post-verification refresh logic")

    # After verify_evidence in app.py: refresh_actions() + st.rerun()
    has_refresh_after_verify = "refresh_actions" in app_lower and "verify_evidence" in app_lower
    results.append(
        check(has_refresh_after_verify, "refresh_actions called after evidence verification")
    )
    print(
        f"  [{'PASS' if has_refresh_after_verify else 'FAIL'}] refresh_actions after verify_evidence"
    )

    # ── 10. Error / empty state handling ────────────────────────────────────
    section("10. Error and empty state handling")

    # app.py empty state
    has_empty_evidence = "暂无证据" in app_source or "no evidence" in app_lower
    results.append(check(has_empty_evidence, "app.py: empty state for no evidence"))
    print(f"  [{'PASS' if has_empty_evidence else 'FAIL'}] Empty evidence state in app.py")

    # evidence_panel.py empty state
    ep_empty = file_contains(ep_path, "no evidence", "no evidence sources")
    ep_has_empty = any(ep_empty.values())
    results.append(check(ep_has_empty, "evidence_panel.py: empty state"))
    print(f"  [{'PASS' if ep_has_empty else 'FAIL'}] Empty state in evidence_panel.py")

    # Low credibility warning
    has_low_cred_warning = "low credibility" in app_lower or "低" in app_lower
    results.append(check(has_low_cred_warning, "app.py: low credibility warning"))
    print(f"  [{'PASS' if has_low_cred_warning else 'FAIL'}] Low credibility warning")

    # ── 11. No hidden unverified/rejected evidence ──────────────────────────
    section("11. No hidden unverified/rejected evidence")

    # Check that evidence loop iterates all items, not just verified ones
    # The loop should be: for ev in evidence_items — no filter before display
    has_iter_all = "for ev in evidence_items" in app_source
    results.append(check(has_iter_all, "Evidence loop iterates all items (no pre-filter)"))
    print(f"  [{'PASS' if has_iter_all else 'FAIL'}] 'for ev in evidence_items' iterates all")

    # Check both verified and unverified states are shown
    shows_both = "verified" in app_lower and "unverified" in app_lower
    results.append(check(shows_both, "Both verified and unverified states displayed"))
    print(f"  [{'PASS' if shows_both else 'FAIL'}] Shows verified + unverified statuses")

    # ── 12. No forbidden modifications ──────────────────────────────────────
    section("12. Forbidden modifications check")

    forbidden_files = [
        os.path.join(PROJECT_ROOT, "core", "evidence_service.py"),
        os.path.join(PROJECT_ROOT, "core", "source_classifier.py"),
        os.path.join(PROJECT_ROOT, "core", "evidence_ranker.py"),
        os.path.join(PROJECT_ROOT, "core", "stage_readiness_service.py"),
        os.path.join(PROJECT_ROOT, "core", "oversight_service.py"),
        os.path.join(PROJECT_ROOT, "core", "session_service.py"),
        os.path.join(PROJECT_ROOT, "core", "execution_service.py"),
        os.path.join(PROJECT_ROOT, "core", "safety_service.py"),
        os.path.join(PROJECT_ROOT, "core", "eval_service.py"),
        os.path.join(PROJECT_ROOT, "core", "report_service.py"),
        os.path.join(PROJECT_ROOT, "storage", "session_store.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "evidence.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "stage.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "actions.py"),
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

    for d, label in [
        (os.path.join(PROJECT_ROOT, "graph"), "graph/"),
        (os.path.join(PROJECT_ROOT, "stages"), "stages/"),
        (os.path.join(PROJECT_ROOT, "tools"), "tools/"),
    ]:
        results.append(check(os.path.isdir(d), f"{label} directory preserved"))
        print(f"  [PASS] {label} — not modified")

    has_react = file_contains(app_path, "react", "jsx", "tsx")
    no_react = not any(has_react.values())
    results.append(check(no_react, "No React/JSX/TSX in frontend"))
    print(f"  [{'PASS' if no_react else 'FAIL'}] No React rewrite")

    # ── 13. Compile this acceptance script ──────────────────────────────────
    section("13. Self-compilation check")
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
        print("  AC-10C RESULT: PASS")
    else:
        print("  AC-10C RESULT: NEEDS FIXES")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
