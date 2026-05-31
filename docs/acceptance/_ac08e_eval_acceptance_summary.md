# AC-08E Eval 阶段验收汇总

**日期**: 2026-05-09
**范围**: AC-08A / AC-08B/C / AC-08D 汇总
**结论**: 通过 — 建议进入 AC-09A ReportArtifact 验收

---

## 1. AC-08A EvalCase Coverage Gate 结论

**结果**: 通过（9/9 验收标准）

- EvalCase 模型字段完整（eval_id, target_node_id, covered_failure_mode_ids, scenario_type, input_payload, expected_behavior, pass_criteria, passed, human_score 等）
- 高风险节点通过 `_high_risk_node_ids()` 正确识别（Stage 1 high/critical FM → Stage 2 WorkflowNode）
- 缺少 EvalCase 覆盖 → `eval_failure` blocker（gap_type=missing_eval_case_coverage）
- 正确 EvalCase（target_node_id 匹配）→ 覆盖率缺口清除
- 错误 target_node_id → 不误清除正确目标的 blocker

**审计脚本**: `_ac08a_evalcase_coverage_gate_audit.py` (3 scenarios)

---

## 2. AC-08B/C EvalRun + Scoring + Blocker/Action 结论

**结果**: 通过（11/11 验收标准）

- `run_eval_case(manual)` 安全创建 EvalRun（不调 LLM，judge_mode=human）
- 完整字段写入：run_id, eval_id, target_node_id, status, judge_result, judge_mode, actual_output 等
- judge_result=failed → `eval_failure` blocker + blocking PendingHumanAction
- judge_result=needs_review → `eval_failure` blocker + blocking PendingHumanAction
- `score_eval_case()` 保存 human_score/human_comment/passed/scored_at
- 评分写入 `eval_case_scored` 审计事件
- Action resolve (decision=edit + payload_after) 清除对应 eval blocker

**审计脚本**: `_ac08bc_evalrun_scoring_gate_audit.py` (6 scenarios)

---

## 3. AC-08D API 可见性结论

**结果**: 通过（12/12 验收标准）

**API 路由清单**:

| Method | Path | Handler |
|--------|------|---------|
| GET | `/sessions/{id}/eval-cases` | list_eval_cases |
| POST | `/sessions/{id}/eval-cases/{eid}/score` | score_eval_case |
| GET | `/sessions/{id}/eval-runs` | list_eval_runs |
| POST | `/sessions/{id}/eval-cases/run` | run_eval_cases |
| POST | `/sessions/{id}/eval-cases/{eid}/run` | run_single_eval_case |
| GET | `/sessions/{id}/stage-readiness` | list_stage_readiness |
| GET | `/sessions/{id}/stage-readiness/{sid}` | read_stage_readiness |
| GET | `/sessions/{id}/stage-gate/{sid}` | read_stage_gate |

- EvalCase API 透出 8+ 字段（eval_id, stage_id, target_node_id, covered_failure_mode_ids, input_payload, expected_behavior, pass_criteria, scenario_type）
- Single run API (dry_run) 产生 EvalRun（不调 LLM）
- EvalRun API 透出 run_id, eval_id, target_node_id, run_mode, status, judge_result, judge_mode
- Readiness API 透出 eval_failure blocker（含 5 个必要字段）
- Score API 透出 human_score, human_comment, passed, scored_at
- 7 个审计事件记录，6 种类型

**审计脚本**: `_ac08de_eval_api_visibility_summary_audit.py` (7 TestClient tests)

---

## 4. 通过项矩阵

### EvalCase 能力矩阵

| 能力 | AC-08A | AC-08BC | AC-08D |
|------|--------|---------|--------|
| 模型创建（eval_id, target_node_id, covered_failure_mode_ids, ...） | P | P | - |
| 覆盖度检查（high-risk node - eval_case_nodes） | P | - | - |
| 覆盖率缺口 → eval_failure blocker | P | - | P |
| EvalCase.passed=False → eval_failure blocker | - | - | P |
| API list 透出 | - | - | P |

### EvalRun 能力矩阵

| 能力 | AC-08BC | AC-08D |
|------|---------|--------|
| manual mode 创建（不调 LLM） | P | - |
| dry_run mode 创建（不调 LLM） | - | P |
| 字段写入（run_id, eval_id, target_node_id, status, judge_result, judge_mode） | P | P |
| failed → eval_failure blocker | P | P |
| needs_review → eval_failure blocker | P | P |
| failed/needs_review → PendingHumanAction | P | - |
| API list 透出 | - | P |
| API single run | - | P |

### Stage Gate Eval Blocker 矩阵

| 能力 | AC-08A | AC-08BC | AC-08D |
|------|--------|---------|--------|
| missing_eval_case_coverage | P | - | - |
| EvalRun failed → eval_failure | - | P | P |
| EvalRun needs_review → eval_failure | - | P | P |
| 5 个必要字段完整性 | P | P | P |
| Action resolve 清除 blocker | - | P | P |
| API readiness/gate 透出 | - | - | P |

### PendingHumanAction 矩阵

| 能力 | AC-08BC |
|------|---------|
| Coverage gap → edit action | P |
| EvalRun needs_review → edit action (high-risk path) | P |
| EvalRun failed → edit action | P |
| Action 关联 eval_run source_type + source_id | P |
| blocking=True for high-risk | P |

### AuditEvent 矩阵

| 事件类型 | AC-08BC | AC-08D |
|----------|---------|--------|
| eval_run_created | P | P |
| eval_run_judged (manual) | P | - |
| eval_run_completed (dry_run) | - | P |
| eval_case_scored | P | P |
| human_action_created | P | P |
| human_action_resolved | P | P |

### API 可见性矩阵

| 端点 | AC-08D |
|------|--------|
| GET /eval-cases (8+ fields) | P |
| POST /eval-cases/{eid}/run (dry_run, no LLM) | P |
| GET /eval-runs (7 fields) | P |
| GET /stage-readiness/3 (eval_failure blockers) | P |
| POST /eval-cases/{eid}/score (human_score/comment/passed) | P |
| Action resolve → blocker cleared in readiness | P |

---

## 5. 未解决风险

### 后移到 AC-09 ReportArtifact

| 风险 | 说明 |
|------|------|
| Eval summary 在 Report JSON/Markdown 导出中的正确性 | `build_eval_summary()` 已实现，待 AC-09 验证 |
| Report 中包含 eval_failure blocker 信息 | 待 AC-09 验证 |
| Report 中包含 unverified evidence + open safety + eval 三类未关闭项 | 待 AC-09 联合验证 |

### 后移到 PostgreSQL / Redis

| 风险 | 说明 |
|------|------|
| EvalCase/EvalRun JSONB 持久化 | model_dump_json() 已就绪 |
| 大量 EvalRun 的查询性能 | 后移至性能验收 |
| Redis 热缓存与 PG 冷存储一致性 | context_cache 已有降级逻辑 |

### 后移到 Streamlit

| 风险 | 说明 |
|------|------|
| Eval 面板（case 列表/run 列表/score 交互） | 前端组件待开发 |
| Stage Gate blocker 可视化（含 eval_failure） | 前端组件待开发 |

### 后移到真实 LLM / 集成验收

| 风险 | 说明 |
|------|------|
| llm_node 模式的真实 LLM 调用 | 后移至集成测试 |
| 完整四阶段流程中 eval 的端到端行为 | 后移至集成验收 |
| 三类 blocker (evidence + safety + eval) 在完整流程中的联合 gate | AC-07C 已证明结构独立 |

---

## 6. AC-08 系列总览

| 子任务 | 范围 | 标准数 | 通过 | 修改 |
|--------|------|--------|------|------|
| AC-08A | EvalCase 覆盖率 | 9 | 9 | 0 |
| AC-08BC | EvalRun + 评分 + blocker/action | 11 | 11 | 0 |
| AC-08D | API 可见性 | 12 | 12 | 0 |
| **总计** | | **32** | **32** | **0** |

---

## 7. 是否允许进入 AC-09

### 支持理由

1. EvalCase / EvalRun 双模型闭环完整（创建 → 执行 → 评分 → audit）
2. 覆盖率 gate（missing_eval_case_coverage）+ 质量 gate（failed/needs_review）双门控
3. PendingHumanAction 与 eval blocker 联动正确
4. API 8 端点全覆盖，TestClient 验证通过
5. 零生产代码修改
6. Evidence + Safety + Eval 三类 gate 独立共存（AC-07C 已验证结构）

### 判断

**允许进入 AC-09A ReportArtifact JSON / Markdown 最小导出验收。**

---

**AC-08E 结论: 通过。Eval 阶段验收全部完成（32/32），可进入 AC-09 ReportArtifact 验收。**
