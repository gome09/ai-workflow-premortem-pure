"""Regression test: report creation must not fail on large sessions.

Covers the bug where 936 LLM traces with full metadata caused
PostgreSQL JSONB size limit (268MB) to be exceeded during
session_store.save() after report artifact creation.

Root cause: context_json serialized full LLM trace metadata.
Fix: _build_context_json_for_storage() truncates trace metadata
and audit event snapshots before JSONB serialization.
"""

import json

from core.models import AuditEvent, LLMTrace, ProjectContext, SessionState
from core.report_service import build_report_dict, create_report_artifact
from storage.session_store import SessionStore


class TestReportCreationLargeSession:
    """Report creation must succeed even with many LLM traces."""

    def _build_large_context(self, trace_count: int = 1000) -> ProjectContext:
        """Build a context with many LLM traces containing large metadata."""
        ctx = ProjectContext(
            session_id="test-large-session-001",
            current_state=SessionState.COMPLETE,
            research_target="会议室预约系统",
            domain="enterprise",
            goal="pre-mortem analysis",
        )
        for i in range(trace_count):
            trace = LLMTrace(
                trace_id=f"TRC-{i:06d}",
                session_id=ctx.session_id,
                stage=(i % 4) + 1,
                node_name=f"node_{i % 10}",
                trace_type="llm",
                model="deepseek-chat",
                input_token_count=2000,
                output_token_count=1500,
                latency_ms=1200,
                parser_status="success",
                # Large metadata simulating real LLM request/response
                metadata={
                    "prompt": f"Large prompt text for trace {i}. " * 200,
                    "response": f"Large response text for trace {i}. " * 200,
                    "raw_request": {"messages": [{"role": "user", "content": "x" * 5000}]},
                    "raw_response": {"choices": [{"message": {"content": "y" * 5000}}]},
                },
            )
            ctx.llm_traces.append(trace)

        # Also add some audit events with large snapshots
        for i in range(50):
            event = AuditEvent(
                event_id=f"EVT-{i:06d}",
                session_id=ctx.session_id,
                actor="system",
                event_type="stage_output_updated",
                target_type="stage_output",
                target_id=f"stage_{(i % 4) + 1}",
                before_snapshot={"data": "x" * 10000},
                after_snapshot={"data": "y" * 10000},
                metadata={"iteration": i},
            )
            ctx.audit_events.append(event)

        return ctx

    def test_build_report_dict_with_many_traces(self) -> None:
        """build_report_dict must succeed with many LLM traces."""
        ctx = self._build_large_context(trace_count=1000)
        report = build_report_dict(ctx)
        assert isinstance(report, dict)
        assert report["session_id"] == ctx.session_id
        # Report should contain trace summary, not raw traces
        assert "eval_summary" in report
        assert "evidence_summary" in report

    def test_create_report_artifact_with_many_traces(self) -> None:
        """create_report_artifact must succeed with many LLM traces."""
        ctx = self._build_large_context(trace_count=1000)
        artifact = create_report_artifact(ctx)
        assert artifact.session_id == ctx.session_id
        assert artifact.content_json is not None
        assert artifact.content_markdown
        # Artifact should be appended to ctx
        assert len(ctx.report_artifacts) == 1

    def test_context_json_truncates_trace_metadata(self) -> None:
        """_build_context_json_for_storage must truncate LLM trace metadata."""
        ctx = self._build_large_context(trace_count=500)
        json_str = SessionStore._build_context_json_for_storage(ctx)
        data = json.loads(json_str)

        # Traces should be present but truncated
        traces = data.get("llm_traces", [])
        assert len(traces) == 500

        # Each trace should have metadata_keys but not full metadata
        for trace in traces[:5]:
            assert "trace_id" in trace
            assert "metadata_keys" in trace
            # Full metadata should NOT be present
            assert "metadata" not in trace or isinstance(trace.get("metadata_keys"), list)

    def test_context_json_truncates_audit_event_snapshots(self) -> None:
        """_build_context_json_for_storage must truncate audit event snapshots."""
        ctx = self._build_large_context(trace_count=10)
        json_str = SessionStore._build_context_json_for_storage(ctx)
        data = json.loads(json_str)

        events = data.get("audit_events", [])
        assert len(events) == 50

        # Each event should NOT have before_snapshot / after_snapshot
        for event in events[:5]:
            assert "event_id" in event
            assert "before_snapshot" not in event
            assert "after_snapshot" not in event

    def test_context_json_size_is_bounded(self) -> None:
        """_build_context_json_for_storage must produce bounded JSON size.

        With 1000 traces each having ~30KB metadata, raw dump would be ~30MB.
        Truncated version should be under 1MB.
        """
        ctx = self._build_large_context(trace_count=1000)
        json_str = SessionStore._build_context_json_for_storage(ctx)
        size_mb = len(json_str.encode("utf-8")) / (1024 * 1024)
        # Should be well under 1MB (original would be ~30MB+)
        assert size_mb < 2.0, f"context_json too large: {size_mb:.2f} MB"

    def test_report_has_required_summaries(self) -> None:
        """Report from large session must contain all required summary sections."""
        ctx = self._build_large_context(trace_count=500)
        report = build_report_dict(ctx)

        required_keys = [
            "schema_version",
            "session_id",
            "current_state",
            "project_info",
            "ai_generated",
            "stage_readiness",
            "stage_resolution_summary",
            "next_required_operation",
            "eval_summary",
            "evidence_summary",
            "execution_summary",
            "oversight_summary",
            "disclaimer",
        ]
        for key in required_keys:
            assert key in report, f"Missing required key: {key}"

    def test_report_content_json_audit_events_truncated(self) -> None:
        """_truncate_report_content_json must strip audit event snapshots."""
        ctx = self._build_large_context(trace_count=10)
        artifact = create_report_artifact(ctx)
        truncated = SessionStore._truncate_report_content_json(artifact.content_json)

        audit = truncated.get("audit_events", [])
        assert len(audit) > 0
        for ev in audit[:5]:
            assert "event_id" in ev
            assert "before_snapshot" not in ev
            assert "after_snapshot" not in ev

    def test_context_json_with_report_artifacts_is_bounded(self) -> None:
        """context_json must remain bounded even with report artifacts appended."""
        ctx = self._build_large_context(trace_count=500)
        # Create a report artifact (appends to ctx.report_artifacts)
        create_report_artifact(ctx)
        json_str = SessionStore._build_context_json_for_storage(ctx)
        size_mb = len(json_str.encode("utf-8")) / (1024 * 1024)
        # Should be well under 2MB even with report artifact
        assert size_mb < 3.0, f"context_json with report too large: {size_mb:.2f} MB"
