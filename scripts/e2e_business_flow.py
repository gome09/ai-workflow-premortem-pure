#!/usr/bin/env python3
"""Docker 全栈业务 E2E（CI blocking gate）。

通过 nginx 反代驱动真实 PostgreSQL + Redis 栈，覆盖 Milestone 1 验收要求：

  创建会话 -> 阶段 1 推进 -> 暂停（产生 blocking 人工动作）-> 解决动作恢复
  -> 阶段 2 暂停/恢复 -> 回滚 -> 审计事件可读

仅使用 stdlib（urllib），不依赖 requests，便于 CI 在最小依赖下执行。
默认以 `https://localhost` 为入口（nginx 自签证书），自动探测 `/api` 前缀。

用法：
    python scripts/e2e_business_flow.py --base https://localhost
    E2E_USER_EMAIL=demo@example.com E2E_USER_PASSWORD=... python scripts/e2e_business_flow.py
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_EMAIL = os.getenv("E2E_USER_EMAIL") or os.getenv("DEMO_USER_EMAIL") or "demo@example.com"
DEFAULT_PASSWORD = (
    os.getenv("E2E_USER_PASSWORD") or os.getenv("DEMO_USER_PASSWORD") or "CHANGE_ME_demo_password"
)
DEFAULT_SCENARIO = "generic_rag_demo"

INITIAL_INPUT = """我想分析一个通用 RAG 演示系统。

研究对象：通用 RAG 演示系统。
具体目标：识别失败模式，设计人机协同工作流，生成压力测试/EvalCase，给出触发方式与执行建议。

请确认信息收集完毕，并进入阶段一。"""

STAGE_INPUT = "开始本阶段结构化输出。"


class BusinessFlowE2E:
    def __init__(self, base: str, *, timeout: int = 120) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.prefix = ""
        self.token = ""
        self.failures: list[str] = []

    # ── HTTP helpers ─────────────────────────────────────────────
    def _open(
        self, url: str, data: bytes | None, headers: dict[str, str], method: str
    ) -> tuple[int, str]:
        request = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310
        context = ssl._create_unverified_context()  # noqa: S323 - 本地自签名证书验收
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=context) as resp:  # noqa: S310
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")

    def http(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        form: dict | None = None,
    ) -> tuple[int, str]:
        url = f"{self.base}{self.prefix}{path}"
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            return self._open(url, data, headers, method)
        except urllib.error.URLError as exc:
            raise SystemExit(f"API unreachable: {url} ({exc})") from exc

    def json_body(self, method: str, path: str, **kwargs) -> tuple[int, dict]:
        status, text = self.http(method, path, **kwargs)
        try:
            body = json.loads(text) if text else {}
        except json.JSONDecodeError:
            body = {"_raw": text[:300]}
        return status, body

    # ── assertions ───────────────────────────────────────────────
    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        if condition:
            print(f"PASS {name}")
            return True
        self.failures.append(f"{name}: {detail}")
        print(f"FAIL {name}: {detail}")
        return False

    # ── steps ────────────────────────────────────────────────────
    def detect_prefix(self) -> None:
        for candidate in ("/api", ""):
            url = f"{self.base}{candidate}/health/live"
            try:
                status, _ = self._open(url, None, {"Accept": "application/json"}, "GET")
            except urllib.error.URLError as exc:
                raise SystemExit(f"API unreachable: {url} ({exc})") from exc
            if status == 200:
                self.prefix = candidate
                print(f"INFO api prefix={candidate or '(none)'} base={self.base}")
                self.check("health live", True)
                return
        self.check("health live", False, "neither /api/health/live nor /health/live returned 200")

    def authenticate(self, email: str, password: str) -> None:
        status, body = self.json_body(
            "POST", "/auth/login", form={"username": email, "password": password}
        )
        if status == 200 and body.get("access_token"):
            self.token = body["access_token"]
            self.check("auth login", True)
            return
        status, body = self.json_body(
            "POST", "/auth/register", json_body={"email": email, "password": password}
        )
        if status == 200 and body.get("access_token"):
            self.token = body["access_token"]
            self.check("auth register", True)
            return
        self.check("auth", False, f"login={status} body={str(body)[:200]}")

    def create_session(self, scenario_id: str) -> str | None:
        status, body = self.json_body("POST", "/sessions/", json_body={"scenario_id": scenario_id})
        session_id = body.get("session_id")
        self.check(
            "create session",
            status == 200 and isinstance(session_id, str) and body.get("current_state") == "init",
            f"status={status} body={str(body)[:200]}",
        )
        return session_id if isinstance(session_id, str) else None

    def state(self, session_id: str) -> str:
        status, body = self.json_body("GET", f"/sessions/{session_id}")
        return str(body.get("current_state")) if status == 200 else f"http_{status}"

    def chat(self, session_id: str, message: str) -> dict:
        status, body = self.json_body(
            "POST", f"/chat/{session_id}", json_body={"user_input": message}
        )
        self.check(
            f"chat ({message[:16]})",
            status == 200,
            f"status={status} body={str(body)[:200]}",
        )
        return body

    def drive_to_review(self, session_id: str, stage: int, *, attempts: int = 8) -> str:
        expected = f"s{stage}_review"
        for _ in range(attempts):
            current = self.state(session_id)
            if current == expected:
                return current
            if current == "init":
                self.chat(session_id, INITIAL_INPUT)
                continue
            if current == f"s{stage}_running":
                self.chat(session_id, STAGE_INPUT)
                continue
            time.sleep(0.5)
        return self.state(session_id)

    def pending_actions(self, session_id: str) -> list[dict]:
        status, text = self.http("GET", f"/sessions/{session_id}/actions?status=pending")
        if status != 200:
            return []
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return []
        return body if isinstance(body, list) else []

    def advance_decision(self, session_id: str, stage: int) -> dict | None:
        status, body = self.json_body(
            "GET", f"/sessions/{session_id}/stages/{stage}/advancement-decision"
        )
        return body if status == 200 else None

    def resolve_pending_actions(self, session_id: str) -> int:
        resolved = 0
        for _ in range(3):
            actions = self.pending_actions(session_id)
            if not actions:
                break
            progress = 0
            for action in actions:
                action_id = action.get("action_id")
                action_type = str(action.get("action_type"))
                if action_type == "verify_evidence":
                    decision = "verify_evidence"
                elif action_type == "escalate":
                    decision = "approve"
                elif action_type == "approve":
                    decision = "approve"
                else:
                    # 结构化 edit 需要完整 structured_output，本 E2E 不自动伪造；
                    # 保持 pending 会由后续 advance 断言暴露。
                    print(f"INFO skip action {action_id} type={action_type} (needs manual edit)")
                    continue
                status, body = self.json_body(
                    "POST",
                    f"/sessions/{session_id}/actions/{action_id}/resolve",
                    json_body={"decision": decision, "note": "e2e business flow review"},
                )
                if status == 200:
                    resolved += 1
                    progress += 1
                else:
                    print(f"WARN resolve {action_id} -> {status} {str(body)[:160]}")
            if progress == 0:
                break
        return resolved

    def approve_stage(self, session_id: str, stage: int) -> bool:
        status, body = self.json_body(
            "POST",
            f"/sessions/{session_id}/stages/{stage}/advance",
            json_body={"reason": "e2e_business_flow_advance"},
        )
        advanced = status == 200 and bool(body.get("advanced"))
        self.check(
            f"advance stage {stage}",
            advanced,
            f"status={status} advanced={body.get('advanced')} reason={body.get('decision_reason')}",
        )
        return advanced

    def run(self, *, email: str, password: str, scenario_id: str) -> int:
        print("=" * 64)
        print("Business flow E2E: create -> advance -> pause -> resume -> rollback")
        print("=" * 64)

        self.detect_prefix()
        if self.failures:
            return self.summarize()

        self.authenticate(email, password)
        session_id = self.create_session(scenario_id)
        if self.failures or session_id is None:
            return self.summarize()

        print(f"INFO session={session_id}")

        # Stage 1: create -> advance (generation) -> pause (blocking action)
        self.chat(session_id, INITIAL_INPUT)
        review_state = self.drive_to_review(session_id, 1)
        self.check("stage 1 reaches review", review_state == "s1_review", f"state={review_state}")

        blocking = [a for a in self.pending_actions(session_id) if a.get("blocking")]
        self.check(
            "stage 1 pause: blocking action queued",
            len(blocking) >= 1,
            f"pending={len(self.pending_actions(session_id))} blocking={len(blocking)}",
        )
        decision = self.advance_decision(session_id, 1) or {}
        self.check(
            "stage 1 gate blocks while action pending",
            decision.get("can_advance") is False,
            f"can_advance={decision.get('can_advance')} reason={decision.get('decision_reason')}",
        )

        resolved = self.resolve_pending_actions(session_id)
        print(f"INFO resolved actions={resolved}")

        decision = self.advance_decision(session_id, 1) or {}
        self.check(
            "stage 1 gate clears after human resolution",
            decision.get("can_advance") is True,
            f"can_advance={decision.get('can_advance')} blockers={decision.get('hard_blockers_count')}",
        )
        if self.approve_stage(session_id, 1):
            self.check("stage 1 advanced to s2_running", self.state(session_id) == "s2_running")

        # Stage 2: pause on oversight policy -> resume -> advance
        review_state = self.drive_to_review(session_id, 2)
        self.check("stage 2 reaches review", review_state == "s2_review", f"state={review_state}")

        blocking = [a for a in self.pending_actions(session_id) if a.get("blocking")]
        self.check(
            "stage 2 pause: blocking oversight action queued",
            len(blocking) >= 1,
            f"pending={len(self.pending_actions(session_id))} blocking={len(blocking)}",
        )
        decision = self.advance_decision(session_id, 2) or {}
        self.check(
            "stage 2 gate blocks while action pending",
            decision.get("can_advance") is False,
            f"can_advance={decision.get('can_advance')} reason={decision.get('decision_reason')}",
        )

        resolved = self.resolve_pending_actions(session_id)
        print(f"INFO resolved actions={resolved}")

        decision = self.advance_decision(session_id, 2) or {}
        self.check(
            "stage 2 gate clears after human resolution",
            decision.get("can_advance") is True,
            f"can_advance={decision.get('can_advance')} blockers={decision.get('hard_blockers_count')}",
        )
        if self.approve_stage(session_id, 2):
            self.check("stage 2 advanced to s3_running", self.state(session_id) == "s3_running")

        # Rollback: stage 2 -> stage 1 (review)
        status, body = self.json_body(
            "POST",
            f"/sessions/{session_id}/stages/2/rollback",
            json_body={
                "to_stage": 1,
                "reason": "e2e_business_flow_rollback",
                "note": "verify rollback keeps workflow recoverable",
            },
        )
        self.check(
            "rollback stage 2 -> 1",
            status == 200 and body.get("operation") == "stage_rollback_prepared",
            f"status={status} operation={body.get('operation')}",
        )
        self.check(
            "rollback returns workflow to s1_review",
            self.state(session_id) == "s1_review",
            f"state={self.state(session_id)}",
        )

        status, events = self.json_body("GET", f"/sessions/{session_id}/audit-events")
        event_types = {str(item.get("event_type")) for item in events if isinstance(item, dict)}
        self.check(
            "rollback is audit-logged",
            status == 200 and "stage_rollback_requested" in event_types,
            f"status={status} events={sorted(event_types)[:10]}",
        )

        return self.summarize()

    def summarize(self) -> int:
        print("-" * 64)
        if self.failures:
            print(f"RESULT: FAIL ({len(self.failures)} failure(s))")
            for failure in self.failures:
                print(f"  - {failure}")
            return 1
        print("RESULT: PASS")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Business-flow E2E for the full Docker stack")
    parser.add_argument("--base", default=os.getenv("API_BASE", "https://localhost"))
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    return BusinessFlowE2E(args.base, timeout=args.timeout).run(
        email=args.email, password=args.password, scenario_id=args.scenario
    )


if __name__ == "__main__":
    sys.exit(main())
