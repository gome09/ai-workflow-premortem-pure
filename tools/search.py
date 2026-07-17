# tools/search.py
from __future__ import annotations

import logging
from dataclasses import dataclass

from tavily import TavilyClient

from core.config import settings
from core.models import ProjectContext

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    score: float


class ResearchTool:
    """Tavily 搜索封装，专为阶段一设计。"""

    _DUMMY_KEY_INDICATORS = ("healthcheck_dummy", "dummy", "test_dummy")

    def __init__(self) -> None:
        self._client: TavilyClient | None = None
        self._search_checked: bool = False
        self._search_available: bool = False

    @property
    def external_search_available(self) -> bool:
        """Evaluate once: is the configured Tavily key usable (non-empty, non-dummy)?"""
        if not self._search_checked:
            key = (settings.tavily_api_key or "").strip()
            if not key:
                self._search_available = False
            elif any(indicator in key.lower() for indicator in self._DUMMY_KEY_INDICATORS):
                self._search_available = False
            else:
                self._search_available = True
            self._search_checked = True
            if not self._search_available:
                logger.info(
                    "External search unavailable: Tavily API key is missing or a dummy value."
                )
        return self._search_available

    def _get_client(self) -> TavilyClient:
        """懒加载 Tavily 客户端，避免导入阶段触发外部服务初始化。"""
        if self._client is None:
            self._client = TavilyClient(api_key=settings.tavily_api_key)
        return self._client

    def generate_queries(self, ctx: ProjectContext) -> list[str]:
        """
        基于项目背景生成 3-5 个搜索查询。
        此处使用规则生成，避免引入额外 LLM 调用消耗。
        """
        base = f"{ctx.research_target} {ctx.domain}"
        queries = [
            f"{base} 失败案例 局限性",
            f"{base} failure modes limitations",
            f"{ctx.research_target} 幻觉 错误 {ctx.domain}",
            f"{base} 最佳实践 注意事项",
            f"{ctx.research_target} benchmark {ctx.domain} problems",
        ]
        return queries

    def search(self, ctx: ProjectContext, max_results: int = 5) -> list[SearchResult]:
        """执行搜索，返回去重后的结果。

        当 Tavily API key 为空或为已知 dummy 值时，不发起任何外部 HTTP 请求，
        返回空结果列表。调用方（如 Stage 1 executor）应能处理空搜索结果。
        """
        if settings.llm_mode == "mock":
            return [
                SearchResult(
                    title="Mock Evidence Source 1 — Demo Mode",
                    url="https://mock.example.com/EVID-MOCK-001",
                    content="This is a pre-built mock evidence source for demo and offline CI mode. No network call was made.",
                    score=0.95,
                ),
                SearchResult(
                    title="Mock Evidence Source 2 — Demo Mode",
                    url="https://mock.example.com/EVID-MOCK-002",
                    content="This is a second pre-built mock evidence source. The full workflow runs end-to-end without any API keys.",
                    score=0.90,
                ),
            ]
        if not self.external_search_available:
            return []

        queries = self.generate_queries(ctx)
        all_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for query in queries:
            try:
                response = self._get_client().search(
                    query=query,
                    search_depth="advanced",
                    max_results=3,
                )
                for r in response.get("results", []):
                    if r["url"] not in seen_urls:
                        seen_urls.add(r["url"])
                        all_results.append(
                            SearchResult(
                                title=r.get("title", ""),
                                url=r["url"],
                                content=r.get("content", ""),
                                score=r.get("score", 0.0),
                            )
                        )
            except Exception as e:
                logger.warning(f"Search query failed: '{query}' → {e}")
                continue

        # 按相关度排序，取前 max_results 条
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:max_results]

    def format_for_prompt(
        self,
        search_results: list[SearchResult],
        user_materials: list[str],
    ) -> str:
        """将搜索结果和人工资料格式化为 Prompt 可用的文本块"""
        sections = []

        if search_results:
            sections.append("### 搜索资料")
            for i, r in enumerate(search_results, 1):
                sections.append(f"[资料{i}] {r.title}\n来源：{r.url}\n{r.content[:800]}\n")

        if user_materials:
            sections.append("### 人工补充资料")
            for i, m in enumerate(user_materials, 1):
                sections.append(f"[补充{i}]\n{m}\n")

        if not sections:
            return "（暂无外部资料，请基于已有知识进行分析，并对不确定项标注【需核验】）"

        return "\n".join(sections)


research_tool = ResearchTool()
