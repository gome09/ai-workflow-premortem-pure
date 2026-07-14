# tests/test_gate_evaluation_records_v110.py
"""T3.2 判定结果携带规则版本 + 评估记录持久化契约测试。

覆盖：
- RuleDetail.rule_version 字段携带 manifest 版本
- 旁路落表 gate_evaluation_records（detailed 真假均落）
- 降级测试：persist 失败不阻断主路径
- gate_trends 按周聚合
- governance_overview 租户内聚合
- tenant 隔离（空 tenant_id 不开放跨租户）
- actions_backlog 按 risk_level 排序
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from core.gates.engine import evaluate_stage_gate
from core.gates.report import RuleDetail
from core.gates.rules.manifest import get_rule_version
from core.models import ProjectContext
from core.stage_readiness_service import StageGateResult
from storage.backends.sqlite_store import SQLiteSessionStore

# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────


@pytest.fixture
def sqlite_store(tmp_path, monkeypatch):
    """Fresh isolated SQLite store, patched as the global session_store."""
    db_path = str(tmp_path / "test_gate_eval.db")
    store = SQLiteSessionStore(db_path=db_path)
    store.initialize()
    # Engine lazily imports `session_store` from storage.session_store at call
    # time, so patching the module attribute is picked up.
    monkeypatch.setattr("storage.session_store.session_store", store)
    return store


def _insert_eval(
    store,
    *,
    session_id: str,
    tenant_id: str,
    stage_id: int,
    risk_tier: str,
    passed: bool,
    blocking_rule_ids: list,
    evaluated_at: str,
) -> None:
    """Insert a gate_evaluation_records row with explicit evaluated_at."""
    record_id = str(uuid.uuid4())[:8]
    with store._get_conn() as conn:
        conn.execute(
            "INSERT INTO gate_evaluation_records "
            "(record_id, session_id, tenant_id, stage_id, risk_tier, passed, "
            " blocking_rule_ids, rule_versions, evaluated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                session_id,
                tenant_id,
                stage_id,
                risk_tier,
                int(passed),
                json.dumps(blocking_rule_ids),
                json.dumps({}),
                evaluated_at,
            ),
        )
        conn.commit()


def _insert_session(
    store,
    *,
    session_id: str,
    tenant_id: str,
    current_state: str,
    context_json: dict,
) -> None:
    """Insert a sessions row with explicit context_json."""
    with store._get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions "
            "(session_id, tenant_id, current_state, context_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                tenant_id,
                current_state,
                json.dumps(context_json),
                "2026-07-14T00:00:00",
                "2026-07-14T00:00:00",
            ),
        )
        conn.commit()


# ─────────────────────────────────────────────────────────
# 1. rule_version 携带
# ─────────────────────────────────────────────────────────


class TestRuleVersionCarried:
    def test_rule_detail_has_default_version(self):
        r = RuleDetail(rule_id="x", display_name="X", status="passed")
        assert r.rule_version == "0.0.0"

    def test_report_rules_carry_manifest_version(self, sqlite_store):
        ctx = ProjectContext()
        ctx.session_id = "sess-rv"
        ctx.tenant_id = "tenant-rv"
        result = evaluate_stage_gate(ctx, stage=1, detailed=True)
        report = result.__dict__["report"]
        assert report is not None
        assert len(report.rules) > 0
        for rule in report.rules:
            assert rule.rule_version, f"{rule.rule_id}: rule_version empty"
            assert rule.rule_version == get_rule_version(rule.rule_id)

    def test_report_blocked_rule_carries_correct_version(self, sqlite_store):
        """missing_output rule (version 1.0.0) should block an empty ctx."""
        ctx = ProjectContext()
        ctx.session_id = "sess-rv2"
        ctx.tenant_id = "tenant-rv"
        result = evaluate_stage_gate(ctx, stage=1, detailed=True)
        report = result.__dict__["report"]
        blocked_rules = [r for r in report.rules if r.status == "blocked"]
        assert len(blocked_rules) > 0
        mo = next(r for r in blocked_rules if r.rule_id == "missing_output")
        assert mo.rule_version == "1.0.0"


# ─────────────────────────────────────────────────────────
# 2. 旁路落表
# ─────────────────────────────────────────────────────────


class TestBypassPersist:
    def test_detailed_false_still_persists(self, sqlite_store):
        """detailed=False must still write a gate_evaluation_records row."""
        ctx = ProjectContext()
        ctx.session_id = "sess-bp-false"
        ctx.tenant_id = "tenant-bp"
        result = evaluate_stage_gate(ctx, stage=1, detailed=False)
        assert isinstance(result, StageGateResult)

        with sqlite_store._get_conn() as conn:
            rows = conn.execute(
                "SELECT session_id, stage_id, risk_tier, passed, blocking_rule_ids "
                "FROM gate_evaluation_records WHERE session_id=?",
                ("sess-bp-false",),
            ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["session_id"] == "sess-bp-false"
        assert row["stage_id"] == 1
        assert row["risk_tier"] in {"low", "medium", "high", "critical"}
        blocking = json.loads(row["blocking_rule_ids"])
        assert isinstance(blocking, list)
        # Empty ctx at stage 1 → missing_output blocks → passed=0
        assert row["passed"] == 0
        assert "missing_output" in blocking

    def test_detailed_true_also_persists(self, sqlite_store):
        ctx = ProjectContext()
        ctx.session_id = "sess-bp-true"
        ctx.tenant_id = "tenant-bp"
        evaluate_stage_gate(ctx, stage=1, detailed=True)
        with sqlite_store._get_conn() as conn:
            row = conn.execute(
                "SELECT session_id, stage_id FROM gate_evaluation_records WHERE session_id=?",
                ("sess-bp-true",),
            ).fetchone()
        assert row is not None
        assert row["session_id"] == "sess-bp-true"
        assert row["stage_id"] == 1

    def test_no_session_id_skips_persist(self, sqlite_store):
        """Empty session_id must not attempt a write."""
        ctx = ProjectContext()
        ctx.session_id = ""  # edge case
        ctx.tenant_id = "tenant-bp"
        evaluate_stage_gate(ctx, stage=1, detailed=False)
        with sqlite_store._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM gate_evaluation_records").fetchone()
        assert row["n"] == 0


# ─────────────────────────────────────────────────────────
# 3. 降级测试
# ─────────────────────────────────────────────────────────


class TestDegradation:
    def test_persist_failure_does_not_block_gate(self, sqlite_store, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("simulated DB failure")

        monkeypatch.setattr(sqlite_store, "record_gate_evaluation", boom)
        ctx = ProjectContext()
        ctx.session_id = "sess-deg"
        ctx.tenant_id = "tenant-deg"
        # Must not raise
        result = evaluate_stage_gate(ctx, stage=1, detailed=True)
        assert isinstance(result, StageGateResult)
        assert result.stage_id == 1
        # Report is still attached despite persist failure
        assert result.__dict__.get("report") is not None

    def test_persist_failure_with_detailed_false(self, sqlite_store, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("simulated DB failure")

        monkeypatch.setattr(sqlite_store, "record_gate_evaluation", boom)
        ctx = ProjectContext()
        ctx.session_id = "sess-deg2"
        ctx.tenant_id = "tenant-deg"
        result = evaluate_stage_gate(ctx, stage=1, detailed=False)
        assert isinstance(result, StageGateResult)


# ─────────────────────────────────────────────────────────
# 4. gate_trends 按周聚合
# ─────────────────────────────────────────────────────────


class TestGateTrends:
    def test_weekly_aggregation_pass_rate(self, sqlite_store):
        now = datetime.utcnow()
        last_period = now - timedelta(days=14)
        tenant = "tenant-trends"

        # This week: 2 passed, 1 blocked (missing_output)
        for sid in ("s1", "s2"):
            _insert_eval(
                sqlite_store,
                session_id=sid,
                tenant_id=tenant,
                stage_id=1,
                risk_tier="medium",
                passed=True,
                blocking_rule_ids=[],
                evaluated_at=now.isoformat(),
            )
        _insert_eval(
            sqlite_store,
            session_id="s3",
            tenant_id=tenant,
            stage_id=1,
            risk_tier="high",
            passed=False,
            blocking_rule_ids=["missing_output"],
            evaluated_at=now.isoformat(),
        )
        # Previous period: 1 passed, 1 blocked (safety_finding)
        _insert_eval(
            sqlite_store,
            session_id="s4",
            tenant_id=tenant,
            stage_id=2,
            risk_tier="medium",
            passed=True,
            blocking_rule_ids=[],
            evaluated_at=last_period.isoformat(),
        )
        _insert_eval(
            sqlite_store,
            session_id="s5",
            tenant_id=tenant,
            stage_id=2,
            risk_tier="low",
            passed=False,
            blocking_rule_ids=["safety_finding"],
            evaluated_at=last_period.isoformat(),
        )

        trends = sqlite_store.gate_trends(tenant, weeks=8)
        assert len(trends) == 2  # two distinct week buckets
        total_evals = sum(b["evaluations"] for b in trends)
        assert total_evals == 5
        total_passed = sum(b["passed"] for b in trends)
        assert total_passed == 3

        # Verify pass_rate computed correctly per bucket
        for bucket in trends:
            if bucket["evaluations"] == 3:
                assert bucket["passed"] == 2
                assert abs(bucket["pass_rate"] - 2 / 3) < 0.01
            elif bucket["evaluations"] == 2:
                assert bucket["passed"] == 1
                assert abs(bucket["pass_rate"] - 0.5) < 0.01

        # top_blocking_rules should include both rules
        all_rule_ids = {r["rule_id"] for b in trends for r in b["top_blocking_rules"]}
        assert "missing_output" in all_rule_ids
        assert "safety_finding" in all_rule_ids

    def test_empty_tenant_returns_empty(self, sqlite_store):
        assert sqlite_store.gate_trends("", weeks=8) == []

    def test_no_data_returns_empty(self, sqlite_store):
        assert sqlite_store.gate_trends("tenant-none", weeks=8) == []


# ─────────────────────────────────────────────────────────
# 5. governance_overview
# ─────────────────────────────────────────────────────────


class TestGovernanceOverview:
    def test_overview_aggregation(self, sqlite_store):
        tenant = "tenant-gov"
        _insert_session(
            sqlite_store,
            session_id="g1",
            tenant_id=tenant,
            current_state="s1_running",
            context_json={
                "safety_findings": [{"status": "open"}],
                "pending_actions": [{"status": "pending"}],
                "report_artifacts": [],
            },
        )
        _insert_session(
            sqlite_store,
            session_id="g2",
            tenant_id=tenant,
            current_state="complete",
            context_json={
                "safety_findings": [{"status": "open"}, {"status": "resolved"}],
                "pending_actions": [{"status": "resolved"}],
                "report_artifacts": [{"report_id": "r1"}],
            },
        )
        _insert_session(
            sqlite_store,
            session_id="g3",
            tenant_id=tenant,
            current_state="s2_running",
            context_json={
                "safety_findings": [],
                "pending_actions": [{"status": "pending"}, {"status": "pending"}],
                "report_artifacts": [{"report_id": "r2"}],
            },
        )

        overview = sqlite_store.governance_overview(tenant)
        assert overview["sessions_total"] == 3
        assert overview["state_distribution"]["s1_running"] == 1
        assert overview["state_distribution"]["complete"] == 1
        assert overview["state_distribution"]["s2_running"] == 1
        # g1: 1 open; g2: 1 open; g3: 0 → total 2
        assert overview["open_safety_findings"] == 2
        # g1: 1 pending; g3: 2 pending → total 3
        assert overview["pending_actions"] == 3
        # g2, g3 have report_artifacts
        assert overview["reports_exported"] == 2

    def test_risk_tier_distribution_from_eval_records(self, sqlite_store):
        tenant = "tenant-risk"
        _insert_session(
            sqlite_store,
            session_id="r1",
            tenant_id=tenant,
            current_state="init",
            context_json={},
        )
        _insert_session(
            sqlite_store,
            session_id="r2",
            tenant_id=tenant,
            current_state="init",
            context_json={},
        )
        # r1 latest eval = high, r2 latest eval = medium
        _insert_eval(
            sqlite_store,
            session_id="r1",
            tenant_id=tenant,
            stage_id=1,
            risk_tier="medium",
            passed=True,
            blocking_rule_ids=[],
            evaluated_at="2026-07-01T00:00:00",
        )
        _insert_eval(
            sqlite_store,
            session_id="r1",
            tenant_id=tenant,
            stage_id=2,
            risk_tier="high",
            passed=False,
            blocking_rule_ids=["missing_output"],
            evaluated_at="2026-07-10T00:00:00",
        )
        _insert_eval(
            sqlite_store,
            session_id="r2",
            tenant_id=tenant,
            stage_id=1,
            risk_tier="medium",
            passed=True,
            blocking_rule_ids=[],
            evaluated_at="2026-07-10T00:00:00",
        )

        overview = sqlite_store.governance_overview(tenant)
        # r1 latest → high, r2 latest → medium
        assert overview["risk_tier_distribution"].get("high") == 1
        assert overview["risk_tier_distribution"].get("medium") == 1

    def test_empty_tenant_returns_zero(self, sqlite_store):
        overview = sqlite_store.governance_overview("")
        assert overview["sessions_total"] == 0
        assert overview["state_distribution"] == {}
        assert overview["risk_tier_distribution"] == {}
        assert overview["open_safety_findings"] == 0
        assert overview["pending_actions"] == 0
        assert overview["reports_exported"] == 0


# ─────────────────────────────────────────────────────────
# 6. tenant 隔离
# ─────────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_gate_trends_tenant_isolation(self, sqlite_store):
        now = datetime.utcnow().isoformat()
        _insert_eval(
            sqlite_store,
            session_id="ta1",
            tenant_id="tenantA",
            stage_id=1,
            risk_tier="medium",
            passed=True,
            blocking_rule_ids=[],
            evaluated_at=now,
        )
        _insert_eval(
            sqlite_store,
            session_id="tb1",
            tenant_id="tenantB",
            stage_id=1,
            risk_tier="high",
            passed=False,
            blocking_rule_ids=["missing_output"],
            evaluated_at=now,
        )

        trends_a = sqlite_store.gate_trends("tenantA", weeks=8)
        assert len(trends_a) == 1
        assert trends_a[0]["evaluations"] == 1
        assert trends_a[0]["passed"] == 1

        trends_b = sqlite_store.gate_trends("tenantB", weeks=8)
        assert len(trends_b) == 1
        assert trends_b[0]["evaluations"] == 1
        assert trends_b[0]["passed"] == 0

        # Empty tenant → empty list (no cross-tenant)
        assert sqlite_store.gate_trends("", weeks=8) == []

    def test_governance_overview_tenant_isolation(self, sqlite_store):
        _insert_session(
            sqlite_store,
            session_id="ta-gov",
            tenant_id="tenantA",
            current_state="init",
            context_json={"pending_actions": [{"status": "pending"}]},
        )
        _insert_session(
            sqlite_store,
            session_id="tb-gov",
            tenant_id="tenantB",
            current_state="init",
            context_json={"pending_actions": [{"status": "pending"}]},
        )

        overview_a = sqlite_store.governance_overview("tenantA")
        assert overview_a["sessions_total"] == 1
        assert overview_a["pending_actions"] == 1

        overview_empty = sqlite_store.governance_overview("")
        assert overview_empty["sessions_total"] == 0

    def test_actions_backlog_tenant_isolation(self, sqlite_store):
        _insert_session(
            sqlite_store,
            session_id="ta-act",
            tenant_id="tenantA",
            current_state="init",
            context_json={
                "pending_actions": [
                    {
                        "action_id": "a-ta",
                        "title": "TA action",
                        "risk_level": "high",
                        "status": "pending",
                        "stage_id": 1,
                        "created_at": "2026-07-10T00:00:00",
                    }
                ]
            },
        )
        _insert_session(
            sqlite_store,
            session_id="tb-act",
            tenant_id="tenantB",
            current_state="init",
            context_json={
                "pending_actions": [
                    {
                        "action_id": "a-tb",
                        "title": "TB action",
                        "risk_level": "high",
                        "status": "pending",
                        "stage_id": 1,
                        "created_at": "2026-07-10T00:00:00",
                    }
                ]
            },
        )

        backlog_a = sqlite_store.actions_backlog("tenantA")
        assert len(backlog_a) == 1
        assert backlog_a[0]["action_id"] == "a-ta"

        assert sqlite_store.actions_backlog("") == []


# ─────────────────────────────────────────────────────────
# 7. actions_backlog
# ─────────────────────────────────────────────────────────


class TestActionsBacklog:
    def test_sorted_by_risk_level(self, sqlite_store):
        tenant = "tenant-backlog"
        _insert_session(
            sqlite_store,
            session_id="b1",
            tenant_id=tenant,
            current_state="s1_running",
            context_json={
                "pending_actions": [
                    {
                        "action_id": "a1",
                        "title": "low action",
                        "risk_level": "low",
                        "status": "pending",
                        "stage_id": 1,
                        "created_at": "2026-07-10T00:00:00",
                    },
                    {
                        "action_id": "a2",
                        "title": "critical action",
                        "risk_level": "critical",
                        "status": "pending",
                        "stage_id": 1,
                        "created_at": "2026-07-12T00:00:00",
                    },
                    {
                        "action_id": "a3",
                        "title": "resolved action",
                        "risk_level": "high",
                        "status": "resolved",
                        "stage_id": 1,
                        "created_at": "2026-07-11T00:00:00",
                    },
                ]
            },
        )
        _insert_session(
            sqlite_store,
            session_id="b2",
            tenant_id=tenant,
            current_state="s2_running",
            context_json={
                "pending_actions": [
                    {
                        "action_id": "a4",
                        "title": "high action",
                        "risk_level": "high",
                        "status": "pending",
                        "stage_id": 2,
                        "created_at": "2026-07-09T00:00:00",
                    }
                ]
            },
        )

        backlog = sqlite_store.actions_backlog(tenant, limit=50)
        # a3 is resolved → excluded; 3 pending actions
        assert len(backlog) == 3
        # Sorted: critical (a2) > high (a4) > low (a1)
        assert backlog[0]["action_id"] == "a2"
        assert backlog[0]["risk_level"] == "critical"
        assert backlog[1]["action_id"] == "a4"
        assert backlog[1]["risk_level"] == "high"
        assert backlog[2]["action_id"] == "a1"
        assert backlog[2]["risk_level"] == "low"

    def test_limit_applied(self, sqlite_store):
        tenant = "tenant-limit"
        actions = []
        for i in range(10):
            actions.append(
                {
                    "action_id": f"act-{i}",
                    "title": f"action {i}",
                    "risk_level": "medium",
                    "status": "pending",
                    "stage_id": 1,
                    "created_at": "2026-07-10T00:00:00",
                }
            )
        _insert_session(
            sqlite_store,
            session_id="lim1",
            tenant_id=tenant,
            current_state="init",
            context_json={"pending_actions": actions},
        )
        backlog = sqlite_store.actions_backlog(tenant, limit=5)
        assert len(backlog) == 5

    def test_empty_tenant_returns_empty(self, sqlite_store):
        assert sqlite_store.actions_backlog("") == []
