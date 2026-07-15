"""T1.3 字段级静态加密 — Fernet 应用层加密。

设计：
- 加密范围：data_classification ∈ {business_internal, sensitive_personal} 会话的
  user_materials (list[str]) 与 evidence_sources[*].summary/claims (str / list[str])。
- 密文带 enc:v1: 前缀，便于识别与未来轮换。
- 未配置密钥时：demo/lite 模式（storage_backend=sqlite）静默明文；
  生产模式（postgres）启动时 WARNING，/health 暴露 data_encryption: disabled。
- public_demo 永远明文（保住"零配置离线演示"亮点）。
"""

from __future__ import annotations

import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

_ENCRYPTION_PREFIX = "enc:v1:"
_fernet = None  # lazy init


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


def _encrypt_value(text: str) -> str:
    """Encrypt a string. Returns 'enc:v1:<ciphertext>' or original if encryption disabled."""
    if not text or text.startswith(_ENCRYPTION_PREFIX):
        return text  # idempotent
    f = _get_fernet()
    if f is None:
        return text
    return _ENCRYPTION_PREFIX + f.encrypt(text.encode("utf-8")).decode("ascii")


def _decrypt_value(text: str) -> str:
    """Decrypt a string. Returns original if not encrypted or decryption fails."""
    if not text or not text.startswith(_ENCRYPTION_PREFIX):
        return text
    f = _get_fernet()
    if f is None:
        return text  # can't decrypt without key; return as-is
    try:
        return f.decrypt(text[len(_ENCRYPTION_PREFIX) :].encode("ascii")).decode("utf-8")
    except Exception:
        logger.warning("Failed to decrypt field (wrong key? corrupted?) — returning ciphertext")
        return text


def encrypt_fields_for_storage(data: dict[str, Any], classification: str) -> dict[str, Any]:
    """Mutate `data` dict in-place: encrypt user_materials and evidence_sources summary/claims.

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
            continue  # 仅加密 user_material 类型的证据
        if ev.get("summary"):
            ev["summary"] = _encrypt_value(ev["summary"])
        if ev.get("claims"):
            ev["claims"] = [_encrypt_value(c) for c in ev["claims"]]

    return data


def decrypt_fields_after_load(ctx) -> None:
    """Decrypt encrypted fields on a loaded ProjectContext (in-place).

    Called from backend load() AFTER migrate_context() returns ProjectContext.
    """
    if not is_encryption_enabled():
        return  # 未配置密钥：要么 demo 模式（数据本就明文），要么生产但未配 key

    # user_materials
    ctx.user_materials = [_decrypt_value(m) for m in ctx.user_materials]

    # evidence_sources
    for ev in ctx.evidence_sources:
        if ev.source_type != "user_material":
            continue
        if ev.summary:
            ev.summary = _decrypt_value(ev.summary)
        if ev.claims:
            ev.claims = [_decrypt_value(c) for c in ev.claims]
