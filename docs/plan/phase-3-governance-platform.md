# 阶段 3 实施计划：从评估工具到组织级治理平台

> 上游路线图：[improvement-roadmap.md](improvement-roadmap.md) 第 6 节「阶段 3」。
> 配套设计规格：[../spec/governance-platform.md](../spec/governance-platform.md)。
> 现状基线核实日期：2026-07-13。
> 状态：未启动。前置依赖：阶段 2 的 T2.1（LLM 用量计数与业务指标共用数据源）建议先行；其余无硬依赖。这是最长期的阶段，按子系统分批交付。

---

## 1. 目标

把"单次项目风险评估"粒度扩展为"租户内多个 AI 项目的组织级治理视图"，并让门禁规则体系经得起 ISO/IEC 42001 式管理体系审计提问（"这条规则谁定的、何时改过、为什么"）。

## 2. 现状基线

完整事实清单见 [../spec/governance-platform.md](../spec/governance-platform.md) 第 1 节，要点：门禁规则硬编码无版本/无变更审计；CRITICAL 档 expert_review 开关无消费方（文档已如实标注）；可观测性只有 HTTP 通用指标；全仓无按租户的业务聚合查询；eval_judge 纯规则判分。

## 3. 任务分解

任务顺序刻意与路线图原文不同：**规则治理先行**——没有规则版本化，通过率趋势就无法区分"项目变好了"还是"规则变了"。

### T3.1 门禁规则元数据清单（manifest）

- **内容**：`core/gates/rules/manifest.py`，每条规则声明 version/owner/rationale/standard_refs/changelog；`registered_rules()` 启动校验双向完整性。设计见 spec 3.1 节。
- **验收**：12 条现有规则全部有 manifest 条目；完整性测试固化；standard_refs 与 taxonomy 前缀体系互通。
- 工作量：M

### T3.2 判定结果携带规则版本 + 评估记录持久化

- **内容**：`GateReport`/`RuleDetail` 增加 `rule_version`；新表 `gate_evaluation_records`（alembic V004 + SQLite DDL 同步），每次阶段推进评估旁路落一行。设计见 spec 3.2 节。
- **验收**：导出报告含规则版本；评估落表失败不阻断主路径（有降级测试）；两后端行为一致。
- 工作量：L

### T3.3 规则禁用显式治理 + expert_review 落地

- **内容**：`GATE_RULES_DISABLED` 配置（安全底线规则不可禁用）+ CRITICAL 档自动创建 `escalate` 型专家复核动作。设计见 spec 3.3-3.4 节。
- **验收**：禁用规则在 `/health` 与评估记录中可见；CRITICAL 会话不经专家 approve 无法通过 Stage 3（补上 [../spec/stage3-risk-adaptive-gate.md](../spec/stage3-risk-adaptive-gate.md) 标注的历史欠账，落地后同步删改该文档脚注）。
- 工作量：M

### T3.4 组织级聚合 API 与前端治理页

- **内容**：`api/routers/governance.py` 三个只读端点（overview / gate-trends / actions-backlog）+ 存储层聚合查询（强制 tenant 过滤）+ Streamlit 治理总览页。设计见 spec 4.1-4.2 节。
- **验收**：一个界面看到租户内项目数/风险分布/通过率趋势/积压动作；跨租户不可见（权限测试）。
- 工作量：L

### T3.5 业务指标接入 Prometheus/Grafana

- **内容**：`api/metrics.py` 自定义指标（sessions/gate/actions/LLM 用量）+ Grafana `governance-overview.json` 面板。设计见 spec 4.3 节。
- **验收**：`/metrics` 暴露 premortem_* 指标；Grafana 面板 provisioning 自动加载可见。
- 工作量：M

### T3.6 LLM Judge 建议判分（可选增强，flag 默认关）

- **内容**：`judge_mode="llm"` 第二层建议判分 + `llm_judge_suggestion` 字段 + human_calibrations 一致率闭环 + 防注入 judge prompt。HIGH/CRITICAL 永远人工终裁。设计见 spec 第 5 节。
- **验收**：mock 模式全链路测试；flag 关闭时行为与现状完全一致；治理页展示一致率。
- 工作量：L
- **启动条件**：确认企业场景确有自动化评估需求再做（路线图原文的"如果"条件保留）；若做，排在 T3.1-T3.5 之后。

### T3.7 ISO/IEC 42001 条款映射表（收尾）

- **内容**：`docs/compliance/iso42001-mapping.md`，条款 ↔ 平台能力映射（spec 第 6 节表格的展开版），如实标注未覆盖条款。
- **验收**：映射表存在且每条能力可指到具体端点/表/文档。
- 工作量：M（纯文档）

## 4. 推进顺序与依赖

```
T3.1 → T3.2 → T3.3   （规则治理链，严格串行）
T3.2 → T3.4 → T3.5   （趋势数据源就绪后做视图与指标）
T3.6                  （独立，需求确认后启动）
T3.7                  （收尾）
```

## 5. 风险与注意事项

- T3.2 触碰阶段推进主路径，旁路写入必须有失败降级（治理数据缺一行可接受，评估被治理数据卡死不可接受）。
- T3.4 的"组织"边界=tenant；存储层未暴露的空 `tenant_id` 跨租户分支是安全边界，**不得**为实现集团视图而顺手打开。
- T3.6 的 LLM Judge 与"确定性架构"原则的张力已在 spec 第 5 节消解（LLM 只建议、不终裁）；实现时不要让建议值悄悄变成默认值。
- 指标标签基数：tenant 维度用名称且租户数有限；不要给指标加 session_id 级标签。

## 6. 阶段验收清单

- [x] 任一门禁规则能回答"版本/owner/依据/变更历史"
- [x] 报告与评估记录携带规则版本
- [x] CRITICAL 会话强制专家复核动作（历史欠账关闭）
- [x] 治理总览页可看到租户内项目数/风险分布/通过率趋势/积压动作
- [x] `/metrics` 有业务指标且 Grafana 治理面板可用
- [x] （已启用实现，flag 默认关）LLM Judge：flag 关闭时行为不变（tests/test_llm_judge_v130.py 回归确认）；一致率经既有 human_calibrations/`build_eval_judgment_summary` 聚合，真实 LLM 一致率数据待生产使用后累计 —— T3.6 于 v1.3.0 落地
- [x] ISO 42001 映射表存档
