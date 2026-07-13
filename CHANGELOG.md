# Changelog

## v1.0 (2026-06-10)
- 完成四阶段工作流引擎（失败模式识别 → 工作流设计 → 压力测试 → 触发策略）
- 完成风险自适应门禁系统
- 完成人机监督闭环（PendingHumanAction）
- 完成 Eval 评估体系（EvalCase/EvalRun、Eval 数据集管理、Eval 实验对比）与 Red Team 对抗测试
- 完成证据核验与安全发现模块
- 完成报告导出与审计追踪
- Docker Compose 部署调通
- Streamlit Review Workbench 前端

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
