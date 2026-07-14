# Changelog

> **历史追溯说明**：v0.1–v0.7 阶段的详细提交历史因仓库整理未完整保留于本地 `main` 分支。
> 远程 `origin`（github.com/gome09/ai-workflow-premortem-pure）保有 2026-05-31 起的完整提交历史（21 次提交），如需追溯请查阅远程分支。
> 其中 v0.1（2026-05-01）/ v0.5（2026-05-20）的日期早于可见最早 commit（2026-05-31），为里程碑回溯记录，非逐次提交日志。

## v1.0 (2026-06-10)
- 完成四阶段工作流引擎（失败模式识别 → 工作流设计 → 压力测试 → 触发策略）
- 完成风险自适应门禁系统
- 完成人机监督闭环（PendingHumanAction）
- 完成 Eval 评估体系（EvalCase/EvalRun、Eval 数据集管理、Eval 实验对比）与 Red Team 对抗测试
- 完成证据核验与安全发现模块
- 完成报告导出与审计追踪
- Docker Compose 部署调通
- Streamlit Review Workbench 前端

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
