# tests/test_eval_isolation.py
"""Evaluation isolation: the model under test never receives oracle fields.

覆盖：
- llm_node 执行 prompt 只含节点模板与 input_payload，不含 expected_behavior / pass_criteria；
- 移除 oracle 后 EvalRun 与 EvalJudgment 仍能正常生成；
- dry_run 不调用被测模型；
- judge 路径允许读取 oracle（评估器职责），但不会拿到被测 system prompt；
- 审计 metadata 明确区分模拟执行与真实目标执行。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import eval_llm_judge, eval_runner
from core.config import settings
from core.eval_runner import run_eval_case
from core.models import (
    EvalCase,
    EvalRun,
    ProjectContext,
    Stage2Output,
    WorkflowNode,
)

_ORACLE_BEHAVIOR = "SECRET-ORACLE-BEHAVIOR"
_ORACLE_CRITERION = "SECRET-ORACLE-CRITERION"
_INPUT_PAYLOAD = "input payload for the node"
_SUT_SYSTEM_PROMPT = "You are executing one deterministic workflow node"


class _CapturingChatModel:
    def __init__(self, content: str = "candidate output") -> None:
        self.messages: list = []
        self.content = content

    def invoke(self, messages):
        self.messages = list(messages)
        return SimpleNamespace(content=self.content)


def _ctx_with_eval_case() -> tuple[ProjectContext, EvalCase]:
    ctx = ProjectContext()
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N1",
                stage_name="draft",
                model_assigned="deepseek-chat",
                human_action="review",
                check_criteria="must cite evidence",
                failure_modes_addressed=[],
                prompt_template="Draft with citations only.",
            )
        ]
    )
    case = EvalCase(
        session_id=ctx.session_id,
        target_node_id="N1",
        input_payload=_INPUT_PAYLOAD,
        expected_behavior=_ORACLE_BEHAVIOR,
        pass_criteria=[_ORACLE_CRITERION],
    )
    ctx.eval_cases.append(case)
    return ctx, case


def _joined_messages(model: _CapturingChatModel) -> str:
    return "\n".join(str(message.content) for message in model.messages)


def test_llm_node_prompt_excludes_expected_behavior_and_pass_criteria(monkeypatch):
    ctx, case = _ctx_with_eval_case()
    model = _CapturingChatModel()
    monkeypatch.setattr(eval_runner, "get_llm_for_stage", lambda stage: model)

    run = run_eval_case(ctx, eval_id=case.eval_id, run_mode="llm_node")

    prompt = _joined_messages(model)
    assert _INPUT_PAYLOAD in prompt
    assert _ORACLE_BEHAVIOR not in prompt
    assert _ORACLE_CRITERION not in prompt

    # 移除 oracle 后评估结果仍然正常生成。
    assert run.status == "completed"
    assert run.actual_output == "candidate output"
    assert run.judge_result is not None
    assert any(judgment.eval_run_id == run.run_id for judgment in ctx.eval_judgments)


def test_dry_run_does_not_call_model(monkeypatch):
    ctx, case = _ctx_with_eval_case()

    def _fail(stage):
        raise AssertionError("dry_run must not call the model under test")

    monkeypatch.setattr(eval_runner, "get_llm_for_stage", _fail)
    run = run_eval_case(ctx, eval_id=case.eval_id, run_mode="dry_run")

    assert run.status == "completed"
    assert run.actual_output.startswith("DRY_RUN")


def test_judge_path_receives_oracle_but_not_sut_system_prompt(monkeypatch):
    ctx, case = _ctx_with_eval_case()
    judge_model = _CapturingChatModel(
        content='{"suggested_result": "passed", "rationale": "matches criteria", "confidence": 0.8}'
    )
    monkeypatch.setattr(eval_llm_judge, "_get_judge_llm", lambda: judge_model)

    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        input_payload=case.input_payload,
        expected_behavior=case.expected_behavior,
        pass_criteria=list(case.pass_criteria),
        actual_output="candidate output",
    )
    suggestion = eval_llm_judge.generate_llm_judge_suggestion(ctx, case, run)

    prompt = _joined_messages(judge_model)
    assert _ORACLE_BEHAVIOR in prompt
    assert _ORACLE_CRITERION in prompt
    assert _SUT_SYSTEM_PROMPT not in prompt
    assert suggestion is not None
    assert suggestion["suggested_result"] == "passed"


@pytest.mark.parametrize(
    ("run_mode", "llm_mode", "expected_kind"),
    [
        ("manual", None, "manual_simulation"),
        ("dry_run", None, "dry_run_simulation"),
        ("llm_node", "real", "platform_model_execution"),
        ("llm_node", "mock", "mock_model_execution"),
    ],
)
def test_audit_metadata_distinguishes_execution_kind(
    monkeypatch, run_mode, llm_mode, expected_kind
):
    if llm_mode is not None:
        monkeypatch.setattr(settings, "llm_mode", llm_mode)
    ctx, case = _ctx_with_eval_case()
    model = _CapturingChatModel()
    monkeypatch.setattr(eval_runner, "get_llm_for_stage", lambda stage: model)

    run_eval_case(ctx, eval_id=case.eval_id, run_mode=run_mode)

    event = next(item for item in ctx.audit_events if item.event_type == "eval_run_created")
    assert event.metadata["execution_kind"] == expected_kind
    assert event.metadata["oracle_fields_included"] is False
