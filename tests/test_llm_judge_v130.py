# tests/test_llm_judge_v130.py
"""T3.6 LLM Judge 建议判分契约测试（spec governance-platform §5）。

覆盖：
- 两个 flag 默认 off；EvalRun.llm_judge_suggestion 字段默认 None
- mock 模式下建议生成器输出结构化建议；非法 LLM 输出静默降级为 None
- flag off 时 eval 主路径行为与现状完全一致
- flag on 时建议附着但不改写 judge_result 终值
- autofinal 仅对 LOW/MEDIUM 会话采纳；HIGH/CRITICAL 永远保持 needs_review
"""

from __future__ import annotations

from core.config import Settings, settings
from core.eval_llm_judge import generate_llm_judge_suggestion
from core.eval_runner import run_eval_cases
from core.models import (
    EvalCase,
    EvalRun,
    FailureMode,
    ProjectContext,
    Stage1Output,
    Stage2Output,
    WorkflowNode,
)


def test_llm_judge_flags_default_off():
    s = Settings(jwt_secret="x" * 32, llm_mode="mock", storage_backend="sqlite", _env_file=None)
    assert s.eval_llm_judge is False
    assert s.eval_llm_judge_autofinal is False


def test_eval_run_has_llm_judge_suggestion_field():
    run = EvalRun(session_id="s", eval_id="e", input_payload="p", expected_behavior="b")
    assert run.llm_judge_suggestion is None


def _needs_review_run() -> tuple[ProjectContext, EvalCase, EvalRun]:
    ctx = ProjectContext()
    case = EvalCase(
        session_id=ctx.session_id,
        input_payload="adversarial input",
        expected_behavior="refuse politely",
        pass_criteria=["must refuse"],
    )
    run = EvalRun(
        session_id=ctx.session_id,
        eval_id=case.eval_id,
        input_payload=case.input_payload,
        expected_behavior=case.expected_behavior,
        pass_criteria=list(case.pass_criteria),
        actual_output="I cannot help with that.",
        judge_result="needs_review",
        judge_mode="rule",
    )
    return ctx, case, run


def test_llm_judge_suggestion_mock_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    ctx, case, run = _needs_review_run()
    suggestion = generate_llm_judge_suggestion(ctx, case, run)
    assert suggestion is not None
    assert suggestion["suggested_result"] in ("passed", "failed")
    assert isinstance(suggestion["rationale"], str) and suggestion["rationale"]
    assert 0.0 <= suggestion["confidence"] <= 1.0


def test_llm_judge_suggestion_invalid_llm_output_returns_none(monkeypatch):
    class _BadResponse:
        content = "not json at all"

    class _BadLLM:
        def invoke(self, messages):
            return _BadResponse()

    monkeypatch.setattr("core.eval_llm_judge._get_judge_llm", lambda: _BadLLM())
    ctx, case, run = _needs_review_run()
    assert generate_llm_judge_suggestion(ctx, case, run) is None


def _ctx_with_case(goal: str = "personal study helper for my own notes") -> ProjectContext:
    """构造带一个 dry_run 即判 needs_review 的用例的 ctx；goal 决定风险分层。

    注意：FailureMode.description 避开风险关键词（如 'minor' 命中 child-safety 正则）。
    """
    ctx = ProjectContext()
    ctx.goal = goal
    ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-1",
                category="hallucination",
                description="wording drift in generated summaries",
                severity="low",
            )
        ]
    )
    ctx.stage_2_output = Stage2Output(
        workflow_nodes=[
            WorkflowNode(
                node_id="N1",
                stage_name="draft",
                model_assigned="mock-model",
                human_action="review",
                check_criteria="cite evidence",
                failure_modes_addressed=["FM-1"],
                prompt_template="Draft.",
            )
        ]
    )
    ctx.eval_cases.append(
        EvalCase(
            session_id=ctx.session_id,
            target_node_id="N1",
            covered_failure_mode_ids=["FM-1"],
            input_payload="payload",
            expected_behavior="behave",
            pass_criteria=["ok"],
        )
    )
    return ctx


def test_judge_flag_off_no_suggestion(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(settings, "eval_llm_judge", False)
    ctx = _ctx_with_case()
    runs = run_eval_cases(ctx, run_mode="dry_run")
    assert runs[0].llm_judge_suggestion is None
    assert runs[0].judge_result == "needs_review"
    assert runs[0].judge_mode == "rule"


def test_judge_flag_on_attaches_suggestion_without_overriding_result(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(settings, "eval_llm_judge", True)
    monkeypatch.setattr(settings, "eval_llm_judge_autofinal", False)
    ctx = _ctx_with_case()
    runs = run_eval_cases(ctx, run_mode="dry_run")
    assert runs[0].llm_judge_suggestion is not None
    assert runs[0].judge_result == "needs_review"  # 建议不改写终值
    assert runs[0].judge_mode == "rule"


def test_autofinal_adopts_suggestion_for_low_risk(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(settings, "eval_llm_judge", True)
    monkeypatch.setattr(settings, "eval_llm_judge_autofinal", True)
    ctx = _ctx_with_case(goal="personal study helper for my own notes")  # LOW 档
    runs = run_eval_cases(ctx, run_mode="dry_run")
    # mock fixture 建议 passed；LOW/MEDIUM 会话允许采纳为终值
    assert runs[0].judge_result == "passed"
    assert runs[0].judge_mode == "llm"
    assert runs[0].llm_judge_suggestion is not None
    assert "autofinal" in runs[0].judge_reason
    # 审计建议链：judgment 推断为 llm 类型并携带建议元数据
    judgment = next(j for j in ctx.eval_judgments if j.eval_run_id == runs[0].run_id)
    assert judgment.judge_type == "llm"
    assert judgment.metadata["llm_judge_suggestion"]["suggested_result"] == "passed"


def test_autofinal_never_applies_to_high_risk(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(settings, "eval_llm_judge", True)
    monkeypatch.setattr(settings, "eval_llm_judge_autofinal", True)
    # healthcare 关键词 → CRITICAL 档（early return，不可被 low-scope 词降档）
    ctx = _ctx_with_case(goal="medical diagnosis assistant for cancer patients 医疗诊断")
    runs = run_eval_cases(ctx, run_mode="dry_run")
    assert runs[0].judge_result == "needs_review"  # 永远待人工
    assert runs[0].judge_mode == "rule"
    assert runs[0].llm_judge_suggestion is not None  # 建议仍附上供人工参考
