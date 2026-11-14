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
    store.create(ctx)

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
    store.create(ctx)

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
    store.create(ctx)

    monkeypatch.setattr(settings, "data_encryption_key", _KEY_B)
    _reset_fernet_cache()

    with pytest.raises(FieldDecryptionError) as exc:
        store.load(ctx.session_id, TENANT)
    assert "user_materials" in exc.value.field
    # 错误信息只带字段路径与原因，不携带密文。
    assert "enc:v1:" not in str(exc.value)


def test_missing_key_on_non_sqlite_backend_refuses_ciphertext(store, monkeypatch):
    ctx = _sensitive_ctx()
    store.create(ctx)

    monkeypatch.setattr(settings, "data_encryption_key", "")
    monkeypatch.setattr(settings, "storage_backend", "postgres")
    _reset_fernet_cache()

    with pytest.raises(FieldDecryptionError):
        store.load(ctx.session_id, TENANT)


def test_wrong_tenant_cannot_read_and_empty_tenant_is_rejected(store):
    ctx = _sensitive_ctx()
    store.create(ctx)

    assert store.load(ctx.session_id, "tenant-b") is None
    with pytest.raises(TenantIsolationError):
        store.load(ctx.session_id, "")


def test_public_demo_stays_plaintext(store):
    ctx = ProjectContext(tenant_id=TENANT, session_name="demo")
    ctx.data_classification = "public_demo"
    ctx.user_materials = ["演示材料-明文"]
    store.create(ctx)

    raw = _raw_context_json(store, ctx.session_id)
    assert "enc:v1:" not in raw
    assert "演示材料-明文" in raw

    loaded = store.load(ctx.session_id, TENANT)
    assert loaded is not None
    assert loaded.user_materials == ["演示材料-明文"]


def test_projection_human_actions_encrypted_at_rest(store):
    ctx = _sensitive_ctx()
    store.create(ctx)
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


def test_eval_safety_redteam_and_cache_copies_are_encrypted(store):
    """上下文、投影表与缓存副本均不得出现敏感样本文本明文。"""
    from core.models import (
        EvalCase,
        EvalJudgment,
        EvalRun,
        HumanCalibration,
        RedTeamCase,
        SafetyFinding,
    )
    from storage.backends.memory_cache import MemoryCache
    from storage.cache import _deserialize, _serialize

    ctx = ProjectContext(tenant_id=TENANT, session_name="enc-eval")
    ctx.data_classification = "business_internal"
    case = EvalCase(
        session_id=ctx.session_id,
        stage_id=3,
        target_node_id="N-1",
        input_payload="样本-明文-eval-001",
        expected_behavior="预期-明文-eval-002",
        pass_criteria=["citation"],
        actual_output="实际-明文-eval-003",
        human_comment="人工-明文-eval-004",
    )
    ctx.eval_cases.append(case)
    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        target_node_id="N-1",
        run_mode="target_http",
        execution_kind="real_target_execution",
        execution_outcome="success",
        input_payload="运行输入-明文-005",
        expected_behavior="运行预期-明文-006",
        actual_output="运行输出-明文-007",
        judge_reason="评审理由-明文-008",
        error_message="错误-明文-009",
        status="completed",
    )
    ctx.eval_runs.append(run)
    ctx.human_calibrations.append(
        HumanCalibration(
            session_id=ctx.session_id,
            eval_run_id=run.run_id,
            human_label="passed",
            human_comment="校准依据-明文-010",
            disagreement_reason="分歧-明文-011",
        )
    )
    ctx.eval_judgments.append(
        EvalJudgment(
            session_id=ctx.session_id,
            eval_run_id=run.run_id,
            rationale="判定理由-明文-012",
        )
    )
    ctx.redteam_cases.append(
        RedTeamCase(
            session_id=ctx.session_id,
            prompt="红队提示-明文-013",
            malicious_material="恶意材料-明文-014",
            expected_failure_mode="预期失败-明文-015",
            expected_safe_behavior="安全行为-明文-016",
        )
    )
    ctx.safety_findings.append(
        SafetyFinding(
            session_id=ctx.session_id,
            risk_type="unsupported_claim",
            severity="high",
            location="stage_3",
            description="安全描述-明文-017",
            recommended_action="建议动作-明文-018",
        )
    )

    store.create(ctx)
    raw = _raw_context_json(store, ctx.session_id)
    for marker in (
        "样本-明文-eval-001",
        "预期-明文-eval-002",
        "实际-明文-eval-003",
        "运行输入-明文-005",
        "评审理由-明文-008",
        "校准依据-明文-010",
        "判定理由-明文-012",
        "红队提示-明文-013",
        "安全描述-明文-017",
    ):
        assert marker not in raw, marker

    with store._get_conn() as conn:  # noqa: SLF001
        case_row = conn.execute(
            "SELECT input_payload, expected_behavior, actual_output FROM eval_cases "
            "WHERE session_id=?",
            (ctx.session_id,),
        ).fetchone()
        run_row = conn.execute(
            "SELECT input_payload, actual_output, judge_reason FROM eval_runs WHERE session_id=?",
            (ctx.session_id,),
        ).fetchone()
        finding_row = conn.execute(
            "SELECT description, recommended_action FROM safety_findings WHERE session_id=?",
            (ctx.session_id,),
        ).fetchone()
    assert case_row["input_payload"].startswith("enc:v1:")
    assert case_row["expected_behavior"].startswith("enc:v1:")
    assert case_row["actual_output"].startswith("enc:v1:")
    assert run_row["input_payload"].startswith("enc:v1:")
    assert run_row["actual_output"].startswith("enc:v1:")
    assert run_row["judge_reason"].startswith("enc:v1:")
    assert finding_row["description"].startswith("enc:v1:")
    assert finding_row["recommended_action"].startswith("enc:v1:")

    cases = store.list_projection("eval_cases", ctx.session_id, TENANT)
    assert cases is not None
    assert cases[0]["input_payload"] == "样本-明文-eval-001"
    findings = store.list_projection("safety_findings", ctx.session_id, TENANT)
    assert findings is not None
    assert findings[0]["description"] == "安全描述-明文-017"

    cache = MemoryCache(ttl_seconds=3600)
    cache.set(ctx)
    cached_raw = next(iter(cache._store.values()))[0]  # noqa: SLF001
    assert "样本-明文-eval-001" not in cached_raw
    assert "安全描述-明文-017" not in cached_raw
    restored_cache = cache.get(ctx.session_id, TENANT)
    assert restored_cache is not None
    assert restored_cache.eval_cases[0].input_payload == "样本-明文-eval-001"
    assert restored_cache.safety_findings[0].description == "安全描述-明文-017"

    serialized = _serialize(ctx)
    assert "样本-明文-eval-001" not in serialized
    assert "校准依据-明文-010" not in serialized
    restored = _deserialize(serialized)
    assert restored is not None
    assert restored.eval_runs[0].actual_output == "运行输出-明文-007"
    assert restored.human_calibrations[0].human_comment == "校准依据-明文-010"
