# Changelog

> **历史追溯说明**：v0.1–v0.7 阶段的详细提交历史因仓库整理未完整保留于本地 `main` 分支。
> 远程 `origin`（github.com/gome09/ai-workflow-premortem-pure）保有 2026-05-31 起的完整提交历史（21 次提交），如需追溯请查阅远程分支。
> 其中 v0.1（2026-05-01）/ v0.5（2026-05-20）的日期早于可见最早 commit（2026-05-31），为里程碑回溯记录，非逐次提交日志。

## v1.2.2 (2026-07-15)
- **离线 Demo 内置场景精简（4 → 2）**：彻底移除 `student_course_selection` 与 `university_course_qa` 两个场景，仅保留 `generic_rag_demo`（干净基线，展示完整四阶段链路）与 `university_mental_health`（高敏感/CRITICAL 门禁 + 强制人工审核，平台差异化亮点）。
  - **删除**：2 份 manifest（`scenarios/manifests/`）、2 个 mock fixture（`core/llm/adapters/mock_fixtures/`）、2 份输入样例（`examples/`）；`core/llm/adapters/mock.py` 的 `_PROFILE_MODULES` 移除对应两条注册项。`university_ai` domain profile 保留（仍被 `university_mental_health` 引用）。
  - **测试**：`test_e2e_four_scenarios.py` → `test_e2e_scenarios.py`（改为 2 场景参数化），并同步更新 `test_scenario_semantic_integrity.py` / `test_scenarios_registry.py` / `test_scenario_session_flow.py` / `test_api.py`。
  - **文档**：更新当前面向用户文档 `docs/demo-scenarios.md`、`docs/showcase.md`；历史/设计类文档（`docs/plan/`、`docs/spec/risk-governance-demo.md`、`docs/archive/`）作为设计记录保留不动。
- **测试验证**：670 passed + 8 skipped（全量 pytest）；lint + format clean；四阶段实况 E2E（`scripts/live_e2e_four_stage.py`）PASS。

## v1.2.1 (2026-07-14)
- **Phase 4 开源社区打磨（T4.1 / T4.2 / T4.3 / T4.5；T4.4 明确不承诺）**：
  - **T4.1 文档-代码一致性检查 CI 化**：新建 `scripts/doc_consistency_check.py`（三类规则：Markdown 相对链接存在性 / `make <target>` 存在性 / 反引号仓库路径存在性）；新增 `make doc-check` target；ci.yml lint job 追加 doc-check 步骤（初期 `continue-on-error: true` 观察期）；修复 stage3 文档悬空引用（补档 `docs/archive/verification-reports/risk_adaptive_gate_final_validation.md`，决策记录见 `.upgrade/decisions/doc-check-stage3-dangling-ref.md`）
  - **T4.5 社区响应约定**：新建 `.github/ISSUE_TEMPLATE/bug_report.md` + `feature_request.md`；新建 `.github/PULL_REQUEST_TEMPLATE.md`（含改动类型 + 提交前检查清单）；CONTRIBUTING.md 追加"分支保护"与"社区响应约定"段落（7 天响应承诺，不过度承诺）
  - **T4.2 分支保护与评审流程**：新建 `.upgrade/decisions/branch-protection.md`（main 分支保护策略决策 + 维护者手动操作步骤 + 预期 Scorecard 影响）；分支保护为 GitHub 后台配置，需维护者手动开启
  - **T4.3 Scorecard 持续爬升机制**：机制已就位（`.github/workflows/scorecard.yml` weekly cron）；新建 `.upgrade/reports/scorecard-trend-20260714.md` 趋势报告（基线对照 + 18 项预期变化 + 待操作项）
  - **T4.4 锦上添花项**：明确不承诺（Signed Releases / CII Badge / Packaging）——无外部用户信号前不投入
- **新增测试**：无（本阶段为工程健康度/文档/CI 任务，无新业务逻辑）
- **测试验证**：642 passed + 1 skipped（unit，回归确认无破坏）；lint + format clean；doc-check 运行正常（26 处存量违规，均为既有问题与设计文档代码示例误报，CI non-blocking）
- **详细设计方案**：[docs/plan/phase-4-design.md](docs/plan/phase-4-design.md)

## v1.0 (2026-06-10)
- 完成四阶段工作流引擎（失败模式识别 → 工作流设计 → 压力测试 → 触发策略）
- 完成风险自适应门禁系统
- 完成人机监督闭环（PendingHumanAction）
- 完成 Eval 评估体系（EvalCase/EvalRun、Eval 数据集管理、Eval 实验对比）与 Red Team 对抗测试
- 完成证据核验与安全发现模块
- 完成报告导出与审计追踪
- Docker Compose 部署调通
- Streamlit Review Workbench 前端

## v1.2.0 (2026-07-14)
- **Phase 3 组织级治理平台（T3.1–T3.5, T3.7；T3.6 可选未启用）**：
  - **T3.1 门禁规则元数据清单（manifest）**：新建 `core/gates/rules/manifest.py`，13 条规则每条声明 `version`/`owner`/`rationale`/`standard_refs`/`changelog`/`safety_bottom_line`；`registered_rules()` 启动双向完整性校验（WARNING-only 不阻断）。回答 ISO/IEC 42001 "谁定的、改过几次、为什么"提问，规则保持代码化不引入 DB 存储
  - **T3.2 判定结果携带规则版本 + 评估记录持久化**：`GateReport`/`RuleDetail` 新增 `rule_version` 字段；新建 `gate_evaluation_records` 表（alembic V005 + SQLite DDL），每次阶段评估旁路落一行（失败不阻断主路径，有降级测试）；存储层新增 `record_gate_evaluation`/`gate_trends`/`governance_overview`/`actions_backlog` 聚合方法（强制 tenant 过滤）
  - **T3.3 规则禁用显式治理 + expert_review 落地**：新增 `GATE_RULES_DISABLED` 配置（安全底线规则 7 类不可禁用，配置也忽略+WARNING）；新建 `core/gates/rules/expert_review.py` 消费 CRITICAL 档 `require_expert_review`（补 [stage3-risk-adaptive-gate.md](docs/spec/stage3-risk-adaptive-gate.md) 历史欠账——CRITICAL 会话不经专家 approve 无法通过 Stage 3）；`/health` 暴露被禁用规则列表
  - **T3.4 组织级聚合 API 与前端治理页**：新建 `api/routers/governance.py`（3 个只读端点 `/governance/overview`/`/governance/gate-trends`/`/governance/actions-backlog`，viewer 可读，tenant 隔离）；新建 Streamlit 治理总览页（项目数/风险分布/通过率趋势/积压动作表）
  - **T3.5 业务指标接入 Prometheus/Grafana**：新建 `api/metrics.py`（6 个 `premortem_*` 指标：sessions/gate-evals/blocks/pending-actions/llm-calls/llm-tokens）；`engine`+`execution_service` 评估与 LLM 路径打点；新建 `monitoring/grafana/dashboards/governance-overview.json`（4 panel，provisioning 自动加载）
  - **T3.7 ISO/IEC 42001 条款映射表**：新建 `docs/compliance/iso42001-mapping.md`（25 条款映射，21 已覆盖 / 4 部分覆盖 / 4 未覆盖缺口）；修正 spec 两处过时表述（V004→V005、expert_review 状态）
  - **T3.6 LLM Judge（可选，未启用）**：设计完成（spec §5），flag 默认关，待企业需求确认后作为独立 Wave 启动
- **门禁规则数**：12 → 13（新增 `expert_review`）
- **新增测试**：`test_rule_manifest_v110.py`(44)、`test_gate_evaluation_records_v110.py`(20)、`test_expert_review_gate_v110.py`(11)、`test_governance_api_v110.py`(24)、`test_metrics_v110.py`(16)
- **数据库迁移**：alembic V005（`gate_evaluation_records` 表 + 2 索引）
- **测试验证**：642 passed + 1 skipped（unit）；63 passed（e2e-mock）；lint + format clean
- **详细设计方案**：[docs/plan/phase-3-design.md](docs/plan/phase-3-design.md)

## v1.1.0 (2026-07-14)
- **Phase 2 AI 风险分类体系补强（T2.1–T2.6）**：
  - **T2.1 OWASP LLM Top 10 2025 补齐 + Context schema v0.9.0**：risk_type Literal 7→10（新增 `improper_output_handling`(LLM05) / `system_prompt_leakage`(LLM07) / `unbounded_consumption`(LLM10)）；`prompt_injection_scanner.py` 重写为 `classify_injection()`（injection/leakage 分流）；`safety_classifier.py` 新增 LLM05 输出净化检测 + LLM10 资源消耗监控；`execution_service.py` 包裹 LLM 调用计数与 token 估算；Context schema v0.8.0→v0.9.0 迁移（`core/migrations/v080_to_v090.py`）；slowapi 429 审计事件接入
  - **T2.2 NIST AI 600-1 Generative AI Profile**：新建 `tools/taxonomies/nist_ai_600_1.py`，10 个 risk_type 全覆盖动作项映射（4 项标 [存疑] 待人工核对），含 `.upgrade/reports/nist-ai-600-1-action-summary.md`
  - **T2.3 OWASP Agentic Security Initiative Top 10 2026**：新建 `tools/taxonomies/owasp_agentic_2026.py`，8 个 attack_type + 5 个 risk_type 映射；ASI07 经核实为 Insecure Inter-Agent Communication（非 Resource Abuse），已删除错误映射
  - **T2.4 TC260《智能体部署使用安全指引》**：新建 `tools/taxonomies/tc260_agent_deployment.py`，五阶段（评估/准备/部署/使用/停用）+ 6 control + 6 risk_type；停用阶段=None 标产品缺口；含 `.upgrade/reports/tc260-agent-deployment-summary.md`
  - **T2.5 领域扩展标签接入生产链路**：`apply_taxonomy_to_safety_finding` 新增 `domain` 参数，命中 `university_ai`/`medical_ai` 时叠加领域专属标签（PIPL/HIPAA 等）；`safety_classifier._finding` + `safety_classifier.add_findings_dedup` + `safety_service.resolve_safety_finding` 透传 `domain=current_domain_profile(ctx)`
  - **T2.6 标准动态跟踪记录**：新建 `.upgrade/logs/standard-tracking-2026-07-14.md`，记录 7 项已落地标准基线 + 6 项跟踪项（未成年人指南/TC260 分行业/NIST AI RMF 修订/OWASP ASI 正式版/PIPL 实施细则/GENAI 立法）
  - **mapper.py 三表聚合接入**：`refs_for_risk_type` 追加 NIST_GAI + ASI + TC260 三表；`refs_for_attack_type` 追加 ASI
- **新增测试**：`test_owasp_llm_completion.py`(19)、`test_context_migrations_v090.py`(6)、`test_taxonomy_nist_ai_600_1.py`(6)、`test_taxonomy_owasp_agentic_2026.py`(12)、`test_taxonomy_tc260_agent_deployment.py`(10)、`test_taxonomy_mapper_aggregation.py`(17)、`test_domain_labels_production.py`(20)
- **Context schema 升级**：v0.8.0 → v0.9.0（`ProjectContext` 新增 `llm_call_count`/`llm_token_estimate` 字段）
- **测试验证**：524 passed + 1 skipped（unit）；63 passed（e2e-mock）；lint + format clean

## v1.0.3 (2026-07-14)
- **Phase 1 安全与合规硬缺口修复（T1.1–T1.9）**：
  - **T1.1 数据分类分级**：新增 `data_classification` 字段（public_demo / business_internal / sensitive_personal），实现应用层迁移链 v0.7.0→v0.8.0，提供数据分级覆写端点与审计记录
  - **T1.2 敏感场景风险升档**：`risk_profile.py` 新增"心理健康/心理/精神/学生/未成年人/校园霸凌/自伤/自杀"等关键词，`university_mental_health` 场景现已真正自动升档为 HIGH
  - **T1.3 存储层字段级加密**：实现 Fernet 对称加密（`enc:v1:` 前缀），`context_json` 敏感字段落库加密、读出解密，支持 SQLite/PostgreSQL 双后端，空密钥安全旁路
  - **T1.4 PII 检测与掩码**：新增身份证/手机号/邮箱/银行卡 PII 模式检测，实现 pattern-preserving 掩码，仅在用户材料/证据源位置运行（避免 LLM 输出误报），命中自动升级数据分级到 `sensitive_personal`
  - **T1.5 报告 AI 生成内容标识**：报告 metadata 新增 `ai_generated_notice` 字段，生成报告时自动添加 AI 生成内容声明块（符合《人工智能生成合成内容标识办法》2025-09-01）
  - **T1.6 数据生命周期**：新增 DELETE /sessions/{session_id} 端点（admin only），实现审计事件归档（`audit_events_archive` 表无 FK，保留审计链），Alembic V004 迁移，`audit_retention_days=183`/`session_retention_days=0` 配置
  - **T1.7 PIA 文档**：产出三份个人信息保护影响评估文档——`pia-platform.md`（平台自评，含 DeepSeek 跨境传输披露与 PIPL 第56条三要素评估）、`pia-template.md`（用户可填写模板）、`pia-university-mental-health.md`（高敏现场实例）
  - **T1.8 供应链安全**：接入 ruff S 规则（SAST）、pip-audit（依赖漏洞扫描）、CodeQL 工作流（手动触发 + 每周 cron），新增 `make audit`/`make security-check` 目标
  - **T1.9 应急响应**：产出 `docs/compliance/incident-response.md` 六段式数据泄露应急响应 checklist，在 `SECURITY.md` 增加"应急响应"章节
- **新增测试**：`test_data_classification.py`、`test_field_encryption.py`、`test_pii_detection.py`、`test_risk_profile_mental_health.py`、`test_report_ai_notice.py`、`test_session_lifecycle.py`
- **docs/compliance/** 目录建立：包含 PIA 文档、应急响应、备份恢复指引
- **.gitignore**：补充 `*.db-shm`/`*.db-wal` 规则
- **improvement-roadmap.md**：第 3.5 节补充修订说明，第 10.5 节标注 T1.2 完成

## v1.0.2 (2026-07-13)
- **修复红队测试覆盖门控与人工动作状态不联通问题**：
  - 添加 `create_actions_from_redteam_gaps` 函数，为红队测试覆盖不足创建对应的人工动作
  - 在 `create_review_actions_for_stage` 中注册新函数
  - 在 `resolve_action` 中添加红队动作处理分支，处理 gap_type 并调用对应的 redteam_service 函数
  - 解决阶段3"红队测试覆盖不足但无待处理人工动作"的问题

## v1.0.1 (2026-07-13)
- 新增 `scripts/live_e2e_four_stage.py` 四阶段全流程 E2E 测试脚本
- 修复 StageAdvancementDecision 响应结构解析（blockers 嵌套在 gate_result 中）
- 新增 RedTeamCase 自动生成、审批与同步到 Eval 的处理逻辑
- 完成本地离线全流程测试验证（SQLite + Mock LLM）
- **修复证据门控与人工动作状态不联通问题**：在 `resolve_action` 函数中添加处理 `verify_evidence` 动作时自动更新 `evidence.verified` 字段的逻辑，解决"人工动作已完成但阶段仍被阻断"的问题
- 生成完整验收报告与会话导出文档

## v0.5 (2026-05-20)
- 基本框架搭建，FastAPI + LangGraph 状态机
- PostgreSQL + Redis 存储层
- JWT 认证与 RBAC 权限
- Mock LLM 模式支持离线演示

## v0.1 (2026-05-01)
- 项目初始化，确定四阶段分析流程
- Pydantic 数据模型设计
