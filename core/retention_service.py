# core/retention_service.py
"""数据留存执行器（T1.6）。

`AUDIT_RETENTION_DAYS` / `SESSION_RETENTION_DAYS` 此前只是配置展示项，没有执行器。
本模块补齐执行闭环：

- 会话：超过 `SESSION_RETENTION_DAYS` 未更新的会话走与管理员删除一致的生命周期
  （删除 checkpoint → 归档审计 → 级联清理投影表 → 失效缓存）。0 表示永久保留。
- 审计：超过 `AUDIT_RETENTION_DAYS` 的 `audit_events` 与 `audit_events_archive`
  按批删除。0 表示永久保留。
- 默认 `RETENTION_DRY_RUN=true`，只统计候选不写库；显式关闭 dry-run 才实际删除。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.config import settings
from storage.access import SYSTEM_ACCESS

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task[None] | None = None


def _utc_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _purge_one_session(store: Any, cache: Any, session_id: str, tenant_id: str) -> None:
    """按会话删除生命周期清理单个到期会话。"""
    from graph.checkpoint_manager import delete_session_checkpoints
    from storage.backends.postgres import PostgresSessionStore

    # 历史行可能没有租户归属，此时只能显式走系统访问通道读取。
    ctx = store.load(
        session_id,
        tenant_id,
        system_access=None if tenant_id else SYSTEM_ACCESS,
    )
    if ctx is not None:
        delete_session_checkpoints(ctx, persistent=isinstance(store, PostgresSessionStore))

    summary = {
        "session_id": session_id,
        "tenant_id": tenant_id or None,
        "created_at": ctx.created_at.isoformat() if ctx is not None else None,
        "current_state": ctx.current_state.value if ctx is not None else "unknown",
        "retention_days": settings.session_retention_days,
    }
    store.purge_session(session_id, tenant_id, "retention", summary)
    cache.delete(session_id, tenant_id)


def run_retention_cycle(
    *,
    dry_run: bool | None = None,
    now: datetime | None = None,
    store: Any | None = None,
    cache: Any | None = None,
) -> dict[str, Any]:
    """执行一轮留存清理；返回结构化统计，供定时日志与手动调用复用。"""
    import storage.cache as cache_module
    import storage.session_store as session_store_module

    target_store = store or session_store_module.session_store
    target_cache = cache or cache_module.context_cache
    effective_dry_run = settings.retention_dry_run if dry_run is None else dry_run
    current = _utc_now(now)
    result: dict[str, Any] = {
        "dry_run": effective_dry_run,
        "session_retention_days": settings.session_retention_days,
        "audit_retention_days": settings.audit_retention_days,
        "sessions_matched": 0,
        "sessions_purged": 0,
        "audit_events_matched": 0,
        "audit_events_deleted": 0,
        "archived_events_deleted": 0,
        "errors": [],
    }

    if settings.session_retention_days > 0:
        cutoff = current - timedelta(days=settings.session_retention_days)
        result["session_cutoff"] = cutoff.isoformat()
        result["sessions_matched"] = int(target_store.count_expired_sessions(cutoff))
        if not effective_dry_run:
            candidates = target_store.list_expired_sessions(
                cutoff, limit=settings.retention_batch_size
            )
            for row in candidates:
                session_id = str(row["session_id"])
                tenant_id = str(row["tenant_id"] or "")
                try:
                    _purge_one_session(target_store, target_cache, session_id, tenant_id)
                    result["sessions_purged"] += 1
                except Exception as exc:  # 单个会话失败不阻断整轮清理
                    logger.warning(
                        "Retention purge failed: session_id=%s error=%s",
                        session_id,
                        exc,
                        exc_info=True,
                    )
                    if len(result["errors"]) < 10:
                        result["errors"].append({"session_id": session_id, "error": str(exc)})

    if settings.audit_retention_days > 0:
        cutoff = current - timedelta(days=settings.audit_retention_days)
        result["audit_cutoff"] = cutoff.isoformat()
        audit_match = target_store.count_audit_events_before(cutoff)
        result["audit_events_matched"] = int(audit_match["audit_events"])
        if not effective_dry_run:
            deleted = target_store.purge_audit_events_before(
                cutoff, limit=settings.retention_batch_size
            )
            result["audit_events_deleted"] = int(deleted["audit_events"])
            result["archived_events_deleted"] = int(deleted["archived_events"])

    return result


async def _retention_loop(interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            summary = await asyncio.to_thread(run_retention_cycle)
            logger.info("Retention sweep finished: %s", summary)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Retention sweep failed; retrying next interval")


def start_retention_scheduler() -> None:
    """按配置启动后台留存清理任务；重复调用不会产生第二个任务。"""
    global _scheduler_task
    if not settings.retention_enabled or settings.retention_sweep_interval_seconds <= 0:
        return
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(
        _retention_loop(settings.retention_sweep_interval_seconds),
        name="retention-sweep",
    )
    logger.info(
        "Retention scheduler started: interval=%ss dry_run=%s session_days=%s audit_days=%s",
        settings.retention_sweep_interval_seconds,
        settings.retention_dry_run,
        settings.session_retention_days,
        settings.audit_retention_days,
    )


async def stop_retention_scheduler() -> None:
    """取消后台任务并等待其退出，避免关闭连接池后仍在写库。"""
    global _scheduler_task
    task = _scheduler_task
    _scheduler_task = None
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def retention_scheduler_status() -> str:
    """供 /health 展示的调度器状态。"""
    if not settings.retention_enabled:
        return "disabled"
    if _scheduler_task is None:
        return "not_started"
    return "stopped" if _scheduler_task.done() else "running"
