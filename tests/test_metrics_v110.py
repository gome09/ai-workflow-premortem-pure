"""T3.5 业务指标接入 Prometheus 契约测试。

覆盖：
- api.metrics 可正常 import（prometheus_client 可用，传递依赖）
- Counter/Gauge 注册不重复（多次 import 不报错）
- record_gate_evaluation_metrics 打点正确（passed / blocked + rule_id）
- record_llm_usage 打点正确（call_count / token）
- refresh_gauge_metrics 不抛异常（即使 session_store 未初始化）
- Grafana governance-overview.json 合法且含 4 个 panel
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────


def _get_counter_value(metric, **labels) -> float:
    """通过 collect() 读取带标签 Counter 的当前值（兼容 prometheus_client 各版本）。"""
    for family in metric.collect():
        for sample in family.samples:
            if sample.labels == labels:
                return float(sample.value)
    return 0.0


# ─────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────


def test_metrics_module_importable() -> None:
    """api.metrics 可正常 import（prometheus_client 可用）。"""
    import api.metrics as metrics_mod

    assert hasattr(metrics_mod, "premortem_sessions_total")
    assert hasattr(metrics_mod, "premortem_gate_evaluations_total")
    assert hasattr(metrics_mod, "premortem_gate_blocked_total")
    assert hasattr(metrics_mod, "premortem_pending_actions")
    assert hasattr(metrics_mod, "premortem_llm_calls_total")
    assert hasattr(metrics_mod, "premortem_llm_tokens_total")
    assert callable(metrics_mod.record_gate_evaluation_metrics)
    assert callable(metrics_mod.record_llm_usage)
    assert callable(metrics_mod.refresh_gauge_metrics)


def test_repeated_import_no_duplicate_error() -> None:
    """多次 import 不报错（Python 模块缓存保证，不重新执行 Counter 注册）。"""
    import api.metrics as m1
    import api.metrics as m2

    # sys.modules 缓存保证两次 import 返回同一模块对象
    assert m1 is m2
    # 引用同一 Counter 对象，确认未发生重复注册
    assert m1.premortem_gate_evaluations_total is m2.premortem_gate_evaluations_total
    assert m1.premortem_llm_calls_total is m2.premortem_llm_calls_total


def test_record_gate_evaluation_passed() -> None:
    """passed=True 时 evaluations_total{result=passed} 递增。"""
    from api.metrics import premortem_gate_evaluations_total, record_gate_evaluation_metrics

    before = _get_counter_value(premortem_gate_evaluations_total, result="passed")
    record_gate_evaluation_metrics(passed=True, blocking_rule_ids=[])
    after = _get_counter_value(premortem_gate_evaluations_total, result="passed")
    assert after == before + 1.0


def test_record_gate_evaluation_blocked() -> None:
    """passed=False 时 evaluations_total{result=blocked} 递增且 blocked_total{rule_id} 递增。"""
    from api.metrics import (
        premortem_gate_blocked_total,
        premortem_gate_evaluations_total,
        record_gate_evaluation_metrics,
    )

    rule_id = "missing_output"
    before_eval = _get_counter_value(premortem_gate_evaluations_total, result="blocked")
    before_block = _get_counter_value(premortem_gate_blocked_total, rule_id=rule_id)

    record_gate_evaluation_metrics(passed=False, blocking_rule_ids=[rule_id])

    after_eval = _get_counter_value(premortem_gate_evaluations_total, result="blocked")
    after_block = _get_counter_value(premortem_gate_blocked_total, rule_id=rule_id)
    assert after_eval == before_eval + 1.0
    assert after_block == before_block + 1.0


def test_record_gate_evaluation_blocked_multiple_rules() -> None:
    """一次评估多个阻断规则 ID 时每个 rule_id 计数递增一次。"""
    from api.metrics import premortem_gate_blocked_total, record_gate_evaluation_metrics

    rule_ids = ["rule_a", "rule_b", "rule_c"]
    before_values = {
        rid: _get_counter_value(premortem_gate_blocked_total, rule_id=rid) for rid in rule_ids
    }
    record_gate_evaluation_metrics(passed=False, blocking_rule_ids=rule_ids)
    for rid in rule_ids:
        after = _get_counter_value(premortem_gate_blocked_total, rule_id=rid)
        assert after == before_values[rid] + 1.0


def test_record_llm_usage_call_count() -> None:
    """record_llm_usage(call_count_delta=1) 后 llm_calls_total 递增。"""
    from api.metrics import premortem_llm_calls_total, record_llm_usage

    before = _get_counter_value(premortem_llm_calls_total)
    record_llm_usage(call_count_delta=1)
    after = _get_counter_value(premortem_llm_calls_total)
    assert after == before + 1.0


def test_record_llm_usage_tokens() -> None:
    """record_llm_usage(token_delta=N) 后 llm_tokens_total 递增 N。"""
    from api.metrics import premortem_llm_tokens_total, record_llm_usage

    delta = 42
    before = _get_counter_value(premortem_llm_tokens_total)
    record_llm_usage(call_count_delta=0, token_delta=delta)
    after = _get_counter_value(premortem_llm_tokens_total)
    assert after == before + float(delta)


def test_record_llm_usage_zero_deltas_idempotent() -> None:
    """call_count_delta=0 + token_delta=0 时计数器不变。"""
    from api.metrics import premortem_llm_calls_total, premortem_llm_tokens_total, record_llm_usage

    before_calls = _get_counter_value(premortem_llm_calls_total)
    before_tokens = _get_counter_value(premortem_llm_tokens_total)
    record_llm_usage(call_count_delta=0, token_delta=0)
    assert _get_counter_value(premortem_llm_calls_total) == before_calls
    assert _get_counter_value(premortem_llm_tokens_total) == before_tokens


def test_refresh_gauge_metrics_no_raise_when_store_uninitialized() -> None:
    """refresh_gauge_metrics() 不抛异常（即使 session_store 未初始化或返回空）。"""
    from api.metrics import refresh_gauge_metrics

    # 不应抛异常；函数内部 try/except 兜底
    refresh_gauge_metrics()
    refresh_gauge_metrics(tenant_name="test-tenant")


def test_refresh_gauge_metrics_with_mocked_store() -> None:
    """refresh_gauge_metrics 在 governance_overview 返回有效数据时正确设置 Gauge。"""
    from api.metrics import (
        premortem_pending_actions,
        premortem_sessions_total,
        refresh_gauge_metrics,
    )

    class _FakeStore:
        def governance_overview(self, tenant_id: str) -> dict:
            return {
                "state_distribution": {"stage_1": 3, "stage_2": 5},
                "risk_tier_distribution": {"high": 2, "medium": 4},
                "sessions_total": 8,
                "open_safety_findings": 0,
                "pending_actions": 6,
                "reports_exported": 0,
            }

    import storage.session_store as session_store_mod

    original = session_store_mod.session_store
    session_store_mod.session_store = _FakeStore()  # type: ignore[assignment]
    try:
        refresh_gauge_metrics(tenant_name="acme")
        assert _get_counter_value(premortem_sessions_total, tenant="acme", state="stage_1") == 3.0
        assert _get_counter_value(premortem_sessions_total, tenant="acme", state="stage_2") == 5.0
        assert _get_counter_value(premortem_pending_actions, risk_level="high") == 2.0
        assert _get_counter_value(premortem_pending_actions, risk_level="medium") == 4.0
    finally:
        session_store_mod.session_store = original  # type: ignore[assignment]


def test_grafana_dashboard_json_valid() -> None:
    """Grafana governance-overview.json 合法且结构符合预期。"""
    p = (
        Path(__file__).resolve().parent.parent
        / "monitoring"
        / "grafana"
        / "dashboards"
        / "governance-overview.json"
    )
    assert p.exists(), f"dashboard json not found: {p}"
    data = json.loads(p.read_text(encoding="utf-8"))

    assert data["uid"] == "governance-overview"
    assert data["title"] == "Premortem Governance Overview"
    assert data["schemaVersion"] >= 27
    assert isinstance(data["panels"], list)
    assert len(data["panels"]) == 4

    titles = {panel["title"] for panel in data["panels"]}
    assert "Gate Pass Rate (1h)" in titles
    assert "Top Blocking Rules (24h)" in titles
    assert "Pending Human Actions by Risk Level" in titles
    assert "LLM Usage (calls + tokens / 5m)" in titles

    # 每个 panel 都引用 prometheus 数据源
    for panel in data["panels"]:
        assert panel["datasource"]["type"] == "prometheus"
        assert panel["targets"], f"panel {panel['title']} has no targets"


@pytest.mark.parametrize(
    "expr_fragment",
    [
        "premortem_gate_evaluations_total",
        "premortem_gate_blocked_total",
        "premortem_pending_actions",
        "premortem_llm_calls_total",
        "premortem_llm_tokens_total",
    ],
)
def test_grafana_panels_reference_premortem_metrics(expr_fragment: str) -> None:
    """4 个 panel 的 PromQL 表达式覆盖所有 premortem_* 指标族。"""
    p = (
        Path(__file__).resolve().parent.parent
        / "monitoring"
        / "grafana"
        / "dashboards"
        / "governance-overview.json"
    )
    data = json.loads(p.read_text(encoding="utf-8"))
    all_exprs = "\n".join(
        t.get("expr", "") for panel in data["panels"] for t in panel.get("targets", [])
    )
    assert expr_fragment in all_exprs, f"metric {expr_fragment} not referenced in any panel"
