# 风险治理 Demo 专项整改设计方案

> 基于 `docs/plan/企业 AI 项目部署前风险治理 Demo.md` 实施方案，结合当前项目实际代码状态生成。
>
> 本方案保留原有四阶段流程（失败模式识别 → 人机监督设计 → 压力测试与评测 → 部署前门禁与决策建议），不新增第五个业务阶段。

---

## 一、现状审计结论

对当前仓库进行了逐文件审查，以下为已确认的差距清单：

### 1.1 场景 fixture 语义错位（P0）

| 场景 | 当前 fixture | 当前 domain_profile | 问题 |
|---|---|---|---|
| `generic_rag_demo` | `default` | `default` | 缺少 RAG 特有风险（无依据回答、权限泄露、Prompt Injection、检索失败继续回答） |
| `university_course_qa` | `university_ai` | `university_ai` | 基本匹配，但缺少错误引用课程要求、AI 越权代写等风险 |
| `student_course_selection` | `default` | `default` | **严重错位**：使用通用幻觉 fixture，缺少先修课程、时间冲突、学分计算、毕业要求等教务风险 |
| `university_mental_health` | `university_ai` | `university_ai` | **严重错位**：输出学术诚信风险，完全缺少自伤/他伤漏报、危机误报、不当诊断、隐私泄露等心理健康风险 |

### 1.2 风险分级逻辑缺陷（P0）

`core/gates/risk_profile.py` 第 257–267 行：`_LOW_SCOPE_KEYWORDS`（包含"学习""建议""测试""Demo""辅助"等词）会将 HIGH 降级为 MEDIUM。这直接违反实施方案第五节的"领域风险下限"要求。

```python
# 当前缺陷代码（第 263–265 行）
elif tier == ProjectGateRiskTier.HIGH:
    tier = ProjectGateRiskTier.MEDIUM  # ← HIGH 被低风险词降级
```

### 1.3 Stage 4 缺少部署决策结构（P0）

`core/models.py::Stage4Output` 只有 `trigger_methods` 和 `raw_summary`，完全缺少 `decision`、`decision_scope`、`decision_rationale`、`unresolved_risk_ids`、`required_conditions`、`required_approvals`、`monitoring_requirements`、`rollback_conditions`、`prohibited_uses`、`review_after`、`human_accountable_role`、`is_demo_recommendation` 等部署门禁字段。

### 1.4 Stage 3 overall_passed 非确定性计算（P1）

`Stage3Output.overall_passed` 是一个简单 bool 字段，由 fixture 直接写入 `True`，不是由测试结果确定性计算。fixture 中 `passed: True` / `overall_passed: True` 均为硬编码。

### 1.5 跨阶段 ID 引用校验不完整（P0）

现有 gate 规则覆盖了部分缺口（`stage2_policy_gap`、`stage3_eval_failure` 等），但缺少统一的跨阶段引用完整性校验器：
- Stage 2 引用的 failure_mode_id 是否存在于 Stage 1
- Stage 3 引用的 failure_mode_id 和 node_id 是否存在
- Stage 4 的 unresolved_risk_id 是否存在
- high/critical failure mode 是否被 Stage 2 和 Stage 3 覆盖

### 1.6 模型字段缺失（P0/P1）

| 模型 | 缺失字段 |
|---|---|
| `FailureMode` | `affected_stakeholders`、`likelihood`、`possible_consequences`、`recommended_controls`、`open_questions` |
| `WorkflowNode` | `ai_can_do`、`ai_cannot_do`、`trigger_conditions`、`escalation_conditions`、`rollback_action` |
| `StressTestResult` | `case_id`、`failure_mode_id`、`forbidden_behaviors`、`evidence_type`、`is_mock_evidence`、`human_review_result`、`final_pass_status` |
| `stages/schemas.py` | 与 `core/models.py` 字段定义重复且不一致 |

### 1.7 UI 和报告差距（P1）

- 前端缺少部署决策卡片
- 风险总览缺少领域风险下限理由
- 场景选择页缺少预期结论提示
- 报告缺少部署门禁结论、部署范围、前置条件、禁止用途等章节

---

## 二、总体架构设计

### 2.1 设计原则

1. **保留四阶段流程**：不新增第五阶段，强化现有四阶段的数据依赖关系。
2. **确定性优先**：门禁决策由确定性规则计算，不完全依赖 LLM 自报。
3. **向后兼容**：新增字段使用默认值，确保旧 context_json 可加载。
4. **Mock 透明**：Mock 证据明确标记为 demo evidence，不冒充生产证据。
5. **最小侵入**：扩展现有模型和服务，不创建平行子系统。

### 2.2 数据流

```
Stage 1 (失败模式识别)
  ├─ failure_modes[] → 稳定 ID + 领域风险
  │
  ├─→ Stage 2 (人机监督设计)
  │     ├─ workflow_nodes[] → 引用 failure_mode_id[]
  │     │
  │     ├─→ Stage 3 (压力测试与评测)
  │     │     ├─ test_results[] → 引用 failure_mode_id + node_id
  │     │     ├─ overall_passed = 确定性计算(非 fixture 硬编码)
  │     │     │
  │     │     ├─→ Stage 4 (部署前门禁与决策)
  │     │     │     ├─ trigger_methods[] (保留兼容)
  │     │     │     ├─ deployment_decision{} ← 综合前 3 阶段
  │     │     │     └─ 决策由确定性规则校验
  │     │     │
  │     │     └─ 跨阶段一致性校验器(贯穿全流程)
  │     │
  │     └─ high/critical 风险覆盖检查
  │
  └─ 领域风险下限规则(单调不降级)
```

---

## 三、工作分解结构（可并行）

本方案分为 7 个工作流（Work Stream），其中 WS-1~WS-4 可并行执行，WS-5~WS-7 有依赖关系。

### WS-1：场景 fixture 语义修复（P0，可并行）

**目标**：为四个场景创建独立、语义匹配的 mock fixture。

#### 1.1 新建 fixture 文件

| 新文件 | 场景 | 覆盖风险 |
|---|---|---|
| `mock_fixtures/generic_rag_demo.py` | 通用 RAG | 无依据回答、错误引用、过期知识、权限/跨租户泄露、Prompt Injection、敏感信息暴露、检索失败继续回答、高影响回答需人工核验 |
| `mock_fixtures/university_course_qa.py` | 课程问答 | 课程政策幻觉、过期教学材料、错误引用课程要求、学术诚信、学生数据泄露、AI 越权代写、教师升级 |
| `mock_fixtures/student_course_selection.py` | 学生选课 | 先修课程判断错误、时间冲突、学分/毕业要求计算错误、课程容量过期、学籍资格遗漏、推荐偏差、学生隐私、错误建议延迟毕业 |
| `mock_fixtures/university_mental_health.py` | 心理健康 | 自伤/他伤风险漏报、危机误报、不当诊断、错误标签化、敏感信息泄露、群体偏差、不安全建议、专业人员升级失败、响应延迟、普通情绪误判为临床问题 |

#### 1.2 更新 manifest 指向

每个 scenario manifest 的 `mock_fixture` 字段指向独立 fixture：

| manifest | mock_fixture | domain_profile |
|---|---|---|
| `generic_rag_demo.json` | `generic_rag_demo` | `default` |
| `university_course_qa.json` | `university_course_qa` | `university_ai` |
| `student_course_selection.json` | `student_course_selection` | `university_ai` |
| `university_mental_health.json` | `university_mental_health` | `university_ai` |

#### 1.3 更新 mock.py fixture 注册

在 `core/llm/adapters/mock.py` 中注册 4 个新 fixture 模块。

#### 1.4 每个 fixture 的 Stage 4 输出

每个 fixture 的 `stage_4_response()` 必须包含 `deployment_decision` 结构，预期结论：

| 场景 | 预期 decision | 预期 scope |
|---|---|---|
| `generic_rag_demo` | `conditional_go` | 受限试点 |
| `university_course_qa` | `conditional_go` | 有条件部署 |
| `student_course_selection` | `pilot_only` | 受限试点 |
| `university_mental_health` | `pilot_only` 或 `no_go` | 受限试点/暂停部署 |

---

### WS-2：风险分级逻辑修复（P0，可并行）

**目标**：实现"领域风险下限"单调规则，低风险词不得覆盖高风险领域下限。

#### 2.1 修改 `core/gates/risk_profile.py`

**核心修改**：引入 domain risk floor 概念。

```python
# 领域风险下限映射
_DOMAIN_RISK_FLOOR = {
    "healthcare/medical": CRITICAL,
    "clinical/surgical": CRITICAL,
    "mental health domain": HIGH,
    "financial domain": HIGH,
    "legal domain": HIGH,
    "child safety": HIGH,
    # ... 其他 high 域
}

# classify_project_risk 修改后的算法：
# 1. 扫描 critical 域关键词 → CRITICAL（不可降级）
# 2. 扫描 high 域关键词 → 记录领域下限 HIGH
# 3. 扫描高自动化/敏感数据 → 可升级
# 4. 扫描低风险词 → 仅在不超过领域下限时可降级
# 5. 最终 tier = max(domain_floor, tier_after_low_scope_adjustment)
```

**关键规则**：
- CRITICAL 域 + 低风险词 → 仍为 CRITICAL
- HIGH 域（心理健康/金融/法律等） + "Demo""辅助""学习" → 仍为 HIGH
- 无领域关键词 + 低风险词 → 可降为 LOW
- 敏感个人数据 → 下限 HIGH
- 未成年人/高影响自动决策 → 下限 HIGH

#### 2.2 新增风险下限回归测试

| 测试用例 | 预期 tier |
|---|---|
| 心理健康场景（Stage 1 前后） | ≥ HIGH |
| "心理健康辅助学习 Demo" | ≥ HIGH |
| 医疗诊断原型 | CRITICAL |
| 通用个人笔记助手 | LOW |
| 普通企业 RAG | MEDIUM |
| 高风险自动化 | 可升级 |
| 低风险词不覆盖高风险领域下限 | HIGH 不降为 MEDIUM |

---

### WS-3：数据模型扩展（P0，可并行，WS-1/WS-4/WS-5 的前置依赖）

**目标**：扩展现有模型字段，支持部署决策和跨阶段追踪。

#### 3.1 `core/models.py` 扩展

```python
class FailureMode(BaseModel):
    # 现有字段保留...
    affected_stakeholders: list[str] = Field(default_factory=list)      # 受影响对象
    possible_consequences: str = ""                                     # 可能后果
    likelihood: Literal["low", "medium", "high"] = "medium"             # 发生可能性
    recommended_controls: str = ""                                      # 建议控制方向
    open_questions: list[str] = Field(default_factory=list)             # 尚待核实的问题


class WorkflowNode(BaseModel):
    # 现有字段保留...
    ai_can_do: str = ""                  # AI 在该节点能做什么
    ai_cannot_do: str = ""               # AI 明确不能做什么
    trigger_conditions: list[str] = Field(default_factory=list)   # 触发人工审核条件
    escalation_conditions: list[str] = Field(default_factory=list)  # 升级条件
    rollback_action: str = ""            # 高风险停止/回退动作


class StressTestResult(BaseModel):
    # 现有字段保留...
    case_id: str = ""                    # 测试用例 ID
    failure_mode_id: str = ""            # 对应的 failure_mode_id
    forbidden_behaviors: list[str] = Field(default_factory=list)  # 禁止出现的行为
    evidence_type: Literal[
        "demo_evidence", "production_evidence", "manual_evidence", "none"
    ] = "demo_evidence"
    is_mock_evidence: bool = True        # 是否为 Mock 演示证据
    human_review_result: Literal["pending", "approved", "rejected", "not_required"] = "pending"
    final_pass_status: Literal["passed", "failed", "pending", "blocked"] = "pending"


class DeploymentDecision(BaseModel):
    """Stage 4 部署前门禁决策结构。"""
    decision: Literal["go", "conditional_go", "pilot_only", "no_go"]
    decision_scope: Literal[
        "internal_testing_only",
        "limited_pilot",
        "conditional_deployment",
        "deployment_paused",
    ]
    decision_rationale: str = ""
    unresolved_risk_ids: list[str] = Field(default_factory=list)
    required_conditions: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    monitoring_requirements: list[str] = Field(default_factory=list)
    rollback_conditions: list[str] = Field(default_factory=list)
    prohibited_uses: list[str] = Field(default_factory=list)
    review_after: str = ""               # 复审时间/条件
    human_accountable_role: str = ""     # 人工责任角色
    is_demo_recommendation: bool = True  # 仅为 Demo 决策支持


class Stage4Output(BaseModel):
    # 现有字段保留（trigger_methods 向后兼容）...
    deployment_decision: DeploymentDecision | None = None
```

#### 3.2 `stages/schemas.py` 同步

保持 `stages/schemas.py` 与 `core/models.py` 字段一致。`Stage4Schema` 增加 `deployment_decision`。`validators.py` 中 `stage4_schema_to_output` 同步映射新字段。

#### 3.3 schema 版本迁移

- `CONTEXT_SCHEMA_VERSION` 从 `0.9.0` → `0.10.0`
- 新增 `core/migrations/v090_to_v0100.py`：为新字段提供默认值，确保旧 context_json 可加载。

---

### WS-4：跨阶段一致性校验器（P0，可并行，依赖 WS-3）

**目标**：新增统一的跨阶段引用校验器，复用现有 gate 体系。

#### 4.1 新增 gate 规则文件

`core/gates/rules/cross_stage_integrity.py`：

```python
class CrossStageIntegrityRule(GateRule):
    """跨阶段 ID 引用完整性和覆盖校验。"""
    rule_id = "cross_stage_integrity"

    def evaluate(self, ctx, stage) -> list[Blocker]:
        blockers = []
        if stage >= 2:
            blockers += self._check_stage2_references(ctx)
        if stage >= 3:
            blockers += self._check_stage3_references(ctx)
            blockers += self._check_high_risk_coverage(ctx)
        if stage >= 4:
            blockers += self._check_stage4_decision(ctx)
        return blockers
```

#### 4.2 校验规则明细

| 校验项 | 阶段 | 阻断条件 |
|---|---|---|
| Stage 2 引用的 failure_mode_id 均存在于 Stage 1 | 2+ | 任一引用失效 → 阻断 |
| 所有 high/critical failure mode 被 Stage 2 覆盖 | 2+ | 未覆盖 → 阻断 |
| Stage 3 引用的 failure_mode_id 和 node_id 均存在 | 3+ | 任一引用失效 → 阻断 |
| 所有 high/critical failure mode 至少有一个测试 | 3+ | 未覆盖 → 阻断 |
| Stage 4 的 unresolved_risk_id 均存在 | 4 | 引用失效 → 阻断 |
| Stage 4 决策与门禁状态一致 | 4 | 决策与阻断项矛盾 → 阻断 |

#### 4.3 决策一致性校验

```python
def _check_stage4_decision(self, ctx) -> list[Blocker]:
    blockers = []
    decision = ctx.stage_4_output.deployment_decision
    if not decision:
        blockers.append(Blocker(rule_id=..., message="Stage 4 缺少部署决策结构"))
        return blockers

    open_critical = _count_open_risks(ctx, severity="critical")
    open_high = _count_open_risks(ctx, severity="high")
    failed_evals = _has_failed_evals(ctx)

    # 存在未关闭 critical 风险时不得 go
    if open_critical > 0 and decision.decision == "go":
        blockers.append(...)
    # 存在未解决 high 风险或失败评测时不得无条件 go
    if (open_high > 0 or failed_evals) and decision.decision == "go":
        blockers.append(...)
    # conditional_go 必须有 required_conditions
    if decision.decision == "conditional_go" and not decision.required_conditions:
        blockers.append(...)
    # pilot_only 必须有 decision_scope 和 rollback_conditions
    if decision.decision == "pilot_only" and not decision.rollback_conditions:
        blockers.append(...)
    return blockers
```

#### 4.4 注册到 gate 引擎

在 `core/gates/rules/__init__.py::registered_rules()` 中注册新规则。更新 `core/gates/rules/manifest.py` 的 RULE_MANIFEST。

---

### WS-5：Stage 3 确定性结果计算 + Stage 4 决策引擎（P0/P1，依赖 WS-3 + WS-4）

**目标**：`overall_passed` 由确定性计算；Stage 4 决策由规则校验。

#### 5.1 Stage 3 overall_passed 确定性计算

新增 `core/stage3_result_calculator.py`：

```python
def compute_overall_passed(ctx: ProjectContext) -> bool:
    """确定性计算 Stage 3 overall_passed。"""
    if not ctx.stage_3_output:
        return False
    results = ctx.stage_3_output.test_results
    if not results:
        return False
    # 任一阻断型失败用例 → overall_passed = False
    for r in results:
        if r.final_pass_status == "failed":
            return False
        if r.final_pass_status == "pending":
            return False  # 未完成人工复核不算通过
        # human_review_required 且 human_review_result == pending → 不算通过
        if r.human_review_result == "pending" and _is_high_risk(r):
            return False
    return True
```

在 `stages/stage_3_stress_test.py::parse_output()` 中调用此函数覆盖 fixture 硬编码值。

#### 5.2 Stage 4 决策生成器

新增 `core/deployment_decision_engine.py`：

```python
def generate_deployment_decision(ctx: ProjectContext) -> DeploymentDecision:
    """基于确定性规则生成部署决策建议。

    此函数生成的是 Demo 推荐决策，最终门禁由 CrossStageIntegrityRule 校验。
    """
    open_critical = _count_open_risks(ctx, "critical")
    open_high = _count_open_risks(ctx, "high")
    failed_evals = _has_failed_evals(ctx)
    unresolved_actions = ctx.has_blocking_actions()
    expert_review_pending = _has_pending_expert_review(ctx)

    if open_critical > 0 or failed_evals:
        return DeploymentDecision(decision="no_go", ...)

    if open_high > 0 or unresolved_actions or expert_review_pending:
        return DeploymentDecision(decision="conditional_go", ...)

    # 全部门禁通过
    return DeploymentDecision(decision="pilot_only", ...)
```

在 `stages/stage_4_trigger.py::parse_output()` 中，解析 LLM 输出后调用此函数进行确定性覆盖校验。

---

### WS-6：UI 和报告改造（P1，依赖 WS-3 + WS-5）

**目标**：前端展示部署决策卡片，报告包含完整章节。

#### 6.1 前端改造

| 文件 | 改动 |
|---|---|
| `frontend/app.py` | 顶部定位改为"企业 AI 项目部署前风险预评估 Demo" |
| `frontend/labels.py` | 新增 DECISION / DECISION_SCOPE / EVIDENCE_TYPE 映射 |
| `frontend/components/report_panel.py` | 新增部署决策卡片渲染 |
| `frontend/components/governance_overview.py` | 风险总览显示领域风险下限理由 |
| `frontend/components/gate_panel.py` | 跨阶段一致性校验结果展示 |

#### 6.2 报告改造

`core/report_service.py`：Markdown 和 JSON 报告增加以下章节：
- Demo 声明
- 部署门禁结论（decision + scope + rationale）
- 部署范围
- 前置条件
- 禁止用途
- 监控要求
- 回滚条件
- 人工责任角色
- 评测证据类型（demo_evidence 明确标注）
- Mock 演示证据声明
- "评估完成 ≠ 正式批准部署"声明

#### 6.3 场景选择页

`frontend/app.py` 场景选择区域增加预期结论提示。

---

### WS-7：测试体系（P0/P1，贯穿全程）

#### 7.1 场景语义测试（P0）

`tests/test_scenario_semantic_integrity.py`：
- 每个场景 fixture 包含指定风险类别
- 心理健康场景不得以学术诚信为主要风险
- 学生选课场景包含先修条件/时间冲突/毕业要求
- 通用 RAG 场景包含无依据回答/权限/Prompt Injection
- 每个 manifest 指向匹配 fixture

#### 7.2 风险等级测试（P0）

`tests/test_risk_profile_floor.py`：
- 心理健康 + "辅助学习 Demo" → 仍 ≥ HIGH
- 医疗诊断 → CRITICAL
- 低风险词不覆盖领域下限
- 单调性规则

#### 7.3 跨阶段合同测试（P0）

`tests/test_cross_stage_integrity.py`：
- Stage 1→2 引用完整
- Stage 2→3 引用完整
- Stage 3→4 决策一致
- high/critical 风险有监督节点和测试覆盖
- 失效引用阻断
- 未解决阻断项时不能 go

#### 7.4 Stage 3 结果计算测试（P1）

`tests/test_stage3_result_calculation.py`：
- overall_passed 由测试结果确定
- 任一阻断失败影响整体
- Mock 结果带 demo evidence 标识
- 人工未复核时高风险不算通过

#### 7.5 Stage 4 决策测试（P0）

`tests/test_deployment_decision.py`：
- critical open risk → 不得 go
- high open risk → 不得无条件 go
- failed eval → no_go 或 conditional_go
- 全门禁通过 → 可 pilot_only / conditional_go / go
- conditional_go 必须有 conditions
- pilot_only 必须有 scope 和 rollback conditions
- 评估完成 ≠ 正式批准

#### 7.6 E2E 场景测试（P1）

`tests/test_e2e_four_scenarios.py`：四个场景端到端测试。

---

## 四、Subagent 并行任务分配

基于上述工作分解，以下任务可并行执行（每个 subagent 独立完成一个 WS）：

### 第一波（并行，无依赖）

| Subagent | 工作流 | 产出 | 前置 |
|---|---|---|---|
| SA-1 | WS-1 场景 fixture | 4 个新 fixture 文件 + manifest 更新 + mock.py 注册 | 无 |
| SA-2 | WS-2 风险分级 | risk_profile.py 修改 + 风险测试 | 无 |
| SA-3 | WS-3 数据模型 | models.py + schemas.py + validators.py + migration | 无 |

### 第二波（并行，依赖第一波）

| Subagent | 工作流 | 产出 | 前置 |
|---|---|---|---|
| SA-4 | WS-4 跨阶段校验 | cross_stage_integrity.py + 注册 + manifest | WS-3 |
| SA-5 | WS-5 Stage3/4 引擎 | stage3_result_calculator.py + deployment_decision_engine.py | WS-3 |

### 第三波（并行，依赖第二波）

| Subagent | 工作流 | 产出 | 前置 |
|---|---|---|---|
| SA-6 | WS-6 UI/报告 | 前端 + 报告改造 | WS-3, WS-5 |
| SA-7 | WS-7 测试体系 | 6 个测试文件 | WS-1~WS-5 |

### 第四波（串行）

| 步骤 | 内容 |
|---|---|
| 集成验证 | 全量 pytest + ruff + e2e-mock |
| 定位声明 | README / show.md / 前端顶部定位更新 |
| STATE.md | 更新 .upgrade/STATE.md + decisions |

---

## 五、详细实施顺序

### P0（必须完成）

1. **WS-3 数据模型扩展**（SA-3）— 其他所有 WS 的基础
2. **WS-1 场景 fixture 修复**（SA-1，与 WS-3 并行）— 修复语义错位
3. **WS-2 风险分级修复**（SA-2，与 WS-3 并行）— 修复降级 bug
4. **WS-4 跨阶段校验**（SA-4，依赖 WS-3）— 建立引用完整性
5. **WS-5 Stage 4 决策引擎**（SA-5，依赖 WS-3）— 部署门禁决策
6. **WS-7 核心测试**（SA-7，依赖 WS-1~5）— 场景语义 + 风险等级 + 跨阶段 + 决策
7. **产品定位声明** — README / 前端顶部 / 报告免责
8. **`.upgrade/STATE.md` 更新**

### P1（应当完成）

1. **WS-5 Stage 3 确定性计算** — overall_passed 不信 fixture
2. **WS-6 UI 和报告改造** — 部署决策卡片 + 报告章节
3. **Demo evidence 标识** — Mock 结果明确标记
4. **E2E 四场景测试** — 端到端验证

### P2（有余力时完成）

1. 适度消除 `stages/schemas.py` 和 `core/models.py` 的重复定义
2. 优化风险分类解释
3. 优化场景选择和演示引导

---

## 六、兼容性约束

1. **API 向后兼容**：`Stage4Output` 新增字段均有默认值（`None`），旧 API 消费者不受影响。
2. **context_json 迁移**：`CONTEXT_SCHEMA_VERSION` 升级到 `0.10.0`，migration 为新字段填默认值。
3. **Mock 模式**：继续支持无网络、无 API Key 演示。
4. **不引入新依赖**：所有实现使用现有技术栈。
5. **deterministic demo**：相同场景输入产生稳定结果。
6. **不降低安全能力**：认证、RBAC、多租户隔离、审计不受影响。

---

## 七、验证命令

```bash
# P0 完成后
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
make e2e-mock
git status --short
```

---

## 八、验收标准

对照实施方案第十四节，以下条件必须全部满足：

- [ ] 产品定位不冒充完整企业立项或生产验收系统
- [ ] 四阶段结构不变
- [ ] 四个场景使用领域匹配的 fixture
- [ ] 心理健康场景不再输出教学类主风险
- [ ] 学生选课场景覆盖真实教务约束
- [ ] 高风险领域不被"辅助""学习""Demo"等词降级
- [ ] high/critical 风险有人工监督映射
- [ ] high/critical 风险有测试覆盖
- [ ] 跨阶段 ID 引用有效
- [ ] Stage 3 通过结果不信 fixture 布尔值
- [ ] Stage 4 能输出 go / conditional_go / pilot_only / no_go
- [ ] 有阻断项时不能输出不一致的 go
- [ ] no_go 被视为合法评估结论
- [ ] 界面和报告明确"评估完成 ≠ 正式批准部署"
- [ ] Mock 结果明确标注为演示证据
- [ ] 新增业务语义测试和端到端测试
- [ ] 原有核心测试不被破坏
- [ ] `.upgrade/STATE.md` 已更新
