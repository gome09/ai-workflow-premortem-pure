# tools/evidence_ranker.py
from __future__ import annotations

import uuid

from core.config import settings
from core.models import EvidenceSource, ProjectContext
from tools.evidence_filters import is_low_quality_source
from tools.search import SearchResult
from tools.source_classifier import classify_source

SOURCE_WEIGHTS = {
    "official_doc": 1.0,
    "paper": 0.9,
    "github": 0.8,
    "news": 0.6,
    "blog": 0.4,
    "forum": 0.3,
    "user_material": 0.7,
    "unknown": 0.2,
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def score_evidence(result: SearchResult, source_type: str) -> float:
    tavily_score = _clamp(float(result.score or 0.0))
    source_score = SOURCE_WEIGHTS.get(source_type, 0.2)
    completeness = _clamp(len(result.content or "") / 1200.0)
    score = tavily_score * 0.55 + source_score * 0.35 + completeness * 0.1
    if is_low_quality_source(result.url, result.title):
        score = min(score, 0.2)
    return round(_clamp(score), 3)


def result_to_evidence(ctx: ProjectContext, result: SearchResult) -> EvidenceSource:
    source_type = classify_source(result.url, result.title)
    evidence_id = None
    if settings.llm_mode == "mock" and result.url:
        tail = result.url.rstrip("/").rsplit("/", 1)[-1]
        if tail.startswith("EVID-"):
            evidence_id = tail
    return EvidenceSource(
        evidence_id=evidence_id or f"EVID-{str(uuid.uuid4())[:8]}",
        session_id=ctx.session_id,
        title=result.title or result.url or "Untitled evidence",
        url=result.url,
        source_type=source_type,
        credibility_score=score_evidence(result, source_type),
        summary=(result.content or "")[:1000],
        claims=[(result.content or "")[:300]] if result.content else [],
    )
