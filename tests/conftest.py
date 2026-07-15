# tests/conftest.py
from __future__ import annotations

import os

# 测试收集阶段会导入 core.config。这里提供 dummy 值，避免单元测试依赖真实密钥。
os.environ.setdefault("JWT_SECRET", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("DEEPSEEK_API_KEY", "test_deepseek_key")
os.environ.setdefault("TAVILY_API_KEY", "test_tavily_key")
os.environ.setdefault("POSTGRES_PASSWORD", "test_postgres_password")

from unittest.mock import MagicMock

import pytest

from auth.jwt import create_access_token


@pytest.fixture
def auth_headers():
    token = create_access_token({"sub": "test-user", "tenant_id": "test-tenant", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def disable_rate_limiting(monkeypatch):
    """Disable slowapi rate limiting during all tests to prevent flaky 429s."""
    try:
        from api.limiter import limiter

        monkeypatch.setattr(limiter, "enabled", False)
    except Exception:
        pass


from core.models import FailureMode, ProjectContext, SessionState, Stage1Output


@pytest.fixture
def base_ctx() -> ProjectContext:
    """基础测试上下文，已填写项目信息"""
    ctx = ProjectContext()
    ctx.research_target = "GPT-4o"
    ctx.domain = "法律文书生成"
    ctx.goal = "提高合同起草准确率"
    ctx.current_state = SessionState.S1_RUNNING
    return ctx


@pytest.fixture
def ctx_with_stage1(base_ctx) -> ProjectContext:
    """已完成阶段一的上下文"""
    base_ctx.stage_1_output = Stage1Output(
        failure_modes=[
            FailureMode(
                id="FM-001",
                category="幻觉",
                description="虚构不存在的法律条文",
                severity="high",
                evidence="多份测试报告记录",
                needs_verification=False,
            ),
            FailureMode(
                id="FM-002",
                category="上下文遗忘",
                description="长文档中遗漏前置条款约束",
                severity="medium",
                evidence="内部压测结果",
                needs_verification=True,
            ),
        ],
        direct_conclusion="GPT-4o 在法律文书领域存在显著幻觉风险，需要强制核验机制。",
        search_sources=["https://example.com/report1"],
        raw_summary="完整原始输出...",
    )
    base_ctx.current_state = SessionState.S2_RUNNING
    return base_ctx


@pytest.fixture
def mock_llm_response():
    """Mock LLM 响应"""
    mock = MagicMock()
    mock.content = "Mock AI 响应内容"
    return mock


@pytest.fixture
def mock_search_results():
    """Mock 搜索结果"""
    from tools.search import SearchResult

    return [
        SearchResult(
            title="GPT-4o 法律应用研究",
            url="https://example.com/1",
            content="研究发现 GPT-4o 在法律文书生成中存在幻觉问题...",
            score=0.95,
        ),
        SearchResult(
            title="AI 法律工具评测",
            url="https://example.com/2",
            content="测试显示大模型容易遗忘长上下文中的约束条件...",
            score=0.88,
        ),
    ]
