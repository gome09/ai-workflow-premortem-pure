# API 接口参考

> 本文档按当前源码静态提取整理。
> 当前仓库可直接识别的 HTTP 路由总数为 `104`（`api/routers/*.py` 90 条 + `auth/router.py` 11 条 + `/health*` 3 条；`/metrics` 由监控组件在运行时挂载）。

> Status: Implemented（HTTP 路由按当前源码静态提取）
> 最近复核：2026-11-07（路由数与 v1.8.0 发布门禁端点核对）

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
| POST | `/auth/register` | 创建工作区并注册；创建者固定为 `admin`（不再是“首个全局用户”） |
| POST | `/auth/login` | 登录；使用 `OAuth2PasswordRequestForm`，不是 JSON body |
| POST | `/auth/refresh` | 使用 refresh token 换取新的 access token；角色取自当前用户记录，降级后不会恢复旧权限 |
| GET | `/auth/users` | 列出租户内用户，`admin` only |
| PATCH | `/auth/users/{user_id}/role` | 更新用户角色，`admin` only |
| POST | `/auth/invitations` | 创建同租户邀请；原始 token 仅返回一次，`admin` only |
| GET | `/auth/invitations` | 列出本租户邀请（不返回 token），`admin` only |
| POST | `/auth/invitations/accept` | 接受邀请并创建成员，返回 token 对；公开端点 + 限流 |
| POST | `/auth/service-tokens` | 创建租户级机器凭证（`admin` only；原始 token 仅返回一次，默认 90 天，`Cache-Control: no-store`） |
| GET | `/auth/service-tokens` | 列出本租户机器凭证（不返回原始 token 或 hash，`admin` only） |
| DELETE | `/auth/service-tokens/{token_id}` | 撤销机器凭证（`admin` only；重复撤销幂等） |

---

## 会话与对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/sessions/` | 创建新会话 |
| GET | `/sessions/scenarios` | 列出内置场景（须在 `/sessions/{session_id}` 之前注册，否则会被后者的路径参数捕获） |
| GET | `/sessions/scenarios/{scenario_id}` | 查看单个内置场景详情 |
| GET | `/sessions/` | 列出会话 |
| GET | `/sessions/{session_id}` | 获取完整会话上下文 |
| PATCH | `/sessions/{session_id}/name` | 修改会话名称（editor / admin；租户隔离并记录审计事件） |
| PATCH | `/sessions/{session_id}/data-classification` | 覆写会话数据分级（editor+；降级须 admin 并写审计事件） |
| GET | `/sessions/{session_id}/risk-profile` | 读取六因子风险画像、结构/floor/生效等级与 override 历史（viewer+） |
| PUT | `/sessions/{session_id}/risk-profile` | 显式设置六因子（0–3；editor+；若生效等级下降则须 admin；写 `risk_profile_updated` 审计事件） |
| POST | `/sessions/{session_id}/risk-profile/override` | 人工覆写风险等级（editor+；降级须 admin 且不得低于确定性 floor；写 `risk_tier_overridden` 审计事件，含原等级/请求等级/生效等级/floor/原因/操作者/租户） |
| DELETE | `/sessions/{session_id}` | 删除会话（admin；审计归档保留，写 `session_purged` 处置事件） |
| POST | `/chat/{session_id}` | 发送消息并推进一个执行回合；会话处于 `ERROR` / `RECOVERY_REQUIRED` 时返回 409；模型上游超时/失败时返回 502 |
| POST | `/sessions/{session_id}/workflow/recover` | 将 `ERROR` / `RECOVERY_REQUIRED` 会话显式恢复到可推进状态（editor / admin）；`target_state` 必须属于可恢复集合，写 `workflow_recovered` 审计事件 |
| POST | `/sessions/{session_id}/materials` | 追加用户材料（更新材料输入版本） |
| PUT | `/sessions/{session_id}/target-deployment` | 声明/更新目标部署 endpoint+version（editor+；实际变化使旧审批与旧运行失效） |
| POST | `/sessions/{session_id}/flags/resolve` | 处理需核验项 |
| GET | `/sessions/{session_id}/export` | 导出报告（`json` 或 `markdown`） |

阻断语义：`/chat`、阶段推进与动作处理入口会在服务层调用 `core.workflow_state_service.assert_advanceable`。会话处于 `ERROR` / `RECOVERY_REQUIRED`（含存储层发现未知持久化状态后自动改写为 `RECOVERY_REQUIRED` 的情形）时返回 HTTP 409 `WorkflowBlockedError`，不执行任何节点；唯一出口是上述 `/workflow/recover` 端点。目标状态非法返回 400、目标状态合法但当前未阻断返回 409、会话不存在返回 404。

模型失败语义：真实模型调用超时、限流、鉴权、连接或 5xx 失败统一返回 HTTP 502，响应体为 `{"detail": "Model provider call failed...", "error_code": "timeout|rate_limit|auth|connection|server_error|bad_request|provider_error", "retryable": true|false, "session_id": "...", "stage": 0-4}`。响应不包含 provider 原文、提示词、密钥或用户内容；出站 PII 守卫失败仍按 fail-closed 原路径处理，不会伪装成 502。

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
| GET | `/sessions/{session_id}/gate-report` | 获取单阶段 Gate 诊断报告；`stage` 为必填 query 参数（1–4） |

---

## 人机监督

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/actions` | 列出人工动作 |
| GET | `/sessions/{session_id}/actions/{action_id}` | 查看单个人工动作 |
| GET | `/sessions/{session_id}/actions/{action_id}/resolution-logs` | 查看动作处理日志 |
| POST | `/sessions/{session_id}/actions/{action_id}/resolve` | 处理人工动作；CRITICAL `expert_review` 批准须 admin 且非会话创建者，资质/身份/独立性失败返回 403，风险摘要过期返回 409 |
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

## 业务闭环（风险处置与上线批准）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/risk-treatments` | 查看风险处置记录、要求项与覆盖摘要（viewer+） |
| POST | `/sessions/{session_id}/risk-treatments` | 创建/更新高风险项处置（editor+） |
| POST | `/sessions/{session_id}/risk-treatments/{treatment_id}/review` | 独立复核处置（editor+，复核人不得是最后更新人） |
| GET | `/sessions/{session_id}/approval-status` | 查看报告生成/评估完成/上线批准三段状态、release readiness、必测集合与 release batch |
| GET | `/sessions/{session_id}/approvals` | 查看 append-only 上线批准历史（含 `effective_status`：approved / stale / invalidated / rejected） |
| POST | `/sessions/{session_id}/approvals/release` | 申请上线批准（仅 admin 且非创建者；前置条件不满足返回 409 blockers） |

错误口径：403 = 角色/身份/自审批；409 = 前置条件不满足或处置版本过期；400 = public_demo 不适用或非法处置来源。

---

## 发布门禁（机器调用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/release-gate/{session_id}` | 部署前只读门禁检查；只接受 `Authorization: Bearer pmgate_...` 服务凭证（scope `release_gate:read`），人类 JWT 不通过 |

契约：

- `decision=allow` 当且仅当当前 `ProjectApproval.effective_status=approved`、`release_readiness.can_approve=true`，且 `evaluation_version_digest` / `evidence_digest` 均为当前计算值。
- 其他情况返回 HTTP 200 + `decision=block`，`reason_code` 为 `approval_not_requested` / `approval_rejected` / `approval_stale` / `approval_invalidated` / `not_applicable` / `prerequisites_not_met` 之一；`blockers` 携带固定 code / severity / source / required_resolution。
- HTTP 401 = 凭证缺失、格式错误、已撤销、已过期或不存在；403 = scope 不允许；404 = 会话不存在或跨租户；503 = 门禁计算或审计写入不可用（`decision=block` + `gate_unavailable`）。
- **只有 HTTP 200 且 `decision=allow` 才允许部署**；其他任何响应都必须由 CI 视为阻断。
- 响应设置 `Cache-Control: no-store`，不含会话正文、用户材料、审批备注或人工判定依据。每次通过认证的检查写入 `release_gate_checks`；门禁绕过 72 小时上下文缓存，直接读取存储。
- 服务凭证由 `/auth/service-tokens` 管理；数据库只存 SHA-256，原始 token 只返回一次，默认 90 天有效，可随时撤销。

---

## Eval

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/eval-cases` | 查看 EvalCase 列表 |
| PATCH | `/sessions/{session_id}/eval-cases/{eval_id}` | 更新用例标准（editor+；实际变更使 `standard_version`+1 并使旧运行失效） |
| POST | `/sessions/{session_id}/eval-cases/{eval_id}/score` | 人工评分单个 EvalCase |
| GET | `/sessions/{session_id}/eval-runs` | 查看 EvalRun 列表（含 `case_version_digest` / `target_deployment_version`） |
| POST | `/sessions/{session_id}/eval-cases/run` | 批量运行 EvalCase（`run_mode`：manual / dry_run / llm_node / target_http） |
| POST | `/sessions/{session_id}/eval-cases/{eval_id}/run` | 运行单个 EvalCase（同上；运行绑定当前用例版本与目标部署） |
| GET | `/sessions/{session_id}/eval-judgments` | 查看自动评判记录 |
| GET | `/sessions/{session_id}/human-calibrations` | 查看人工校准记录 |
| POST | `/sessions/{session_id}/eval-runs/{run_id}/calibrate` | 对 EvalRun 做人工校准；复核人固定取 JWT 身份，执行失败的真实目标运行不可改判为 passed |

`target_http` 是真实目标系统执行：请求体需带 `target_config`（endpoint / timeout_seconds / output_field），endpoint host 必须在 `TARGET_SYSTEM_ALLOWED_HOSTS` 白名单内。响应写入 `EvalRun.execution_kind`（`real_target_execution`）与 `execution_outcome`（success / failed / timeout / error）；模拟执行（manual / dry_run / mock_model_execution）不会计入上线批准证据。响应体按流式读取并受字节上限约束（由 `TARGET_SYSTEM_MAX_RESPONSE_CHARS × 4 + 4096` 推导，最低 16 KB）：声明长度或实际读取超过上限时返回 `execution_outcome=error`、`error_code=response_too_large`、`truncated=true`，不解析残缺 JSON；错误文本写入 `EvalRun.error_message` 前截断到 500 字符。

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

---

## 组织级治理（T3.4）

> 租户级聚合视图，支撑 ISO/IEC 42001 式的组织级 AI 治理台账。详见 [governance-platform.md](governance-platform.md)。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/governance/overview` | 真实业务治理总览：租户内会话数、状态/风险分布、安全发现、待处理动作、报告数和已隔离演示会话数 |
| GET | `/governance/gate-trends` | 真实业务门禁通过率周趋势（基于 `gate_evaluation_records` 聚合，不补造空周） |
| GET | `/governance/actions-backlog` | 真实业务会话的待处理人工动作积压清单 |

三个治理端点的统计口径均为当前租户的真实业务会话（`business_internal` / `sensitive_personal`）。`public_demo` 数据及带 `selected_scenario_id` 的四个内置场景会话会被排除；`/governance/overview` 通过 `excluded_demo_sessions` 返回本次隔离的演示会话数。真实业务数为零时仍返回 HTTP 200 与零值结构，不属于加载失败。
