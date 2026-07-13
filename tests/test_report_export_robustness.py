"""Regression tests for report export robustness.

Covers edge cases that previously caused IndexError or other failures
during report generation:
- Empty current_required_operations list (complete session)
- Empty/missing stage outputs
- Empty/missing report artifacts
- Empty/missing eval cases, safety findings, evidence sources

These tests do NOT modify Stage 1–4 business logic.
"""

from unittest.mock import patch

from core.models import ProjectContext, SessionState
from core.report_service import build_report_dict


class TestReportExportRobustness:
    """build_report_dict must not raise on empty/missing data."""

    def test_default_context_does_not_raise(self) -> None:
        """A bare ProjectContext() with all defaults must produce a valid report."""
        ctx = ProjectContext()
        report = build_report_dict(ctx)
        assert isinstance(report, dict)
        assert report["session_id"] == ctx.session_id

    def test_complete_state_empty_operations(self) -> None:
        """Session in COMPLETE state has no actionable stages → empty
        current_required_operations.  Must not raise IndexError (the
        original bug: dict.get(key, [None])[0] on empty list)."""
        ctx = ProjectContext(current_state=SessionState.COMPLETE)
        # Must not raise IndexError — this was the original crash
        report = build_report_dict(ctx)
        assert "next_required_operation" in report

    def test_empty_stage_outputs(self) -> None:
        """All stage outputs are None (default). Report must still render."""
        ctx = ProjectContext()
        assert ctx.stage_1_output is None
        assert ctx.stage_2_output is None
        assert ctx.stage_3_output is None
        assert ctx.stage_4_output is None
        report = build_report_dict(ctx)
        ai = report["ai_generated"]
        assert ai["stage_1"] is None
        assert ai["stage_2"] is None
        assert ai["stage_3"] is None
        assert ai["stage_4"] is None

    def test_empty_all_lists(self) -> None:
        """Explicitly empty all list fields. Must not raise."""
        ctx = ProjectContext(
            user_materials=[],
            flagged_items=[],
            pending_actions=[],
            audit_events=[],
            evidence_sources=[],
            safety_findings=[],
            report_artifacts=[],
            eval_cases=[],
            eval_runs=[],
            eval_judgments=[],
            human_calibrations=[],
            eval_datasets=[],
            eval_experiments=[],
            redteam_cases=[],
            interrupt_records=[],
        )
        report = build_report_dict(ctx)
        assert report["eval_cases"] == []
        assert report["safety_findings"] == []
        assert report["evidence_sources"] == []
        assert report["open_actions"] == []
        assert report["resolved_actions"] == []

    def test_report_has_required_keys(self) -> None:
        """Report must contain all top-level keys expected by frontend/API."""
        ctx = ProjectContext()
        report = build_report_dict(ctx)
        required_keys = [
            "schema_version",
            "generated_at",
            "session_id",
            "current_state",
            "project_info",
            "ai_generated",
            "stage_readiness",
            "stage_resolution_summary",
            "next_required_operation",
            "report_export_status",
            "stage_advancement_summary",
            "unresolved_governance_items",
        ]
        for key in required_keys:
            assert key in report, f"Missing required key: {key}"

    def test_report_schema_version(self) -> None:
        """Report schema version must match current version."""
        ctx = ProjectContext()
        report = build_report_dict(ctx)
        assert report["schema_version"] is not None
        assert isinstance(report["schema_version"], str)

    def test_empty_current_required_operations_no_index_error(self) -> None:
        """Directly test the IndexError fix: when stage_resolution_summary
        returns current_required_operations=[], the old code did
        dict.get(key, [None])[0] which raised IndexError because
        .get() returns [] (not the default) when the key exists.

        The fix uses `or [None]` to handle the empty-list case.
        """
        fake_summary = {
            "by_stage": {},
            "current_stage_id": None,
            "actionable_stage_ids": [],
            "future_stage_placeholders": [],
            "total_operations": 0,
            "hard_blockers_count": 0,
            "overridable_blockers_count": 0,
            "executable_operations_count": 0,
            "hard_blockers": [],
            "overridable_blockers": [],
            "current_required_operations": [],  # <-- the empty list that caused the crash
        }
        ctx = ProjectContext()
        with patch(
            "core.report_service.build_stage_resolution_summary",
            return_value=fake_summary,
        ):
            # This was the exact crash path — must not raise IndexError
            report = build_report_dict(ctx)
        assert report["next_required_operation"] is None
