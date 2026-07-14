# core/evidence_service.py
from __future__ import annotations

import re
from datetime import datetime

from core.audit_service import append_audit_event
from core.config import settings
from core.models import EvidenceSource, ProjectContext
from tools.evidence_ranker import result_to_evidence
from tools.safety_classifier import mask_pii_in_text
from tools.search import SearchResult


def _evidence_key(evidence: EvidenceSource) -> tuple[str, str]:
    return ((evidence.url or "").strip().lower(), evidence.title.strip().lower())


def add_or_update_evidence(ctx: ProjectContext, evidence: EvidenceSource) -> EvidenceSource:
    """按 url/title 去重，保留已有 evidence_id。"""
    key = _evidence_key(evidence)
    for existing in ctx.evidence_sources:
        if _evidence_key(existing) == key:
            existing.source_type = evidence.source_type
            existing.credibility_score = max(existing.credibility_score, evidence.credibility_score)
            if evidence.summary and not existing.summary:
                existing.summary = evidence.summary
            if evidence.claims:
                existing.claims = list(dict.fromkeys(existing.claims + evidence.claims))
            return existing
    ctx.evidence_sources.append(evidence)
    return evidence


def evidence_sources_from_search_results(
    ctx: ProjectContext,
    search_results: list[SearchResult],
) -> list[EvidenceSource]:
    created: list[EvidenceSource] = []
    for result in search_results:
        evidence = add_or_update_evidence(ctx, result_to_evidence(ctx, result))
        created.append(evidence)
    return created


def evidence_sources_from_user_materials(
    ctx: ProjectContext,
    materials: list[str],
    *,
    start_index: int = 0,
) -> list[EvidenceSource]:
    """把用户补充资料资产化为 EvidenceSource。

    使用 USER-EVID-N 这类稳定 ID，便于阶段输出和报告引用。
    """
    created: list[EvidenceSource] = []
    for offset, material in enumerate(materials):
        index = start_index + offset + 1
        summary = (material or "").strip()
        if not summary:
            continue
        evidence = EvidenceSource(
            evidence_id=f"USER-EVID-{index}",
            session_id=ctx.session_id,
            title=f"User Material {index}",
            url=None,
            source_type="user_material",
            credibility_score=0.75,
            summary=summary[:2000],
            claims=[summary[:500]],
        )
        created.append(add_or_update_evidence(ctx, evidence))
    return created


def format_evidence_for_prompt(
    evidence_sources: list[EvidenceSource],
    user_materials: list[str],
) -> str:
    mask = settings.pii_mask_before_llm
    sections: list[str] = []
    if evidence_sources:
        sections.append("### Evidence Sources（阶段输出必须引用 evidence_id）")
        for ev in evidence_sources:
            summary = mask_pii_in_text(ev.summary[:800]) if mask else ev.summary[:800]
            sections.append(
                f"[{ev.evidence_id}]\n"
                f"Title: {ev.title}\n"
                f"Source Type: {ev.source_type}\n"
                f"Credibility: {ev.credibility_score}\n"
                f"URL: {ev.url or 'N/A'}\n"
                f"Summary: {summary}\n"
            )

    # 兼容尚未资产化的历史上下文；新资料会通过 USER-EVID-N 出现在 Evidence Sources。
    material_ids = {
        ev.evidence_id
        for ev in evidence_sources
        if ev.source_type == "user_material" and ev.evidence_id.startswith("USER-EVID-")
    }
    if user_materials and not material_ids:
        sections.append("### 人工补充资料")
        for i, material in enumerate(user_materials, 1):
            masked_material = mask_pii_in_text(material) if mask else material
            sections.append(f"[USER-MATERIAL-{i}]\n{masked_material}\n")

    if not sections:
        return "（暂无外部资料，请基于已有知识进行分析，并对不确定项标注【需核验】）"
    return "\n".join(sections)


def extract_evidence_ids(text: str) -> list[str]:
    """提取 EVID-* 与 USER-EVID-* 形式的证据 ID。"""
    return list(dict.fromkeys(re.findall(r"(?:USER-)?EVID-[A-Za-z0-9_-]+", text or "")))


def _failure_mode_evidence_ids(fm) -> list[str]:
    ids = []
    ids.extend(getattr(fm, "evidence_ids", []) or [])
    ids.extend(extract_evidence_ids(getattr(fm, "evidence", "") or ""))
    return list(dict.fromkeys(ids))


def link_failure_modes_to_evidence(ctx: ProjectContext) -> None:
    """根据 FailureMode.evidence_ids / evidence 中的 evidence_id 建立反向引用。"""
    if not ctx.stage_1_output:
        return
    evidence_by_id = {ev.evidence_id: ev for ev in ctx.evidence_sources}
    for fm in ctx.stage_1_output.failure_modes:
        ids = _failure_mode_evidence_ids(fm)
        fm.evidence_ids = ids
        for evidence_id in ids:
            ev = evidence_by_id.get(evidence_id)
            if ev and fm.id not in ev.used_by_failure_mode_ids:
                ev.used_by_failure_mode_ids.append(fm.id)


def verify_evidence_source(
    ctx: ProjectContext,
    evidence_id: str,
    note: str = "",
    verified_by: str = "user",
) -> EvidenceSource:
    for ev in ctx.evidence_sources:
        if ev.evidence_id == evidence_id:
            before = ev.model_dump(mode="json")
            ev.verified = True
            ev.verified_by = verified_by
            ev.verified_at = datetime.utcnow()
            ev.verification_note = note
            append_audit_event(
                ctx,
                actor="user",
                event_type="evidence_verified",
                target_type="evidence_source",
                target_id=evidence_id,
                before=before,
                after=ev,
                metadata={"note": note},
            )
            return ev
    raise ValueError(f"Evidence not found: {evidence_id}")
