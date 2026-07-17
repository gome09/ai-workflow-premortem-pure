# core/llm/adapters/mock_fixtures/llm_judge.py
"""Judge fixture response for the T3.6 LLM judge suggestion path (offline CI/demo).

不走 stage fixture 分发表（mock.py 的 _PROFILE_MODULES/_STAGE_FUNCTIONS）——
judge 不是阶段，由 core/eval_llm_judge.py 的 mock 分支直接导入。
"""

from __future__ import annotations

import json


def judge_response() -> str:
    return json.dumps(
        {
            "suggested_result": "passed",
            "rationale": "Mock judge: actual output matches the refusal expectation in pass criteria.",
            "confidence": 0.85,
        }
    )
