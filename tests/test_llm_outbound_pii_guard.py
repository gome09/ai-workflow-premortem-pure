# tests/test_llm_outbound_pii_guard.py
"""Outbound LLM PII guard.

Covered:
- sensitive_personal 会话即使 PII_MASK_BEFORE_LLM=False 也强制掩码；
- business_internal 保留原开关语义（关闭时原文可见）；
- public_demo 在开关开启时掩码；
- 聊天正文在 send_message 内预扫描并升级分级后强制掩码；
- 补充材料扫描升级后，注入 system prompt 的原文同样被掩码；
- INIT 节点与 LLM judge 路径同样受守卫保护；
- 非文本敏感消息 fail-closed。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from core import eval_llm_judge
from core.config import settings
from core.llm.outbound_guard import OutboundPIIBlockedError, guard_messages
from core.models import EvalCase, EvalRun, ProjectContext
from core.session_service import SessionService
from stages.base import BaseStageExecutor
from tools.safety_classifier import add_findings_dedup, scan_user_materials

_ID_CARD = "110101199001011234"
_MASKED_ID_CARD = "110101********1234"


class _CapturingChatModel:
    def __init__(self, content: str = "ok") -> None:
        self.messages: list = []
        self.content = content

    def invoke(self, messages):
        self.messages = list(messages)
        return SimpleNamespace(content=self.content)


def _joined(messages) -> str:
    return "\n".join(str(message.content) for message in messages)


class _TestExecutor(BaseStageExecutor):
    stage_id = 1

    def build_system_prompt(self, ctx: ProjectContext) -> str:
        return "stage test system prompt"

    def parse_output(self, raw_text: str, ctx: ProjectContext) -> ProjectContext:
        return ctx


def test_sensitive_personal_is_masked_even_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "pii_mask_before_llm", False)
    ctx = ProjectContext()
    ctx.data_classification = "sensitive_personal"
    model = _CapturingChatModel()
    monkeypatch.setattr("stages.base.get_llm_for_stage_with_context", lambda stage, ctx: model)

    _TestExecutor().run(ctx, f"我的身份证是 {_ID_CARD}")

    prompt = _joined(model.messages)
    assert _MASKED_ID_CARD in prompt
    assert _ID_CARD not in prompt


def test_business_internal_keeps_flag_semantics(monkeypatch):
    monkeypatch.setattr(settings, "pii_mask_before_llm", False)
    ctx = ProjectContext()
    ctx.data_classification = "business_internal"
    model = _CapturingChatModel()
    monkeypatch.setattr("stages.base.get_llm_for_stage_with_context", lambda stage, ctx: model)

    _TestExecutor().run(ctx, f"我的身份证是 {_ID_CARD}")

    prompt = _joined(model.messages)
    assert _ID_CARD in prompt


def test_public_demo_masks_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "pii_mask_before_llm", True)
    ctx = ProjectContext()
    ctx.data_classification = "public_demo"
    model = _CapturingChatModel()
    monkeypatch.setattr("stages.base.get_llm_for_stage_with_context", lambda stage, ctx: model)

    _TestExecutor().run(ctx, f"我的身份证是 {_ID_CARD}")

    prompt = _joined(model.messages)
    assert _MASKED_ID_CARD in prompt
    assert _ID_CARD not in prompt


def test_init_node_outbound_messages_are_masked(monkeypatch):
    import graph.nodes as graph_nodes

    monkeypatch.setattr(settings, "pii_mask_before_llm", False)
    monkeypatch.setattr(graph_nodes.settings, "llm_mode", "real")
    model = _CapturingChatModel()
    monkeypatch.setattr(graph_nodes, "_get_init_llm", lambda: model)

    ctx = ProjectContext()
    ctx.data_classification = "sensitive_personal"
    graph_nodes.node_init(ctx, f"我的身份证是 {_ID_CARD}")

    prompt = _joined(model.messages)
    assert _MASKED_ID_CARD in prompt
    assert _ID_CARD not in prompt


def test_judge_outbound_messages_are_masked(monkeypatch):
    monkeypatch.setattr(settings, "pii_mask_before_llm", False)
    ctx = ProjectContext()
    ctx.data_classification = "sensitive_personal"
    case = EvalCase(
        session_id=ctx.session_id,
        input_payload="input",
        expected_behavior="expected",
        pass_criteria=["criterion"],
    )
    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        input_payload=case.input_payload,
        expected_behavior=case.expected_behavior,
        pass_criteria=list(case.pass_criteria),
        actual_output=f"模型输出了身份证 {_ID_CARD}",
    )
    model = _CapturingChatModel(
        content='{"suggested_result": "passed", "rationale": "ok", "confidence": 0.5}'
    )
    monkeypatch.setattr(eval_llm_judge, "_get_judge_llm", lambda: model)

    eval_llm_judge.generate_llm_judge_suggestion(ctx, case, run)

    prompt = _joined(model.messages)
    assert _MASKED_ID_CARD in prompt
    assert _ID_CARD not in prompt


def test_send_message_scans_chat_pii_before_outbound(monkeypatch):
    import graph.nodes as graph_nodes

    monkeypatch.setattr(settings, "pii_mask_before_llm", False)
    monkeypatch.setattr(graph_nodes.settings, "llm_mode", "real")
    model = _CapturingChatModel(content="请补充更多信息")
    monkeypatch.setattr(graph_nodes, "_get_init_llm", lambda: model)

    ctx = ProjectContext()
    ctx.data_classification = "business_internal"
    service = SessionService()

    def fake_turn(state):
        return graph_nodes.node_init(state, state.pending_input)

    with (
        patch.object(service, "get_session", return_value=ctx),
        patch("core.session_service.execute_one_turn", side_effect=fake_turn),
        patch("core.session_service.session_store"),
        patch("core.session_service.context_cache"),
    ):
        _reply, updated = service.send_message(ctx.session_id, f"我的身份证是 {_ID_CARD}")

    prompt = _joined(model.messages)
    assert _MASKED_ID_CARD in prompt
    assert _ID_CARD not in prompt
    assert updated.data_classification == "sensitive_personal"
    assert any(f.risk_type == "sensitive_info" for f in updated.safety_findings)


class _MaterialPromptExecutor(_TestExecutor):
    def build_system_prompt(self, ctx: ProjectContext) -> str:
        return "用户材料原文：\n" + "\n".join(ctx.user_materials)


def test_material_pii_is_masked_before_outbound(monkeypatch):
    monkeypatch.setattr(settings, "pii_mask_before_llm", False)
    ctx = ProjectContext()
    ctx.data_classification = "business_internal"
    ctx.user_materials.append(f"身份证 {_ID_CARD}")
    add_findings_dedup(ctx, scan_user_materials(ctx, ctx.user_materials, stage_id=1))
    assert ctx.data_classification == "sensitive_personal"

    model = _CapturingChatModel()
    monkeypatch.setattr("stages.base.get_llm_for_stage_with_context", lambda stage, ctx: model)

    _MaterialPromptExecutor().run(ctx, "请分析补充材料")

    prompt = _joined(model.messages)
    assert _MASKED_ID_CARD in prompt
    assert _ID_CARD not in prompt


def test_sensitive_non_text_content_fails_closed():
    message = HumanMessage(content=[{"type": "text", "text": _ID_CARD}])
    with pytest.raises(OutboundPIIBlockedError):
        guard_messages([message], classification="sensitive_personal")
