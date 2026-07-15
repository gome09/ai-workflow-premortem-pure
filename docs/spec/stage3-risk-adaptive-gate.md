# Stage 3 Risk-Adaptive Gate

> **Last updated:** 2026-07-14
> **Status:** Implemented and validated (including `expert review` for CRITICAL tier — T3.3)
> **Tests:** 26/26 PASS, 3 smokes PASS

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

| Tier | Domain Keywords | Gate Profile |
|------|----------------|--------------|
| **CRITICAL** | 药物、处方、诊断、患者、临床、drug, medication, prescription | Strongest: all gates |
| **HIGH** | 金融、贷款、法律、合同、儿童、认证、多租户, finance, legal | Strong: redteam + regression + trace |
| **MEDIUM** | 团队管理、项目协作 (no explicit low-risk markers) | Medium: eval coverage + failed eval |
| **LOW** | 个人、学习、读书、笔记、本地、非生产, personal, learning | Basic: safety底线 only |

---

## Gate Behavior Matrix

| Gate Rule | LOW | MEDIUM | HIGH | CRITICAL |
|-----------|-----|--------|------|----------|
| missing output | ✅ block | ✅ block | ✅ block | ✅ block |
| parser error | ✅ block | ✅ block | ✅ block | ✅ block |
| pending blocking action | ✅ block | ✅ block | ✅ block | ✅ block |
| rejected action | ✅ block | ✅ block | ✅ block | ✅ block |
| open critical safety finding | ✅ block | ✅ block | ✅ block | ✅ block |
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
- Open critical safety finding
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
