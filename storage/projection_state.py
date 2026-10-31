# storage/projection_state.py
"""save() 差分同步状态。

状态持久化在 `sessions.projection_state`（PostgreSQL Alembic V009 / SQLite TEXT）：

- hash 模式：对集合规范化 JSON 求 sha256，哈希相同即跳过整表重写；
- append 模式：记录 count 与 last_id，只追加 count 之后的行。

状态缺失、损坏、模式不符或结构不完整时一律回退全量同步（fail-safe）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectionSpec:
    """一个投影集合的同步策略。"""

    attribute: str  # ProjectContext 上的集合属性
    mode: str  # "hash" | "append"
    id_field: str  # 主键字段，append 模式用于校验尾部位置


COLLECTIONS: dict[str, CollectionSpec] = {
    "human_actions": CollectionSpec("pending_actions", "hash", "action_id"),
    "action_resolution_logs": CollectionSpec("action_resolution_logs", "append", "log_id"),
    "llm_traces": CollectionSpec("llm_traces", "append", "trace_id"),
    "audit_events": CollectionSpec("audit_events", "append", "event_id"),
    "evidence_sources": CollectionSpec("evidence_sources", "hash", "evidence_id"),
    "safety_findings": CollectionSpec("safety_findings", "hash", "finding_id"),
    "report_artifacts": CollectionSpec("report_artifacts", "hash", "report_id"),
    "eval_cases": CollectionSpec("eval_cases", "hash", "eval_id"),
    "eval_runs": CollectionSpec("eval_runs", "hash", "run_id"),
    "eval_judgments": CollectionSpec("eval_judgments", "hash", "judgment_id"),
    "human_calibrations": CollectionSpec("human_calibrations", "hash", "calibration_id"),
    "eval_datasets": CollectionSpec("eval_datasets", "hash", "dataset_id"),
    "eval_experiments": CollectionSpec("eval_experiments", "hash", "experiment_id"),
    "redteam_cases": CollectionSpec("redteam_cases", "hash", "redteam_case_id"),
    "interrupt_records": CollectionSpec("interrupt_records", "hash", "interrupt_id"),
}


@dataclass(frozen=True)
class SyncPlan:
    """一个集合的同步计划：`skip=True` 不写；否则从 `start` 开始写。"""

    skip: bool = False
    start: int = 0


FULL_SYNC = SyncPlan()


def compute_state(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """基于一次 `model_dump(mode="json")` 结果生成新的投影状态。"""
    state: dict[str, dict[str, Any]] = {}
    for key, spec in COLLECTIONS.items():
        items = _items(data, spec)
        if spec.mode == "append":
            state[key] = {
                "mode": "append",
                "count": len(items),
                "last_id": _last_id(items, spec),
            }
        else:
            state[key] = {"mode": "hash", "hash": _digest(items), "count": len(items)}
    return state


def plan_sync(
    previous: Any,
    current: dict[str, dict[str, Any]],
    data: dict[str, Any],
) -> dict[str, SyncPlan]:
    """对比持久化状态与新状态，生成逐集合的同步计划。"""
    previous_state = previous if isinstance(previous, dict) else {}
    plans: dict[str, SyncPlan] = {}
    for key, spec in COLLECTIONS.items():
        prior = previous_state.get(key)
        entry = current.get(key) or {}
        plans[key] = _plan_one(spec, prior, entry, _items(data, spec))
    return plans


def _plan_one(
    spec: CollectionSpec,
    prior: Any,
    entry: dict[str, Any],
    items: list[Any],
) -> SyncPlan:
    if not isinstance(prior, dict) or prior.get("mode") != spec.mode:
        return FULL_SYNC
    if spec.mode == "hash":
        prior_hash = prior.get("hash")
        if isinstance(prior_hash, str) and prior_hash == entry.get("hash"):
            return SyncPlan(skip=True)
        return FULL_SYNC
    count = prior.get("count")
    if not isinstance(count, int) or not 0 <= count <= len(items):
        return FULL_SYNC
    expected_last = _last_id(items[:count], spec)
    if prior.get("last_id") != expected_last:
        return FULL_SYNC
    if count >= len(items):
        return SyncPlan(skip=True)
    return SyncPlan(start=count)


def _items(data: dict[str, Any], spec: CollectionSpec) -> list[Any]:
    items = data.get(spec.attribute)
    return items if isinstance(items, list) else []


def _last_id(items: list[Any], spec: CollectionSpec) -> Any:
    if not items:
        return None
    last = items[-1]
    return last.get(spec.id_field) if isinstance(last, dict) else None


def _digest(items: list[Any]) -> str:
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
