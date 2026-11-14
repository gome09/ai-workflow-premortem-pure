"""报告列表契约：投影与上下文回退都必须按生成时间降序。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from core.models import ProjectContext, ReportArtifact
from core.services.session_workflow import SessionWorkflowService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "report-tenant"


def _ctx_with_reports(count: int = 25) -> ProjectContext:
    ctx = ProjectContext(tenant_id=_TENANT, research_target="目标", domain="领域", goal="目标")
    base = datetime(2026, 1, 1, 0, 0, 0)
    for index in range(count):
        ctx.report_artifacts.append(
            ReportArtifact(
                session_id=ctx.session_id,
                version=f"v{index + 1}",
                generated_at=base + timedelta(minutes=index),
                content_markdown=f"report {index + 1}",
            )
        )
    return ctx


def _store(tmp_path) -> SQLiteSessionStore:
    store = SQLiteSessionStore(str(tmp_path / "reports.db"))
    store.initialize()
    return store


def test_context_fallback_returns_newest_first(tmp_path):
    store = _store(tmp_path)
    cache = MemoryCache(ttl_seconds=3600)
    ctx = _ctx_with_reports()
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        store.create(ctx)
        with patch.object(store, "list_report_artifacts", side_effect=RuntimeError("no table")):
            rows = SessionWorkflowService().list_report_artifacts(ctx.session_id, tenant_id=_TENANT)

    assert len(rows) == 25
    assert rows[0]["version"] == "v25"
    assert rows[-1]["version"] == "v1"
    generated = [row["generated_at"] for row in rows]
    assert generated == sorted(generated, reverse=True)


def test_projection_returns_newest_first(tmp_path):
    store = _store(tmp_path)
    ctx = _ctx_with_reports()
    store.create(ctx)
    rows = store.list_report_artifacts(ctx.session_id)
    assert [row["version"] for row in rows[:2]] == ["v25", "v24"]
    assert rows[-1]["version"] == "v1"


def test_equal_timestamps_are_stable_by_report_id(tmp_path):
    store = _store(tmp_path)
    cache = MemoryCache(ttl_seconds=3600)
    ctx = ProjectContext(tenant_id=_TENANT, research_target="目标", domain="领域", goal="目标")
    same_time = datetime(2026, 2, 1, 0, 0, 0)
    ctx.report_artifacts.extend(
        [
            ReportArtifact(
                report_id="RPT-A",
                session_id=ctx.session_id,
                version="vA",
                generated_at=same_time,
            ),
            ReportArtifact(
                report_id="RPT-B",
                session_id=ctx.session_id,
                version="vB",
                generated_at=same_time,
            ),
        ]
    )
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        store.create(ctx)
        with patch.object(store, "list_report_artifacts", side_effect=RuntimeError("no table")):
            rows = SessionWorkflowService().list_report_artifacts(ctx.session_id, tenant_id=_TENANT)

    assert [row["report_id"] for row in rows] == ["RPT-B", "RPT-A"]


def test_frontend_report_selector_consumes_desc_order_with_paging():
    source = (
        Path(__file__).resolve().parent.parent
        / "frontend"
        / "views"
        / "panels"
        / "report_workspace.py"
    ).read_text(encoding="utf-8")
    assert "list_report_artifacts_checked(" in source
    assert "reversed(artifacts[-20:])" not in source
    assert "artifacts[:limit]" in source
    assert "最新在前" in source
    assert "显示更多（+20）" in source


def test_frontend_calibration_can_reach_all_target_runs():
    source = (
        Path(__file__).resolve().parent.parent / "frontend" / "views" / "panels" / "eval_panels.py"
    ).read_text(encoding="utf-8")
    assert "target_runs[-20:]" not in source
    assert "list_eval_runs_checked(" in source
    assert "calibration_batch_filter" in source
    assert "calibration_run_keyword" in source
    assert "calibration_limit" in source
    assert "显示更多（+20）" in source
