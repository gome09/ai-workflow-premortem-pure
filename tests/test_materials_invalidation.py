# tests/test_materials_invalidation.py
"""Material changes invalidate stage analyses and block re-approval."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.approval_service import (
    ReleaseApprovalPrerequisiteError,
    build_release_readiness,
    request_release_approval,
)
from core.models import (
    ProjectContext,
    SessionState,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
)
from core.session_service import SessionService
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "materials-tenant"
_CREATOR = "creator-user"
_REVIEWER = "reviewer-admin"


def _complete_ctx() -> ProjectContext:
    ctx = ProjectContext(
        tenant_id=_TENANT,
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions",
        created_by=_CREATOR,
        data_classification="business_internal",
    )
    ctx.current_state = SessionState.COMPLETE
    ctx.stage_1_output = Stage1Output()
    ctx.stage_2_output = Stage2Output()
    ctx.stage_3_output = Stage3Output()
    ctx.stage_4_output = Stage4Output()
    ctx.stage_output_versions = {"stage_1": 1, "stage_2": 1, "stage_3": 1, "stage_4": 1}
    return ctx


@pytest.fixture
def service(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "materials.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService(), store


def test_material_change_resets_workflow_and_marks_all_stages_stale(service):
    svc, store = service
    ctx = _complete_ctx()
    store.save(ctx)

    result = svc.add_materials(
        ctx.session_id, ["新增需求材料：需要支持多轮追问"], tenant_id=_TENANT
    )

    assert result["ok"] is True
    reloaded = store.load(ctx.session_id, _TENANT)
    assert reloaded is not None
    assert reloaded.current_state == SessionState.S1_RUNNING
    assert set(reloaded.stage_staleness) == {"stage_1", "stage_2", "stage_3", "stage_4"}
    assert all(meta.get("stale") for meta in reloaded.stage_staleness.values())
    assert reloaded.input_versions["materials"] == 1

    readiness = build_release_readiness(reloaded)
    codes = {blocker.code for blocker in readiness.blockers}
    assert "evaluation_not_completed" in codes
    assert "stale_stage" in codes
    assert readiness.can_approve is False

    with pytest.raises(ReleaseApprovalPrerequisiteError):
        request_release_approval(
            reloaded,
            decision="approve",
            note="cannot approve before re-evaluation",
            actor_id=_REVIEWER,
            actor_role="admin",
        )


def test_clearing_stale_flags_alone_does_not_restore_approvability(service):
    """手工清除 stale 也不能绕过：旧目标测试证据仍绑定旧评估版本。"""
    svc, store = service
    ctx = _complete_ctx()
    store.save(ctx)
    svc.add_materials(ctx.session_id, ["another material"], tenant_id=_TENANT)

    reloaded = store.load(ctx.session_id, _TENANT)
    assert reloaded is not None
    reloaded.current_state = SessionState.COMPLETE
    reloaded.stage_staleness.clear()

    readiness = build_release_readiness(reloaded)
    assert readiness.can_approve is False
    assert readiness.checks["release_batch_complete"] is False
