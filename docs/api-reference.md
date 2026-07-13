# API 接口参考

> 本文档按当前源码静态提取整理。
> 当前仓库可直接识别的 HTTP 路由总数为 `79`（`api/routers/*.py` 70 条 + `auth/router.py` 5 条 + `/health*`/`/health` 3 条 + `/metrics` 1 条）。

---

## 健康检查 & 监控

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health/live` | Liveness probe，进程存活检查 |
| GET | `/health/ready` | Readiness probe；`sqlite` 模式跳过 Redis 检查 |
| GET | `/health` | 兼容旧版的健康检查 |
| GET | `/metrics` | Prometheus metrics |

---

## 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册；首个用户自动成为 `admin` |
| POST | `/auth/login` | 登录；使用 `OAuth2PasswordRequestForm`，不是 JSON body |
| POST | `/auth/refresh` | 使用 refresh token 换取新的 access token |
| GET | `/auth/users` | 列出租户内用户，`admin` only |
| PATCH | `/auth/users/{user_id}/role` | 更新用户角色，`admin` only |

---

## 会话与对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/sessions/` | 创建新会话 |
| GET | `/sessions/scenarios` | 列出内置场景（须在 `/sessions/{session_id}` 之前注册，否则会被后者的路径参数捕获） |
| GET | `/sessions/scenarios/{scenario_id}` | 查看单个内置场景详情 |
| GET | `/sessions/` | 列出会话 |
| GET | `/sessions/{session_id}` | 获取完整会话上下文 |
| POST | `/chat/{session_id}` | 发送消息并推进一个执行回合 |
| POST | `/sessions/{session_id}/materials` | 追加用户材料 |
| POST | `/sessions/{session_id}/flags/resolve` | 处理需核验项 |
| GET | `/sessions/{session_id}/export` | 导出报告（`json` 或 `markdown`） |

---

## 阶段治理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/stage-readiness` | 查看全部阶段 readiness |
| GET | `/sessions/{session_id}/stage-readiness/{stage_id}` | 查看单阶段 readiness |
| GET | `/sessions/{session_id}/stage-gate/{stage_id}` | 查看单阶段 gate 结果 |
| GET | `/sessions/{session_id}/stage-resolution` | 查看全部阶段下一步操作 |
| GET | `/sessions/{session_id}/stage-resolution/{stage_id}` | 查看单阶段下一步操作 |
| GET | `/sessions/{session_id}/stages/{stage_id}/advancement-decision` | 查看统一阶段推进决策 |
| POST | `/sessions/{session_id}/stages/{stage_id}/advance` | 在 gate 允许时推进阶段 |
| POST | `/sessions/{session_id}/stages/{stage_id}/rerun` | 准备阶段重跑 |
| POST | `/sessions/{session_id}/stages/{stage_id}/revise` | 准备阶段修订 |
| POST | `/sessions/{session_id}/stages/{stage_id}/rollback` | 回退阶段 |
| POST | `/sessions/{session_id}/stages/{stage_id}/sync-review-actions` | 同步审核动作 |
| GET | `/sessions/{session_id}/gate-report?stage={stage_id}` | 获取单阶段 Gate 诊断报告 |

---

## 人机监督

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/actions` | 列出人工动作 |
| GET | `/sessions/{session_id}/actions/{action_id}` | 查看单个人工动作 |
| GET | `/sessions/{session_id}/actions/{action_id}/resolution-logs` | 查看动作处理日志 |
| POST | `/sessions/{session_id}/actions/{action_id}/resolve` | 处理人工动作 |
| GET | `/sessions/{session_id}/audit-events` | 查看审计事件 |

---

## 证据与安全

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/evidence` | 查看证据列表 |
| GET | `/sessions/{session_id}/evidence/{evidence_id}` | 查看单条证据 |
| POST | `/sessions/{session_id}/evidence/{evidence_id}/verify` | 核验证据 |
| GET | `/sessions/{session_id}/safety-findings` | 查看安全发现 |
| POST | `/sessions/{session_id}/safety-findings/{finding_id}/resolve` | 处理安全发现 |

---

## Eval

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/eval-cases` | 查看 EvalCase 列表 |
| POST | `/sessions/{session_id}/eval-cases/{eval_id}/score` | 人工评分单个 EvalCase |
| GET | `/sessions/{session_id}/eval-runs` | 查看 EvalRun 列表 |
| POST | `/sessions/{session_id}/eval-cases/run` | 批量运行 EvalCase |
| POST | `/sessions/{session_id}/eval-cases/{eval_id}/run` | 运行单个 EvalCase |
| GET | `/sessions/{session_id}/eval-judgments` | 查看自动评判记录 |
| GET | `/sessions/{session_id}/human-calibrations` | 查看人工校准记录 |
| POST | `/sessions/{session_id}/eval-runs/{run_id}/calibrate` | 对 EvalRun 做人工校准 |

---

## Eval 数据集

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/eval-datasets` | 列出数据集 |
| POST | `/sessions/{session_id}/eval-datasets` | 创建数据集 |
| POST | `/sessions/{session_id}/eval-datasets/from-stage3` | 从 Stage 3 生成数据集 |
| GET | `/sessions/{session_id}/eval-datasets/{dataset_id}` | 查看单个数据集 |
| POST | `/sessions/{session_id}/eval-datasets/{dataset_id}/cases` | 向数据集添加 case |
| DELETE | `/sessions/{session_id}/eval-datasets/{dataset_id}/cases` | 从数据集删除 case |
| POST | `/sessions/{session_id}/eval-datasets/{dataset_id}/baseline` | 设置 baseline |

---

## Eval 实验

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/eval-experiments` | 列出实验 |
| POST | `/sessions/{session_id}/eval-experiments` | 创建实验 |
| GET | `/sessions/{session_id}/eval-experiments/{experiment_id}` | 查看单个实验 |
| POST | `/sessions/{session_id}/eval-experiments/{experiment_id}/run` | 运行实验 |
| GET | `/sessions/{session_id}/eval-experiments/{experiment_id}/metrics` | 查看实验指标 |
| GET | `/sessions/{session_id}/eval-experiments/{experiment_id}/comparison` | 查看实验对比摘要 |
| POST | `/sessions/{session_id}/eval-experiments/{experiment_id}/comparison` | 生成实验对比 |

---

## Red Team

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/redteam/cases` | 列出 redteam case |
| GET | `/sessions/{session_id}/redteam/coverage` | 查看覆盖率摘要 |
| POST | `/sessions/{session_id}/redteam/generate` | 生成 redteam case |
| POST | `/sessions/{session_id}/redteam/cases` | 手工创建 redteam case |
| POST | `/sessions/{session_id}/redteam/cases/{case_id}/approve` | 批准 case |
| POST | `/sessions/{session_id}/redteam/cases/{case_id}/reject` | 拒绝 case |
| POST | `/sessions/{session_id}/redteam/cases/{case_id}/to-eval-case` | 转为 EvalCase |
| POST | `/sessions/{session_id}/redteam/datasets` | 创建 redteam 数据集 |

---

## 追踪与报告

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/traces` | 列出追踪 |
| GET | `/sessions/{session_id}/traces/{trace_id}` | 查看单条追踪 |
| POST | `/sessions/{session_id}/traces/{trace_id}/to-eval-case` | 追踪转 EvalCase |
| POST | `/sessions/{session_id}/traces/to-eval-dataset` | 批量追踪转数据集 |
| POST | `/sessions/{session_id}/reports` | 创建报告 artifact |
| GET | `/sessions/{session_id}/reports` | 列出报告 artifact |
| GET | `/sessions/{session_id}/reports/{report_id}` | 查看单个报告 artifact |

---

## Interrupt 记录

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/interrupt-records` | 列出 interrupt records |
| GET | `/sessions/{session_id}/interrupt-records/{interrupt_id}` | 查看单条 interrupt record |
