# 文档目录

## 使用指南

| 文档 | 说明 |
|------|------|
| [startup.md](startup.md) | 启动指南 |
| [local_setup.md](local_setup.md) | 本地开发环境配置 |
| [lite-mode.md](lite-mode.md) | SQLite 轻量模式 |
| [demo-scenarios.md](demo-scenarios.md) | 内置场景机制说明 |
| [acceptance_report.md](acceptance_report.md) | 四阶段全流程 E2E 测试验收报告 |

## spec/ — 系统设计与规格文档

| 文档 | 说明 |
|------|------|
| [spec/architecture.md](spec/architecture.md) | 系统架构图与设计说明 |
| [spec/api-reference.md](spec/api-reference.md) | API 接口参考 |
| [spec/security-model.md](spec/security-model.md) | 安全模型 |
| [spec/stage3-risk-adaptive-gate.md](spec/stage3-risk-adaptive-gate.md) | 风险自适应门禁详解 |
| [spec/supply-chain-security.md](spec/supply-chain-security.md) | 供应链与 CI 安全设计规格（权限最小化 / Dependabot / SAST / Scorecard / 文档一致性检查）·设计态 |
| [spec/data-classification-and-privacy.md](spec/data-classification-and-privacy.md) | 数据分类分级与隐私保护设计规格（分级 / 字段加密 / PII 掩码 / AI 生成标识 / PIA）·设计态 |
| [spec/risk-taxonomy-engine.md](spec/risk-taxonomy-engine.md) | 风险分类体系升级设计规格（OWASP LLM 2025 补齐 / Agentic ASI 2026 / NIST-AI-600-1 / TC260 智能体指引）·设计态 |
| [spec/governance-platform.md](spec/governance-platform.md) | 组织级治理平台设计规格（门禁规则版本化 / 治理视图 / 业务指标 / LLM Judge）·设计态 |

## plan/ — 规划与路线图文档

| 文档 | 说明 |
|------|------|
| [plan/improvement-roadmap.md](plan/improvement-roadmap.md) | 分阶段改进路线图：合规映射（中国监管+国际标准）、企业内部工具标准、开源社区工程健康度对照；第 10 节为 2026-07-13 外部标准复核增补 |
| [plan/phase-0-repo-governance.md](plan/phase-0-repo-governance.md) | 阶段 0 实施计划：仓库治理最小闭环（LICENSE / SECURITY / CI 权限 / Dependabot / Scorecard 基线） |
| [plan/phase-1-security-compliance.md](plan/phase-1-security-compliance.md) | 阶段 1 实施计划：安全与合规硬缺口修复（数据分级 / 加密 / PIA / AI 标识 / SAST） |
| [plan/phase-2-risk-taxonomy.md](plan/phase-2-risk-taxonomy.md) | 阶段 2 实施计划：AI 风险分类体系补强（LLM05/07/10 / ASI 2026 / NIST 动作项 / TC260 映射） |
| [plan/phase-3-governance-platform.md](plan/phase-3-governance-platform.md) | 阶段 3 实施计划：组织级治理平台（规则治理 / 聚合视图 / 业务指标 / LLM Judge） |
| [plan/phase-4-community.md](plan/phase-4-community.md) | 阶段 4 实施计划：开源社区打磨（文档一致性 CI / 分支保护 / Scorecard 爬升） |
