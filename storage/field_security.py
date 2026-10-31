"""T1.3 字段级静态加密 — Fernet 应用层加密。

设计：
- 加密范围（classification ≠ public_demo 且已配置密钥）：
  `user_materials`、`evidence_sources[*].summary/claims`（user_material 类型）、
  `research_target` / `research_goal`、`conversation_history[*][*].content`、
  `pending_actions[*].title/description/trigger_reason/payload_before/payload_after/reviewer_note`、
  `report_artifacts[*].content_markdown/content_json`。
- 投影表列级加密通过 `ENCRYPTED_COLUMNS` 注册表统一处理，双后端写入前加密、
  读出后解密。
- 密文带 enc:v1: 前缀，便于识别与未来轮换。
- 未配置密钥时：demo/lite 模式（storage_backend=sqlite）静默明文；
  生产模式（postgres）启动时 WARNING，/health 暴露 data_encryption: disabled。
- public_demo 永远明文（保住"零配置离线演示"亮点）。
- 解密 fail-closed：密文无法解密（错误密钥/损坏）时抛 `FieldDecryptionError`，
  绝不把密文当明文返回。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.config import settings
from storage.errors import FieldDecryptionError

logger = logging.getLogger(__name__)

_ENCRYPTION_PREFIX = "enc:v1:"
_fernet = None  # lazy init

# 投影表列级加密矩阵（列名来自各表显式 SELECT/INSERT，不接受调用方输入）。
ENCRYPTED_COLUMNS: dict[str, tuple[str, ...]] = {
    "human_actions": (
        "title",
        "description",
        "trigger_reason",
        "payload_before",
        "payload_after",
        "reviewer_note",
    ),
    "evidence_sources": ("summary", "claims"),
    "report_artifacts": ("content_json", "content_markdown"),
}


def _get_fernet():
    """Lazily initialize Fernet. Returns None if no key configured."""
    global _fernet
    if _fernet is not None:
        return _fernet
    key = settings.data_encryption_key
    if not key:
        if settings.storage_backend != "sqlite":
            logger.warning(
                "DATA_ENCRYPTION_KEY not set; sensitive fields stored in plaintext "
                "(storage_backend=%s). Set DATA_ENCRYPTION_KEY in production.",
                settings.storage_backend,
            )
        return None
    from cryptography.fernet import Fernet

    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def is_encryption_enabled() -> bool:
    return _get_fernet() is not None


def _reset_fernet_cache() -> None:
    """Reset the cached Fernet instance. Used by tests to pick up key changes."""
    global _fernet
    _fernet = None


def _strict_decryption_required() -> bool:
    """无密钥时是否必须拒绝密文。

    sqlite 离线演示允许无密钥明文；生产（或非 sqlite 后端）检测到 enc:v1:
    前缀却没有密钥时视为配置错误，fail-closed。
    """
    return settings.app_env == "production" or settings.storage_backend != "sqlite"


def _encrypt_value(text: str) -> str:
    """Encrypt a string. Returns 'enc:v1:<ciphertext>' or original if encryption disabled."""
    if not text or text.startswith(_ENCRYPTION_PREFIX):
        return text  # idempotent
    f = _get_fernet()
    if f is None:
        return text
    return _ENCRYPTION_PREFIX + f.encrypt(text.encode("utf-8")).decode("ascii")


def _decrypt_value(text: str, *, field: str = "", strict: bool = True) -> str:
    """Decrypt a string; fail-closed on wrong key / corrupted ciphertext."""
    if not text or not text.startswith(_ENCRYPTION_PREFIX):
        return text
    f = _get_fernet()
    if f is None:
        if strict and _strict_decryption_required():
            raise FieldDecryptionError(field or "<unknown>", "encryption key is not configured")
        return text  # sqlite 离线演示：无密钥保持原样
    try:
        return f.decrypt(text[len(_ENCRYPTION_PREFIX) :].encode("ascii")).decode("utf-8")
    except Exception as exc:
        if strict:
            raise FieldDecryptionError(
                field or "<unknown>", "ciphertext cannot be decrypted"
            ) from exc
        logger.warning("Failed to decrypt field (wrong key? corrupted?) — returning ciphertext")
        return text


def _encrypt_structure(value: Any, *, field: str = "") -> Any:
    """Recursively encrypt string leaves inside a dict/list structure."""
    if isinstance(value, str):
        return _encrypt_value(value)
    if isinstance(value, dict):
        return {key: _encrypt_structure(item, field=field) for key, item in value.items()}
    if isinstance(value, list):
        return [_encrypt_structure(item, field=field) for item in value]
    return value


def _decrypt_structure(value: Any, *, field: str = "") -> Any:
    """Recursively decrypt string leaves inside a dict/list structure."""
    if isinstance(value, str):
        return _decrypt_value(value, field=field)
    if isinstance(value, dict):
        return {key: _decrypt_structure(item, field=field) for key, item in value.items()}
    if isinstance(value, list):
        return [_decrypt_structure(item, field=field) for item in value]
    return value


def encrypt_text_field(value: str | None, classification: str) -> str | None:
    """Encrypt a single text column value for storage."""
    if value is None or classification == "public_demo" or not is_encryption_enabled():
        return value
    return _encrypt_value(value)


def encrypt_json_field(value: Any, classification: str) -> str | None:
    """Serialize a JSON-ish column value and encrypt the serialized text."""
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    return encrypt_text_field(text, classification)


def decrypt_text_field(value: str | None, *, field: str = "", strict: bool = True) -> str | None:
    """Decrypt a single text column value after load."""
    if value is None:
        return None
    return _decrypt_value(value, field=field, strict=strict)


def encrypted_columns_for_table(table: str) -> tuple[str, ...]:
    return ENCRYPTED_COLUMNS.get(table, ())


def encrypt_row_columns(table: str, row: dict[str, Any], classification: str) -> dict[str, Any]:
    """Encrypt registered columns of a serialized projection row (in-place)."""
    if classification == "public_demo" or not is_encryption_enabled():
        return row
    for column in encrypted_columns_for_table(table):
        value = row.get(column)
        if isinstance(value, str) and value:
            row[column] = _encrypt_value(value)
    return row


def decrypt_row_columns(table: str, row: dict[str, Any], *, strict: bool = True) -> dict[str, Any]:
    """Decrypt registered columns of a raw projection row (in-place)."""
    for column in encrypted_columns_for_table(table):
        value = row.get(column)
        if isinstance(value, str):
            row[column] = _decrypt_value(value, field=f"{table}.{column}", strict=strict)
    return row


def encrypt_fields_for_storage(data: dict[str, Any], classification: str) -> dict[str, Any]:
    """Mutate `data` dict in-place: encrypt sensitive context_json fields.

    Called from _build_context_json_for_storage AFTER truncation, BEFORE json.dumps.
    """
    if classification == "public_demo":
        return data  # demo 永远明文
    if not is_encryption_enabled():
        return data  # 未配置密钥静默明文

    # user_materials: list[str]
    materials = data.get("user_materials") or []
    data["user_materials"] = [_encrypt_value(m) for m in materials]

    # evidence_sources: list[dict] with summary (str) and claims (list[str])
    sources = data.get("evidence_sources") or []
    for ev in sources:
        if ev.get("source_type") != "user_material":
            continue  # 仅加密 user_material 类型的证据（与历史行为一致）
        if ev.get("summary"):
            ev["summary"] = _encrypt_value(ev["summary"])
        if ev.get("claims"):
            ev["claims"] = [_encrypt_value(c) for c in ev["claims"]]

    # research_target / research_goal
    for field in ("research_target", "research_goal"):
        value = data.get(field)
        if isinstance(value, str) and value:
            data[field] = _encrypt_value(value)

    # conversation_history[*][*].content
    history = data.get("conversation_history") or {}
    for messages in history.values():
        for message in messages or []:
            content = message.get("content") if isinstance(message, dict) else None
            if content:
                message["content"] = _encrypt_value(content)

    # pending_actions[*] 自由文本与 payload 结构
    for action in data.get("pending_actions") or []:
        if not isinstance(action, dict):
            continue
        for field in ("title", "description", "trigger_reason", "reviewer_note"):
            value = action.get(field)
            if isinstance(value, str) and value:
                action[field] = _encrypt_value(value)
        for field in ("payload_before", "payload_after"):
            if action.get(field) is not None:
                action[field] = _encrypt_structure(action[field], field=f"pending_actions.{field}")

    # report_artifacts[*].content_markdown / content_json
    for artifact in data.get("report_artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        markdown = artifact.get("content_markdown")
        if isinstance(markdown, str) and markdown:
            artifact["content_markdown"] = _encrypt_value(markdown)
        content_json = artifact.get("content_json")
        if content_json:
            artifact["content_json"] = _encrypt_structure(
                content_json, field="report_artifacts.content_json"
            )

    return data


def decrypt_fields_after_load(ctx) -> None:
    """Decrypt encrypted fields on a loaded ProjectContext (in-place).

    Called from backend load() AFTER migrate_context() returns ProjectContext.
    Fail-closed: 解密失败抛 `FieldDecryptionError`，不返回密文。
    """
    if not is_encryption_enabled() and not settings.app_env == "production":
        # sqlite 离线演示：无密钥时数据本就明文。
        # 生产/PostgreSQL 即使无密钥也继续走下去，检测到密文会 fail-closed。
        if settings.storage_backend == "sqlite":
            return

    # user_materials
    ctx.user_materials = [_decrypt_value(m, field="user_materials") for m in ctx.user_materials]

    # evidence_sources
    for ev in ctx.evidence_sources:
        if ev.source_type != "user_material":
            continue
        if ev.summary:
            ev.summary = _decrypt_value(
                ev.summary, field=f"evidence_sources[{ev.evidence_id}].summary"
            )
        if ev.claims:
            ev.claims = [
                _decrypt_value(c, field=f"evidence_sources[{ev.evidence_id}].claims")
                for c in ev.claims
            ]

    # research_target / research_goal
    if ctx.research_target:
        ctx.research_target = _decrypt_value(ctx.research_target, field="research_target")
    if getattr(ctx, "research_goal", ""):
        ctx.research_goal = _decrypt_value(ctx.research_goal, field="research_goal")

    # conversation_history[*][*].content
    for messages in ctx.conversation_history.values():
        for message in messages:
            if message.content:
                message.content = _decrypt_value(
                    message.content,
                    field=f"conversation_history[{message.role}].content",
                )

    # pending_actions
    for action in ctx.pending_actions:
        for field in ("title", "description", "trigger_reason", "reviewer_note"):
            value = getattr(action, field, "")
            if value:
                setattr(
                    action,
                    field,
                    _decrypt_value(value, field=f"pending_actions[{action.action_id}].{field}"),
                )
        for field in ("payload_before", "payload_after"):
            value = getattr(action, field, None)
            if value is not None:
                setattr(
                    action,
                    field,
                    _decrypt_structure(value, field=f"pending_actions[{action.action_id}].{field}"),
                )

    # report_artifacts
    for artifact in ctx.report_artifacts:
        if artifact.content_markdown:
            artifact.content_markdown = _decrypt_value(
                artifact.content_markdown, field=f"report_artifacts[{artifact.report_id}].markdown"
            )
        if artifact.content_json:
            artifact.content_json = _decrypt_structure(
                artifact.content_json, field=f"report_artifacts[{artifact.report_id}].content_json"
            )
