# api/routers/governance.py
"""Organization-level governance read-only API (spec §4.1).

三个只读端点，viewer 可读——治理透明度本身是价值，无写操作。
组织边界 = tenant；强制 WHERE tenant_id = ?，跨租户不可见。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from auth.jwt import TenantContext
from auth.permissions import Role, require_roles
from storage.session_store import session_store

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/overview")
def governance_overview(
    tenant: TenantContext = require_roles(Role.viewer, Role.editor, Role.admin),
) -> dict:
    """租户内：会话总数/状态分布/风险分布/open 发现/pending 动作/报告数。"""
    return session_store.governance_overview(tenant_id=tenant.tenant_id)


@router.get("/gate-trends")
def gate_trends(
    weeks: int = Query(8, ge=1, le=52),
    tenant: TenantContext = require_roles(Role.viewer, Role.editor, Role.admin),
) -> list[dict]:
    """按周的评估次数/通过率/Top 阻断规则（基于 gate_evaluation_records）。"""
    return session_store.gate_trends(tenant_id=tenant.tenant_id, weeks=weeks)


@router.get("/actions-backlog")
def actions_backlog(
    limit: int = Query(50, ge=1, le=200),
    tenant: TenantContext = require_roles(Role.viewer, Role.editor, Role.admin),
) -> list[dict]:
    """待处理人工动作明细，按 risk_level 与等待时长排序。"""
    return session_store.actions_backlog(tenant_id=tenant.tenant_id, limit=limit)
