#!/usr/bin/env python3
"""
Live E2E Student Management Test Script - Simplified Version
Directly drives a full Stage 0-4 workflow through the real API.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "http://localhost:8000"
EVIDENCE_DIR = Path("artifacts/live_e2e_student_management_latest")

INITIAL_INPUT = """我想分析一个高校/成人继续教育学生管理系统。

研究对象：学生管理系统。
具体领域：教务、学籍、选课、成绩、考勤、通知、权限、审计、数据导入导出。
具体目标：识别系统失败模式，设计人机协同工作流，生成压力测试/EvalCase，给出触发方式与执行建议。

范围限制：
不处理未成年人画像；
不涉及医疗；
不涉及金融贷款；
不做自动惩戒；
不做自动录取或自动开除；
所有涉及成绩、隐私、权限、通知、数据导入导出的关键操作，都必须有人类确认、审计记录、回滚机制和权限边界。

请确认信息收集完毕，并进入阶段一。"""


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def api(method, path, timeout=120, **kwargs):
    url = f"{BASE_URL}{path}"
    log(f"  {method} {url}")
    resp = requests.request(method, url, timeout=timeout, **kwargs)
    log(f"  -> {resp.status_code}")
    return resp


def save_json(name, data):
    path = EVIDENCE_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def create_session():
    resp = api("POST", "/sessions/")
    sid = resp.json()["session_id"]
    log(f"Session: {sid}")
    return sid


def send_chat(sid, msg, timeout=300):
    resp = api(
        "POST", f"/chat/{sid}", timeout=timeout, json={"user_input": msg, "user_materials": None}
    )
    return resp.status_code == 200


def get_session(sid):
    resp = api("GET", f"/sessions/{sid}")
    return resp.json() if resp.status_code == 200 else None


def get_actions(sid, status="pending"):
    resp = api("GET", f"/sessions/{sid}/actions", params={"status": status})
    if resp.status_code != 200:
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


def resolve_action(sid, aid, decision, note, payload_after=None):
    body = {"decision": decision, "note": note}
    if payload_after is not None:
        body["payload_after"] = payload_after
    resp = api("POST", f"/sessions/{sid}/actions/{aid}/resolve", json=body)
    return resp.status_code == 200


def verify_all_evidence(sid):
    resp = api("GET", f"/sessions/{sid}/evidence")
    if resp.status_code != 200:
        return 0
    evidence = resp.json()
    count = 0
    for e in evidence:
        if e.get("status") is None:
            eid = e.get("evidence_id")
            r = api(
                "POST",
                f"/sessions/{sid}/evidence/{eid}/verify",
                json={"decision": "verified", "note": "E2E verified"},
            )
            if r.status_code == 200:
                count += 1
    return count


def advance_stage(sid, stage_id):
    resp = api(
        "POST", f"/sessions/{sid}/stages/{stage_id}/advance", json={"reason": "e2e_approved"}
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("advanced", False)
    return False


def get_stage_output_version(sid, stage_id):
    session = get_session(sid)
    if not session:
        return None
    versions = session.get("stage_output_versions", {})
    return versions.get(f"stage_{stage_id}")


def resolve_current_actions(sid, stage_id):
    """Resolve all pending actions for the current stage version."""
    version = get_stage_output_version(sid, stage_id)
    if version is None:
        return 0

    actions = get_actions(sid, "pending")
    current = [a for a in actions if a.get("stage_output_version") == version]
    if not current:
        return 0

    log(f"  Resolving {len(current)} actions (version {version})")
    resolved = 0
    for a in current:
        aid = a.get("action_id", a.get("id"))
        atype = a.get("action_type", a.get("type"))

        if atype == "edit":
            # For edit actions, get the stage output and use it as payload_after
            session = get_session(sid)
            stage_output = session.get(f"stage_{stage_id}_output") if session else None
            if stage_output and isinstance(stage_output, dict):
                ok = resolve_action(
                    sid, aid, "edit", "E2E approved stage output", payload_after=stage_output
                )
            else:
                ok = resolve_action(sid, aid, "reject", "E2E rejected to trigger revision")
        elif atype == "escalate":
            ok = resolve_action(
                sid, aid, "approve", "E2E approved escalation for adult education scenario"
            )
        elif atype == "verify_evidence":
            ok = resolve_action(sid, aid, "verified", "E2E verified evidence")
            if not ok:
                ok = resolve_action(sid, aid, "approve", "E2E approved evidence")
        else:
            ok = resolve_action(sid, aid, "approve", "E2E approved")

        if ok:
            resolved += 1

    return resolved


def process_stage(sid, stage_id, max_attempts=10):
    """Process a stage through review to advancement."""
    for attempt in range(max_attempts):
        session = get_session(sid)
        state = session.get("current_state") if session else "unknown"
        log(f"Stage {stage_id} attempt {attempt + 1}: {state}")

        if state == "complete":
            return True

        if state == f"s{stage_id}_running":
            send_chat(sid, "开始。请生成本阶段结构化结果。")
            continue

        if state == f"s{stage_id}_review":
            # Resolve actions
            resolved = resolve_current_actions(sid, stage_id)
            log(f"  Resolved {resolved} actions")

            # Verify evidence
            verified = verify_all_evidence(sid)
            log(f"  Verified {verified} evidence items")

            # Try to advance
            if advance_stage(sid, stage_id):
                log(f"  Stage {stage_id} advanced!")
                return True

            # If not advanced, check if we need to re-run
            session = get_session(sid)
            new_state = session.get("current_state") if session else "unknown"
            if new_state == f"s{stage_id}_running":
                log(f"  Stage {stage_id} re-running after rejection")
                continue

        if state.endswith("_blocked"):
            log("  Stage blocked, sending clarification")
            send_chat(
                sid, "请注意，本轮场景限定为高校/成人继续教育学生管理系统。请基于该边界重新评估。"
            )

        time.sleep(2)

    return False


def main():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    start_time = datetime.now()

    # Create session
    sid = create_session()

    # Send initial input
    log("Sending initial input...")
    if not send_chat(sid, INITIAL_INPUT):
        log("FAIL: Initial chat failed")
        return 1

    save_json("initial_session.json", get_session(sid))

    # Wait for stage 1 to start
    time.sleep(5)
    session = get_session(sid)
    log(f"Initial state: {session.get('current_state')}")

    # Process each stage
    for stage_id in range(1, 5):
        log(f"\n=== Processing Stage {stage_id} ===")

        # Wait for stage to be ready
        for _ in range(20):
            session = get_session(sid)
            state = session.get("current_state")
            if state == "complete":
                log("Session complete!")
                break
            if state == f"s{stage_id}_running" or state == f"s{stage_id}_review":
                break
            time.sleep(3)

        # Process the stage
        if not process_stage(sid, stage_id):
            log(f"Stage {stage_id} did not advance after max attempts")

        save_json(f"stage_{stage_id}_result.json", get_session(sid))

    # Final state
    session = get_session(sid)
    final_state = session.get("current_state")
    log(f"\nFinal state: {final_state}")

    # Export
    log("Exporting...")
    resp = api("GET", f"/sessions/{sid}/export", params={"format": "json"})
    if resp.status_code == 200:
        save_json("session_export.json", resp.json())

    resp = api("GET", f"/sessions/{sid}/export", params={"format": "markdown"})
    if resp.status_code == 200:
        with open(EVIDENCE_DIR / "session_export.md", "w", encoding="utf-8") as f:
            f.write(resp.text)

    # Create report
    resp = api("POST", f"/sessions/{sid}/reports")
    if resp.status_code == 200:
        save_json("report.json", resp.json())

    # Save final session
    save_json("session_final.json", session)

    # Count stage outputs
    s1 = session.get("stage_1_output", {})
    s2 = session.get("stage_2_output", {})
    s3 = session.get("stage_3_output", {})
    s4 = session.get("stage_4_output", {})

    s1_count = len(s1.get("failure_modes", [])) if isinstance(s1, dict) else 0
    s2_count = 0
    if isinstance(s2, dict):
        for v in s2.values():
            if isinstance(v, list):
                s2_count = max(s2_count, len(v))
    s3_count = len(s3.get("eval_cases", [])) if isinstance(s3, dict) else 0
    s4_count = 0
    if isinstance(s4, dict):
        for v in s4.values():
            if isinstance(v, list):
                s4_count = max(s4_count, len(v))

    log(f"\nStage 1 failure modes: {s1_count}")
    log(f"Stage 2 workflow items: {s2_count}")
    log(f"Stage 3 eval cases: {s3_count}")
    log(f"Stage 4 triggers: {s4_count}")

    # Check evidence sources
    evidence_sources = session.get("evidence_sources", [])
    log(f"Evidence sources: {len(evidence_sources)}")

    # Check LLM traces
    traces = session.get("llm_traces", [])
    log(f"LLM traces: {len(traces)}")

    # Save summary
    end_time = datetime.now()
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
        "evidence_sources": len(evidence_sources),
        "llm_traces": len(traces),
    }
    save_json("e2e_result.json", summary)

    # Determine result
    if (
        final_state == "complete"
        and s1_count >= 3
        and s2_count >= 3
        and s3_count >= 3
        and s4_count >= 3
    ):
        log("\nPASS: Student management E2E completed successfully.")
        return 0
    elif final_state == "complete":
        log("\nPARTIAL: Session complete but stage counts insufficient.")
        return 1
    else:
        log(f"\nFAIL: Session did not complete. Final state: {final_state}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
