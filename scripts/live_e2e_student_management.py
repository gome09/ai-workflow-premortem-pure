#!/usr/bin/env python3
"""
Live E2E Student Management Test Script
Drives a full Stage 0-4 workflow through the real API for a higher-education/
adult continuing education student management system scenario.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

BASE_URL = "http://localhost:8000"
EVIDENCE_DIR = Path("artifacts/live_e2e_student_management_latest")
MAX_ITERATIONS = 60

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

CONFIRM_INPUT = (
    "确认以上信息完整，请开始阶段一。请围绕高校/成人继续教育学生管理系统生成结构化结果。"
)

STAGE_PUSH_INPUT = "开始。请生成本阶段结构化结果，重点覆盖隐私、成绩、权限、通知、数据导入导出、审计、回滚和人工确认机制。"

ESCALATION_CLARIFICATION = """请注意，本轮场景限定为高校/成人继续教育学生管理系统，不涉及未成年人画像、医疗、金融贷款、自动惩戒、自动录取或自动开除。所有高影响操作均要求人工确认、审计记录和回滚机制。请基于该边界重新评估当前阶段。"""


class E2ERunner:
    def __init__(self):
        self.session_id: str | None = None
        self.iteration = 0
        self.action_log: list[dict] = []
        self.stage_results: dict[str, dict] = {}
        self.fix_log: list[str] = []
        self.error_notes: list[str] = []
        self.start_time = datetime.now()
        self.chat_sent_this_iteration = False
        self.stage_revision_counts: dict[int, int] = {}  # Track revisions per stage

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")

    def api_request(
        self, method: str, path: str, timeout: int = 120, **kwargs
    ) -> requests.Response:
        url = f"{BASE_URL}{path}"
        self.log(f"  {method} {url}")
        resp = requests.request(method, url, timeout=timeout, **kwargs)
        self.log(f"  -> {resp.status_code}")
        return resp

    def create_session(self) -> bool:
        self.log("Creating session...")
        resp = self.api_request("POST", "/sessions/")
        if resp.status_code != 200:
            self.error_notes.append(f"Create session failed: {resp.status_code} {resp.text[:500]}")
            return False
        data = resp.json()
        self.session_id = data["session_id"]
        self.log(f"Session created: {self.session_id}")
        self.save_snapshot("session_created", data)
        return True

    def get_session(self) -> dict | None:
        if not self.session_id:
            return None
        resp = self.api_request("GET", f"/sessions/{self.session_id}")
        if resp.status_code != 200:
            self.error_notes.append(f"Get session failed: {resp.status_code}")
            return None
        return resp.json()

    def send_chat(self, message: str) -> dict | None:
        if not self.session_id:
            return None
        resp = self.api_request(
            "POST",
            f"/chat/{self.session_id}",
            timeout=300,  # LLM calls can take a while
            json={"user_input": message, "user_materials": None},
        )
        if resp.status_code != 200:
            self.error_notes.append(f"Chat failed: {resp.status_code} {resp.text[:500]}")
            return None
        self.chat_sent_this_iteration = True
        return resp.json()

    def sync_review_actions(self, stage_id: int) -> dict | None:
        """Sync review actions after chat changes stage output version."""
        if not self.session_id:
            return None
        resp = self.api_request(
            "POST",
            f"/sessions/{self.session_id}/stages/{stage_id}/sync-review-actions",
            json={"reason": "e2e_sync_after_chat"},
        )
        if resp.status_code != 200:
            self.log(f"  sync-review-actions failed: {resp.status_code}")
            return None
        return resp.json()

    def get_stage_readiness(self) -> dict | None:
        if not self.session_id:
            return None
        resp = self.api_request("GET", f"/sessions/{self.session_id}/stage-readiness")
        if resp.status_code != 200:
            return None
        return resp.json()

    def get_stage_gate(self, stage_id: int) -> dict | None:
        if not self.session_id:
            return None
        resp = self.api_request("GET", f"/sessions/{self.session_id}/stage-gate/{stage_id}")
        if resp.status_code != 200:
            return None
        return resp.json()

    def get_stage_resolution(self, stage_id: int) -> dict | None:
        if not self.session_id:
            return None
        resp = self.api_request("GET", f"/sessions/{self.session_id}/stage-resolution/{stage_id}")
        if resp.status_code != 200:
            return None
        return resp.json()

    def get_actions(self, status: str = "pending") -> list:
        if not self.session_id:
            return []
        resp = self.api_request(
            "GET",
            f"/sessions/{self.session_id}/actions",
            params={"status": status},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else data.get("actions", data.get("items", []))

    def resolve_action(
        self, action_id: str, decision: str, note: str, payload_after: dict | None = None
    ) -> dict | None:
        if not self.session_id:
            return None
        body: dict = {"decision": decision, "note": note}
        if payload_after is not None:
            body["payload_after"] = payload_after
        resp = self.api_request(
            "POST",
            f"/sessions/{self.session_id}/actions/{action_id}/resolve",
            json=body,
        )
        if resp.status_code != 200:
            self.log(f"  resolve_action {action_id} -> {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()

    def get_evidence(self) -> list:
        """Get all evidence items for the session."""
        if not self.session_id:
            return []
        resp = self.api_request("GET", f"/sessions/{self.session_id}/evidence")
        if resp.status_code != 200:
            return []
        return resp.json() if isinstance(resp.json(), list) else []

    def verify_evidence(self, evidence_id: str) -> bool:
        """Verify an evidence item."""
        if not self.session_id:
            return False
        resp = self.api_request(
            "POST",
            f"/sessions/{self.session_id}/evidence/{evidence_id}/verify",
            json={"decision": "verified", "note": "Live E2E verified"},
        )
        return resp.status_code == 200

    def verify_all_evidence(self) -> int:
        """Verify all unverified evidence items. Returns count verified."""
        evidence = self.get_evidence()
        verified = 0
        for e in evidence:
            if e.get("status") is None:
                eid = e.get("evidence_id")
                if self.verify_evidence(eid):
                    verified += 1
        return verified

    def advance_stage(self, stage_id: int) -> dict | None:
        if not self.session_id:
            return None
        resp = self.api_request(
            "POST",
            f"/sessions/{self.session_id}/stages/{stage_id}/advance",
            json={"reason": "live_e2e_student_management_stage_approved"},
        )
        if resp.status_code != 200:
            self.error_notes.append(
                f"Advance stage {stage_id} failed: {resp.status_code} {resp.text[:300]}"
            )
            return None
        return resp.json()

    def export_session(self, fmt: str) -> tuple[int, str]:
        if not self.session_id:
            return 0, ""
        resp = self.api_request(
            "GET",
            f"/sessions/{self.session_id}/export",
            params={"format": fmt},
        )
        return resp.status_code, resp.text[:2000] if resp.status_code == 200 else resp.text[:500]

    def create_report(self) -> tuple[int, dict | None]:
        if not self.session_id:
            return 0, None
        resp = self.api_request("POST", f"/sessions/{self.session_id}/reports")
        if resp.status_code != 200:
            return resp.status_code, None
        return resp.status_code, resp.json()

    def save_snapshot(self, label: str, data: Any):
        path = EVIDENCE_DIR / f"snap_{self.iteration:03d}_{label}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def save_stage_review(self, stage_id: int, data: dict):
        path = EVIDENCE_DIR / f"stage_{stage_id}_review.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def get_current_stage_version(self, stage_id: int) -> int | None:
        """Get the current stage output version from the session."""
        session = self.get_session()
        if not session:
            return None
        versions = session.get("stage_output_versions", {})
        return versions.get(f"stage_{stage_id}")

    def filter_current_actions(self, actions: list, stage_id: int) -> list:
        """Filter actions to only include those matching the current stage output version."""
        current_version = self.get_current_stage_version(stage_id)
        if current_version is None:
            return actions
        return [a for a in actions if a.get("stage_output_version") == current_version]

    def handle_pending_actions(self, stage_id: int) -> bool:
        """Handle pending actions for a stage. Returns True if all resolved."""
        # First, get current actions
        all_actions = self.get_actions("pending")
        if not all_actions:
            self.log(f"  No pending actions for stage {stage_id}")
            return True

        # Filter to current version only
        actions = self.filter_current_actions(all_actions, stage_id)
        self.log(f"  {len(all_actions)} total pending, {len(actions)} for current version")

        if not actions:
            self.log(f"  No current-version pending actions for stage {stage_id}")
            return True

        # Separate actions by type
        escalate_actions = [a for a in actions if a.get("action_type", a.get("type")) == "escalate"]
        edit_actions = [a for a in actions if a.get("action_type", a.get("type")) == "edit"]
        approve_actions = [a for a in actions if a.get("action_type", a.get("type")) == "approve"]
        verify_actions = [
            a for a in actions if a.get("action_type", a.get("type")) == "verify_evidence"
        ]
        other_actions = [
            a
            for a in actions
            if a.get("action_type", a.get("type"))
            not in ("escalate", "edit", "approve", "verify_evidence")
        ]

        # Resolve escalate actions - approve them directly
        for action in escalate_actions:
            action_id = action.get("action_id", action.get("id"))
            result = self.resolve_action(
                action_id,
                "approve",
                "Live E2E reviewer approved escalation after confirming scenario is higher-education/adult student management with no minors, medical, financial, or auto-punishment concerns.",
            )
            self.action_log.append(
                {
                    "action_id": action_id,
                    "type": "escalate",
                    "decision": "approve",
                    "resolved": result is not None,
                }
            )

        # Resolve edit actions - must use "edit" + payload_after, or "reject"
        rev_count = self.stage_revision_counts.get(stage_id, 0)
        for action in edit_actions:
            action_id = action.get("action_id", action.get("id"))
            if rev_count >= 3:
                # After 3 revision cycles, use edit+payload to approve and break loop
                session_for_payload = self.get_session()
                stage_output_key = f"stage_{stage_id}_output"
                current_output = (
                    session_for_payload.get(stage_output_key) if session_for_payload else None
                )
                result = self.resolve_action(
                    action_id,
                    "edit",
                    "Live E2E reviewer approved edit with current stage output after multiple revision cycles.",
                    payload_after=current_output,
                )
                decision = "edit"
                if result is None:
                    result = self.resolve_action(
                        action_id,
                        "reject",
                        "Live E2E reviewer rejected edit to trigger final revision.",
                    )
                    decision = "reject"
            else:
                # First 3 cycles: reject to trigger LLM revision
                result = self.resolve_action(
                    action_id,
                    "reject",
                    "Live E2E reviewer rejected edit to trigger stage revision for higher-ed student management scenario.",
                )
                decision = "reject"
            self.action_log.append(
                {
                    "action_id": action_id,
                    "type": "edit",
                    "decision": decision,
                    "resolved": result is not None,
                }
            )

        # Resolve approve actions
        for action in approve_actions:
            action_id = action.get("action_id", action.get("id"))
            result = self.resolve_action(
                action_id,
                "approve",
                "Live E2E reviewer approved this stage item for progression after checking privacy, grade, permission, notification, import/export, audit, rollback, and human confirmation concerns.",
            )
            self.action_log.append(
                {
                    "action_id": action_id,
                    "type": "approve",
                    "decision": "approve",
                    "resolved": result is not None,
                }
            )

        # Resolve verify_evidence actions
        for action in verify_actions:
            action_id = action.get("action_id", action.get("id"))
            result = self.resolve_action(
                action_id,
                "verified",
                "Live E2E reviewer verified evidence relevance for the higher-education/adult student management scenario.",
            )
            if result is None:
                result = self.resolve_action(
                    action_id,
                    "approve",
                    "Live E2E reviewer approved evidence relevance for the higher-education/adult student management scenario.",
                )
            self.action_log.append(
                {
                    "action_id": action_id,
                    "type": "verify_evidence",
                    "decision": "verified",
                    "resolved": result is not None,
                }
            )

        # Resolve other actions
        for action in other_actions:
            action_id = action.get("action_id", action.get("id"))
            action_type = action.get("action_type", action.get("type"))
            result = self.resolve_action(
                action_id,
                "approve",
                f"Live E2E reviewer auto-approved {action_type} action.",
            )
            self.action_log.append(
                {
                    "action_id": action_id,
                    "type": action_type,
                    "decision": "auto_approve",
                    "resolved": result is not None,
                }
            )

        return True

    def run(self) -> str:
        """Main E2E loop. Returns final status: PASS, EXPECTED_SAFETY_BLOCK, or FAIL."""
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

        # Create session
        if not self.create_session():
            return "FAIL"

        # Send initial input
        self.log("Sending initial user input...")
        chat_result = self.send_chat(INITIAL_INPUT)
        if chat_result is None:
            self.error_notes.append("Initial chat failed")
            return "FAIL"
        self.save_snapshot("initial_chat", chat_result)

        # Main loop
        consecutive_same_state = 0
        last_state = ""

        while self.iteration < MAX_ITERATIONS:
            self.iteration += 1
            self.chat_sent_this_iteration = False
            self.log(f"\n=== Iteration {self.iteration} ===")

            # Get session state
            session = self.get_session()
            if session is None:
                self.error_notes.append(f"Failed to get session at iteration {self.iteration}")
                time.sleep(2)
                continue

            current_state = session.get("current_state", "unknown")
            self.log(f"Current state: {current_state}")
            self.save_snapshot("session", session)

            # Check for completion
            if current_state == "complete":
                self.log("Session reached COMPLETE state!")
                self.stage_results["final_state"] = current_state
                return self._finalize(session)

            # Track state stuck and per-stage review count
            if current_state == last_state:
                consecutive_same_state += 1
            else:
                consecutive_same_state = 0
            last_state = current_state

            # Track per-stage review count to break revision loops
            if current_state in ("s1_review", "s2_review", "s3_review", "s4_review"):
                stage_num = int(current_state[1])
                review_key = f"_review_count_s{stage_num}"
                current_review_count = self.stage_revision_counts.get(review_key, 0) + 1
                self.stage_revision_counts[review_key] = current_review_count
                if current_review_count > 10:
                    self.log(
                        f"Stage {stage_num} has been in review {current_review_count} times - force advancing"
                    )
                    self.stage_revision_counts[stage_num] = 99  # Force approve-all mode

            if consecutive_same_state > 8:
                self.log(f"State stuck at {current_state} for {consecutive_same_state} iterations")
                # Try sending a push message
                self.send_chat(STAGE_PUSH_INPUT)
                # Sync actions if in review
                if "review" in current_state:
                    stage_num = int(current_state[1])
                    self.sync_review_actions(stage_id=stage_num)
                consecutive_same_state = 0

            # Handle based on state
            if current_state == "init":
                self.log("State is init, sending confirmation...")
                self.send_chat(CONFIRM_INPUT)

            elif current_state in ("s1_running", "s2_running", "s3_running", "s4_running"):
                stage_num = int(current_state[1])
                self.log(f"Stage {stage_num} is running, pushing...")
                self.send_chat(STAGE_PUSH_INPUT)

            elif current_state in ("s1_review", "s2_review", "s3_review", "s4_review"):
                stage_num = int(current_state[1])
                self.log(f"Stage {stage_num} in review, processing...")

                # Track revision count
                current_version = session.get("stage_output_versions", {}).get(
                    f"stage_{stage_num}", 0
                )
                prev_version = self.stage_revision_counts.get(f"_last_seen_v{stage_num}", 0)
                if current_version > prev_version:
                    self.stage_revision_counts[stage_num] = (
                        self.stage_revision_counts.get(stage_num, 0) + 1
                    )
                    self.stage_revision_counts[f"_last_seen_v{stage_num}"] = current_version
                    self.log(
                        f"  Revision count for stage {stage_num}: {self.stage_revision_counts[stage_num]} (v{current_version})"
                    )

                # Gather review data
                readiness = self.get_stage_readiness()
                gate = self.get_stage_gate(stage_num)
                resolution = self.get_stage_resolution(stage_num)
                actions = self.get_actions("pending")

                review_data = {
                    "stage_id": stage_num,
                    "readiness": readiness,
                    "gate": gate,
                    "resolution": resolution,
                    "pending_actions": actions,
                }
                self.save_stage_review(stage_num, review_data)
                self.save_snapshot(f"stage_{stage_num}_review", review_data)

                # Handle pending actions (may send chat and sync)
                self.handle_pending_actions(stage_num)

                # Verify all evidence before advancing
                verified_count = self.verify_all_evidence()
                self.log(f"  Verified {verified_count} evidence items")

                # Try to advance
                self.log(f"Attempting to advance stage {stage_num}...")
                advance_result = self.advance_stage(stage_num)
                if advance_result:
                    self.save_snapshot(f"stage_{stage_num}_advanced", advance_result)

                # Save stage results
                session_after = self.get_session()
                if session_after:
                    self.stage_results[f"stage_{stage_num}"] = {
                        "state": session_after.get("current_state"),
                        "output_keys": list(
                            session_after.get("stages", {})
                            .get(f"s{stage_num}", {})
                            .get("output", {})
                            .keys()
                        )
                        if isinstance(
                            session_after.get("stages", {})
                            .get(f"s{stage_num}", {})
                            .get("output", {}),
                            dict,
                        )
                        else [],
                    }

            elif current_state.endswith("_blocked"):
                self.log(f"Stage blocked: {current_state}")
                self.send_chat(ESCALATION_CLARIFICATION)
                stage_num = int(current_state[1])
                self.sync_review_actions(stage_id=stage_num)

            else:
                self.log(f"State: {current_state}, waiting...")
                time.sleep(2)

            time.sleep(1)

        self.error_notes.append(f"Max iterations ({MAX_ITERATIONS}) reached without completion")
        return "FAIL"

    def _finalize(self, session: dict) -> str:
        """Run final checks and generate outputs."""
        self.log("\n=== Finalization ===")

        # Export JSON
        json_status, json_data = self.export_session("json")
        self.log(f"Export JSON: {json_status}")
        if json_status == 200:
            with open(EVIDENCE_DIR / "session_export.json", "w", encoding="utf-8") as f:
                f.write(json_data)

        # Export Markdown
        md_status, md_data = self.export_session("markdown")
        self.log(f"Export Markdown: {md_status}")
        if md_status == 200:
            with open(EVIDENCE_DIR / "session_export.md", "w", encoding="utf-8") as f:
                f.write(md_data)

        # Create report
        report_status, report_data = self.create_report()
        self.log(f"Create report: {report_status}")
        if report_data:
            with open(EVIDENCE_DIR / "report.json", "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)

        # Save final session
        with open(EVIDENCE_DIR / "session_final.json", "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2, ensure_ascii=False, default=str)

        # Check for blocking pending actions
        final_actions = self.get_actions("pending")
        blocking_actions = [
            a for a in final_actions if a.get("blocking", a.get("is_blocking", False))
        ]

        # Validate stage outputs
        stages = session.get("stages", {})
        s1_output = stages.get("s1", {}).get("output", {})
        s2_output = stages.get("s2", {}).get("output", {})
        s3_output = stages.get("s3", {}).get("output", {})
        s4_output = stages.get("s4", {}).get("output", {})

        # Count items
        s1_count = self._count_stage_items(s1_output, ["failure_modes", "failure_modes_analysis"])
        s2_count = self._count_stage_items(
            s2_output, ["workflow_nodes", "workflow", "human_oversight_workflow"]
        )
        s3_count = self._count_stage_items(
            s3_output, ["eval_cases", "test_results", "eval_results"]
        )
        s4_count = self._count_stage_items(
            s4_output, ["trigger_methods", "execution_recommendations", "triggers"]
        )

        self.log(f"Stage 1 failure modes: {s1_count}")
        self.log(f"Stage 2 workflow nodes: {s2_count}")
        self.log(f"Stage 3 eval cases: {s3_count}")
        self.log(f"Stage 4 triggers: {s4_count}")

        # Save summary
        summary = {
            "session_id": self.session_id,
            "final_state": "complete",
            "started_at": self.start_time.isoformat(),
            "completed_at": datetime.now().isoformat(),
            "stage_counts": {
                "s1_failure_modes": s1_count,
                "s2_workflow_nodes": s2_count,
                "s3_eval_cases": s3_count,
                "s4_triggers": s4_count,
            },
            "exports": {
                "json_status": json_status,
                "markdown_status": md_status,
                "report_status": report_status,
            },
            "pending_actions": len(final_actions),
            "blocking_actions": len(blocking_actions),
            "action_log": self.action_log,
            "error_notes": self.error_notes,
            "fix_log": self.fix_log,
        }

        with open(EVIDENCE_DIR / "e2e_result.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

        # Determine pass/fail
        if (
            s1_count >= 3
            and s2_count >= 3
            and s3_count >= 3
            and s4_count >= 3
            and json_status == 200
            and md_status == 200
            and report_status == 200
            and len(blocking_actions) == 0
        ):
            return "PASS"
        else:
            reasons = []
            if s1_count < 3:
                reasons.append(f"s1_failure_modes={s1_count}<3")
            if s2_count < 3:
                reasons.append(f"s2_workflow_nodes={s2_count}<3")
            if s3_count < 3:
                reasons.append(f"s3_eval_cases={s3_count}<3")
            if s4_count < 3:
                reasons.append(f"s4_triggers={s4_count}<3")
            if json_status != 200:
                reasons.append(f"export_json={json_status}")
            if md_status != 200:
                reasons.append(f"export_markdown={md_status}")
            if report_status != 200:
                reasons.append(f"report={report_status}")
            if len(blocking_actions) > 0:
                reasons.append(f"blocking_actions={len(blocking_actions)}")
            self.error_notes.append(f"FAIL criteria not met: {', '.join(reasons)}")
            return "FAIL"

    def _count_stage_items(self, output: Any, keys: list[str]) -> int:
        """Count items in stage output by trying multiple key names."""
        if not isinstance(output, dict):
            return 0
        for key in keys:
            val = output.get(key)
            if isinstance(val, list):
                return len(val)
            elif isinstance(val, dict):
                for k, v in val.items():
                    if isinstance(v, list):
                        return len(v)
        # Try any list in the output
        for val in output.values():
            if isinstance(val, list):
                return len(val)
            elif isinstance(val, dict):
                for v in val.values():
                    if isinstance(v, list):
                        return len(v)
        return 0


def main():
    runner = E2ERunner()
    result = runner.run()

    print(f"\n{'=' * 60}")
    print(f"E2E Result: {result}")
    print(f"Session ID: {runner.session_id}")
    print(f"Iterations: {runner.iteration}")
    print(f"Actions resolved: {len(runner.action_log)}")
    print(f"Error notes: {len(runner.error_notes)}")
    print(f"Evidence directory: {EVIDENCE_DIR}")
    print(f"{'=' * 60}")

    # Write fix log
    with open(EVIDENCE_DIR / "fix_log.md", "w", encoding="utf-8") as f:
        f.write("# Fix Log\n\n")
        f.write(f"Date: {datetime.now().isoformat()}\n\n")
        if runner.fix_log:
            for entry in runner.fix_log:
                f.write(f"- {entry}\n")
        else:
            f.write("No fixes needed.\n")

    if result == "PASS":
        print("\nPASS: Student management E2E completed successfully.")
        return 0
    elif result == "EXPECTED_SAFETY_BLOCK":
        print("\nEXPECTED_SAFETY_BLOCK: Safety gate blocked as expected.")
        return 0
    else:
        print(f"\nFAIL: E2E did not complete. Errors: {runner.error_notes}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
