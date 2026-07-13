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

## v0.5 (2026-05-20)
- 基本框架搭建，FastAPI + LangGraph 状态机
- PostgreSQL + Redis 存储层
- JWT 认证与 RBAC 权限
- Mock LLM 模式支持离线演示

## v0.1 (2026-05-01)
- 项目初始化，确定四阶段分析流程
- Pydantic 数据模型设计
