# tests/test_field_security_extended.py
"""Milestone 1 P3: 字段级加密的完整覆盖面与 fail-closed 语义。

验收：
- 六类敏感持久化路径在 SQLite 中均落密文（enc:v1:），load/投影读取恢复明文。
- 错误密钥 → FieldDecryptionError（绝不返回密文）。
- 非 sqlite 后端且无密钥时遇到密文 → FieldDecryptionError（fail-closed）。
- 错误 tenant 无法读取；空 tenant 直接抛 TenantIsolationError。
- public_demo 永远明文，保住零配置离线演示。
"""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from core.config import settings
from core.models import (
    EvidenceSource,
    Message,
    MessageRole,
    PendingHumanAction,
    ProjectContext,
    ReportArtifact,
)
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.errors import FieldDecryptionError, TenantIsolationError
from storage.field_security import _reset_fernet_cache

_KEY_A = Fernet.generate_key().decode()
_KEY_B = Fernet.generate_key().decode()
TENANT = "tenant-a"


@pytest.fixture(autouse=True)
def _reset_encryption_cache():
    _reset_fernet_cache()
    yield
    _reset_fernet_cache()


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", _KEY_A)
    backend = SQLiteSessionStore(db_path=str(tmp_path / "field_security.db"))
    backend.initialize()
    return backend


def _raw_context_json(store: SQLiteSessionStore, session_id: str) -> str:
    with store._get_conn() as conn:  # noqa: SLF001  # direct DB introspection for test
        row = conn.execute(
            "SELECT context_json FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    assert row is not None
    # context_json 使用 ensure_ascii 序列化，先还原成可读文本再做明文断言。
    return json.dumps(json.loads(row["context_json"]), ensure_ascii=False)


def _sensitive_ctx() -> ProjectContext:
    ctx = ProjectContext(tenant_id=TENANT, session_name="enc-e2e")
    ctx.data_classification = "business_internal"
    ctx.research_target = "内部项目代号-ALPHA"
    ctx.goal = "项目目标-机密-014"
    ctx.user_materials = ["用户材料-机密-001"]
    ctx.evidence_sources = [
        EvidenceSource(
            session_id=ctx.session_id,
            title="用户提交材料",
            source_type="user_material",
            summary="证据摘要-机密-002",
            claims=["claim-机密-003", "claim-机密-004"],
        )
    ]
    ctx.conversation_history = {
        "stage_1": [
            Message(role=MessageRole.USER, content="对话内容-机密-005"),
            Message(role=MessageRole.ASSISTANT, content="AI 回复-机密-006"),
        ]
    }
    ctx.pending_actions = [
        PendingHumanAction(
            session_id=ctx.session_id,
            stage_id=1,
            action_type="edit",
            title="动作标题-机密-007",
            description="动作描述-机密-008",
            trigger_reason="触发原因-机密-009",
            payload_before={"note": "payload-机密-010"},
            reviewer_note="复核备注-机密-011",
        )
    ]
    ctx.report_artifacts = [
        ReportArtifact(
            session_id=ctx.session_id,
            version="v1",
            content_markdown="报告正文-机密-012",
            content_json={"conclusion": "报告结论-机密-013"},
        )
    ]
    return ctx


def test_sqlite_encrypts_all_sensitive_paths_and_round_trips(store):
    ctx = _sensitive_ctx()
    store.save(ctx)

    raw = _raw_context_json(store, ctx.session_id)
    assert "enc:v1:" in raw
    for marker in (
        "用户材料-机密-001",
        "证据摘要-机密-002",
        "claim-机密-003",
        "内部项目代号-ALPHA",
        "项目目标-机密-014",
        "对话内容-机密-005",
        "AI 回复-机密-006",
        "动作标题-机密-007",
        "动作描述-机密-008",
        "触发原因-机密-009",
        "payload-机密-010",
        "复核备注-机密-011",
    ):
        assert marker not in raw, marker

    loaded = store.load(ctx.session_id, TENANT)
    assert loaded is not None
    assert loaded.user_materials == ctx.user_materials
    assert loaded.research_target == ctx.research_target
    assert loaded.goal == ctx.goal
    assert loaded.evidence_sources[0].summary == "证据摘要-机密-002"
    assert loaded.evidence_sources[0].claims == ["claim-机密-003", "claim-机密-004"]
    assert [m.content for m in loaded.conversation_history["stage_1"]] == [
        "对话内容-机密-005",
        "AI 回复-机密-006",
    ]
    action = loaded.pending_actions[0]
    assert action.title == "动作标题-机密-007"
    assert action.description == "动作描述-机密-008"
    assert action.trigger_reason == "触发原因-机密-009"
    assert action.payload_before["note"] == "payload-机密-010"
    assert action.reviewer_note == "复核备注-机密-011"


def test_report_artifacts_are_encrypted_in_projection_table(store):
    ctx = _sensitive_ctx()
    store.save(ctx)

    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT content_json, content_markdown FROM report_artifacts WHERE session_id=?",
            (ctx.session_id,),
        ).fetchone()
    assert row is not None
    assert row["content_markdown"].startswith("enc:v1:")
    assert "报告正文-机密-012" not in row["content_markdown"]
    assert row["content_json"].startswith("enc:v1:")
    assert "报告结论-机密-013" not in row["content_json"]

    artifacts = store.list_report_artifacts(ctx.session_id)
    assert artifacts[0]["content_markdown"] == "报告正文-机密-012"
    content_json = artifacts[0]["content_json"]
    if isinstance(content_json, str):
        content_json = json.loads(content_json)
    assert content_json == {"conclusion": "报告结论-机密-013"}


def test_wrong_key_fails_closed(store, monkeypatch):
    ctx = _sensitive_ctx()
    store.save(ctx)

    monkeypatch.setattr(settings, "data_encryption_key", _KEY_B)
    _reset_fernet_cache()

    with pytest.raises(FieldDecryptionError) as exc:
        store.load(ctx.session_id, TENANT)
    assert "user_materials" in exc.value.field
    # 错误信息只带字段路径与原因，不携带密文。
    assert "enc:v1:" not in str(exc.value)


def test_missing_key_on_non_sqlite_backend_refuses_ciphertext(store, monkeypatch):
    ctx = _sensitive_ctx()
    store.save(ctx)

    monkeypatch.setattr(settings, "data_encryption_key", "")
    monkeypatch.setattr(settings, "storage_backend", "postgres")
    _reset_fernet_cache()

    with pytest.raises(FieldDecryptionError):
        store.load(ctx.session_id, TENANT)


def test_wrong_tenant_cannot_read_and_empty_tenant_is_rejected(store):
    ctx = _sensitive_ctx()
    store.save(ctx)

    assert store.load(ctx.session_id, "tenant-b") is None
    with pytest.raises(TenantIsolationError):
        store.load(ctx.session_id, "")


def test_public_demo_stays_plaintext(store):
    ctx = ProjectContext(tenant_id=TENANT, session_name="demo")
    ctx.data_classification = "public_demo"
    ctx.user_materials = ["演示材料-明文"]
    store.save(ctx)

    raw = _raw_context_json(store, ctx.session_id)
    assert "enc:v1:" not in raw
    assert "演示材料-明文" in raw

    loaded = store.load(ctx.session_id, TENANT)
    assert loaded is not None
    assert loaded.user_materials == ["演示材料-明文"]


def test_projection_human_actions_encrypted_at_rest(store):
    ctx = _sensitive_ctx()
    store.save(ctx)
    action_id = ctx.pending_actions[0].action_id

    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT title, description, reviewer_note FROM human_actions WHERE action_id=?",
            (action_id,),
        ).fetchone()
    assert row is not None
    assert row["title"].startswith("enc:v1:")
    assert row["description"].startswith("enc:v1:")
    assert row["reviewer_note"].startswith("enc:v1:")

    rows = store.list_projection("human_actions", ctx.session_id, TENANT)
    assert rows is not None
    assert rows[0]["title"] == "动作标题-机密-007"
    assert rows[0]["description"] == "动作描述-机密-008"
