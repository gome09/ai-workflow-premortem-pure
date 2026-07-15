#!/usr/bin/env python3
"""
Live E2E Low Risk Room Booking Test Script
Drives a full Stage 0-4 workflow through the real API for the
enterprise internal meeting room booking system scenario.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "http://localhost:8000"
EVIDENCE_DIR = Path("artifacts/live_e2e_low_risk_room_booking")
MAX_LOOP = 100

INITIAL_INPUT = """我想分析一个企业内部会议室预约系统。

研究对象：企业内部会议室预约系统。
具体领域：办公协同、会议室资源管理、预约冲突处理、通知提醒、管理员维护和操作日志。
具体目标：识别系统失败模式，设计人机协同工作流，生成压力测试/EvalCase，给出触发方式与执行建议。

范围限制：
仅使用测试数据；
只处理会议室资源、预约时间、预约人、部门、邮箱和通知提醒；
不涉及未成年人；
不涉及医疗；
不涉及金融贷款；
不涉及成绩、教务、招聘、解雇、绩效考核或自动惩戒；
不做任何高影响自动化决策；
冲突处理只提供提示和建议，不自动剥夺用户权益；
管理员操作必须有日志；
用户可以取消或修改预约。

请确认信息收集完毕，并进入阶段一。"""

CONFIRM_INPUT = "确认以上信息完整，请开始阶段一。请围绕企业内部会议室预约系统生成结构化结果，保持低风险办公协同场景边界。"

STAGE_RUN_INPUT = (
    "开始。请生成本阶段结构化结果，重点覆盖预约冲突、资源不可用、"
    "通知失败、重复预约、权限误配、管理员误操作、日志缺失和用户取消/修改预约流程。"
)

CLARIFY_INPUT = (
    "请注意，本轮场景限定为企业内部会议室预约系统，仅用于办公资源预约、"
    "冲突提示和通知提醒。不涉及未成年人、医疗、金融、成绩、招聘、解雇、"
    "绩效考核、自动惩戒或任何高影响自动化决策。请基于该低风险办公协同边界重新评估当前阶段。"
)

POLICY_FIX_INPUT = (
    "请在阶段二的工作流节点中补充 HumanOversightPolicy。"
    "每个引用了高严重度 failure_mode 的节点都必须包含明确的人类监督策略，"
    "包括：审核触发条件、审核角色、超时处理和回退机制。"
    "请重新生成阶段二的结构化输出，确保所有节点的 HumanOversightPolicy 完整。"
)

# Fix log entries
fix_log = []


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def log_fix(description, file_changed=None, details=None):
    entry = {
        "time": datetime.now().isoformat(),
        "description": description,
        "file": file_changed,
        "details": details,
    }
    fix_log.append(entry)
    log(f"  FIX: {description}")


def api(method, path, timeout=120, **kwargs):
    url = f"{BASE_URL}{path}"
    log(f"  {method} {url}")
    try:
        resp = requests.request(method, url, timeout=timeout, **kwargs)
        log(f"  -> {resp.status_code}")
        return resp
    except requests.exceptions.Timeout:
        log(f"  -> TIMEOUT after {timeout}s")
        return None
    except requests.exceptions.ConnectionError as e:
        log(f"  -> CONNECTION ERROR: {e}")
        return None


def save_json(name, data):
    path = EVIDENCE_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def save_text(name, text):
    path = EVIDENCE_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def create_session():
    resp = api("POST", "/sessions/", timeout=30)
    if resp is None or resp.status_code != 200:
        log(f"FAIL: Cannot create session. resp={resp}")
        return None
    sid = resp.json()["session_id"]
    log(f"Session created: {sid}")
    return sid


def send_chat(sid, msg, timeout=300):
    resp = api(
        "POST", f"/chat/{sid}", timeout=timeout, json={"user_input": msg, "user_materials": None}
    )
    if resp is None:
        return False
    if resp.status_code == 200:
        return True
    log(f"  Chat failed: {resp.status_code} {resp.text[:500]}")
    return False


def get_session(sid):
    resp = api("GET", f"/sessions/{sid}", timeout=30)
    if resp is None or resp.status_code != 200:
        return None
    return resp.json()


def get_actions(sid, status="pending"):
    resp = api("GET", f"/sessions/{sid}/actions", params={"status": status}, timeout=30)
    if resp is None or resp.status_code != 200:
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


def resolve_action(sid, aid, decision, note, payload_after=None):
    body = {"decision": decision, "note": note}
    if payload_after is not None:
        body["payload_after"] = payload_after
    resp = api("POST", f"/sessions/{sid}/actions/{aid}/resolve", json=body, timeout=30)
    if resp is None:
        return False
    if resp.status_code == 200:
        return True
    log(f"  Resolve failed: {resp.status_code} {resp.text[:500]}")
    return False


def verify_all_evidence(sid):
    resp = api("GET", f"/sessions/{sid}/evidence", timeout=30)
    if resp is None or resp.status_code != 200:
        return 0
    evidence = resp.json()
    if not isinstance(evidence, list):
        return 0
    count = 0
    for e in evidence:
        if e.get("status") is None:
            eid = e.get("evidence_id")
            if eid:
                r = api(
                    "POST",
                    f"/sessions/{sid}/evidence/{eid}/verify",
                    json={
                        "decision": "verified",
                        "note": "Live E2E verified evidence for room booking scenario",
                    },
                    timeout=30,
                )
                if r and r.status_code == 200:
                    count += 1
    return count


def advance_stage(sid, stage_id):
    resp = api(
        "POST",
        f"/sessions/{sid}/stages/{stage_id}/advance",
        json={"reason": "live_e2e_low_risk_room_booking_stage_approved"},
        timeout=60,
    )
    if resp is None:
        return False
    if resp.status_code == 200:
        data = resp.json()
        return data.get("advanced", False)
    log(f"  Advance failed: {resp.status_code} {resp.text[:500]}")
    return False


def get_stage_output_version(sid, stage_id):
    session = get_session(sid)
    if not session:
        return None
    versions = session.get("stage_output_versions", {})
    return versions.get(f"stage_{stage_id}")


def get_stage_output(sid, stage_id):
    """Get the stage output from the session."""
    session = get_session(sid)
    if not session:
        return None
    # Try various keys
    for key in [f"stage_{stage_id}_output", f"stage{stage_id}_output", f"stage_{stage_id}"]:
        val = session.get(key)
        if val and isinstance(val, dict):
            return val
    return None


def resolve_all_pending_actions(sid, stage_id):
    """Resolve ALL pending actions, with multiple passes to catch newly created ones."""
    total_resolved = 0
    for pass_num in range(5):  # up to 5 passes
        actions = get_actions(sid, "pending")
        if not actions:
            break
        log(f"  Pass {pass_num + 1}: {len(actions)} pending actions")
        resolved_this_pass = 0
        for a in actions:
            aid = a.get("action_id", a.get("id"))
            atype = a.get("action_type", a.get("type", "unknown"))
            log(f"    Action {aid} type={atype}")

            if atype == "edit":
                # For edit actions, use payload_before as payload_after (approve current state)
                payload = a.get("payload_before")
                if payload:
                    ok = resolve_action(
                        sid,
                        aid,
                        "edit",
                        "Live E2E reviewer approved current state for low-risk room booking",
                        payload_after=payload,
                    )
                else:
                    ok = resolve_action(
                        sid, aid, "approve", "Live E2E reviewer approved (no payload to edit)"
                    )
            elif atype == "verify_evidence":
                ok = resolve_action(
                    sid, aid, "verified", "Live E2E verified evidence for room booking scenario"
                )
                if not ok:
                    ok = resolve_action(
                        sid, aid, "approve", "Live E2E approved evidence for room booking scenario"
                    )
            elif atype == "escalate":
                ok = resolve_action(
                    sid,
                    aid,
                    "approve",
                    "Live E2E approved escalation for low-risk room booking scenario",
                )
            else:
                ok = resolve_action(
                    sid,
                    aid,
                    "approve",
                    "Live E2E reviewer approved for low-risk room booking scenario",
                )

            if ok:
                resolved_this_pass += 1

        total_resolved += resolved_this_pass
        if resolved_this_pass == 0:
            break  # no progress, stop
        time.sleep(1)  # brief pause between passes

    return total_resolved


def check_safety_block(session, stage_id):
    """Check if the session was blocked by safety gates."""
    state = session.get("current_state", "")
    if "blocked" in state.lower():
        return True
    # Check safety findings
    findings = session.get("safety_findings", [])
    if isinstance(findings, list):
        for f in findings:
            if f.get("status") == "blocked" or f.get("severity") == "critical":
                return True
    return False


def check_policy_gap(sid, stage_id):
    """Check if there are policy_gap blockers in the stage gate."""
    resp = api("GET", f"/sessions/{sid}/stage-gate/{stage_id}", timeout=30)
    if resp is None or resp.status_code != 200:
        return False
    gate = resp.json()
    blockers = gate.get("blockers", [])
    for b in blockers:
        if b.get("blocker_type") == "policy_gap":
            return True
    return False


def trigger_revision(sid, stage_id):
    """Trigger a stage revision via the revise endpoint."""
    resp = api(
        "POST",
        f"/sessions/{sid}/stages/{stage_id}/revise",
        json={"reason": "policy_gap_fix", "note": "Adding HumanOversightPolicy to workflow nodes"},
        timeout=30,
    )
    if resp and resp.status_code == 200:
        log("  Revision triggered successfully")
        return True
    log(f"  Revision trigger failed: {resp.status_code if resp else 'None'}")
    return False


def save_review_snapshot(sid, stage_id):
    """Save stage review data."""
    snapshot = {}

    # Stage readiness
    resp = api("GET", f"/sessions/{sid}/stage-readiness", timeout=30)
    if resp and resp.status_code == 200:
        snapshot["stage_readiness"] = resp.json()

    # Stage gate
    resp = api("GET", f"/sessions/{sid}/stage-gate/{stage_id}", timeout=30)
    if resp and resp.status_code == 200:
        snapshot["stage_gate"] = resp.json()

    # Stage resolution
    resp = api("GET", f"/sessions/{sid}/stage-resolution/{stage_id}", timeout=30)
    if resp and resp.status_code == 200:
        snapshot["stage_resolution"] = resp.json()

    # Pending actions
    actions = get_actions(sid, "pending")
    snapshot["pending_actions"] = actions

    save_json(f"stage_{stage_id}_review.json", snapshot)
    return snapshot


def process_stage(sid, stage_id, max_attempts=30):
    """Process a stage through review to advancement."""
    for attempt in range(max_attempts):
        session = get_session(sid)
        if session is None:
            log("  Cannot get session, retrying...")
            time.sleep(3)
            continue

        state = session.get("current_state", "unknown")
        log(f"Stage {stage_id} attempt {attempt + 1}: {state}")

        if state == "complete":
            return True

        # Safety block check
        if check_safety_block(session, stage_id):
            log("  Safety block detected, sending clarification...")
            send_chat(sid, CLARIFY_INPUT)
            time.sleep(5)
            # Re-check
            session = get_session(sid)
            if session and check_safety_block(session, stage_id):
                log("  Still blocked after clarification")
                save_json(f"stage_{stage_id}_safety_block.json", session)
                return False
            continue

        # Running state -> send prompt
        if state == f"s{stage_id}_running":
            if attempt == 0:
                send_chat(sid, STAGE_RUN_INPUT, timeout=300)
            else:
                send_chat(sid, STAGE_RUN_INPUT, timeout=300)
            time.sleep(5)
            continue

        # Review state -> resolve actions and advance
        if state == f"s{stage_id}_review":
            # Save review snapshot
            save_review_snapshot(sid, stage_id)

            # Verify evidence
            verified = verify_all_evidence(sid)
            log(f"  Verified {verified} evidence items")

            # Resolve ALL pending actions (multiple passes)
            resolved = resolve_all_pending_actions(sid, stage_id)
            log(f"  Resolved {resolved} total actions")

            # Verify no pending actions remain
            remaining = get_actions(sid, "pending")
            if remaining:
                log(f"  WARNING: {len(remaining)} actions still pending after resolve")
                # Try one more round
                resolve_all_pending_actions(sid, stage_id)
                remaining = get_actions(sid, "pending")
                if remaining:
                    log(f"  Still {len(remaining)} pending, will try advance anyway")

            # Try to advance
            if advance_stage(sid, stage_id):
                log(f"  Stage {stage_id} advanced!")
                save_json(f"stage_{stage_id}_post_advance.json", get_session(sid))
                return True

            # Check for policy_gap blockers
            if check_policy_gap(sid, stage_id):
                log("  Policy gap detected, triggering revision...")
                trigger_revision(sid, stage_id)
                send_chat(sid, POLICY_FIX_INPUT, timeout=300)
                time.sleep(5)
                continue

            # If not advanced, check if re-running
            time.sleep(3)
            session = get_session(sid)
            new_state = session.get("current_state") if session else "unknown"
            if new_state == f"s{stage_id}_running":
                log(f"  Stage {stage_id} re-running after rejection")
                continue
            elif new_state == f"s{stage_id}_review":
                # Still in review, try chat
                send_chat(sid, "确认，本阶段已审核完成，请继续下一阶段。")
                time.sleep(3)
                continue

        # Blocked state
        if state.endswith("_blocked"):
            log("  Blocked state, sending clarification...")
            send_chat(sid, CLARIFY_INPUT)
            time.sleep(5)
            continue

        # Init state
        if state == "init":
            send_chat(sid, CONFIRM_INPUT, timeout=300)
            time.sleep(5)
            continue

        # Unknown state, wait
        time.sleep(3)

    return False


def run_docker_log_check():
    """Check Docker logs for errors."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "compose", "logs", "--tail=200", "api", "frontend", "postgres", "redis"],  # noqa: S607  # docker expected on PATH in e2e script
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(EVIDENCE_DIR.parent.parent),
        )
        logs = result.stdout + result.stderr
        save_text("docker_runtime_tail.txt", logs)

        error_patterns = [
            "Traceback",
            "ImportError",
            "ModuleNotFoundError",
            "ValidationError",
            "RuntimeError",
            "HTTP 500",
            "500 Internal Server Error",
        ]
        found_errors = []
        for line in logs.split("\n"):
            for pattern in error_patterns:
                if pattern in line:
                    found_errors.append(line.strip())
                    break
        return found_errors
    except Exception as e:
        log(f"  Docker log check failed: {e}")
        return []


def main():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    start_time = datetime.now()
    loop_count = 0

    log("=" * 60)
    log("Live E2E Low Risk Room Booking Test")
    log("=" * 60)

    # Step 1: Create session
    sid = create_session()
    if sid is None:
        log("FAIL: Cannot create session")
        return 1

    # Step 2: Send initial input
    log("Sending initial input...")
    if not send_chat(sid, INITIAL_INPUT, timeout=300):
        log("FAIL: Initial chat failed")
        return 1

    save_json("01_initial_session.json", get_session(sid))

    # Step 3: Wait for stage 1 to start
    log("Waiting for session to initialize...")
    time.sleep(8)
    session = get_session(sid)
    if session is None:
        log("FAIL: Cannot get session after initial input")
        return 1

    state = session.get("current_state", "unknown")
    log(f"Initial state: {state}")

    # If still in init, send confirmation
    if state == "init":
        log("Still in init, sending confirmation...")
        send_chat(sid, CONFIRM_INPUT, timeout=300)
        time.sleep(8)
        session = get_session(sid)
        state = session.get("current_state") if session else "unknown"
        log(f"State after confirmation: {state}")

    # Step 4: Process each stage
    for stage_id in range(1, 5):
        loop_count += 1
        if loop_count > MAX_LOOP:
            log(f"FAIL: Exceeded max loop count ({MAX_LOOP})")
            break

        log(f"\n{'=' * 40}")
        log(f"Processing Stage {stage_id}")
        log(f"{'=' * 40}")

        # Wait for stage to be ready
        for wait in range(30):
            session = get_session(sid)
            if session is None:
                time.sleep(3)
                continue
            state = session.get("current_state", "unknown")
            if state == "complete":
                log("Session complete!")
                break
            if state == f"s{stage_id}_running" or state == f"s{stage_id}_review":
                break
            if state.startswith(f"s{stage_id}") or state == "init":
                break
            # Check if previous stage is still current
            if stage_id > 1 and (
                state == f"s{stage_id - 1}_review" or state == f"s{stage_id - 1}_running"
            ):
                log(f"  Previous stage {stage_id - 1} still active ({state}), trying to advance...")
                process_stage(sid, stage_id - 1)
                continue
            time.sleep(3)

        # Process the stage
        success = process_stage(sid, stage_id)
        session = get_session(sid)
        save_json(f"stage_{stage_id}_result.json", session)

        if not success:
            log(f"Stage {stage_id} did not advance cleanly, continuing...")

        # Check if complete
        if session and session.get("current_state") == "complete":
            log("Session reached complete state!")
            break

    # Step 5: Final state
    session = get_session(sid)
    final_state = session.get("current_state") if session else "unknown"
    log(f"\nFinal state: {final_state}")

    # Step 6: Export
    log("\nExporting session...")
    export_json_ok = False
    export_md_ok = False
    report_ok = False

    resp = api("GET", f"/sessions/{sid}/export", params={"format": "json"}, timeout=60)
    if resp and resp.status_code == 200:
        save_json("session_export.json", resp.json())
        export_json_ok = True
        log("  JSON export: OK")
    else:
        log(f"  JSON export: FAIL ({resp.status_code if resp else 'None'})")

    resp = api("GET", f"/sessions/{sid}/export", params={"format": "markdown"}, timeout=60)
    if resp and resp.status_code == 200:
        save_text("session_export.md", resp.text)
        export_md_ok = True
        log("  Markdown export: OK")
    else:
        log(f"  Markdown export: FAIL ({resp.status_code if resp else 'None'})")

    # Step 7: Create report
    resp = api("POST", f"/sessions/{sid}/reports", timeout=60)
    if resp and resp.status_code == 200:
        report_data = resp.json()
        save_json("report.json", report_data)
        report_ok = True
        log("  Report creation: OK")
        # Also try to get report markdown
        report_id = report_data.get("report_id") or report_data.get("id")
        if report_id:
            resp2 = api("GET", f"/sessions/{sid}/reports/{report_id}", timeout=30)
            if resp2 and resp2.status_code == 200:
                save_json("report_detail.json", resp2.json())
    else:
        log(f"  Report creation: FAIL ({resp.status_code if resp else 'None'})")

    # Step 8: Save final session
    session = get_session(sid)
    save_json("session_final.json", session)

    # Step 9: Analyze results
    s1 = session.get("stage_1_output", {}) if session else {}
    s2 = session.get("stage_2_output", {}) if session else {}
    s3 = session.get("stage_3_output", {}) if session else {}
    s4 = session.get("stage_4_output", {}) if session else {}

    # Count stage 1 failure modes
    s1_count = 0
    if isinstance(s1, dict):
        for key in ["failure_modes", "failure_modes_analysis", "risks", "findings"]:
            val = s1.get(key)
            if isinstance(val, list):
                s1_count = max(s1_count, len(val))

    # Count stage 2 workflow items
    s2_count = 0
    if isinstance(s2, dict):
        for key, val in s2.items():
            if isinstance(val, list):
                s2_count = max(s2_count, len(val))

    # Count stage 3 eval cases
    s3_count = 0
    if isinstance(s3, dict):
        for key in ["eval_cases", "eval_cases_results", "test_results", "stress_tests"]:
            val = s3.get(key)
            if isinstance(val, list):
                s3_count = max(s3_count, len(val))

    # Count stage 4 triggers
    s4_count = 0
    if isinstance(s4, dict):
        for key in ["trigger_methods", "execution_recommendations", "triggers"]:
            val = s4.get(key)
            if isinstance(val, list):
                s4_count = max(s4_count, len(val))

    log(f"\nStage 1 failure modes: {s1_count}")
    log(f"Stage 2 workflow items: {s2_count}")
    log(f"Stage 3 eval cases: {s3_count}")
    log(f"Stage 4 triggers: {s4_count}")

    # Check evidence / traces
    evidence_sources = session.get("evidence_sources", []) if session else []
    traces = session.get("llm_traces", []) if session else []
    log(f"Evidence sources: {len(evidence_sources)}")
    log(f"LLM traces: {len(traces)}")

    # Check pending actions
    final_actions = get_actions(sid, "pending")
    log(f"Remaining pending actions: {len(final_actions)}")

    # Docker log check
    log("\nChecking Docker logs for errors...")
    docker_errors = run_docker_log_check()
    if docker_errors:
        log(f"  Found {len(docker_errors)} error lines in Docker logs")
        for e in docker_errors[:10]:
            log(f"    {e[:200]}")
    else:
        log("  No errors in Docker logs")

    # Step 10: Generate summary
    end_time = datetime.now()

    # Save fix log
    save_json("fix_log.json", fix_log)

    # Determine result
    passed = (
        final_state == "complete"
        and s1_count >= 3
        and s2_count >= 3
        and s3_count >= 3
        and s4_count >= 3
        and export_json_ok
        and export_md_ok
        and report_ok
    )

    result = "PASS" if passed else "FAIL"
    if final_state != "complete":
        result = "FAIL"

    summary = {
        "session_id": sid,
        "final_state": final_state,
        "started_at": start_time.isoformat(),
        "completed_at": end_time.isoformat(),
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
        "evidence_sources": len(evidence_sources),
        "llm_traces": len(traces),
        "pending_actions": len(final_actions),
        "docker_errors": len(docker_errors),
        "result": result,
        "fixes_applied": len(fix_log),
    }
    save_json("e2e_result.json", summary)

    log(f"\n{'=' * 60}")
    log(f"RESULT: {result}")
    log(f"{'=' * 60}")

    if passed:
        log("PASS: Room booking E2E completed successfully.")
        return 0
    else:
        log(
            f"FAIL: final_state={final_state}, s1={s1_count}, s2={s2_count}, s3={s3_count}, s4={s4_count}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
