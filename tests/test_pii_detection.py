# tests/test_pii_detection.py
"""T1.4 PII 检测与出境前掩码 (PII detection & pre-LLM masking) tests.

Covers:
- scan_text on user_materials produces sensitive_info finding (severity high for ID card).
- PII hit auto-upgrades ctx.data_classification to sensitive_personal (T1.1 联动).
- PII detection NOT triggered for stage_N.ai_output locations (avoid LLM-output false positives).
- scan_pii returns correct kinds (email + cn_mobile).
- mask_pii_in_text masks ID card (110101********1234).
- mask_pii_in_text masks email (t***@example.com).
- format_evidence_for_prompt with masking OFF (default) keeps full PII visible.
- format_evidence_for_prompt with masking ON returns masked PII.
"""

from __future__ import annotations

from core.config import settings
from core.evidence_service import format_evidence_for_prompt
from core.models import EvidenceSource, ProjectContext
from tools.safety_classifier import mask_pii_in_text, scan_pii, scan_text

# 18 位身份证号（满足 cn_id_card 正则的日期结构）
_ID_CARD = "110101199001011234"


# ── 1: PII detection produces finding ────────────────────────────────
def test_pii_detection_produces_finding():
    ctx = ProjectContext()
    ctx.data_classification = "business_internal"

    findings = scan_text(
        ctx,
        stage_id=1,
        location="user_materials[0]",
        text=f"用户资料，身份证 {_ID_CARD}",
    )

    pii_findings = [f for f in findings if f.risk_type == "sensitive_info"]
    assert pii_findings, "expected a sensitive_info finding for PII in user_materials"
    # 身份证 severity=high（bank_card 同样 high，max 仍为 high）
    assert any(f.severity == "high" for f in pii_findings)


# ── 2: PII auto-upgrades data_classification ─────────────────────────
def test_pii_auto_upgrades_data_classification():
    ctx = ProjectContext()
    ctx.data_classification = "business_internal"
    assert ctx.data_classification == "business_internal"

    scan_text(
        ctx,
        stage_id=1,
        location="user_materials[0]",
        text=f"身份证 {_ID_CARD}",
    )

    assert ctx.data_classification == "sensitive_personal"


# ── 3: PII detection NOT triggered for LLM output ────────────────────
def test_pii_not_triggered_for_llm_output():
    ctx = ProjectContext()
    ctx.data_classification = "business_internal"

    findings = scan_text(
        ctx,
        stage_id=1,
        location="stage_1.ai_output",
        text=f"AI 输出包含 {_ID_CARD}",
    )

    # location 不以 user_materials / evidence_source 开头，PII 检测应跳过
    assert not any(
        f.risk_type == "sensitive_info" and f.description.startswith("用户材料包含 PII")
        for f in findings
    )
    # 数据分级不应被升级
    assert ctx.data_classification == "business_internal"


# ── 4: scan_pii returns correct kinds ────────────────────────────────
def test_scan_pii_returns_correct_kinds():
    hits = scan_pii("我的邮箱是 test@example.com，手机 13800138000")
    kinds = {kind for _matched, kind, _sev in hits}
    assert "email" in kinds
    assert "cn_mobile" in kinds


# ── 5: mask_pii_in_text masks ID card ────────────────────────────────
def test_mask_pii_in_text_masks_id_card():
    masked = mask_pii_in_text(f"身份证 {_ID_CARD}")
    assert "110101********1234" in masked
    # 完整身份证号不应再出现
    assert _ID_CARD not in masked


# ── 6: mask_pii_in_text masks email ──────────────────────────────────
def test_mask_pii_in_text_masks_email():
    masked = mask_pii_in_text("联系 test@example.com")
    assert "t***@example.com" in masked
    # 完整邮箱不应再出现
    assert "test@example.com" not in masked


# ── 7: format_evidence_for_prompt with masking OFF (default) ─────────
def test_format_evidence_for_prompt_masking_off(monkeypatch):
    monkeypatch.setattr(settings, "pii_mask_before_llm", False)

    evidence = [
        EvidenceSource(
            session_id="test-session",
            title="user-provided evidence",
            source_type="user_material",
            summary=f"身份证 {_ID_CARD}",
        )
    ]
    result = format_evidence_for_prompt(evidence, user_materials=[])

    # 掩码关闭：完整 PII 应可见
    assert _ID_CARD in result


# ── 8: format_evidence_for_prompt with masking ON ────────────────────
def test_format_evidence_for_prompt_masking_on(monkeypatch):
    monkeypatch.setattr(settings, "pii_mask_before_llm", True)

    evidence = [
        EvidenceSource(
            session_id="test-session",
            title="user-provided evidence",
            source_type="user_material",
            summary=f"身份证 {_ID_CARD}",
        )
    ]
    result = format_evidence_for_prompt(evidence, user_materials=[])

    # 掩码开启：身份证应被掩码，完整号码不应出现
    assert "110101********1234" in result
    assert _ID_CARD not in result
