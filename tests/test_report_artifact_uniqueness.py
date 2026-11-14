# tests/test_report_artifact_uniqueness.py
"""Report generation must append exactly one unique artifact per invocation."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from core.approval_service import build_approval_summary
from core.models import ProjectContext, ReportArtifact
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "report-unique-tenant"


@contextmanager
def _service(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "report_unique.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService(), store


def test_one_report_generation_appends_one_unique_id(tmp_path):
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT, research_target="report uniqueness")
        store.create(ctx)

        first = svc.create_report_artifact(ctx.session_id, tenant_id=_TENANT)
        report_id = first["report_id"]

        reloaded = store.load(ctx.session_id, _TENANT)
        assert reloaded is not None
        ids = [artifact.report_id for artifact in reloaded.report_artifacts]
        assert ids == [report_id]

        projection = store.list_report_artifacts(ctx.session_id)
        assert [item["report_id"] for item in projection] == [report_id]

        api_rows = svc.list_report_artifacts(ctx.session_id, tenant_id=_TENANT)
        assert [row["report_id"] for row in api_rows] == [report_id]

        summary = build_approval_summary(reloaded)
        assert summary["report_generation"]["artifact_count"] == 1

        with store._get_conn() as conn:  # noqa: SLF001
            db_count = conn.execute(
                "SELECT COUNT(*) AS n FROM report_artifacts WHERE session_id=?",
                (ctx.session_id,),
            ).fetchone()["n"]
            distinct_count = conn.execute(
                "SELECT COUNT(DISTINCT report_id) AS n FROM report_artifacts WHERE session_id=?",
                (ctx.session_id,),
            ).fetchone()["n"]
        assert db_count == 1
        assert distinct_count == 1


def test_two_report_generations_create_two_distinct_ids(tmp_path):
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        store.create(ctx)

        first = svc.create_report_artifact(ctx.session_id, tenant_id=_TENANT)
        second = svc.create_report_artifact(ctx.session_id, tenant_id=_TENANT)

        reloaded = store.load(ctx.session_id, _TENANT)
        assert reloaded is not None
        ids = [artifact.report_id for artifact in reloaded.report_artifacts]
        assert len(ids) == 2
        assert len(set(ids)) == 2
        assert first["report_id"] != second["report_id"]


def test_context_validator_dedupes_historical_duplicates():
    duplicate = ReportArtifact(session_id="s-1", version="1")
    ctx = ProjectContext(
        session_id="s-1",
        report_artifacts=[duplicate, duplicate.model_copy(deep=True)],
    )
    assert [artifact.report_id for artifact in ctx.report_artifacts] == [duplicate.report_id]
