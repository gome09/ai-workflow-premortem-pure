# 决策：stage3 悬空引用采用补档而非修链

> 日期：2026-07-14
> 关联：phase-4-design.md T4.1 / docs/spec/stage3-risk-adaptive-gate.md line 119

## 背景

`docs/spec/stage3-risk-adaptive-gate.md` 的 line 119 引用了最终验证报告：

```
**Report:** [../archive/verification-reports/risk_adaptive_gate_final_validation.md](../archive/verification-reports/risk_adaptive_gate_final_validation.md)
```

目标文件 `docs/archive/verification-reports/risk_adaptive_gate_final_validation.md` 在仓库中不存在，属于悬空引用（dangling reference）。该问题已在 `.upgrade/MANIFEST.md` 中记录为既有问题。

T4.1 引入 doc-check 脚本后，规则 1（链接存在性）会检出此坏链并报告违规，需要先清除该存量问题才能让 CI 进入稳定观察期。

## 决策

采用**补档方案**（创建目标文件 `docs/archive/verification-reports/risk_adaptive_gate_final_validation.md`），而非**修链方案**（删除 stage3 文档中的引用）。

## 决策依据

| 方案 | 优点 | 缺点 |
|------|------|------|
| **补档（采纳）** | 保留设计证据溯源链；stage3 文档语义完整；读者可跳转查看验证结论 | 原始报告已不可考，补档内容为基于 spec 重建的摘要 |
| **修链（否决）** | 改动最小，仅删一行 | 丢失 stage3 风险自适应门禁的最终验证证据溯源；未来追溯设计依据时断链 |

该验证报告是 stage3 风险自适应门禁的设计证据，删除引用会导致设计溯源断裂。补档虽无法恢复原文，但基于 spec 的 Validation 章节重建了关键结论摘要，足以支撑设计审查。

## 补档内容

新建文件 `docs/archive/verification-reports/risk_adaptive_gate_final_validation.md`：
- 标注存档说明（原文档已不可考）
- 基于 `docs/spec/stage3-risk-adaptive-gate.md` 的 Validation 章节重建验证结论摘要（单元测试 26 passed、3 项冒烟测试 PASS、真实会话验证结果）

## 影响

- doc-check 规则 1（链接存在性）不再报告该坏链
- stage3 文档的验证报告引用恢复可用
- 设计溯源链完整
