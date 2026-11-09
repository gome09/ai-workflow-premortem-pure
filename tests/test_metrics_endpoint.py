# tests/test_metrics_endpoint.py
"""Governance metrics must be DB-backed, zero-clearing and worker-consistent."""

from __future__ import annotations

from pathlib import Path

import yaml

from api import metrics


def _family_values(families, name: str) -> dict[tuple, float]:
    for family in families:
        if family.name == name:
            return {tuple(sorted(sample.labels.items())): sample.value for sample in family.samples}
    return {}


def test_collector_yields_zero_for_known_empty_labels(monkeypatch):
    monkeypatch.setattr(
        metrics,
        "_governance_metrics_data",
        lambda: {
            "state_distribution": {"init": 2},
            "pending_actions_by_risk": {},
        },
    )
    families = list(metrics.GovernanceMetricsCollector().collect())

    sessions = _family_values(families, "premortem_sessions_total")
    assert sessions[(("state", "init"), ("tenant", "all"))] == 2
    assert sessions[(("state", "complete"), ("tenant", "all"))] == 0

    pending = _family_values(families, "premortem_pending_actions")
    assert pending[(("risk_level", "high"),)] == 0


def test_two_workers_render_same_governance_values(monkeypatch):
    monkeypatch.setattr(
        metrics,
        "_governance_metrics_data",
        lambda: {
            "state_distribution": {"init": 1, "complete": 3},
            "pending_actions_by_risk": {"high": 2},
        },
    )
    first = list(metrics.GovernanceMetricsCollector().collect())
    second = list(metrics.GovernanceMetricsCollector().collect())
    assert _family_values(first, "premortem_sessions_total") == _family_values(
        second, "premortem_sessions_total"
    )
    assert _family_values(first, "premortem_pending_actions") == _family_values(
        second, "premortem_pending_actions"
    )


def test_render_metrics_contains_governance_gauges(monkeypatch):
    monkeypatch.setattr(
        metrics,
        "_governance_metrics_data",
        lambda: {"state_distribution": {}, "pending_actions_by_risk": {}},
    )
    payload = metrics.render_metrics().decode("utf-8")
    assert "premortem_sessions_total" in payload
    assert "premortem_pending_actions" in payload


def test_refresh_gauge_metrics_clears_stale_values(monkeypatch):
    monkeypatch.setattr(
        metrics,
        "_governance_metrics_data",
        lambda: {"state_distribution": {"init": 1}, "pending_actions_by_risk": {}},
    )
    metrics.refresh_gauge_metrics(tenant_name="t1")
    assert metrics.premortem_sessions_total.labels(tenant="t1", state="init")._value.get() == 1
    assert metrics.premortem_pending_actions.labels(risk_level="high")._value.get() == 0


def test_alert_rules_are_valid_and_cover_critical_failures():
    path = Path(__file__).resolve().parent.parent / "monitoring" / "alert_rules.yml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = [rule for group in payload["groups"] for rule in group["rules"]]
    names = {rule["alert"] for rule in rules}
    assert {
        "PremortemLLMFailures",
        "PremortemStructuredOutputFailures",
        "PremortemReleaseGateUnavailable",
        "PremortemRetentionErrors",
        "PremortemTargetExecutionFailures",
        "PremortemMetricsCollectorErrors",
    }.issubset(names)
    assert all(rule.get("expr") for rule in rules)
