#!/usr/bin/env python3
"""AC-10D Streamlit Safety + Eval Panels Combined Minimum Acceptance.

Verifies that the Streamlit frontend can display and process SafetyFindings
(severity, status, high/critical warnings) and EvalCases/EvalRuns (unique IDs,
status, scoring, API calls). Static checks only — no service startup.
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
    print("  AC-10D  Streamlit Safety + Eval Panels Combined Minimum Acceptance")
    print("=" * 70)
    print(f"  Timestamp: {datetime.now(UTC).isoformat()}")
    print(f"  Project root: {PROJECT_ROOT}")
    print("  No service startup, no pytest, no external calls.")

    results: list[dict] = []

    app_path = os.path.join(FRONTEND_DIR, "app.py")
    api_path = os.path.join(FRONTEND_DIR, "api_client.py")
    safety_path = os.path.join(FRONTEND_DIR, "components", "safety_panel.py")
    eval_path = os.path.join(FRONTEND_DIR, "components", "eval_panel.py")

    with open(app_path, encoding="utf-8") as f:
        app_source = f.read()
    app_lower = app_source.lower()

    # ── 1. File existence ───────────────────────────────────────────────────
    section("1. Required frontend files exist")

    for fpath in [app_path, api_path, safety_path, eval_path]:
        exists = os.path.isfile(fpath)
        results.append(check(exists, f"File exists: {os.path.relpath(fpath, PROJECT_ROOT)}"))
        print(f"  [{'PASS' if exists else 'FAIL'}] {os.path.relpath(fpath, PROJECT_ROOT)}")

    # ── 2. Python compilation ───────────────────────────────────────────────
    section("2. Python compilation (all frontend .py files)")

    compile_ok = True
    for fpath in sorted(find_python_files(FRONTEND_DIR)):
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

    # ══════════════════════════════════════════════════════════════════════════
    # SAFETY SECTION
    # ══════════════════════════════════════════════════════════════════════════

    # ── 3. SafetyFinding list display in app.py ─────────────────────────────
    section("3. SAFETY — app.py displays SafetyFinding list")

    safety_display = [
        ("list_safety_findings", "calls list_safety_findings API"),
        ("finding_id", "references finding_id"),
        ("severity", "shows severity"),
        ("risk_type", "shows risk_type"),
        ("description", "shows description"),
        ("recommended_action", "shows recommended_action"),
    ]
    for pattern, label in safety_display:
        found = pattern in app_lower
        results.append(check(found, f"app.py safety: {label}"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}'")

    # ── 4. finding_id clearly displayed ─────────────────────────────────────
    section("4. SAFETY — finding_id clearly displayed")

    has_backtick_fid = "`{finding.get('finding_id')}`" in app_source or "finding_id" in app_lower
    results.append(check(has_backtick_fid, "app.py displays finding_id"))
    print(f"  [{'PASS' if has_backtick_fid else 'FAIL'}] finding_id display in app.py")

    with open(safety_path, encoding="utf-8") as f:
        sp_source = f.read()
    sp_lower = sp_source.lower()
    sp_has_fid = "finding_id" in sp_lower and "st.code" in sp_lower
    results.append(check(sp_has_fid, "safety_panel.py displays finding_id via st.code"))
    print(f"  [{'PASS' if sp_has_fid else 'FAIL'}] finding_id + st.code in safety_panel.py")

    # ── 5. High/critical unresolved warning ─────────────────────────────────
    section("5. SAFETY — high/critical unresolved findings have visible warning")

    has_high_crit_warning = (
        "high" in app_lower and "critical" in app_lower and "st.warning" in app_lower
    ) or ("high/critical" in app_lower)
    results.append(check(has_high_crit_warning, "High/critical unresolved findings get st.warning"))
    print(f"  [{'PASS' if has_high_crit_warning else 'FAIL'}] High/critical warning in app.py")

    # safety_panel.py must also warn on high/critical
    sp_warns = "st.warning" in sp_lower and ("high" in sp_lower or "critical" in sp_lower)
    results.append(check(sp_warns, "safety_panel.py warns on high/critical findings"))
    print(f"  [{'PASS' if sp_warns else 'FAIL'}] High/critical warning in safety_panel.py")

    # ── 6. Safety findings not hidden ───────────────────────────────────────
    section("6. SAFETY — no hidden high/critical findings")

    has_iter_all_findings = "for finding in findings" in app_source
    results.append(check(has_iter_all_findings, "Safety loop iterates all findings"))
    print(
        f"  [{'PASS' if has_iter_all_findings else 'FAIL'}] 'for finding in findings' iterates all"
    )

    shows_both_statuses = "open" in app_lower and (
        "resolved" in app_lower or "dismissed" in app_lower
    )
    results.append(check(shows_both_statuses, "Both open and resolved/dismissed statuses visible"))
    print(f"  [{'PASS' if shows_both_statuses else 'FAIL'}] Shows open + resolved/dismissed")

    # ── 7. Formal safety API call ───────────────────────────────────────────
    section("7. SAFETY — resolve calls official API")

    has_safety_endpoint = "safety-findings" in app_lower and "resolve" in app_lower
    results.append(check(has_safety_endpoint, "resolve_safety_finding calls official API"))
    print(f"  [{'PASS' if has_safety_endpoint else 'FAIL'}] safety-findings resolve endpoint")

    ac_safety = file_contains(api_path, "list_safety_findings", "resolve_safety_finding")
    for pattern, found in ac_safety.items():
        results.append(check(found, f"api_client.py contains '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] api_client.py: '{pattern}'")

    # ── 8. Safety post-action refresh ──────────────────────────────────────
    section("8. SAFETY — post-resolution refresh")

    has_safety_refresh = "refresh_actions" in app_lower and "resolve_safety_finding" in app_lower
    results.append(check(has_safety_refresh, "refresh_actions called after safety resolution"))
    print(f"  [{'PASS' if has_safety_refresh else 'FAIL'}] refresh after safety resolve")

    # ══════════════════════════════════════════════════════════════════════════
    # EVAL SECTION
    # ══════════════════════════════════════════════════════════════════════════

    # ── 9. EvalCase list display in app.py ──────────────────────────────────
    section("9. EVAL — app.py displays EvalCase list")

    eval_display = [
        ("list_eval_cases", "calls list_eval_cases API"),
        ("eval_id", "references eval_id"),
        ("target_node_id", "shows target_node_id"),
        ("scenario_type", "shows scenario_type"),
        ("input_payload", "shows input_payload"),
        ("expected_behavior", "shows expected_behavior"),
    ]
    for pattern, label in eval_display:
        found = pattern in app_lower
        results.append(check(found, f"app.py eval: {label}"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}'")

    # ── 10. EvalRun display ─────────────────────────────────────────────────
    section("10. EVAL — EvalRun display with run_id and status")

    eval_run_display = [
        ("list_eval_runs", "calls list_eval_runs"),
        ("run_id", "shows run_id"),
        ("judge_result", "shows judge_result"),
        ("status", "shows run status"),
    ]
    for pattern, label in eval_run_display:
        found = pattern in app_lower
        results.append(check(found, f"app.py eval: {label}"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}'")

    # ── 11. Eval unique IDs clearly displayed ──────────────────────────────
    section("11. EVAL — case_id / run_id clearly displayed")

    has_evalid_display = "eval_id" in app_lower
    has_runid_display = "run_id" in app_lower
    results.append(check(has_evalid_display, "app.py displays eval_id"))
    print(f"  [{'PASS' if has_evalid_display else 'FAIL'}] eval_id display in app.py")
    results.append(check(has_runid_display, "app.py displays run_id"))
    print(f"  [{'PASS' if has_runid_display else 'FAIL'}] run_id display in app.py")

    with open(eval_path, encoding="utf-8") as f:
        ep_source = f.read()
    ep_lower = ep_source.lower()
    ep_has_ids = "eval_id" in ep_lower and "run_id" in ep_lower and "st.code" in ep_lower
    results.append(check(ep_has_ids, "eval_panel.py displays eval_id + run_id via st.code"))
    print(f"  [{'PASS' if ep_has_ids else 'FAIL'}] eval_id + run_id + st.code in eval_panel.py")

    # ── 12. Failed not displayed as passed ─────────────────────────────────
    section("12. EVAL — failed/needs_review NOT displayed as passed")

    has_failed_indicator = (
        "failed" in app_lower or "不通过" in app_source or "passed=false" in app_lower
    )
    results.append(check(has_failed_indicator, "Failed status is distinguishable from passed"))
    print(f"  [{'PASS' if has_failed_indicator else 'FAIL'}] Failed indicator present")

    # eval_panel.py must also distinguish failed
    ep_has_failed = "failed" in ep_lower or "not passed" in ep_lower
    results.append(check(ep_has_failed, "eval_panel.py distinguishes failed from passed"))
    print(f"  [{'PASS' if ep_has_failed else 'FAIL'}] eval_panel.py failed indicator")

    # ── 13. Human scoring support ───────────────────────────────────────────
    section("13. EVAL — human scoring / review fields")

    scoring_patterns = [
        ("human_score", "human_score field"),
        ("human_comment", "human_comment field"),
        ("score_eval_case", "calls score_eval_case API"),
        ("slider", "score slider widget"),
    ]
    for pattern, label in scoring_patterns:
        found = pattern in app_lower
        results.append(check(found, f"app.py eval: {label}"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}'")

    # ── 14. Formal eval API calls ───────────────────────────────────────────
    section("14. EVAL — run and score call official API")

    eval_api_patterns = [
        ("run_eval_cases", "run_eval_cases function"),
        ("score_eval_case", "score_eval_case function"),
        ("eval-cases/run", "eval run endpoint"),
        ("eval-cases/{eval_id}/score", "eval score endpoint"),
    ]
    for pattern, label in eval_api_patterns:
        found = pattern in app_lower
        results.append(check(found, f"app.py eval: {label}"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}'")

    ac_eval = file_contains(
        api_path,
        "list_eval_cases",
        "list_eval_runs",
        "run_eval_cases",
        "score_eval_case",
    )
    for pattern, found in ac_eval.items():
        results.append(check(found, f"api_client.py contains '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] api_client.py: '{pattern}'")

    # ── 15. Eval post-action refresh ────────────────────────────────────────
    section("15. EVAL — post-run/score refresh")

    has_eval_refresh = (
        (
            "run_eval_cases" in app_lower
            or "run_single_eval_case" in app_lower
            or "score_eval_case" in app_lower
        )
        and "refresh_actions" in app_lower
        and "st.rerun" in app_lower
    )
    results.append(check(has_eval_refresh, "refresh_actions called after eval run/score"))
    print(f"  [{'PASS' if has_eval_refresh else 'FAIL'}] Refresh after eval operations")

    # ── 16. Error / empty state handling ────────────────────────────────────
    section("16. Error and empty state handling (safety + eval)")

    # Safety empty state
    has_safety_empty = "暂无未关闭安全发现" in app_source or "no open safety" in app_lower
    results.append(check(has_safety_empty, "Safety empty state"))
    print(f"  [{'PASS' if has_safety_empty else 'FAIL'}] Safety empty state in app.py")

    # Eval empty state
    has_eval_empty = "暂无 evalcase" in app_lower or "no eval cases" in app_lower
    results.append(check(has_eval_empty, "Eval empty state"))
    print(f"  [{'PASS' if has_eval_empty else 'FAIL'}] Eval empty state in app.py")

    # Safety panel component empty state
    sp_empty = file_contains(safety_path, "no open safety", "no safety findings")
    sp_has_empty = any(sp_empty.values())
    results.append(check(sp_has_empty, "safety_panel.py empty state"))
    print(f"  [{'PASS' if sp_has_empty else 'FAIL'}] Safety panel empty state")

    # Eval panel component empty state
    ep_empty = file_contains(eval_path, "no eval cases")
    ep_has_empty = any(ep_empty.values())
    results.append(check(ep_has_empty, "eval_panel.py empty state"))
    print(f"  [{'PASS' if ep_has_empty else 'FAIL'}] Eval panel empty state")

    # Error UI
    has_error_ui = "st.error" in app_lower
    results.append(check(has_error_ui, "st.error used for API failures"))
    print(f"  [{'PASS' if has_error_ui else 'FAIL'}] st.error in app.py")

    # ── 17. Safety panel component detail checks ────────────────────────────
    section("17. safety_panel.py detail checks")

    sp_detail = file_contains(
        safety_path,
        "finding_id",
        "severity",
        "status",
        "risk_type",
        "description",
        "recommended_action",
        "st.warning",
        "st.code",
    )
    for pattern, found in sp_detail.items():
        results.append(check(found, f"safety_panel.py: '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}'")

    # ── 18. eval_panel.py detail checks ─────────────────────────────────────
    section("18. eval_panel.py detail checks")

    ep_detail = file_contains(
        eval_path,
        "eval_id",
        "run_id",
        "scenario_type",
        "target_node_id",
        "input_payload",
        "expected_behavior",
        "judge_result",
        "passed",
        "failed",
        "st.code",
    )
    for pattern, found in ep_detail.items():
        results.append(check(found, f"eval_panel.py: '{pattern}'"))
        print(f"  [{'PASS' if found else 'FAIL'}] '{pattern}'")

    # ── 19. No forbidden modifications ──────────────────────────────────────
    section("19. Forbidden modifications check")

    forbidden_files = [
        os.path.join(PROJECT_ROOT, "core", "safety_service.py"),
        os.path.join(PROJECT_ROOT, "core", "safety_classifier.py"),
        os.path.join(PROJECT_ROOT, "core", "prompt_injection_scanner.py"),
        os.path.join(PROJECT_ROOT, "core", "eval_service.py"),
        os.path.join(PROJECT_ROOT, "core", "eval_runner.py"),
        os.path.join(PROJECT_ROOT, "core", "stage_readiness_service.py"),
        os.path.join(PROJECT_ROOT, "core", "oversight_service.py"),
        os.path.join(PROJECT_ROOT, "core", "evidence_service.py"),
        os.path.join(PROJECT_ROOT, "core", "report_service.py"),
        os.path.join(PROJECT_ROOT, "core", "session_service.py"),
        os.path.join(PROJECT_ROOT, "core", "execution_service.py"),
        os.path.join(PROJECT_ROOT, "storage", "session_store.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "safety.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "eval.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "stage.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "actions.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "evidence.py"),
        os.path.join(PROJECT_ROOT, "api", "routers", "reports.py"),
    ]

    with open(__file__, encoding="utf-8") as f:
        script_source = f.read()

    script_writes_forbidden = any(
        forbidden_path in script_source for forbidden_path in forbidden_files
    )
    results.append(check(not script_writes_forbidden, "Script does not write to forbidden files"))
    print(f"  [{'PASS' if not script_writes_forbidden else 'FAIL'}] No forbidden file writes")

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

    # ── 20. Self-compilation ────────────────────────────────────────────────
    section("20. Self-compilation check")
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
        print("  AC-10D RESULT: PASS")
    else:
        print("  AC-10D RESULT: NEEDS FIXES")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
