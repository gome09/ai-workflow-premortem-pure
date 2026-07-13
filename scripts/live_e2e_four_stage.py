#!/usr/bin/env python3
"""
Live E2E Four-Stage Full-Flow Test

Drives the full Stage 1-4 workflow through the live API against the
`generic_rag_demo` mock scenario. No external services needed.

Stages exercised:
  - Stage 1: Failure mode pre-mortem
  - Stage 2: Human oversight workflow design
  - Stage 3: Stress test / eval cases
  - Stage 4: Trigger methods

Per-stage coverage:
  - GET /sessions/{sid}
  - GET /sessions/{sid}/stage-readiness
  - GET /sessions/{sid}/stage-resolution
  - GET /sessions/{sid}/stages/{n}/advancement-decision
  - GET /sessions/{sid}/actions?status=pending
  - POST /sessions/{sid}/actions/{aid}/resolve
  - GET /sessions/{sid}/evidence
  - POST /sessions/{sid}/evidence/{eid}/verify
  - GET /sessions/{sid}/safety-findings?status=open
  - GET /sessions/{sid}/eval-cases
  - GET /sessions/{sid}/eval-runs
  - GET /sessions/{sid}/redteam/cases
  - GET /sessions/{sid}/redteam/coverage
  - GET /sessions/{sid}/interrupt-records
  - GET /sessions/{sid}/audit-events
  - GET /sessions/{sid}/reports

Final-stage coverage:
  - GET /sessions/{sid}/export?format=json
  - GET /sessions/{sid}/export?format=markdown
  - POST /sessions/{sid}/reports
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000"
EVIDENCE_DIR = Path("artifacts/live_e2e_four_stage")
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password-123"
MAX_LOOP = 60

INITIAL_INPUT = """我想分析一个通用 RAG 演示系统。

研究对象：通用 RAG 演示系统。
具体目标：识别失败模式，设计人机协同工作流，生成压力测试/EvalCase，给出触发方式与执行建议。

请确认信息收集完毕，并进入阶段一。"""

CONFIRM_INPUT = "确认，本阶段已审核完成，请继续下一阶段。"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def save_json(name: str, data) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def api(method: str, path: str, timeout: int = 120, **kwargs):
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.request(method, url, timeout=timeout, **kwargs)
        return resp
    except requests.exceptions.Timeout:
        log(f"  TIMEOUT {method} {url} after {timeout}s")
        return None
    except requests.exceptions.ConnectionError as e:
        log(f"  CONNECTION ERROR {method} {url}: {e}")
        return None


def auth_headers() -> dict:
    # Try refresh / register / login flow used by the frontend.
    headers = {}
    # 1) Try login
    r = api(
        "POST",
        "/auth/login",
        timeout=10,
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    if r is not None and r.status_code == 200:
        token = r.json().get("access_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
            return headers
    # 2) Register
    r = api(
        "POST",
        "/auth/register",
        timeout=10,
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    if r is not None and r.status_code == 200:
        token = r.json().get("access_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
            return headers
    log(f"  WARN: auth failed (login={r.status_code if r is not None else 'None'})")
    return headers


def create_session(headers: dict, scenario_id: str | None = None) -> str | None:
    body: dict = {}
    if scenario_id:
        body["scenario_id"] = scenario_id
    r = api("POST", "/sessions/", timeout=30, json=body, headers=headers)
    if r is None or r.status_code != 200:
        log(f"  FAIL create_session: {r.status_code if r else 'None'} {r.text[:200] if r else ''}")
        return None
    sid = r.json()["session_id"]
    log(f"  Session created: {sid}")
    return sid


def send_chat(sid: str, headers: dict, msg: str, timeout: int = 120) -> dict | None:
    r = api(
        "POST",
        f"/chat/{sid}",
        timeout=timeout,
        json={"user_input": msg, "user_materials": None},
        headers=headers,
    )
    if r is None:
        return None
    if r.status_code != 200:
        log(f"  Chat failed: {r.status_code} {r.text[:500]}")
        return None
    return r.json()


def get_session(sid: str, headers: dict) -> dict | None:
    r = api("GET", f"/sessions/{sid}", timeout=30, headers=headers)
    if r is None or r.status_code != 200:
        return None
    return r.json()


def get_actions(sid: str, headers: dict, status: str = "pending") -> list[dict]:
    r = api(
        "GET",
        f"/sessions/{sid}/actions",
        timeout=30,
        params={"status": status},
        headers=headers,
    )
    if r is None or r.status_code != 200:
        return []
    data = r.json()
    return data if isinstance(data, list) else []


def resolve_action(
    sid: str,
    headers: dict,
    action_id: str,
    decision: str,
    note: str,
    payload_after: dict | None = None,
) -> dict | None:
    body: dict = {"decision": decision, "note": note}
    if payload_after is not None:
        body["payload_after"] = payload_after
    r = api(
        "POST",
        f"/sessions/{sid}/actions/{action_id}/resolve",
        timeout=30,
        json=body,
        headers=headers,
    )
    if r is None or r.status_code != 200:
        log(f"  resolve_action FAIL: {r.status_code if r else 'None'} {r.text[:300] if r else ''}")
        return None
    return r.json()


def verify_evidence(sid: str, headers: dict, evidence_id: str, note: str = "") -> bool:
    r = api(
        "POST",
        f"/sessions/{sid}/evidence/{evidence_id}/verify",
        timeout=30,
        json={"note": note},
        headers=headers,
    )
    return r is not None and r.status_code == 200


def list_endpoint(sid: str, headers: dict, path: str) -> list | dict | None:
    r = api("GET", f"/sessions/{sid}/{path}", timeout=30, headers=headers)
    if r is None or r.status_code != 200:
        log(f"  GET /sessions/{sid}/{path} -> {r.status_code if r else 'None'}")
        return None
    return r.json()


def get_stage_advancement(sid: str, headers: dict, stage_id: int) -> dict | None:
    r = api(
        "GET",
        f"/sessions/{sid}/stages/{stage_id}/advancement-decision",
        timeout=30,
        headers=headers,
    )
    if r is None or r.status_code != 200:
        return None
    return r.json()


def advance_stage(sid: str, headers: dict, stage_id: int) -> dict | None:
    r = api(
        "POST",
        f"/sessions/{sid}/stages/{stage_id}/advance",
        timeout=60,
        json={"reason": "live_e2e_four_stage_advance", "source": "api_advance"},
        headers=headers,
    )
    if r is None or r.status_code != 200:
        log(f"  advance FAIL: {r.status_code if r else 'None'} {r.text[:300] if r else ''}")
        return None
    return r.json()


def resolve_all_pending_actions(sid: str, headers: dict) -> int:
    total = 0
    for _pass in range(5):
        actions = get_actions(sid, headers, "pending")
        if not actions:
            break
        resolved = 0
        for a in actions:
            aid = a.get("action_id")
            atype = a.get("action_type", "approve")
            if atype == "verify_evidence":
                decision = "verify_evidence"
                note = "verified in live e2e"
            elif atype == "edit":
                decision = "edit"
                note = "edit approved as-is in live e2e"
                a.setdefault("payload_after", a.get("payload_before") or {})
            elif atype == "escalate":
                decision = "approve"
                note = "escalation approved in live e2e"
            else:
                decision = "approve"
                note = "approved in live e2e"
            payload_after = a.get("payload_before") if atype == "edit" else None
            if resolve_action(sid, headers, aid, decision, note, payload_after):
                resolved += 1
        total += resolved
        if resolved == 0:
            break
        time.sleep(0.5)
    return total


def verify_all_evidence(sid: str, headers: dict) -> int:
    r = api("GET", f"/sessions/{sid}/evidence", timeout=30, headers=headers)
    if r is None or r.status_code != 200:
        return 0
    evidence = r.json()
    if not isinstance(evidence, list):
        return 0
    count = 0
    for e in evidence:
        if not e.get("verified"):
            eid = e.get("evidence_id")
            if eid and verify_evidence(sid, headers, eid, "verified in live e2e"):
                count += 1
    return count


def generate_redteam_cases(sid: str, headers: dict) -> list[dict]:
    """Generate deterministic RedTeamCase drafts from current signals."""
    r = api(
        "POST",
        f"/sessions/{sid}/redteam/generate",
        timeout=60,
        json={"stage": 3},
        headers=headers,
    )
    if r is None or r.status_code != 200:
        log(f"  redteam/generate FAIL: {r.status_code if r else 'None'} {r.text[:300] if r else ''}")
        return []
    body = r.json()
    # Endpoint may return an envelope or a list directly
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("items", "result", "created_cases", "redteam_cases"):
            val = body.get(key)
            if isinstance(val, list):
                return val
        # If only a single case, return as list
        if body.get("redteam_case_id"):
            return [body]
    return []


def approve_redteam_case(sid: str, headers: dict, case_id: str) -> bool:
    r = api(
        "POST",
        f"/sessions/{sid}/redteam/cases/{case_id}/approve",
        timeout=30,
        json={"note": "approved in live e2e"},
        headers=headers,
    )
    return r is not None and r.status_code == 200


def sync_redteam_to_eval(sid: str, headers: dict, case_id: str) -> dict | None:
    r = api(
        "POST",
        f"/sessions/{sid}/redteam/cases/{case_id}/to-eval-case",
        timeout=30,
        json={},
        headers=headers,
    )
    if r is None or r.status_code != 200:
        return None
    return r.json()


def handle_redteam_blockers(sid: str, headers: dict, stage_id: int) -> bool:
    """Resolve redteam_coverage blockers by generating, approving, and syncing cases."""
    decision = get_stage_advancement(sid, headers, stage_id)
    if not decision:
        return False
    required_ops = decision.get("required_operations") or []
    redteam_ops = [
        op for op in required_ops
        if op.get("required_resolution") == "generate_redteam_cases"
    ]
    if not redteam_ops:
        return False
    log(f"  Handling {len(redteam_ops)} redteam blockers...")

    # 1) Generate redteam cases
    cases = generate_redteam_cases(sid, headers)
    log(f"  Generated {len(cases)} redteam cases")
    if not cases:
        return False

    # 2) Approve all draft cases
    approved = 0
    for case in cases:
        case_id = case.get("redteam_case_id")
        if not case_id:
            continue
        status = case.get("status")
        if status != "draft":
            continue
        if approve_redteam_case(sid, headers, case_id):
            approved += 1
    log(f"  Approved {approved} cases")

    # 3) Sync approved cases to eval (creates linked EvalCase)
    synced = 0
    # Refresh case list to get latest statuses
    r = api("GET", f"/sessions/{sid}/redteam/cases", timeout=30, headers=headers)
    if r and r.status_code == 200:
        cases = r.json() if isinstance(r.json(), list) else []
    for case in cases:
        case_id = case.get("redteam_case_id")
        if not case_id:
            continue
        if case.get("status") == "approved":
            eval_case = sync_redteam_to_eval(sid, headers, case_id)
            if eval_case:
                synced += 1
    log(f"  Synced {synced} cases to eval")
    return synced > 0


def resolve_safety_findings(sid: str, headers: dict) -> int:
    """Resolve open safety findings via the resolve endpoint."""
    r = api(
        "GET",
        f"/sessions/{sid}/safety-findings",
        timeout=30,
        params={"status": "open"},
        headers=headers,
    )
    if r is None or r.status_code != 200:
        return 0
    findings = r.json()
    if not isinstance(findings, list):
        return 0
    count = 0
    for f in findings:
        fid = f.get("finding_id")
        if not fid:
            continue
        # Try to resolve high/critical findings
        severity = f.get("severity", "low")
        if severity in {"high", "critical"} and f.get("requires_human_review"):
            # Already covered by redteam, try resolved
            r2 = api(
                "POST",
                f"/sessions/{sid}/safety-findings/{fid}/resolve",
                timeout=30,
                json={"status": "resolved", "note": "mitigated via redteam coverage in live e2e"},
                headers=headers,
            )
            if r2 and r2.status_code == 200:
                count += 1
    return count


def assert_panel_endpoints(sid: str, headers: dict, stage_id: int) -> dict:
    """Hit every read endpoint the frontend renders for the current stage."""
    result = {}
    # Stage readiness
    data = list_endpoint(sid, headers, "stage-readiness")
    result["stage_readiness"] = data is not None
    # Stage resolution
    data = list_endpoint(sid, headers, "stage-resolution")
    result["stage_resolution"] = data is not None
    # Stage advancement decision
    data = get_stage_advancement(sid, headers, stage_id)
    result["stage_advancement_decision"] = data is not None
    # Pending actions
    actions = get_actions(sid, headers, "pending")
    result["actions_count"] = len(actions)
    # Interrupt records
    data = list_endpoint(sid, headers, "interrupt-records")
    result["interrupt_records"] = data is not None
    # Evidence
    data = list_endpoint(sid, headers, "evidence")
    result["evidence"] = data is not None
    # Safety findings
    data = list_endpoint(sid, headers, "safety-findings?status=open")
    result["safety_findings"] = data is not None
    # Eval cases
    data = list_endpoint(sid, headers, "eval-cases")
    result["eval_cases"] = data is not None
    # Eval runs
    data = list_endpoint(sid, headers, "eval-runs")
    result["eval_runs"] = data is not None
    # Eval datasets
    data = list_endpoint(sid, headers, "eval-datasets")
    result["eval_datasets"] = data is not None
    # Eval experiments
    data = list_endpoint(sid, headers, "eval-experiments")
    result["eval_experiments"] = data is not None
    # Red team cases
    data = list_endpoint(sid, headers, "redteam/cases")
    result["redteam_cases"] = data is not None
    # Red team coverage
    data = list_endpoint(sid, headers, "redteam/coverage")
    result["redteam_coverage"] = data is not None
    # Audit events
    data = list_endpoint(sid, headers, "audit-events")
    result["audit_events"] = data is not None
    # Reports
    data = list_endpoint(sid, headers, "reports")
    result["reports"] = data is not None
    # Traces
    data = list_endpoint(sid, headers, "traces")
    result["traces"] = data is not None
    return result


def process_stage(sid: str, headers: dict, stage_id: int) -> bool:
    """Drive a stage from running -> review -> advance."""
    for attempt in range(MAX_LOOP):
        session = get_session(sid, headers)
        if session is None:
            time.sleep(2)
            continue
        state = session.get("current_state", "unknown")
        log(f"  Stage {stage_id} attempt {attempt + 1}: state={state}")

        if state == "complete":
            return True

        if state == f"s{stage_id}_running":
            # Trigger generation
            send_chat(sid, headers, "开始本阶段结构化输出。")
            time.sleep(2)
            continue

        if state == f"s{stage_id}_review":
            # Snapshot panel endpoints (frontend integration test)
            panel = assert_panel_endpoints(sid, headers, stage_id)
            log(f"  Panel check: {panel}")
            save_json(f"stage_{stage_id}_panels.json", panel)
            failed = [k for k, v in panel.items() if v is False]
            if failed:
                log(f"  WARN: failing panels at stage {stage_id}: {failed}")

            # Verify evidence (frontend auto-displays them as 待核验)
            verified = verify_all_evidence(sid, headers)
            log(f"  Verified evidence: {verified}")

            # Resolve pending actions (frontend shows them in 待处理动作)
            resolved = resolve_all_pending_actions(sid, headers)
            log(f"  Resolved actions: {resolved}")

            # Try advance — the endpoint returns StageAdvancementDecision directly
            adv = advance_stage(sid, headers, stage_id)
            if adv:
                advanced = adv.get("advanced")
                can_advance = adv.get("can_advance")
                current_after = adv.get("current_state")
                decision_reason = adv.get("decision_reason")
                hard_cnt = adv.get("hard_blockers_count", 0)
                exec_cnt = adv.get("executable_operations_count", 0)
                log(
                    f"  Advance returned: advanced={advanced} can_advance={can_advance} "
                    f"current_state={current_after} reason={decision_reason} "
                    f"hard_blockers={hard_cnt} exec_ops={exec_cnt}"
                )
                if advanced:
                    return True
                # If not advanced, check required operations (blockers nested in gate_result)
                gate_result = adv.get("gate_result") or {}
                blockers = gate_result.get("blockers", []) or []
                required_ops = adv.get("required_operations") or []
                if blockers or required_ops:
                    log(f"  Blockers: {len(blockers)}, Required ops: {len(required_ops)}")
                    for b in blockers[:3]:
                        log(
                            f"    - [{b.get('severity')}/{b.get('blocker_type')}] "
                            f"{b.get('message')}"
                        )

                    # Categorize required operations
                    redteam_ops = [
                        op for op in required_ops
                        if op.get("required_resolution") == "generate_redteam_cases"
                    ]
                    if redteam_ops:
                        log(f"  Auto-handling {len(redteam_ops)} redteam blockers...")
                        handled = handle_redteam_blockers(sid, headers, stage_id)
                        if handled:
                            # Try advance again
                            time.sleep(1)
                            adv2 = advance_stage(sid, headers, stage_id)
                            if adv2 and adv2.get("advanced"):
                                log(f"  Stage {stage_id} advanced after redteam handling")
                                return True
                            # Check if safety findings need resolution
                            sf_count = resolve_safety_findings(sid, headers)
                            if sf_count:
                                log(f"  Resolved {sf_count} safety findings")
                                time.sleep(1)
                                adv3 = advance_stage(sid, headers, stage_id)
                                if adv3 and adv3.get("advanced"):
                                    log(f"  Stage {stage_id} advanced after safety resolution")
                                    return True

                    # Try sending confirmation message via chat
                    send_chat(sid, headers, CONFIRM_INPUT)
                    time.sleep(2)
                    continue
            else:
                log(f"  Advance returned None; sending confirm via chat")
                send_chat(sid, headers, CONFIRM_INPUT)

            time.sleep(2)
            continue

        # Past the current stage — current stage is complete
        try:
            current_stage_num = int(state[1]) if state[0] == "s" and state[1:2].isdigit() else 0
        except (IndexError, ValueError):
            current_stage_num = 0
        if current_stage_num > stage_id:
            log(f"  Already past stage {stage_id} (current stage ~{current_stage_num})")
            return True

        # init state -> send initial input
        if state == "init":
            send_chat(sid, headers, INITIAL_INPUT)
            time.sleep(2)
            continue

        # Previous stage still active
        if stage_id > 1 and (
            state == f"s{stage_id - 1}_running" or state == f"s{stage_id - 1}_review"
        ):
            log(f"  Previous stage {stage_id - 1} still active, processing...")
            process_stage(sid, headers, stage_id - 1)
            continue

        time.sleep(2)

    return False


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    start_time = datetime.now()
    log("=" * 60)
    log("Live E2E Four-Stage Full-Flow Test")
    log("=" * 60)

    # Step 0: Health check
    r = api("GET", "/health", timeout=5)
    if r is None or r.status_code != 200:
        log(f"FAIL: /health did not return 200 (got {r.status_code if r else 'None'})")
        return 1
    health = r.json()
    log(f"Health OK: mode={health.get('workflow_execution_mode')} scenario={health.get('default_scenario_id')}")

    # Step 1: Auth
    headers = auth_headers()
    if not headers:
        log("FAIL: cannot authenticate demo user")
        return 1
    log("Auth OK")

    # Step 2: Create session with generic_rag_demo
    sid = create_session(headers, scenario_id="generic_rag_demo")
    if sid is None:
        log("FAIL: cannot create session")
        return 1

    # Step 3: Bootstrap with initial input
    log("Bootstrapping scenario input...")
    reply = send_chat(sid, headers, INITIAL_INPUT, timeout=180)
    if not reply:
        log("FAIL: bootstrap chat failed")
        return 1
    log(f"Bootstrap reply state: {reply.get('current_state')}")
    save_json("01_bootstrap.json", reply)

    # Step 4: Process each stage
    for stage_id in range(1, 5):
        log(f"\n{'=' * 40}")
        log(f"Processing Stage {stage_id}")
        log(f"{'=' * 40}")

        success = process_stage(sid, headers, stage_id)
        session = get_session(sid, headers)
        save_json(f"stage_{stage_id}_result.json", session or {})

        if not success:
            log(f"WARN: Stage {stage_id} did not advance cleanly")
        else:
            log(f"Stage {stage_id} processed successfully")

        if session and session.get("current_state") == "complete":
            log("Session reached complete state!")
            break

    # Step 5: Final state checks
    session = get_session(sid, headers)
    final_state = session.get("current_state") if session else "unknown"
    log(f"\nFinal state: {final_state}")

    # Step 6: Exports & reports
    log("\nExporting session...")
    export_json_ok = False
    export_md_ok = False
    report_ok = False

    r = api("GET", f"/sessions/{sid}/export", timeout=60, params={"format": "json"}, headers=headers)
    if r and r.status_code == 200:
        save_json("session_export.json", r.json())
        export_json_ok = True
        log("  JSON export: OK")
    else:
        log(f"  JSON export FAIL: {r.status_code if r else 'None'}")

    r = api(
        "GET",
        f"/sessions/{sid}/export",
        timeout=60,
        params={"format": "markdown"},
        headers=headers,
    )
    if r and r.status_code == 200:
        (EVIDENCE_DIR / "session_export.md").write_text(r.text, encoding="utf-8")
        export_md_ok = True
        log("  Markdown export: OK")
    else:
        log(f"  Markdown export FAIL: {r.status_code if r else 'None'}")

    r = api("POST", f"/sessions/{sid}/reports", timeout=60, json={}, headers=headers)
    if r and r.status_code == 200:
        report = r.json()
        save_json("report.json", report)
        report_ok = True
        report_id = report.get("report_id")
        log(f"  Report created: {report_id}")
        if report_id:
            r2 = api(
                "GET",
                f"/sessions/{sid}/reports/{report_id}",
                timeout=30,
                headers=headers,
            )
            if r2 and r2.status_code == 200:
                save_json("report_detail.json", r2.json())
    else:
        log(f"  Report creation FAIL: {r.status_code if r else 'None'}")

    # Step 7: Count outputs
    s1 = (session or {}).get("stage_1_output", {}) or {}
    s2 = (session or {}).get("stage_2_output", {}) or {}
    s3 = (session or {}).get("stage_3_output", {}) or {}
    s4 = (session or {}).get("stage_4_output", {}) or {}

    s1_count = 0
    if isinstance(s1, dict):
        for key in ["failure_modes", "failure_modes_analysis", "risks", "findings"]:
            val = s1.get(key)
            if isinstance(val, list):
                s1_count = max(s1_count, len(val))

    s2_count = 0
    if isinstance(s2, dict):
        for key in ["workflow_nodes", "nodes", "workflow_steps", "steps"]:
            val = s2.get(key)
            if isinstance(val, list):
                s2_count = max(s2_count, len(val))

    s3_count = 0
    if isinstance(s3, dict):
        for key in ["eval_cases", "stress_tests", "test_cases"]:
            val = s3.get(key)
            if isinstance(val, list):
                s3_count = max(s3_count, len(val))

    s4_count = 0
    if isinstance(s4, dict):
        for key in ["trigger_methods", "triggers", "execution_recommendations"]:
            val = s4.get(key)
            if isinstance(val, list):
                s4_count = max(s4_count, len(val))

    log(f"\nStage 1 failure modes: {s1_count}")
    log(f"Stage 2 workflow items: {s2_count}")
    log(f"Stage 3 eval cases:    {s3_count}")
    log(f"Stage 4 triggers:      {s4_count}")

    # Final pending actions
    final_actions = get_actions(sid, headers, "pending")
    log(f"Remaining pending actions: {len(final_actions)}")

    # Final panel endpoint check
    final_panel = assert_panel_endpoints(sid, headers, 4)
    save_json("final_panels.json", final_panel)
    log(f"Final panel: {final_panel}")
    failed_panels = [k for k, v in final_panel.items() if v is False]
    if failed_panels:
        log(f"FAILING PANELS: {failed_panels}")

    # Build summary
    passed = (
        final_state == "complete"
        and export_json_ok
        and export_md_ok
        and report_ok
        and not failed_panels
    )
    result = "PASS" if passed else "FAIL"

    summary = {
        "session_id": sid,
        "final_state": final_state,
        "started_at": start_time.isoformat(),
        "completed_at": datetime.now().isoformat(),
        "stage_counts": {
            "s1_failure_modes": s1_count,
            "s2_workflow_items": s2_count,
            "s3_eval_cases": s3_count,
            "s4_triggers": s4_count,
        },
        "exports": {
            "json": export_json_ok,
            "markdown": export_md_ok,
            "report": report_ok,
        },
        "pending_actions": len(final_actions),
        "final_panel": final_panel,
        "result": result,
    }
    save_json("e2e_result.json", summary)

    log(f"\n{'=' * 60}")
    log(f"RESULT: {result}")
    log(f"{'=' * 60}")
    if not passed:
        log(f"  state={final_state}")
        log(f"  exports: json={export_json_ok} md={export_md_ok} report={report_ok}")
        log(f"  failing panels: {failed_panels}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
