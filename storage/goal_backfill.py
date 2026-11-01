# storage/goal_backfill.py
"""Historical plaintext `goal` backfill helpers.

The field-level encryption layer historically encrypted ``research_goal`` by
typo while ``ProjectContext`` stores ``goal``. This module contains the pure
JSON transformation used by both storage backends' ``backfill_goal_encryption``
methods and by ``scripts/encrypt_legacy_goal.py``.

Modes:
- ``encrypt``: plaintext goal -> ``enc:v1:`` ciphertext;
- ``verify``: confirm an existing ciphertext is decryptable with the current key;
- ``decrypt``: ciphertext -> plaintext (rollback to pre-1.7 application code).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from storage.field_security import (
    _ENCRYPTION_PREFIX,
    _decrypt_value,
    _encrypt_value,
    is_encryption_enabled,
)

GoalBackfillMode = Literal["encrypt", "verify", "decrypt"]

# Result status values returned per row.
STATUS_ENCRYPTED = "encrypted"
STATUS_ALREADY_ENCRYPTED = "already_encrypted"
STATUS_DECRYPTED = "decrypted"
STATUS_ALREADY_PLAINTEXT = "already_plaintext"
STATUS_VERIFIED = "verified"
STATUS_EMPTY = "empty"
STATUS_PUBLIC_DEMO = "public_demo"
STATUS_INVALID_JSON = "invalid_json"
STATUS_DECRYPT_FAILED = "decrypt_failed"


@dataclass(frozen=True)
class GoalTransform:
    status: str
    changed: bool
    context_json: str
    error: str = ""


def transform_goal_context(raw_context_json: str, *, mode: GoalBackfillMode) -> GoalTransform:
    """Apply one backfill mode to a raw ``context_json`` string."""
    try:
        data: Any = json.loads(raw_context_json or "{}")
    except json.JSONDecodeError:
        return GoalTransform(STATUS_INVALID_JSON, False, raw_context_json)

    if not isinstance(data, dict):
        return GoalTransform(STATUS_INVALID_JSON, False, raw_context_json)

    classification = data.get("data_classification") or "business_internal"
    if classification == "public_demo":
        return GoalTransform(STATUS_PUBLIC_DEMO, False, raw_context_json)

    goal = data.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return GoalTransform(STATUS_EMPTY, False, raw_context_json)

    if goal.startswith(_ENCRYPTION_PREFIX):
        if mode == "verify":
            try:
                _decrypt_value(goal, field="goal")
            except Exception as exc:  # noqa: BLE001 - report per-row failure, do not abort the sweep
                return GoalTransform(STATUS_DECRYPT_FAILED, False, raw_context_json, str(exc))
            return GoalTransform(STATUS_VERIFIED, False, raw_context_json)
        if mode == "encrypt":
            return GoalTransform(STATUS_ALREADY_ENCRYPTED, False, raw_context_json)
        try:
            data["goal"] = _decrypt_value(goal, field="goal")
        except Exception as exc:  # noqa: BLE001 - report per-row failure, do not abort the sweep
            return GoalTransform(STATUS_DECRYPT_FAILED, False, raw_context_json, str(exc))
        return GoalTransform(
            STATUS_DECRYPTED,
            True,
            json.dumps(data, ensure_ascii=False, default=str),
        )

    if mode in {"verify", "decrypt"}:
        return GoalTransform(STATUS_ALREADY_PLAINTEXT, False, raw_context_json)

    if not is_encryption_enabled():
        return GoalTransform(
            STATUS_DECRYPT_FAILED,
            False,
            raw_context_json,
            "DATA_ENCRYPTION_KEY is not configured",
        )

    data["goal"] = _encrypt_value(goal)
    return GoalTransform(
        STATUS_ENCRYPTED,
        True,
        json.dumps(data, ensure_ascii=False, default=str),
    )
