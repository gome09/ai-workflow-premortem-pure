# tests/test_ids_unique.py
"""Milestone 1 P0: 标识必须使用可靠的全局唯一 ID。

历史实现使用 `str(uuid.uuid4())[:8]`（约 32-bit 熵），生产并发下存在
真实碰撞风险。本测试锁定：
- `core.ids.new_id` 返回完整 UUID4（36 字符，122-bit 熵）。
- 高并发批量生成不存在碰撞。
- 模型 default_factory 使用同一入口并保留既有可读前缀。
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.ids import new_id
from core.models import (
    ActionResolutionLog,
    EvalCase,
    EvidenceSource,
    LLMTrace,
    PendingHumanAction,
)

UUID_LEN = 36


def test_new_id_is_full_uuid4():
    value = new_id()
    assert len(value) == UUID_LEN
    parsed = uuid.UUID(value)
    assert parsed.version == 4


def test_new_id_preserves_prefix_contract():
    value = new_id("EVID-")
    assert value.startswith("EVID-")
    unprefixed = value[len("EVID-") :]
    assert len(unprefixed) == UUID_LEN
    assert uuid.UUID(unprefixed).version == 4


def test_new_id_high_concurrency_has_no_collisions():
    total = 50_000
    with ThreadPoolExecutor(max_workers=16) as pool:
        values = list(pool.map(lambda _: new_id(), range(total)))
    assert len(values) == total
    assert len(set(values)) == total


@pytest.mark.parametrize(
    ("factory", "prefix"),
    [
        (
            lambda: PendingHumanAction(
                session_id="s", stage_id=1, action_type="approve", title="t", description="d"
            ),
            "",
        ),
        (
            lambda: ActionResolutionLog(
                session_id="s", action_id="a", requested_status="resolved", result_status="resolved"
            ),
            "ARL-",
        ),
        (lambda: LLMTrace(session_id="s"), "TRC-"),
        (lambda: EvidenceSource(session_id="s", title="t"), "EVID-"),
        (lambda: EvalCase(session_id="s", input_payload="i", expected_behavior="e"), "EVAL-"),
    ],
)
def test_model_default_ids_are_full_uuid4_with_prefix(factory, prefix):
    first = factory()
    second = factory()
    field = {
        "": "action_id",
        "ARL-": "log_id",
        "TRC-": "trace_id",
        "EVID-": "evidence_id",
        "EVAL-": "eval_id",
    }[prefix]
    value = getattr(first, field)
    assert value.startswith(prefix)
    assert len(value) == len(prefix) + UUID_LEN
    assert uuid.UUID(value[len(prefix) :]).version == 4
    assert value != getattr(second, field)


def test_pending_action_contract_id_uses_prefixed_uuid():
    action = PendingHumanAction(
        session_id="s", stage_id=1, action_type="approve", title="t", description="d"
    )
    assert action.action_contract_id.startswith("ACTC-")
    assert uuid.UUID(action.action_contract_id[len("ACTC-") :]).version == 4
