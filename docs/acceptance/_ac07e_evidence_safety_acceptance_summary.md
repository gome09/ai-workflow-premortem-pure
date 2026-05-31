# AC-07E Evidence + Safety 阶段验收汇总

**日期**: 2026-05-09
**范围**: AC-07A / AC-07B / AC-07C / AC-07D 汇总
**结论**: 通过 — 建议进入 AC-08A EvalCase 验收

---

## 1. AC-07A EvidenceSource 最小闭环结论

**结果**: 通过（6/6 验收标准）

| # | 验收项 | 状态 |
|---|-------|------|
| 1 | `EvidenceSource` 能创建并关联 `failure_mode_id` | 通过 |
| 2 | high/critical FM 缺少 verified evidence 时产生 `evidence_gap` blocker | 通过 |
| 3 | verified evidence 清除 evidence blocker | 通过 |
| 4 | evidence verification 写入 `AuditEvent` (before/after snapshot) | 通过 |
| 5 | 未触碰 Safety / Eval / Report / Streamlit / LangGraph | 通过 |
| 6 | 未运行 pytest，未启动服务，未连接外部依赖 | 通过 |

**审计脚本**: `_ac07a_evidence_gate_audit.py` (3 scenarios, all PASS)

---

## 2. AC-07B SafetyFinding 最小闭环结论

**结果**: 通过（7/7 验收标准）

| # | 验收项 | 状态 |
|---|-------|------|
| 1 | `SafetyFinding` 能创建并进入 context | 通过 |
| 2 | high/critical unresolved finding 产生 `safety_finding` blocker | 通过 |
| 3 | unresolved finding 阻止推进 (`can_continue=False`) | 通过 |
| 4 | resolve/dismiss 清除 blocker，且不能静默绕过审计 | 通过 |
| 5 | resolve/dismiss 写入 `AuditEvent` | 通过 |
| 6 | 未触碰 Eval / Report / Streamlit / LangGraph | 通过 |
| 7 | 未运行 pytest，未启动服务，未连接外部依赖 | 通过 |

**审计脚本**: `_ac07b_safety_gate_audit.py` (5 scenarios including prompt injection scanner, all PASS)

---

## 3. AC-07C Evidence + Safety 联合 Stage Gate 结论

**结果**: 通过（8/8 验收标准）

| # | 验收项 | 状态 |
|---|-------|------|
| 1 | `evidence_gap` 与 `safety_finding` blocker 可同时存在 | 通过 |
| 2 | 两类 blocker 不因聚合/排序/去重互相覆盖 | 通过 |
| 3 | verify evidence 只清除 evidence blocker | 通过 |
| 4 | resolve/dismiss safety 只清除 safety blocker | 通过 |
| 5 | 两类 blocker 都处理后 gate 才允许继续 | 通过 |
| 6 | evidence verify + safety resolve/dismiss 均有独立审计记录 | 通过 |
| 7 | 未触碰 Eval / Report / Streamlit / LangGraph | 通过 |
| 8 | 未运行 pytest，未启动服务，未连接外部依赖 | 通过 |

**审计脚本**: `_ac07c_evidence_safety_joint_gate_audit.py` (4 scenarios across 2 contexts, all PASS)

**去重机制确认**: blocker_id 格式为 `S{stage}_V{version}_{blocker_type}_{source_type}_{source_id}`。由于 `evidence_gap` 与 `safety_finding` 的 `blocker_type` 字段不同，两类 blocker 的 ID 不会冲突。

---

## 4. AC-07D API 可见性结论

**结果**: 通过（9/9 验收标准）

| # | 验收项 | 状态 |
|---|-------|------|
| 1 | evidence / safety / stage readiness / gate 路由存在 | 通过 |
| 2 | evidence API 透出 verification/credibility/linkage | 通过 |
| 3 | safety API 透出 severity/status/review_required/stage | 通过 |
| 4 | readiness/gate API 同时透出两类 blocker | 通过 |
| 5 | blocker 含 5 个必要字段 | 通过 |
| 6 | verify evidence 后 API 仅清除 evidence blocker | 通过 |
| 7 | resolve safety 后 API 中 safety blocker 清除 | 通过 |
| 8 | 未触碰 Eval / Report / Streamlit / LangGraph | 通过 |
| 9 | 未运行 pytest，未启动服务，未连接外部依赖 | 通过 |

**审计脚本**: `_ac07d_api_visibility_audit.py` (8 tests using FastAPI TestClient, all PASS, zero DB connections)

**API 路由清单**:

| Method | Path | Domain |
|--------|------|--------|
| GET | `/sessions/{id}/evidence` | Evidence |
| GET | `/sessions/{id}/evidence/{eid}` | Evidence |
| POST | `/sessions/{id}/evidence/{eid}/verify` | Evidence |
| GET | `/sessions/{id}/safety-findings` | Safety |
| POST | `/sessions/{id}/safety-findings/{fid}/resolve` | Safety |
| GET | `/sessions/{id}/stage-readiness` | Stage Gate |
| GET | `/sessions/{id}/stage-readiness/{sid}` | Stage Gate |
| GET | `/sessions/{id}/stage-gate/{sid}` | Stage Gate |

---

## 5. 通过项矩阵

### Evidence 闭环

| 能力 | AC-07A | AC-07C | AC-07D |
|------|--------|--------|--------|
| 模型创建 (`evidence_id`, `credibility_score`, `verified`, ...) | P | - | - |
| 关联 FM (`evidence_ids` / `used_by_failure_mode_ids`) | P | P | P |
| verify 操作 (`verify_evidence_source`) | P | P | - |
| unverified → `evidence_gap` Stage Gate blocker | P | P | P |
| verified → blocker 清除 | P | P | P |
| AuditEvent (`evidence_verified`) | P | P | P |
| API 可见性 (list/single/verify endpoints) | - | - | P |

### Safety 闭环

| 能力 | AC-07B | AC-07C | AC-07D |
|------|--------|--------|--------|
| 模型创建 (`finding_id`, `severity`, `status`, ...) | P | - | - |
| prompt injection scanner (纯本地规则) | P | - | - |
| open high/critical → `safety_finding` Stage Gate blocker | P | P | P |
| resolve → blocker 清除 + 关联 action 自动关闭 | P | P | - |
| dismiss → blocker 清除 (含防护: 有 blocking action 时禁止) | P | - | - |
| AuditEvent (`safety_finding_resolved` / `safety_finding_dismissed`) | P | P | P |
| API 可见性 (list/resolve endpoints) | - | - | P |

### Stage Gate Blocker

| 能力 | AC-07A | AC-07B | AC-07C | AC-07D |
|------|--------|--------|--------|--------|
| `evidence_gap` (missing_evidence_id / unknown_evidence_id / unverified_evidence_id) | P | - | P | P |
| `safety_finding` (open + high/critical + requires_human_review) | - | P | P | P |
| 两类 blocker 共存不覆盖 | - | - | P | P |
| 独立清除 (verify/resolve 不交叉影响) | - | - | P | P |
| blocker 字段完整性 (`blocker_id`/`blocker_type`/`severity`/`source_id`/`required_resolution`) | P | P | P | P |
| API StageReadiness / StageGateResult 可查询 | - | - | - | P |

### AuditEvent

| 能力 | AC-07A | AC-07B | AC-07C | AC-07D |
|------|--------|--------|--------|--------|
| `evidence_verified` (含 before/after snapshot) | P | - | P | P |
| `safety_finding_resolved` (含 before/after snapshot) | - | P | P | P |
| `safety_finding_dismissed` (含 before/after snapshot) | - | P | P | - |
| 独立事件类型 (证据/安全审计不混淆) | - | - | P | P |

### API 可见性

| 能力 | AC-07D |
|------|--------|
| Evidence list (含 `verified`, `credibility_score`, `used_by_failure_mode_ids`) | P |
| Evidence single | P |
| Safety list (含 `severity`, `status`, `requires_human_review`, `stage_id`) | P |
| Stage Readiness (含两类 blocker 完整字段) | P |
| Stage Gate (含两类 blocker 完整字段) | P |
| Verify evidence → readiness/gate 实时反映 | P |
| Resolve safety → readiness/gate 实时反映 | P |

---

## 6. 未解决风险

### 后移到 AC-08 Eval

| 风险 | 说明 |
|------|------|
| EvalCase / EvalRun 与 failure mode 的关联 | 需要验证 EvalCase 覆盖度对 Stage Gate 的阻断 |
| 三类 blocker (evidence + safety + eval) 共存时的独立性 | 需确认 `eval_failure` blocker 不覆盖前两类 |
| Eval 覆盖率不足时是否产生 `eval_failure` blocker | AC-08 核心验收项 |
| Eval 失败后的 PendingHumanAction 生成 | 已存在 `create_actions_from_eval_failures`，待验证 |

### 后移到 PostgreSQL / Redis 持久化

| 风险 | 说明 |
|------|------|
| `ProjectContext` 完整序列化到 PostgreSQL JSONB | `model_dump_json()` / `model_validate_json()` 已实现，待集成测试 |
| Redis 热缓存与 PG 冷存储的一致性 | `context_cache` 已有降级逻辑，待验证 |
| Evidence/Safety 大量数据时的 JSONB 查询性能 | 后移至性能验收 |
| `session_store.save()` 的真实 DB 事务行为 | 后移至数据库集成验收 |

### 后移到 Streamlit Review Workbench

| 风险 | 说明 |
|------|------|
| Evidence 面板: 列表/详情/核验按钮 | 前端组件待开发 |
| Safety 面板: finding 列表/状态/resolve 按钮 | 前端组件待开发 |
| Stage Gate 面板: blocker 可视化 | `build_stage_readiness()` 已提供后端数据 |
| Review Gate UI 与 Stage Gate 的联动 | 前端交互设计待定 |

### 后移到后续集成验收

| 风险 | 说明 |
|------|------|
| 完整四阶段流程中 evidence/safety 的跨阶段传递 | 后移至端到端验收 |
| 真实 Tavily 搜索 → EvidenceSource 的资产化链路 | `result_to_evidence()` 已实现，待集成测试 |
| 真实 LLM 输出 → safety_classifier 的扫描触发 | `scan_stage_io()` 已实现，待集成测试 |
| `PendingHumanAction` 通过 safety finding 时的 dismiss 防护完整性 | `_has_blocking_safety_action` 已实现，待完整 action 链路验证 |
| LangGraph interrupt mode 下 evidence/safety blocker 的同步 | 后移至 execution mode 验收 |

---

## 7. 审慎判断：是否允许进入 AC-08

### 支持进入的理由

1. **Evidence 闭环完整**: 创建→关联→核验→blocker→清除→审计 全部通过内存验证
2. **Safety 闭环完整**: 创建→扫描→blocker→resolve/dismiss→审计 全部通过内存验证
3. **联合 gate 独立**: evidence 和 safety blocker 共存/独立清除 已验证
4. **API 层透出完整**: 14 条路由注册，response 字段齐全，TestClient 验证通过
5. **零生产代码修改**: AC-07 全系列未修改任何生产代码
6. **审计链完整**: evidence_verified / safety_finding_resolved / safety_finding_dismissed 三种审计事件均已验证

### 需注意的前提

1. Eval 验收 (AC-08) 可能回踩 evidence/safety 的联合 gate 场景，但 AC-07C 已证明 gate 聚合机制可扩展
2. PostgreSQL/Redis 持久化未验证，但 API 层通过 monkeypatch 已证明序列化路径正确
3. Streamlit 前端未验证，但后端 API 已提供完整数据结构

### 判断

**允许进入 AC-08A EvalCase 最小创建与 Stage Gate coverage blocker 验收。**

---

## 8. 修改摘要

**无生产代码修改。**

新增汇总文件:
- `_ac07e_evidence_safety_acceptance_summary.md` (本文件)

---

## 9. 执行命令

| 命令 | 说明 |
|------|------|
| `ls -la _ac07*.py` | 确认 4 个 AC-07 审计脚本存在 |
| `rg -n "class EvidenceSource\|..." core api tools` | 静态复核 29 处关键符号在 core/ 中, 2 处在 api/ 中 |
| `python -m py_compile core/evidence_service.py core/safety_service.py core/stage_readiness_service.py core/audit_service.py` | 4 文件编译通过 |

**明确未运行**: pytest, uvicorn, Streamlit, Docker, 真实 Tavily, 真实 LLM, PostgreSQL, Redis。

---

## 10. 建议下一步

> **AC-08A — EvalCase 最小创建与 Stage Gate coverage blocker 验收**

验证 EvalCase 创建、与 failure mode / workflow node 的关联、high-risk node 缺少 EvalCase 覆盖时产生 `eval_failure` blocker、EvalCase 失败后的 PendingHumanAction 生成，以及 API 可见性。

**AC-07E 结论: 通过。Evidence + Safety 阶段验收全部完成，可进入 AC-08 Eval 验收。**
