# tools/evidence_filters.py
from __future__ import annotations

from urllib.parse import urlparse

LOW_QUALITY_DOMAIN_HINTS = (
    "contentfarm",
    "clickbait",
    "best10",
    "top10",
    "coupon",
    "casino",
    "essaybot",
)
LOW_QUALITY_TITLE_HINTS = (
    "ultimate list",
    "you won't believe",
    "top 10",
    "best 10",
    "秘密技巧",
    "震惊",
)


def is_low_quality_source(url: str | None, title: str = "") -> bool:
    """Rule-based low-quality source guard without extending EvidenceSource.source_type."""
    host = (urlparse(url or "").netloc or "").lower()
    haystack = f"{host} {title}".lower()
    return any(hint in haystack for hint in LOW_QUALITY_DOMAIN_HINTS + LOW_QUALITY_TITLE_HINTS)
