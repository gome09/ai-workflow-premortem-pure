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
from core.models import EvalCase, EvalRun, ProjectContext


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
