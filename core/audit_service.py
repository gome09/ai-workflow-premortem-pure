# core/audit_service.py
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.models import AuditEvent, ProjectContext


def _to_plain_dict(value: Any) -> dict | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"value": value}


def stable_hash(value: Any) -> str | None:
    """生成稳定 hash，便于审计前后版本差异。"""
    plain = _to_plain_dict(value)
    if plain is None:
        return None
    data = json.dumps(plain, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def append_audit_event(
    ctx: ProjectContext,
    *,
    actor: str,
    event_type: str,
    target_type: str,
    target_id: str,
    before: Any = None,
    after: Any = None,
    metadata: dict | None = None,
) -> AuditEvent:
    """向 ProjectContext 追加审计事件。"""
    event = AuditEvent(
        session_id=ctx.session_id,
        actor=actor,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        before_hash=stable_hash(before),
        after_hash=stable_hash(after),
        before_snapshot=_to_plain_dict(before),
        after_snapshot=_to_plain_dict(after),
        metadata=metadata or {},
    )
    ctx.audit_events.append(event)
    return event
