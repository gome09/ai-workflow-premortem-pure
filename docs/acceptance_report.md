# AI Workflow Pre-mortem 验收报告

## 测试概述

| 项目 | 详情 |
|------|------|
| 测试类型 | 本地离线全流程 E2E 测试 |
| 测试环境 | SQLite + Mock LLM（无需真实 LLM，无需 Docker） |
| 会话 ID | `91e799e4-15d1-4af3-baa9-79a8be890eb5` |
| 测试时间 | 2026-07-14T15:20:00 - 2026-07-14T15:20:18（v1.2.1 全流程 E2E 实测）；2026-07-18 四种启动方式复测（见下节） |
| 测试结果 | ✅ PASS |
| 当前版本 | v1.3.0（含 Phase 1 安全合规 + Phase 2 风险分类 + Phase 3 治理平台 + Phase 4 社区打磨 + formal-project-uplift Wave A–E；四阶段 E2E 会话实测于 v1.2.1，v1.3.0 回归验证见下节） |
| 前端验证 | ✅ Streamlit 工作台正常渲染，JWT 自动登录，无控制台错误，无失败网络请求 |
| 后端监控 | ✅ 全部 HTTP 200 OK，无 WARNING / ERROR / Exception |

## v1.3.0 回归验证（2026-07-17）

v1.3.0（formal-project-uplift Wave A–E）在 v1.2.1 基础上的变更均不改动四阶段工作流执行路径：治理门面文件（CODE_OF_CONDUCT / GOVERNANCE / CODEOWNERS）、mypy 渐进式类型检查（153 源文件 0 issue）、T3.6 LLM Judge（`EVAL_LLM_JUDGE` / `EVAL_LLM_JUDGE_AUTOFINAL` 双 flag，默认全关）、合规映射 2026-07-17 复核落账（ISO/IEC 42005 对标 + roadmap §10.7）、公开前安全扫描与 CI 覆盖率产出（doc-check 转 blocking）。

| 验证项 | 结果 |
|------|------|
| 全量测试（Mock + SQLite 离线） | ✅ 650 passed, 1 skipped（2026-07-17 实测，含 LLM Judge 新增 8 条） |
| e2e-mock 场景验收 | ✅ 63 passed（2026-07-17 实测） |
| 版本一致性 | ✅ `core/version.py` = `pyproject.toml` = 1.3.0，git tag `v1.3.0` |
| 四阶段全流程 E2E 会话 | 沿用 2026-07-14 v1.2.1 实测快照（见下节；v1.3.0 无工作流行为变更，新增能力均在默认关闭 flag 之后） |

## 四种启动方式全流程复测（2026-07-18）

四种启动方式全部冷启动实测 PASS，验证方法为 API 冒烟 + Playwright 浏览器驱动真实 UI 交互 + 后台日志监控；Docker 构建使用 `--no-cache` 防旧镜像污染。完整报告见 `.upgrade/reports/startup-methods-e2e-20260718.md`。

| 启动方式 | 结果 | 关键验证 |
|------|------|------|
| 离线演示（uv + mock + SQLite） | ✅ PASS | API 与 UI 双路径走满四阶段至 complete；四阶段 gate-report 全部 overall=passed（13 规则）；报告导出 JSON/Markdown + 快照 |
| Docker Lite（2 容器） | ✅ PASS | `--no-cache` 全新构建；/health/ready ready；登录→建会话→chat 推进→readiness 全链路 |
| 混合开发（容器 DB 临时端口 15432/16379） | ✅ PASS | alembic 自动建 21 张表；会话数据落 postgres、缓存落 redis 实测确认 |
| 生产栈（7 容器 + nginx TLS + 监控） | ✅ PASS | 自建 secrets；HTTP→HTTPS 301；`/api/` 反代全链路冒烟；Prometheus target up + Grafana healthy；空库冷启动双 worker 无迁移竞态 |

本轮测试发现并修复 6 处缺陷（注册限流 429 致前端 401 / secrets CRLF 致 redis 认证失败 / alembic 多 worker 竞态 / 治理总览页不可达 / `interrupt_adapter_status` 字段缺失 / 前端丢弃字段补展示），修复后全量回归 650 passed, 1 skipped，明细见 CHANGELOG 维护记录 (2026-07-18) 与上述报告。

## 问题修复记录

### 问题描述
用户反馈"待处理人工动作已经全部完成，但依旧存在阻断"的现象。前端显示"无待处理人工动作"，但阶段推进阻断器仍然存在。此问题涉及两个场景：
1. **阶段1证据核验**：证据门控阻断器无法通过处理人工动作解除
2. **阶段3红队测试**：红队测试覆盖阻断器无法通过处理人工动作解除

### 根因分析

**问题1：证据门控**
在 `resolve_action` 函数中，处理 `verify_evidence` 类型的人工动作时，只是将动作状态标记为 `RESOLVED`，但**没有更新对应的 `evidence.verified` 字段**。而证据门控（`stage1_evidence_gap.py`）检查的是 `evidence.verified`，不是动作是否已解决。

**问题2：红队测试覆盖门控**
`create_review_actions_for_stage` 函数中**没有创建红队测试覆盖相关的人工动作**。红队测试覆盖门控（`redteam_coverage.py`）会生成阻断器，但没有对应的人工动作让用户去处理，导致前端显示"无待处理人工动作"但阻断器仍然存在。

### 修复方案

**修复1：证据门控**
在 [core/oversight_service.py](../core/oversight_service.py) 的 `resolve_action` 函数中添加了处理 `verify_evidence` 动作的逻辑：
- 当 `action.action_type == "verify_evidence"` 且决策不是 dismiss/reject 时
- 从 `action.payload_before` 中提取 `weak_sources` 和 `unverified_sources` 中的 `evidence_id`
- 将对应的 `evidence.verified` 设置为 `True`
- 添加审计事件记录

**修复2：红队测试覆盖门控**
1. 在 [core/oversight_service.py](../core/oversight_service.py) 添加了 `create_actions_from_redteam_gaps` 函数：
   - 检查 `build_redteam_coverage_summary` 返回的各种 gap 类型
   - 为每种 gap 类型创建对应的 PendingHumanAction
   - 包括：missing_safety_redteam_case, missing_node_redteam_case, draft_redteam_case, approved_redteam_case_not_synced, redteam_eval_case_not_in_dataset

2. 在 `create_review_actions_for_stage` 中注册了新函数

3. 在 [core/oversight_service.py](../core/oversight_service.py) 的 `resolve_action` 函数中添加了红队动作处理分支：
   - `missing_safety_redteam_case` / `missing_node_redteam_case` → 调用 `generate_redteam_cases`
   - `draft_redteam_case` → 调用 `approve_redteam_case`
   - `approved_redteam_case_not_synced` → 调用 `redteam_case_to_eval_case`
   - `redteam_eval_case_not_in_dataset` → 调用 `create_redteam_dataset`

## 四阶段测试结果（2026-07-14 v1.2.1 复测）

### 阶段 1：失败模式识别
- **失败模式数量**: 2 个
- **证据核验**: 通过处理 verify_evidence 动作自动更新（v1.0.2 修复后持续有效）
- **人机监督**: pending actions 全部 resolved
- **推进结果**: ✅ 成功进入阶段 2（hard_blockers=0）

### 阶段 2：人机协同工作流设计
- **工作流节点数量**: 2 个
- **人机监督**: 1 个 human_action，已 resolved
- **推进结果**: ✅ 成功进入阶段 3（hard_blockers=0）

### 阶段 3：压力测试 / EvalCase 生成
- **Eval Cases**: 通过 /eval-cases 端点获取（端点返回 200，数据存在）
- **Red Team Cases**: /redteam/cases 与 /redteam/coverage 端点均返回 200
- **人机监督**: 1 个 human_action，已 resolved
- **推进结果**: ✅ 成功进入阶段 4（hard_blockers=0）

### 阶段 4：触发策略与部署建议
- **触发方法数量**: 2 个
- **人机监督**: 2 个 human_action，全部 resolved
- **推进结果**: ✅ 流程完成（current_state=complete）

## 最终状态面板

| 面板 | 状态 |
|------|------|
| stage_readiness | ✅ 通过 |
| stage_resolution | ✅ 通过 |
| stage_advancement_decision | ✅ 通过 |
| actions_count | ✅ 0 个待处理 |
| interrupt_records | ✅ 通过 |
| evidence | ✅ 通过 |
| safety_findings | ✅ 通过 |
| eval_cases | ✅ 通过 |
| eval_runs | ✅ 通过 |
| eval_datasets | ✅ 通过 |
| eval_experiments | ✅ 通过 |
| redteam_cases | ✅ 通过 |
| redteam_coverage | ✅ 通过 |
| audit_events | ✅ 通过 |
| reports | ✅ 通过 |
| traces | ✅ 通过 |

## 前后端链路验证（2026-07-14 新增）

| 验证项 | 结果 |
|------|------|
| 后端 /health | ✅ 200 OK，version=1.2.1（实测当时版本），mode=single_step |
| 后端 /health/live | ✅ 200 OK |
| 前端 Streamlit 页面 | ✅ 200 OK，正常渲染欢迎页 |
| 前端 JWT 自动登录 | ✅ demo 用户注册/登录成功，access_token 写入 session_state |
| 前端→后端 API 调用 | ✅ 16 个 panel 端点全部返回 200（stage-readiness / stage-resolution / actions / evidence / safety-findings / eval-cases / eval-runs / eval-datasets / eval-experiments / interrupt-records / reports / audit-events / traces / redteam-cases / redteam-coverage / advancement-decision） |
| 治理 API（T3.4） | ✅ /governance/overview、/governance/gate-trends、/governance/actions-backlog 均返回 200 |
| 浏览器控制台 | ✅ 无 JavaScript 错误 |
| 浏览器网络请求 | ✅ 无失败请求 |
| 后端日志监控 | ✅ 全部 200 OK，无 WARNING / ERROR / Exception |
| 报告导出 | ✅ JSON + Markdown 双格式导出成功 |
| 报告快照 | ✅ RPT-c4e668a3 创建并读取成功 |

## 安全发现汇总

| 安全发现 ID | 风险等级 | 类型 | 状态 |
|-------------|----------|------|------|
| SAFE-67db6f9d | high | prompt_injection | resolved |
| SAFE-c36252d1 | high | prompt_injection | resolved |
| SAFE-f6eeee97 | high | prompt_injection | resolved |
| SAFE-[其他] | medium | source_untrusted | open |

## 人机监督统计

| 指标 | 数量 |
|------|------|
| total_actions | 10 |
| pending_actions | 0 |
| pending_blocking_actions | 0 |
| resolved_actions | 10 |
| rejected_actions | 0 |
| critical_escalations | 0 |

## 修复验证要点

1. **证据门控与人工动作联通**: 修复后，处理 `verify_evidence` 类型的人工动作时，会自动更新对应证据的 `verified` 字段
2. **阶段推进阻断器清除**: 证据验证后，`stage1_evidence_gap` 门控规则不再生成阻断项
3. **前端显示一致**: "无待处理人工动作"状态与阶段可推进状态保持一致

---

*报告生成时间: 2026-07-14T15:20:18（四阶段 E2E 实测，v1.2.1）*
*报告最近更新: 2026-07-17（v1.3.0 回归验证段追加，报告架构版本同步 1.3.0）*
*报告架构版本: 1.3.0*
*历史修复版本: v1.0.1 / v1.0.2（证据门控与红队覆盖门控联通）*
*复测覆盖: Phase 1 安全合规 + Phase 2 风险分类 + Phase 3 治理平台 + Phase 4 社区打磨 + formal-project-uplift Wave A–E（v1.3.0）*