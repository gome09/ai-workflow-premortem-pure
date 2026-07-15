# tests/test_gate_report.py
"""Tests for Task E2: Gate Decision Path Visualisation.

≥ 15 tests covering:
- RuleDetail model validation
- GateReportSummary model validation
- GateReport model validation
- build_report() helper
- evaluate_stage_gate(detailed=False) — backward compat
- evaluate_stage_gate(detailed=True) — report attached
- GateReport.overall matches gate result
- Rules list non-empty after evaluation
- Per-rule status values
- API endpoint 404 for nonexistent session
- API endpoint returns GateReport JSON for valid session
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

# ─────────────────────────────────────────────────────────
# Model tests
# ─────────────────────────────────────────────────────────


class TestRuleDetailModel:
    def test_required_fields_pass_status(self):
        from core.gates.report import RuleDetail

        r = RuleDetail(rule_id="missing_output", display_name="Missing Output", status="passed")
        assert r.rule_id == "missing_output"
        assert r.display_name == "Missing Output"
        assert r.status == "passed"
        assert r.severity is None
        assert r.reason is None
        assert r.skipped_reason is None

    def test_required_fields_blocked_status(self):
        from core.gates.report import RuleDetail

        r = RuleDetail(
            rule_id="safety_finding",
            display_name="Safety Finding",
            status="blocked",
            severity="high",
            reason="Critical safety issue unresolved.",
        )
        assert r.status == "blocked"
        assert r.severity == "high"
        assert r.reason == "Critical safety issue unresolved."

    def test_skipped_status_with_reason(self):
        from core.gates.report import RuleDetail

        r = RuleDetail(
            rule_id="redteam_coverage",
            display_name="Red-Team Coverage",
            status="skipped",
            skipped_reason="Rule does not apply to stage 1.",
        )
        assert r.status == "skipped"
        assert r.skipped_reason == "Rule does not apply to stage 1."

    def test_invalid_status_raises(self):
        from pydantic import ValidationError

        from core.gates.report import RuleDetail

        with pytest.raises(ValidationError):
            RuleDetail(rule_id="x", display_name="X", status="unknown_status")

    def test_invalid_severity_raises(self):
        from pydantic import ValidationError

        from core.gates.report import RuleDetail

        with pytest.raises(ValidationError):
            RuleDetail(
                rule_id="x",
                display_name="X",
                status="passed",
                severity="extreme",  # not in Literal
            )


class TestGateReportSummaryModel:
    def test_summary_counts(self):
        from core.gates.report import GateReportSummary

        s = GateReportSummary(total=10, passed=7, blocked=2, skipped=1)
        assert s.total == 10
        assert s.passed == 7
        assert s.blocked == 2
        assert s.skipped == 1

    def test_summary_zero_counts(self):
        from core.gates.report import GateReportSummary

        s = GateReportSummary(total=0, passed=0, blocked=0, skipped=0)
        assert s.total == 0


class TestGateReportModel:
    def _make_report(self, overall="passed"):
        from datetime import datetime

        from core.gates.report import GateReport, GateReportSummary, RuleDetail

        return GateReport(
            session_id="sess-abc",
            stage=2,
            risk_profile="medium",
            overall=overall,
            evaluated_at=datetime.now(tz=UTC),
            rules=[
                RuleDetail(rule_id="missing_output", display_name="Missing Output", status="passed")
            ],
            summary=GateReportSummary(total=1, passed=1, blocked=0, skipped=0),
        )

    def test_gate_report_fields(self):
        report = self._make_report("passed")
        assert report.session_id == "sess-abc"
        assert report.stage == 2
        assert report.risk_profile == "medium"
        assert report.overall == "passed"
        assert len(report.rules) == 1

    def test_gate_report_blocked_overall(self):
        report = self._make_report("blocked")
        assert report.overall == "blocked"

    def test_gate_report_invalid_overall(self):
        from datetime import datetime

        from pydantic import ValidationError

        from core.gates.report import GateReport, GateReportSummary

        with pytest.raises(ValidationError):
            GateReport(
                session_id="x",
                stage=1,
                risk_profile="low",
                overall="partial",  # invalid
                evaluated_at=datetime.now(tz=UTC),
                rules=[],
                summary=GateReportSummary(total=0, passed=0, blocked=0, skipped=0),
            )


# ─────────────────────────────────────────────────────────
# build_report() tests
# ─────────────────────────────────────────────────────────


class TestBuildReport:
    def _make_records(self):
        from core.gates.report import _RuleEvalRecord

        return [
            _RuleEvalRecord("missing_output", "Missing Output", "passed"),
            _RuleEvalRecord(
                "safety_finding",
                "Safety Finding",
                "blocked",
                severity="high",
                reason="Open safety finding.",
            ),
            _RuleEvalRecord(
                "redteam_coverage",
                "Red-Team Coverage",
                "skipped",
                skipped_reason="Not applicable to stage 1.",
            ),
        ]

    def test_build_report_summary_counts(self):
        from core.gates.report import build_report

        records = self._make_records()
        report = build_report(
            session_id="s1",
            stage=1,
            risk_profile="medium",
            rule_records=records,
            overall_passed=False,
        )
        assert report.summary.total == 3
        assert report.summary.passed == 1
        assert report.summary.blocked == 1
        assert report.summary.skipped == 1

    def test_build_report_overall_matches_arg(self):
        from core.gates.report import build_report

        report_pass = build_report(
            session_id="s1",
            stage=1,
            risk_profile="low",
            rule_records=[],
            overall_passed=True,
        )
        assert report_pass.overall == "passed"

        report_block = build_report(
            session_id="s1",
            stage=1,
            risk_profile="low",
            rule_records=[],
            overall_passed=False,
        )
        assert report_block.overall == "blocked"

    def test_build_report_evaluated_at_defaults_to_now(self):
        from core.gates.report import build_report

        before = datetime.now(tz=UTC)
        report = build_report(
            session_id="s",
            stage=2,
            risk_profile="high",
            rule_records=[],
            overall_passed=True,
        )
        after = datetime.now(tz=UTC)
        assert before <= report.evaluated_at <= after

    def test_build_report_rules_list_populated(self):
        from core.gates.report import build_report

        records = self._make_records()
        report = build_report(
            session_id="s",
            stage=1,
            risk_profile="medium",
            rule_records=records,
            overall_passed=False,
        )
        assert len(report.rules) == 3
        statuses = {r.status for r in report.rules}
        assert statuses == {"passed", "blocked", "skipped"}


# ─────────────────────────────────────────────────────────
# evaluate_stage_gate() tests
# ─────────────────────────────────────────────────────────


class TestEvaluateStageGate:
    def _empty_ctx(self):
        from core.models import ProjectContext

        return ProjectContext()

    def test_detailed_false_no_report(self):
        """detailed=False (default) must NOT attach a real GateReport."""
        from core.gates.engine import evaluate_stage_gate

        ctx = self._empty_ctx()
        result = evaluate_stage_gate(ctx, 1, detailed=False)
        # report should be None when detailed=False
        assert result.__dict__.get("report") is None

    def test_detailed_true_returns_gate_report(self):
        """detailed=True attaches a GateReport to result.__dict__['report']."""
        from core.gates.engine import evaluate_stage_gate
        from core.gates.report import GateReport

        ctx = self._empty_ctx()
        result = evaluate_stage_gate(ctx, 1, detailed=True)
        report = result.__dict__.get("report")
        assert isinstance(report, GateReport)

    def test_detailed_true_overall_matches_can_continue(self):
        """GateReport.overall must agree with StageGateResult.can_continue."""
        from core.gates.engine import evaluate_stage_gate

        ctx = self._empty_ctx()
        result = evaluate_stage_gate(ctx, 1, detailed=True)
        report = result.__dict__["report"]

        expected_overall = "passed" if result.can_continue else "blocked"
        assert report.overall == expected_overall

    def test_detailed_true_rules_list_nonempty(self):
        """A real context must produce at least one rule entry."""
        from core.gates.engine import evaluate_stage_gate

        ctx = self._empty_ctx()
        result = evaluate_stage_gate(ctx, 1, detailed=True)
        report = result.__dict__["report"]
        assert len(report.rules) > 0

    def test_detailed_true_rule_statuses_are_valid(self):
        """All per-rule statuses must be one of the allowed literals."""
        from core.gates.engine import evaluate_stage_gate

        ctx = self._empty_ctx()
        result = evaluate_stage_gate(ctx, 1, detailed=True)
        report = result.__dict__["report"]
        valid_statuses = {"passed", "blocked", "skipped"}
        for rule in report.rules:
            assert rule.status in valid_statuses

    def test_detailed_false_default_gate_result_unchanged(self):
        """detailed=False must return identical StageGateResult to old code."""
        from core.gates.engine import evaluate_stage_gate

        ctx = self._empty_ctx()
        result_old = evaluate_stage_gate(ctx, 1)
        result_new = evaluate_stage_gate(ctx, 1, detailed=False)

        assert result_old.stage_id == result_new.stage_id
        assert result_old.can_continue == result_new.can_continue
        assert len(result_old.blockers) == len(result_new.blockers)

    def test_stage_out_of_range_raises(self):
        from core.gates.engine import evaluate_stage_gate

        ctx = self._empty_ctx()
        with pytest.raises(ValueError, match="stage must be 1..4"):
            evaluate_stage_gate(ctx, 0, detailed=True)


# ─────────────────────────────────────────────────────────
# API endpoint tests
# ─────────────────────────────────────────────────────────


pytest.importorskip("fastapi")
pytest.importorskip("psycopg")
pytest.importorskip("redis")
pytest.importorskip("langchain_core")
pytest.importorskip("langchain_openai")
pytest.importorskip("tavily")


@pytest.fixture
def client():
    pytest.importorskip("prometheus_fastapi_instrumentator")
    with patch("storage.session_store.session_store.initialize"):
        from fastapi.testclient import TestClient

        from api.main import app

        return TestClient(app)


@pytest.fixture
def mock_stage_service():
    with patch("api.routers.stage.session_service") as mock:
        yield mock


class TestGateReportEndpoint:
    def test_gate_report_404_for_missing_session(self, client, mock_stage_service, auth_headers):
        mock_stage_service.get_session.return_value = None

        response = client.get(
            "/sessions/nonexistent-session/gate-report?stage=1",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "Session not found" in response.json()["detail"]

    def test_gate_report_returns_json_for_valid_session(
        self, client, mock_stage_service, auth_headers
    ):
        from core.models import ProjectContext

        ctx = ProjectContext()
        ctx.research_target = "Test Project"
        mock_stage_service.get_session.return_value = ctx

        response = client.get(
            f"/sessions/{ctx.session_id}/gate-report?stage=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "overall" in data
        assert "rules" in data
        assert "summary" in data
        assert data["stage"] == 1

    def test_gate_report_response_has_risk_profile(self, client, mock_stage_service, auth_headers):
        from core.models import ProjectContext

        ctx = ProjectContext()
        mock_stage_service.get_session.return_value = ctx

        response = client.get(
            f"/sessions/{ctx.session_id}/gate-report?stage=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["risk_profile"] in {"low", "medium", "high", "critical"}

    def test_gate_report_summary_counts_consistent(self, client, mock_stage_service, auth_headers):
        from core.models import ProjectContext

        ctx = ProjectContext()
        mock_stage_service.get_session.return_value = ctx

        response = client.get(
            f"/sessions/{ctx.session_id}/gate-report?stage=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        summary = data["summary"]
        rules = data["rules"]
        assert summary["total"] == len(rules)
        assert summary["passed"] + summary["blocked"] + summary["skipped"] == summary["total"]
