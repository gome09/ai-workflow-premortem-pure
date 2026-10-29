"""Outbox 周期重试调度器：模式隔离、启动/停止、循环重试。"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from core import execution_service
from core.config import settings
from core.execution_mode import WorkflowExecutionMode


@pytest.fixture(autouse=True)
def _reset_scheduler():
    execution_service._resume_scheduler_task = None
    yield
    execution_service._resume_scheduler_task = None


def test_scheduler_is_noop_in_single_step(monkeypatch):
    monkeypatch.setattr(settings, "workflow_execution_mode", WorkflowExecutionMode.SINGLE_STEP)

    execution_service.start_interrupt_resume_scheduler()

    assert execution_service._resume_scheduler_task is None
    assert execution_service.interrupt_resume_scheduler_status() == "disabled"


def test_scheduler_starts_and_stops_in_interrupt_mode(monkeypatch):
    monkeypatch.setattr(
        settings, "workflow_execution_mode", WorkflowExecutionMode.LANGGRAPH_INTERRUPT
    )
    monkeypatch.setattr(settings, "interrupt_resume_retry_interval_seconds", 3600)

    async def scenario():
        execution_service.start_interrupt_resume_scheduler()
        assert execution_service.interrupt_resume_scheduler_status() == "running"
        await execution_service.stop_interrupt_resume_scheduler()
        assert execution_service.interrupt_resume_scheduler_status() == "not_started"

    asyncio.run(scenario())


def test_zero_interval_disables_scheduler(monkeypatch):
    monkeypatch.setattr(
        settings, "workflow_execution_mode", WorkflowExecutionMode.LANGGRAPH_INTERRUPT
    )
    monkeypatch.setattr(settings, "interrupt_resume_retry_interval_seconds", 0)

    async def scenario():
        execution_service.start_interrupt_resume_scheduler()
        assert execution_service._resume_scheduler_task is None
        assert execution_service.interrupt_resume_scheduler_status() == "not_started"

    asyncio.run(scenario())


def test_retry_loop_runs_periodically_and_survives_failures(monkeypatch):
    calls: list[int] = []

    def fake_reconcile(limit: int = 100) -> dict[str, int]:
        calls.append(limit)
        if len(calls) == 1:
            raise RuntimeError("transient database outage")
        return {"found": 0, "claimed": 0, "completed": 0, "failed": 0}

    monkeypatch.setattr(execution_service, "reconcile_pending_interrupt_resumes", fake_reconcile)

    async def scenario():
        task = asyncio.create_task(execution_service._resume_retry_loop(0.01, 7))
        try:
            # Windows 的 asyncio 定时器粒度约 15ms，留出足够时间完成至少两轮。
            await asyncio.sleep(0.2)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(scenario())

    assert len(calls) >= 2
    assert calls[0] == 7
