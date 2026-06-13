# tools/source_classifier.py
from __future__ import annotations

from urllib.parse import urlparse

from tools.evidence_filters import is_low_quality_source

OFFICIAL_HINTS = (
    "docs.",
    "developer.",
    "developers.",
    "learn.",
    "help.",
    "support.",
)


def classify_source(url: str | None, title: str = "") -> str:
    """规则型来源分类，避免在 evidence 最小闭环中引入额外 LLM 调用。"""
    if not url:
        return "user_material"
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if is_low_quality_source(url, title):
        return "unknown"
    if "github.com" in host:
        return "github"
    if any(
        domain in host
        for domain in ("arxiv.org", "doi.org", "semanticscholar.org", "pubmed.ncbi.nlm.nih.gov")
    ):
        return "paper"
    if any(hint in host for hint in OFFICIAL_HINTS) or path.startswith("/docs"):
        return "official_doc"
    if any(
        domain in host
        for domain in (
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "nytimes.com",
            "theguardian.com",
            "wsj.com",
        )
    ):
        return "news"
    if any(
        domain in host
        for domain in ("reddit.com", "stackoverflow.com", "medium.com", "dev.to", "zhihu.com")
    ):
        return (
            "forum"
            if "reddit.com" in host or "stackoverflow.com" in host or "zhihu.com" in host
            else "blog"
        )
    return "unknown"
