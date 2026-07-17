# 生态定位与竞品分析（2026-07）

> 文档定位：本项目作为长期开源产品的赛道坐标与差异化依据，供 README「生态定位」章节背书、未来 roadmap 输入与求职作品集叙事引用。
> 数据快照：2026-07-16 GitHub API 采集，原始数据见 `.upgrade/research/benchmarking-20260716/`（未随对外分发）。stars 等数字为采集日快照值，会随时间漂移，引用时以本文落款日期为准。
> 编写时间：2026-07-17。竞品事实来源：GitHub API 快照（一手）+ 2026-07-17 联网调研（父计划 `.upgrade/plans/2026-07-17-formal-project-uplift.md`"联网调研关键结论"#11/#12，二手来源已标注）。

---

## 1. 赛道地图

AI 可靠性工程可分三层，本项目占据最上游的"事前分析层"：

| 层 | 时机 | 代表项目 | 回答的问题 |
|------|------|------|------|
| **事前分析层（本项目）** | 立项阶段，写代码之前 | AI Workflow Premortem | 这个 AI 系统会在哪里失败？哪些决策必须有人审核？ |
| 评估层 | 开发/回归阶段 | deepeval、inspect_ai | 模型/系统在测试集上表现如何？ |
| 护栏层 | 运行时 | guardrails-ai、NeMo-Guardrails | 这一次的输入/输出是否越界？ |

### 相邻项目对照（2026-07-16 快照）

| 项目 | stars | License | 最新版本（发布日） | 发版节奏观察 |
|------|------|------|------|------|
| [deepeval](https://github.com/confident-ai/deepeval) | 16,894 | Apache-2.0 | v4.1.0（2026-07-12；tag v4.1.1 已领先 release） | 4.x 成熟期，高频发版，商业公司（Confident AI）驱动 |
| [guardrails-ai](https://github.com/guardrails-ai/guardrails) | 7,157 | Apache-2.0 | v0.10.2（2026-06-04） | 0.x，月度级节奏，社群（Discord）驱动 |
| [NeMo-Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | 6,717 | NOASSERTION（GitHub 未识别；README 徽章声明 Apache-2.0） | v0.23.0（2026-07-01） | 0.x，企业（NVIDIA）官方项目，含 arXiv 论文背书 |
| [inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | 2,360 | MIT | 日期式 tag `release/2025-11-28`（不使用 GitHub Releases） | 政府机构（UK AISI）驱动，文档站为中心 |

与 README「生态定位」章节的定调一致：评估层、护栏层与本项目均为**互补**关系，不构成竞争——本项目产出的 EvalCase 是"事前生成的假设检验"，可导出到评估框架持续回归；预验尸预测出的失败模式，可落地为运行时护栏的具体校验器。

## 2. 直接竞品

**SynthBoard.ai**（商业 SaaS，多智能体顾问团式 AI Pre-Mortem；来源：2026-07-17 联网调研，二手信息）——同样做"事前风险分析"，路线是对话式 AI 顾问团头脑风暴。

本项目差异化（架构级，非功能级）：

1. **确定性代码控制状态机**——工作流状态转换由代码决定，LLM 只生成分析内容，不自主决定流程跳转；顾问团类产品的流程由 LLM 对话驱动。
2. **风险自适应门禁**——LOW/MEDIUM/HIGH/CRITICAL 分档收紧通过条件，高风险项目未完成评估**无法**推进（阻断是设计而非缺陷）。
3. **审计与人工干预一等公民**——Evidence / SafetyFinding / EvalRun / InterruptRecord / ReportArtifact 均为结构化记录，可导出可追溯。
4. **可自部署开源**——Apache-2.0，离线 Mock 模式可完整跑通，不绑定 SaaS。

## 3. 互补集成机会（未来 roadmap 候选，本文档只记录不承诺）

- EvalCase 导出为 deepeval / inspect_ai 可消费格式（事前假设 → 持续回归）
- Stage 4 触发策略导出为 guardrails validator 配置骨架（预测失败模式 → 运行时校验器）
- MIT AI Risk Repository v4（1700+ 风险分类）/ AI Incident Database 作为 Stage 1 失败模式检索的候选数据源

## 4. 开源门面对标结论

对标四项目 README 门面标配元素（快照 README 前 40 行逐项核对）：

| 元素 | deepeval | guardrails | NeMo-Guardrails | inspect_ai | 本项目现状 |
|------|------|------|------|------|------|
| 徽章 | 有（社区/release） | 最密集（CI/coverage/PyPI/社群） | 最全 CI 矩阵 + arXiv | **无** | ✅ 已补齐（CI/License/Python/Scorecard，公开后生效） |
| 文档站链接 | ✅ | ✅ | ✅ | ✅ | 以 docs/ 目录承担（主动不做独立文档站） |
| 社区渠道（Discord 等） | Discord/Reddit | Discord/X | 无（官方文档站） | 无（官方文档站） | 无——单人维护期走 GitHub Issues（GOVERNANCE.md 已声明响应节奏） |
| 论文引用（citation） | 无 | 无 | ✅ arXiv | 无 | 无——主动不做项 |
| Logo/wordmark | ✅ | ✅ | 纯文字 | 机构 logo | 纯文字标题（可后补，低优先级） |

结论：徽章与文档链接为硬标配（已补齐）；社群渠道与 citation 在机构/企业驱动型项目（inspect_ai / NeMo）中同样缺席，单人项目不补不构成短板。inspect_ai 证明"零徽章 + 强文档"路线可行，但其有机构背书，本项目不具备，故保留徽章路线。
