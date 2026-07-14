# Risk-Adaptive Gate — Final Validation Report (Archived)

> **Status:** Archived summary（原文档已不可考）
> **Archive date:** 2026-07-14
> **Source spec:** [../../spec/stage3-risk-adaptive-gate.md](../../spec/stage3-risk-adaptive-gate.md)

---

## 存档说明

本文档为 stage3 风险自适应门禁（Risk-Adaptive Gate）最终验证报告的存档摘要。原始验证报告已不可考，以下结论摘要依据 `docs/spec/stage3-risk-adaptive-gate.md` 的 Validation 章节重建，用于保留设计证据溯源链完整性。

## 验证结论摘要

### 单元测试

- **范围：** LOW / MEDIUM / HIGH / CRITICAL 四档风险分级、各档门禁规则行为、安全底线强制、领域关键词检测
- **结果：** `tests/test_stage3_risk_adaptive_gate.py` — 26 passed

### 冒烟测试

| 场景 | 风险档位 | 结果 |
|------|----------|------|
| 个人读书计划 | LOW | PASS |
| 客户反馈系统 | MEDIUM | PASS |
| 用药管理 | CRITICAL | PASS |

### 真实会话验证

- **会话：** `ae08e110-9c31-47b4-a9c8-bf1336991a94`（LOW 风险）
- **Redteam/regression/trace 规则：** 0 blockers（LOW 档正确跳过高级门禁）
- **安全底线规则：** pending_action + eval_failure blockers（安全底线正确强制）

## 关键结论

风险自适应门禁按预期工作：
1. LOW 风险项目仅保留安全底线门禁，不被 CRITICAL 级别的高级门禁误伤
2. CRITICAL 风险项目（如用药管理）触发全部门禁，包括 T3.3 的 expert review
3. 安全底线（缺失输出 / 解析错误 / 未决阻塞动作 / 拒绝动作 / 严重安全发现 / 依赖过期）在所有档位均强制阻断
