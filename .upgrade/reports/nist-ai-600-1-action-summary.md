# NIST AI 600-1 Generative AI Profile 动作项摘要存档

> 核对日期：2026-07-14
> 主源：https://www.nist.gov/itl/ai-risk-management-framework
> 文档：NIST AI 600-1 (2024-07-26 发布) Generative AI Profile
> DOI：https://doi.org/10.6028/NIST.AI.600-1
> 任务：Phase 2 Wave 1 T2.2（Agent B）

## 动作项清单

### MS-2.7-008 — GAI 红队测试与对抗性评估 ✅ 已核实
- 来源条款：NIST AI 600-1 §MS-2.7（GAI 资源滥用/对抗性）
- 中文摘要：对 GAI 系统进行红队测试与对抗性评估，覆盖越狱、提示注入、敏感信息外泄。
- 核实来源：scfconnect.com AAT-17.5（Fine Tuning Risk Mitigation）+ CSA AI Security Controls Matrix (AICM) AID 44（Quality Testing）均直接映射到 `MS-2.7-008`
- 映射 risk_type：prompt_injection / unsafe_instruction / system_prompt_leakage

### MS-2.10-002 — GAI 隐私风险度量 ⚠️ [存疑]
- 来源条款：NIST AI 600-1 §MS-2.10（隐私）
- 中文摘要：建立 GAI 隐私风险度量，识别训练/推理数据中的个人信息暴露。
- 核实情况：子类别 MS-2.10 经 redteams.ai 映射表确认属 Data Privacy（与 GV-1.1/GV-6.1、MP-3.4/MP-4.2、MG-2.2/MG-3.1 配对）；但 `-002` 后缀未在公开映射中直接核实
- 映射 risk_type：sensitive_info

### MS-2.5-005 — Confabulation 度量与输出净化 ⚠️ [存疑]
- 来源条款：NIST AI 600-1 §MS-2.5（有害内容/错误信息）
- 中文摘要：度量 GAI 输出的事实准确性 / Confabulation，建立输出净化流程。
- 核实情况：子类别 MS-2.5 在 NIST AI RMF 中存在（评估可信特性）；但 `-005` 后缀未在公开映射中直接核实。注：redteams.ai 映射表将 Confabulation 主要配对到 MS-2.6/MS-2.11，本条编号待人工对照官方 PDF 确认
- 映射 risk_type：unsupported_claim / improper_output_handling

### GV-1.3-002 — 人类监督程度界定 ✅ 已核实
- 来源条款：NIST AI 600-1 §GV-1.3（人类监督）
- 中文摘要：界定人类对 GAI 决策的监督程度与 Override 权限。
- 核实来源：CSA AI Security Controls Matrix (AICM) AID 44（Quality Testing）直接映射到 `GV-1.3-002`
- 映射 risk_type：over_autonomy / policy_gap

### MS-2.5-003 — 信息完整性校验 ⚠️ [存疑]
- 来源条款：NIST AI 600-1 §MS-2.5（信息完整性）
- 中文摘要：校验 GAI 引用信息源的完整性与可信度。
- 核实情况：子类别 MS-2.5 存在；`-003` 后缀未在公开映射中直接核实
- 映射 risk_type：source_untrusted

### MS-2.11-001 — GAI 资源消耗监控 ⚠️ [存疑]
- 来源条款：NIST AI 600-1 §MS-2.11（价值链/资源）
- 中文摘要：监控 GAI 资源消耗（算力/调用次数），防止滥用与成本失控。
- 核实情况：子类别 MS-2.11 存在；`-001` 后缀未在公开映射中直接核实。注：redteams.ai 映射表将 Value Chain 主要配对到 MS-2.7/MS-2.8，将 Confabulation 配对到 MS-2.11，本条编号待人工对照官方 PDF 确认
- 映射 risk_type：unbounded_consumption

## risk_type → 动作项映射总览

| risk_type | 动作项编号 | 核实状态 |
|---|---|---|
| prompt_injection | MS-2.7-008 | ✅ 已核实 |
| sensitive_info | MS-2.10-002 | ⚠️ 子类别已确认，后缀存疑 |
| unsupported_claim | MS-2.5-005 | ⚠️ 子类别已确认，后缀存疑 |
| over_autonomy | GV-1.3-002 | ✅ 已核实 |
| unsafe_instruction | MS-2.7-008 | ✅ 已核实 |
| source_untrusted | MS-2.5-003 | ⚠️ 子类别已确认，后缀存疑 |
| policy_gap | GV-1.3-002 | ✅ 已核实 |
| improper_output_handling | MS-2.5-005 | ⚠️ 子类别已确认，后缀存疑 |
| system_prompt_leakage | MS-2.7-008 | ✅ 已核实 |
| unbounded_consumption | MS-2.11-001 | ⚠️ 子类别已确认，后缀存疑 |

## 核对说明

- 本次核对通过 WebFetch / WebSearch 抓取 NIST 官方页面及第三方合规映射（CSA AICM、scfconnect SCF），确认 6 个动作项编号的格式与子类别归属。
- 编号格式 `<FUNC>-<CAT>.<SUBCAT>-<NUM>`（如 `MS-2.7-008`）经 AICM 与 SCF 交叉证实为 NIST AI 600-1 的真实动作项编号结构。
- 2 个编号（MS-2.7-008、GV-1.3-002）经多个独立来源直接映射，置信度高。
- 4 个编号的子类别（MS-2.10/MS-2.5/MS-2.11）经 redteams.ai 映射表确认存在且语义对应，但其 `-NNN` 后缀未在公开映射中直接出现，已在 `nist_ai_600_1.py` 与 `NIST_GAI_ACTION_DESCRIPTIONS` 中标注 `[存疑，待人工核对]`。
- NIST AI RMF 1.0 正在修订中（NIST 官方页面确认 "The AI RMF 1.0 is being revised"），发布后需回头更新（见 phase-2-risk-taxonomy.md T2.6）。
- NIST AI Agent Interoperability Profile 预告 2026 Q4 发布，发布后同样需回头更新条款号。

## 后续行动

- [ ] T2.6 阶段：获取 NIST AI 600-1 官方 PDF（https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf）逐条核对 4 个 [存疑] 后缀
- [ ] NIST AI RMF 修订版发布后：重新核对全部条款号
- [ ] Wave 2 阶段：将 `NIST_GAI_ACTION_REFS` 接入 `mapper.py:refs_for_risk_type` 聚合链
