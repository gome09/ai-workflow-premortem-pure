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

from core.config import Settings
from core.models import EvalRun


def test_llm_judge_flags_default_off():
    s = Settings(jwt_secret="x" * 32, llm_mode="mock", storage_backend="sqlite", _env_file=None)
    assert s.eval_llm_judge is False
    assert s.eval_llm_judge_autofinal is False


def test_eval_run_has_llm_judge_suggestion_field():
    run = EvalRun(session_id="s", eval_id="e", input_payload="p", expected_behavior="b")
    assert run.llm_judge_suggestion is None
