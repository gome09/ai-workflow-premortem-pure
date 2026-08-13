# Stage 3 Risk-Adaptive Gate

> **Last updated:** 2026-07-27
> **Status:** Implemented and validated (including `expert review` for CRITICAL tier — T3.3)
> **Tests:** 原风险自适应门禁验证 26 项 + 3 个 smoke；expert-review 为 T3.3 后续能力，由 `tests/test_expert_review_gate_v110.py` 单独覆盖

---

## Problem

Before this change, Stage 3 used a uniform strong gate profile for all projects. This caused low-risk projects (e.g., personal reading plans) to be blocked by gates designed for high-risk domains:

- `redteam_coverage` — required RedTeamCase generation and approval
- `eval_regression` — required baseline experiment and comparison
- `trace_backfill_gap` — required trace-to-EvalCase conversion
- `stage3_eval_failure` — required eval coverage for all high-severity nodes

These gates are appropriate for CRITICAL-risk domains (medical, financial) but excessive for LOW-risk personal tools.

---

## Solution

Implemented risk-adaptive Stage 3 gate that classifies projects into risk tiers and applies appropriate gate profiles.

### New Files

| File | Purpose |
|------|---------|
| `core/gates/risk_profile.py` | Risk classification logic, `ProjectGateRiskTier`, `Stage3GateProfile` |

### Modified Files

| File | Change |
|------|--------|
| `core/gates/rules/redteam_coverage.py` | Low/medium risk skip non-safety redteam blocks |
| `core/gates/rules/eval_regression.py` | Low/medium risk skip non-gated regression blocks |
| `core/gates/rules/trace_backfill_gap.py` | Low risk skip trace backfill blocks |
| `core/gates/rules/stage3_eval_failure.py` | Low risk only require critical node eval coverage |

---

## Risk Tiers

下表关键词仅为便于理解的示例；完整且可执行的中英文关键词、场景覆盖和优先级以 `core/gates/risk_profile.py` 为准。

| Tier | Domain Keyword Examples | Gate Profile |
|------|----------------|--------------|
| **CRITICAL** | 药物、处方、诊断、患者、临床、医疗、手术、肿瘤、急诊, drug, medication, prescription, surgery, oncology | Strongest: all gates（含 expert_review） |
| **HIGH** | 金融、贷款、法律、合同、儿童、学生、认证、多租户、自动发送、**心理健康**、**军事**、核电、自动驾驶, finance, legal, mental health, military | Strong: redteam + regression + trace |
| **MEDIUM** | 团队管理、项目协作 (no explicit low-risk markers) | eval coverage + failed eval |
| **LOW** | 个人、学习、读书、笔记、本地、非生产, personal, learning | 与 MEDIUM 相同：eval coverage + failed eval |

> 两处易错点：①「心理健康」与「军事」属 **HIGH** 而非 CRITICAL（分别对应 `_HIGH_KEYWORDS` 的 `mental health domain` 与 `nuclear/military domain`）；②**LOW 档并非只有安全底线**——`build_stage3_gate_profile` 中 LOW 与 MEDIUM 的 `require_*` 标志逐字段相同，两档都强制 `require_eval_coverage` 与 `require_failed_eval_resolution`，仅 rationale 文案不同。注意：**字段值相同 ≠ 最终阻断行为等价**——规则实现（如 `stage3_eval_failure.py`）消费 `require_*` 标志后，内部还会按 risk tier 做细分阈值判断（例：LOW 只要求 critical nodes 覆盖，MEDIUM 要求 high+critical 节点覆盖），详见下方 Gate Behavior Matrix。

---

## Gate Behavior Matrix

| Gate Rule | LOW | MEDIUM | HIGH | CRITICAL |
|-----------|-----|--------|------|----------|
| missing output | ✅ block | ✅ block | ✅ block | ✅ block |
| parser error | ✅ block | ✅ block | ✅ block | ✅ block |
| pending blocking action | ✅ block | ✅ block | ✅ block | ✅ block |
| rejected action | ✅ block | ✅ block | ✅ block | ✅ block |
| open high/critical safety finding requiring human review | ✅ block | ✅ block | ✅ block | ✅ block |
| stale dependency | ✅ block | ✅ block | ✅ block | ✅ block |
| eval coverage (critical nodes) | ✅ block | ✅ block | ✅ block | ✅ block |
| eval coverage (high nodes) | — | ✅ block | ✅ block | ✅ block |
| failed eval resolution | ✅ block | ✅ block | ✅ block | ✅ block |
| redteam coverage (safety gaps) | ✅ block | ✅ block | ✅ block | ✅ block |
| redteam coverage (node gaps) | — | — | ✅ block | ✅ block |
| eval regression (gate_required) | ✅ block | ✅ block | ✅ block | ✅ block |
| eval regression (non-gated) | — | — | ✅ block | ✅ block |
| trace backfill | — | — | ✅ block | ✅ block |
| expert review | — | — | — | ✅ block (T3.3) |

> **Note:** `Stage3GateProfile.require_expert_review` is now consumed by the `expert_review` gate rule (`core/gates/rules/expert_review.py`, T3.3). CRITICAL-risk projects must have an approved expert-review action before advancing past Stage 3.

---

## Safety Bottom Line

Regardless of risk tier, these safety底线 **always block**:

- Missing stage output
- Parser error
- Unresolved blocking pending action
- Rejected action without remediation
- Open high/critical safety finding that requires human review
- Stale dependency

---

## Validation

### Unit Tests

```
tests/test_stage3_risk_adaptive_gate.py — 26 passed
```

Covers:
- LOW/MEDIUM/HIGH/CRITICAL tier classification
- Gate rule behavior per tier
- Safety底线 enforcement
- Domain keyword detection

### Smoke Tests

| Scenario | Risk Tier | Result |
|----------|-----------|--------|
| Personal reading planner | LOW | PASS |
| Customer feedback system | MEDIUM | PASS |
| Medication management | CRITICAL | PASS |

### Real Session Verification

Session `ae08e110-9c31-47b4-a9c8-bf1336991a94` (LOW risk):
- Redteam/regression/trace rules evaluated → 0 blockers
- Safety底线 rules evaluated → pending_action + eval_failure blockers (correct)

**Report:** [../archive/verification-reports/risk_adaptive_gate_final_validation.md](../archive/verification-reports/risk_adaptive_gate_final_validation.md)

---

## Design Principles

1. **Risk tiering is not disabling safety** — LOW risk reduces advanced gates, not safety底线
2. **Stage 1 severity is input, not sole decision** — a reading plan's "high" failure mode should not trigger medical-grade gates
3. **`gate_required` datasets always block** — even LOW risk, explicitly marked datasets trigger regression gates
4. **High-risk domain keywords trigger strong gates** — medical, financial, legal projects cannot bypass
