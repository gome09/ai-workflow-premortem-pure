# tests/test_live_llm_smoke.py
"""Opt-in live provider smoke tests.

Never runs by default: requires ``LIVE_LLM_TESTS=1`` plus real credentials.
CI and the offline baseline must not depend on production credentials.
"""

from __future__ import annotations

import os

import pytest

_LIVE = os.getenv("LIVE_LLM_TESTS") == "1"
_PLACEHOLDER_KEYS = {"", "mock", "CHANGE_ME", "test_deepseek_key", "test_tavily_key"}

pytestmark = pytest.mark.skipif(
    not _LIVE,
    reason="LIVE_LLM_TESTS not set; live provider smoke tests are opt-in",
)


def _has_real_key(name: str) -> bool:
    return os.getenv(name, "") not in _PLACEHOLDER_KEYS


@pytest.mark.skipif(not _has_real_key("DEEPSEEK_API_KEY"), reason="real DEEPSEEK_API_KEY missing")
def test_live_stage1_call_and_parse():
    from langchain_core.messages import HumanMessage, SystemMessage

    from core.config import settings
    from core.context_manager import get_llm_for_stage
    from core.llm.outbound_guard import guarded_invoke
    from core.llm.structured_output import StructuredOutputClient
    from core.models import ProjectContext

    if settings.llm_mode != "real":
        pytest.skip("LLM_MODE must be real for the live smoke test")

    ctx = ProjectContext(
        research_target="Internal policy assistant",
        domain="Internal FAQ",
        goal="Answer policy questions with citations",
        data_classification="public_demo",
    )
    llm = get_llm_for_stage(1)
    response = guarded_invoke(
        llm,
        [
            SystemMessage(content="Identify failure modes as a JSON object."),
            HumanMessage(content="Return one failure mode for an internal FAQ assistant."),
        ],
        ctx=ctx,
        stage=1,
    )

    assert str(response.content).strip()
    parsed = StructuredOutputClient().parse_stage_output(1, str(response.content))
    assert parsed.raw_text


@pytest.mark.skipif(
    not all(os.getenv(name) for name in ("LIVE_TARGET_ENDPOINT", "LIVE_TARGET_ALLOWED_HOSTS")),
    reason="LIVE_TARGET_ENDPOINT / LIVE_TARGET_ALLOWED_HOSTS missing",
)
def test_live_target_http_call():
    from core.target_testing import HttpJsonTargetAdapter, TargetSystemConfig

    adapter = HttpJsonTargetAdapter(
        TargetSystemConfig(
            endpoint=os.environ["LIVE_TARGET_ENDPOINT"],
            timeout_seconds=10.0,
        ),
        allowed_hosts=os.environ["LIVE_TARGET_ALLOWED_HOSTS"],
        token=os.getenv("LIVE_TARGET_TOKEN") or None,
    )

    result = adapter.execute("ping", classification="public_demo")

    assert result.outcome in {"success", "failed"}
    assert result.endpoint
