# ISO/IEC 42001:2023 条款映射表

> 对标：ISO/IEC 42001:2023《信息技术—人工智能—管理体系》
> 建立日期：2026-07-14（Phase 3 收尾，T3.7）
> 状态：初版映射，如实标注未覆盖条款

## 1. 概述

本映射表建立 ISO/IEC 42001:2023 管理体系条款与本项目平台能力的对应关系，
回答"平台如何满足 AI 管理体系审计提问"。每条能力可指到具体端点/表/文档。

映射状态标记：
- ✅ 已覆盖：平台有对应能力且可验证
- ⚠️ 部分覆盖：有相关能力但不完整
- ❌ 未覆盖：平台无对应能力（如实标注）

## 2. 条款映射

### 条款 4 组织环境（Context of the organization）

| 条款 | 要求摘要 | 平台能力 | 证据 | 状态 |
|------|----------|----------|------|------|
| 4.1 理解组织及其环境 | 确定影响 AI 管理体系的内外部因素 | 项目风险评估：domain/automation/sensitivity 关键词分级 | `core/gates/risk_profile.py` classify_project_risk | ⚠️ |
| 4.2 理解相关方需求 | 确定相关方对 AI 系统的要求 | ProjectContext.goal/research_target 字段 | `core/models.py` ProjectContext | ⚠️ |
| 4.3 确定 AI 管理体系范围 | 界定管理体系边界 | 多租户 tenant 隔离；会话级项目边界 | `storage/backends/` tenant 过滤 | ✅ |
| 4.4 AI 管理体系及其过程 | 建立、实施、保持、持续改进过程 | 四阶段工作流（Stage1-4）+ 门禁规则版本化 | `core/gates/rules/manifest.py` RULE_MANIFEST | ✅ |

### 条款 5 领导作用（Leadership）

| 条款 | 要求摘要 | 平台能力 | 证据 | 状态 |
|------|----------|----------|------|------|
| 5.1 领导作用与承诺 | 最高管理者对 AI 管理体系的承诺 | 规则 owner 字段明确责任方 | manifest `owner` 字段 | ⚠️ |
| 5.2 AI 方针 | 建立 AI 方针 | 治理总览页暴露门禁通过率/风险分布 | `/governance/overview` | ⚠️ |
| 5.3 组织的角色、职责和权限 | 确保角色职责清晰 | RBAC 三角色（viewer/editor/admin）；规则 owner | `auth/permissions.py` Role | ✅ |

### 条款 6 策划（Planning）

| 条款 | 要求摘要 | 平台能力 | 证据 | 状态 |
|------|----------|----------|------|------|
| 6.1 应对风险和机遇的措施 | 识别 AI 风险并策划措施 | 风险分级 + 安全发现 + 门禁规则 | `core/gates/risk_profile.py` + `core/models.py` SafetyFinding | ✅ |
| 6.2 AI 风险评估 | 评估 AI 风险并处置 | Stage1 失败模式识别 + Stage3 红队/评测 | `stages/stage_1_failure_mode.py` + `core/redteam_service.py` | ✅ |
| 6.3 AI 风险处置 | 实施风险处置措施 | 人工动作 + 安全发现处置 + 门禁阻断 | `core/models.py` PendingHumanAction | ✅ |

### 条款 7 支持（Support）

| 条款 | 要求摘要 | 平台能力 | 证据 | 状态 |
|------|----------|----------|------|------|
| 7.1 资源 | 提供所需资源 | LLM 用量监控（LLM10） | `premortem_llm_calls_total` 指标 | ✅ |
| 7.2 能力 | 确保人员有能力 | expert_review 专家复核机制 | `core/gates/rules/expert_review.py` | ✅ |
| 7.3 意识 | 确保人员有意识 | 治理透明度：viewer 可读治理端点 | `/governance/*` viewer 可读 | ✅ |
| 7.4 沟通 | 内外部沟通 | 报告导出 + 审计事件 | `core/report_service.py` + `core/audit_service.py` | ✅ |
| 7.5 成文信息 | 保持成文信息 | manifest changelog + 评估记录 + 审计归档 | `gate_evaluation_records` 表 + `audit_events_archive` | ✅ |

### 条款 8 运行（Operation）

| 条款 | 要求摘要 | 平台能力 | 证据 | 状态 |
|------|----------|----------|------|------|
| 8.1 运行策划和控制 | 策划、实施和控制过程 | 四阶段门禁引擎 + 规则禁用治理 | `core/gates/engine.py` + `GATE_RULES_DISABLED` | ✅ |
| 8.2 AI 风险评估 | 实施风险评估 | Stage1-3 风险识别与压力测试 | `stages/` 全部 | ✅ |
| 8.3 AI 风险处置 | 实施处置 | 安全发现处置 + 人工动作解决 | `core/safety_service.py` + `core/oversight_service.py` | ✅ |
| 8.4 变更管理 | 控制 AI 系统变更 | 规则版本化 + changelog + context schema 迁移 | `manifest.version` + `core/migrations/` | ✅ |

### 条款 9 绩效评价（Performance evaluation）

| 条款 | 要求摘要 | 平台能力 | 证据 | 状态 |
|------|----------|----------|------|------|
| 9.1 监视、测量、分析和评价 | 评价 AI 管理体系绩效 | Prometheus 业务指标 + Grafana 面板 + 治理趋势 | `/metrics` premortem_* + `/governance/gate-trends` | ✅ |
| 9.2 内部审核 | 定期内部审核 | 评估记录持久化可追溯；规则版本可审计 | `gate_evaluation_records` + manifest | ✅ |
| 9.3 管理评审 | 最高管理者评审 | 治理总览页（项目数/风险/通过率/积压） | `/governance/overview` + Streamlit 页 | ✅ |

### 条款 10 改进（Improvement）

| 条款 | 要求摘要 | 平台能力 | 证据 | 状态 |
|------|----------|----------|------|------|
| 10.1 总则 | 持续改进 | 规则 changelog + 标准动态跟踪 | manifest.changelog + `.upgrade/logs/standard-tracking-*.md` | ✅ |
| 10.2 不符合和纠正措施 | 处理不符合 | 安全发现 + 人工动作 + 审计事件 | `core/safety_service.py` + AuditEvent | ✅ |
| 10.3 持续改进 | 持续改进 AI 管理体系 | 规则版本迭代 + 门禁通过率趋势分析 | `/governance/gate-trends` pass_rate 趋势 | ✅ |

## 3. 未覆盖条款与产品缺口

如实标注以下未完全覆盖的领域：

| 缺口 | 说明 | 来源 |
|------|------|------|
| 系统停用/退役阶段 | 本项目四阶段工作流无"停用"环节，模型/系统退役时的数据清理与交接无对应能力 | TC260 智能体部署指引"停用"阶段（阶段 2 T2.4 已记录） |
| LLM Judge 自动化评估 | T3.6 已于 v1.3.0 实现（`core/eval_llm_judge.py`，flag 默认关）；校准闭环机制就位（human_calibrations 聚合），真实一致率数据待生产启用后累计 | spec §5，测试 `tests/test_llm_judge_v130.py` |
| 跨租户集团视图 | 组织=tenant 边界，跨租户聚合不开放（安全边界非待开发） | spec §2 |
| 第三方供应链风险 | 供应链安全文档已存档但未集成到门禁 | `docs/spec/supply-chain-security.md` |

## 4. 审计提问应答索引

对应 spec §6 表格的展开版：

| 审计提问 | 回答来源 | 平台位置 |
|----------|----------|----------|
| 组织内有多少 AI 项目、风险分布如何 | `/governance/overview` | `api/routers/governance.py` |
| 这条门禁规则谁定的、改过几次、为什么 | 规则 manifest + git 历史 + changelog | `core/gates/rules/manifest.py` RULE_MANIFEST |
| 这份评估报告当时依据什么规则版本 | 报告内嵌 rule_versions | `core/gates/report.py` RuleDetail.rule_version |
| 高风险项目是否经过专家复核 | expert_review 动作记录 + 审计事件 | `core/gates/rules/expert_review.py` + AuditEvent |
| 自动化判分是否可信、如何校准 | human_calibrations 一致率指标（T3.6 已实现，flag 默认关，启用后累计） | `core/eval_llm_judge.py` + `core/eval_judge.py` |
| 门禁通过率趋势如何 | `/governance/gate-trends` | `gate_evaluation_records` 表 |
| 哪些规则被禁用、何时禁用 | `/health` gate_rules_disabled + 评估记录标注 | `api/main.py` health() + gate_evaluation_records.rule_versions |

## 5. 维护说明

- 本映射表随平台能力演进定期更新
- 新增能力时补充对应条款映射
- 未覆盖条款转为待办时记录到 `.upgrade/STATE.md` Blockers

## 6. 附：ISO/IEC 42005:2025（AI 系统影响评估）对标说明

> 复核日期 2026-07-17。ISO/IEC 42005:2025 于 2025-05 正式发布（第 1 版，SC 42/WG 1，指南性标准、非认证标准），
> 是与本平台"预验尸=事前影响评估"定位最直接对标的国际标准。来源：https://www.iso.org/standard/42005

| 42005 核心要求 | 本平台对应能力 | 状态 |
|------|------|------|
| 在生命周期哪个阶段执行影响评估 | 立项阶段四阶段引导式分析（Stage 1–4） | ✅ 覆盖 |
| 评估范围界定、责任分配、阈值设定 | 风险自适应门禁（LOW/MEDIUM/HIGH/CRITICAL 分档阈值），门禁规则 manifest 声明 owner | ✅ 覆盖 |
| 文档化 / 审批 / 复审要求 | ReportArtifact 报告导出 + PendingHumanAction 审批 + 审计事件记录 | ✅ 覆盖 |
| 融入组织 AI 风险管理（对接 ISO/IEC 23894）与管理体系（支撑 42001 的 6.1.4 / 8.4） | 本文件的 42001 条款映射 + 治理视图（/governance/*） | ⚠️ 部分：23894 尚无显式映射 |

注：本表为初版对齐说明，逐条款精细映射待获取标准全文后补充（42005 为付费标准，本表基于官方摘要与二手概述编写，条款号未逐字核对）。
