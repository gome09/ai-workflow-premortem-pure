# storage/projection_read.py
"""共享投影表读取层。

只读列表端点原本需要先反序列化完整 `ProjectContext` 才能取一个集合。
本模块把「投影表行 -> Pydantic 模型 -> JSON dict」的转换收敛到一处，
SQLite / PostgreSQL 两个后端只需各自实现 SQL 查询与租户校验。

失败语义：转换异常由调用方（SessionService）捕获并回退旧上下文路径，
因此这里不做静默降级。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from core.models import (
    ActionResolutionLog,
    AuditEvent,
    EvalCase,
    EvalDataset,
    EvalExperiment,
    EvalRun,
    EvidenceSource,
    InterruptRecord,
    PendingHumanAction,
    RedTeamCase,
    SafetyFinding,
)


@dataclass(frozen=True)
class ProjectionSpec:
    """一张投影表的读取契约。"""

    model: type[BaseModel]
    order_by: str = "created_at ASC"
    # SQLite 用 TEXT 存 JSON，PostgreSQL 用 JSONB；仅当值是 str 时才需要 loads。
    json_fields: tuple[str, ...] = ()
    # 以整行模型快照存表的投影（SQLite TEXT / PG JSONB）。
    payload_column: str | None = None
    # 允许的等值过滤列白名单，避免把调用方参数拼进 SQL 标识符。
    filters: tuple[str, ...] = ()


PROJECTION_TABLES: dict[str, ProjectionSpec] = {
    "human_actions": ProjectionSpec(
        PendingHumanAction,
        json_fields=("payload_before", "payload_after"),
        filters=("status",),
    ),
    "action_resolution_logs": ProjectionSpec(
        ActionResolutionLog,
        filters=("action_id",),
    ),
    "evidence_sources": ProjectionSpec(
        EvidenceSource,
        order_by="retrieved_at ASC",
        json_fields=("claims", "used_by_failure_mode_ids"),
    ),
    "safety_findings": ProjectionSpec(
        SafetyFinding,
        json_fields=("taxonomy_refs", "control_refs"),
        filters=("status",),
    ),
    "audit_events": ProjectionSpec(
        AuditEvent,
        json_fields=("before_snapshot", "after_snapshot", "metadata"),
    ),
    "eval_cases": ProjectionSpec(
        EvalCase,
        json_fields=("covered_failure_mode_ids", "metadata", "pass_criteria"),
    ),
    "eval_runs": ProjectionSpec(
        EvalRun,
        json_fields=(
            "covered_failure_mode_ids",
            "violated_criteria",
            "pass_criteria",
            "llm_judge_suggestion",
        ),
        filters=("eval_id",),
    ),
    "eval_datasets": ProjectionSpec(EvalDataset, payload_column="payload_json"),
    "eval_experiments": ProjectionSpec(EvalExperiment, payload_column="payload_json"),
    "redteam_cases": ProjectionSpec(RedTeamCase, payload_column="payload_json"),
    "interrupt_records": ProjectionSpec(
        InterruptRecord,
        json_fields=("resume_value", "interrupt_payload"),
    ),
}


def get_projection_spec(table: str) -> ProjectionSpec:
    try:
        return PROJECTION_TABLES[table]
    except KeyError:
        raise ValueError(f"Unknown projection table: {table}") from None


def build_model(table: str, row: dict[str, Any]) -> BaseModel:
    """把一行投影数据转换成对应 Pydantic 模型。"""
    spec = get_projection_spec(table)
    data = dict(row)
    if spec.payload_column is not None:
        payload = data.get(spec.payload_column)
        data = _loads(payload) if payload is not None else {}
    for field in spec.json_fields:
        value = data.get(field)
        if isinstance(value, str):
            data[field] = _loads(value)
    return spec.model.model_validate(data)


def build_projection_rows(table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把多行投影数据转换成与旧上下文路径一致的 JSON dict 列表。"""
    return [build_model(table, row).model_dump(mode="json") for row in rows]


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value
