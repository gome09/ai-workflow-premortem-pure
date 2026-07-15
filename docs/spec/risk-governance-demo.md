# 风险治理 Demo 专项整改规格说明

> Status: Designed, pending implementation
>
> 本规格定义"企业 AI 项目部署前风险治理 Demo"专项整改的数据模型、行为契约和验收标准。
> 设计方案见 `docs/plan/risk-governance-demo-design.md`。

---

## 1. 范围

保留四阶段流程，强化阶段间数据依赖和门禁决策：

1. 失败模式识别（Stage 1）
2. 人机监督设计（Stage 2）
3. 压力测试与评测（Stage 3）
4. 部署前门禁与决策建议（Stage 4）

不新增第五阶段。不扩展为企业立项、预算、采购、合同审批或 ISO 认证平台。

---

## 2. 数据模型规格

### 2.1 FailureMode 扩展

```
FailureMode:
  id: str                           # 稳定唯一 ID
  category: str                     # 风险类别
  description: str                  # 具体失败描述
  severity: "critical"|"high"|"medium"|"low"
  evidence: str = ""                # 支持证据/依据
  evidence_ids: list[str] = []      # 结构化 evidence_id 引用
  needs_verification: bool = False  # 是否需要人工复核
  # ── 新增字段 ──
  affected_stakeholders: list[str] = []   # 受影响对象/利益相关者
  possible_consequences: str = ""         # 可能后果
  likelihood: "low"|"medium"|"high" = "medium"  # 发生可能性
  recommended_controls: str = ""          # 建议控制方向
  open_questions: list[str] = []          # 尚待核实的问题
```

向后兼容：新字段均有默认值，旧 context_json 可加载。

### 2.2 WorkflowNode 扩展

```
WorkflowNode:
  node_id: str
  stage_name: str
  model_assigned: str
  human_action: str
  check_criteria: str
  failure_modes_addressed: list[str]    # 引用的 failure_mode_id
  prompt_template: str
  oversight_policy: HumanOversightPolicy | None
  # ── 新增字段 ──
  ai_can_do: str = ""                    # AI 在该节点能做什么
  ai_cannot_do: str = ""                 # AI 明确不能做什么
  trigger_conditions: list[str] = []     # 触发人工审核的条件
  escalation_conditions: list[str] = []  # 升级条件
  rollback_action: str = ""              # 高风险停止/回退动作
```

### 2.3 StressTestResult 扩展

```
StressTestResult:
  tested_node_id: str
  scenario_type: "normal"|"edge"|"adversarial" = "normal"
  test_input: str
  ai_output: str
  error_predictions: list[str] = []
  correction_prompts: list[str] = []
  pass_criteria: list[str] = []
  passed: bool = False
  raw_summary: str = ""
  # ── 新增字段 ──
  case_id: str = ""                      # 测试用例 ID
  failure_mode_id: str = ""              # 对应的 failure_mode_id
  forbidden_behaviors: list[str] = []    # 禁止出现的行为
  evidence_type: "demo_evidence"|"production_evidence"|"manual_evidence"|"none" = "demo_evidence"
  is_mock_evidence: bool = True          # 是否为 Mock 演示证据
  human_review_result: "pending"|"approved"|"rejected"|"not_required" = "pending"
  final_pass_status: "passed"|"failed"|"pending"|"blocked" = "pending"
```

### 2.4 DeploymentDecision 新模型

```
DeploymentDecision:
  decision: "go"|"conditional_go"|"pilot_only"|"no_go"
  decision_scope: "internal_testing_only"|"limited_pilot"|"conditional_deployment"|"deployment_paused"
  decision_rationale: str = ""
  unresolved_risk_ids: list[str] = []
  required_conditions: list[str] = []
  required_approvals: list[str] = []
  monitoring_requirements: list[str] = []
  rollback_conditions: list[str] = []
  prohibited_uses: list[str] = []
  review_after: str = ""                 # 复审时间/条件
  human_accountable_role: str = ""       # 人工责任角色
  is_demo_recommendation: bool = True    # 仅为 Demo 决策支持
```

### 2.5 Stage4Output 扩展

```
Stage4Output:
  trigger_methods: list[TriggerMethod] = []   # 保留向后兼容
  raw_summary: str = ""
  # ── 新增字段 ──
  deployment_decision: DeploymentDecision | None = None
```

### 2.6 Schema 版本迁移

- `CONTEXT_SCHEMA_VERSION`: `0.9.0` → `0.10.0`
- 迁移文件: `core/migrations/v090_to_v0100.py`
- 迁移逻辑: 为所有新增字段填充默认值，无需数据转换

---

## 3. 风险分级规格

### 3.1 领域风险下限规则

| 领域 | 风险下限 | 降级条件 |
|---|---|---|
| 医疗/药物/临床诊断 | CRITICAL | 不可降级（除非明确只分析公开非敏感文本且代码规则证明例外） |
| 心理健康/自伤/危机 | HIGH | 不可降级 |
| 金融/贷款/支付 | HIGH | 不可降级 |
| 法律/合同/合规 | HIGH | 不可降级 |
| 儿童/未成年人 | HIGH | 不可降级 |
| 敏感个人数据 | HIGH | 不可降级 |
| 高影响自动决策 | HIGH | 不可降级 |

### 3.2 单调规则

```
final_tier = max(domain_floor, tier_after_scope_adjustment)
```

- 低风险词（"Demo""测试""辅助""学习""建议"）仅影响 deployment scope，不覆盖领域下限。
- Stage 1 新生成文本只能维持或提高已有领域风险，不得降低。

### 3.3 分类结果可读理由

`classify_project_risk()` 返回的 `reasons` 列表必须包含：
- 命中的领域关键词及对应下限
- 低风险词命中情况（标注"不影响领域下限"）
- 最终 tier 的推导理由

---

## 4. 跨阶段一致性校验规格

### 4.1 校验规则矩阵

| 规则 | 适用阶段 | 阻断条件 | blocker severity |
|---|---|---|---|
| S2→S1 引用完整 | 2+ | workflow_node.failure_modes_addressed 中任一 ID 不在 Stage 1 | high |
| high/critical FM 被覆盖 | 2+ | 任一 high/critical failure_mode 未被任何 workflow_node 引用 | high |
| S3→S1 引用完整 | 3+ | test_result.failure_mode_id 不在 Stage 1 | high |
| S3→S2 引用完整 | 3+ | test_result.tested_node_id 不在 Stage 2 | high |
| high/critical FM 有测试 | 3+ | 任一 high/critical failure_mode 无对应测试 | high |
| S4 unresolved_risk 存在 | 4 | unresolved_risk_id 不在已识别风险列表 | medium |
| S4 决策一致性 | 4 | 见 4.2 | critical |

### 4.2 Stage 4 决策一致性规则

| 条件 | 禁止决策 | 说明 |
|---|---|---|
| 存在未关闭 critical 风险 | `go` | 不得无条件通过 |
| 存在未解决 high 风险 | `go` | 不得无条件通过 |
| 存在失败评测 | `go` | 不得无条件通过 |
| 存在阻断型人工动作 | `go` | 不得无条件通过 |
| `conditional_go` | 无 required_conditions | 必须列出前置条件 |
| `pilot_only` | 无 rollback_conditions | 必须有停止/回滚条件 |
| `no_go` | — | 合法结论，不视为异常 |

### 4.3 失效引用处理

任一跨阶段引用失效 → 产生可解释的 GateBlocker（含 rule_id、message、severity），不得静默忽略。

---

## 5. Stage 3 确定性计算规格

### 5.1 overall_passed 计算规则

```
overall_passed = True
for each test_result in stage_3_output.test_results:
    if test_result.final_pass_status == "failed":
        overall_passed = False
        break
    if test_result.final_pass_status == "pending":
        overall_passed = False  # 未完成不算通过
        break
    if test_result.final_pass_status == "blocked":
        overall_passed = False
        break
    # high/critical 风险测试需人工复核
    if _is_high_risk(test_result) and test_result.human_review_result == "pending":
        overall_passed = False
        break
```

### 5.2 Mock 证据标识

- Mock 模式下所有 `StressTestResult.evidence_type = "demo_evidence"`
- `is_mock_evidence = True`
- 报告中明确标注"演示证据 — 非生产运行证据"

---

## 6. Stage 4 部署决策引擎规格

### 6.1 决策生成算法

```
输入: ProjectContext (含 Stage 1-3 输出 + safety_findings + pending_actions + eval_runs)

open_critical = count_safety_findings(severity="critical", status="open")
open_high = count_safety_findings(severity="high", status="open")
failed_evals = any(eval_run.judge_result == "failed" for eval_run in eval_runs)
blocking_actions = has_blocking_actions()
expert_review_pending = has_pending_expert_review()

if open_critical > 0 or failed_evals:
    decision = "no_go"
elif open_high > 0 or blocking_actions or expert_review_pending:
    decision = "conditional_go"
else:
    decision = "pilot_only"  # Demo 默认保守

# is_demo_recommendation 始终为 True
```

### 6.2 决策校验

决策生成后由 `CrossStageIntegrityRule._check_stage4_decision()` 校验一致性。不一致时产生 blocker。

---

## 7. 场景 Fixture 规格

### 7.1 generic_rag_demo

| Stage | 内容要求 |
|---|---|
| S1 | ≥4 条 failure_mode：无依据回答、错误引用、权限/跨租户泄露、Prompt Injection；≥1 条 critical 或 high |
| S2 | 每个 high/critical FM 有对应 node；包含引用核验、权限检查、人工升级节点 |
| S3 | normal + edge + adversarial 测试；含 Prompt Injection 对抗测试 |
| S4 | conditional_go，受限试点，含引用核验前置条件 |

### 7.2 university_course_qa

| Stage | 内容要求 |
|---|---|
| S1 | ≥5 条：课程政策幻觉、过期材料、错误引用、学术诚信、学生数据泄露、AI 越权代写 |
| S2 | 教师审核节点 + 教务升级节点 |
| S3 | normal + adversarial（代写检测）|
| S4 | conditional_go，有条件部署 |

### 7.3 student_course_selection

| Stage | 内容要求 |
|---|---|
| S1 | ≥6 条：先修课程错误、时间冲突、学分计算错误、课程容量过期、学籍资格遗漏、推荐偏差、隐私 |
| S2 | 教务审核节点（权威数据源）、学生确认节点；AI 只建议不决策 |
| S3 | normal + edge（毕业要求边界）|
| S4 | pilot_only，受限试点，含停止条件 |

### 7.4 university_mental_health

| Stage | 内容要求 |
|---|---|
| S1 | ≥6 条：自伤/他伤漏报、危机误报、不当诊断、错误标签化、隐私泄露、群体偏差、不安全建议、专业人员升级失败 |
| S2 | 危机升级节点（授权专业人员）、高风险输出人工复核节点；AI 不诊断不替代专业人员 |
| S3 | normal + adversarial（危机信号检测）+ edge（普通情绪误判）|
| S4 | pilot_only 或 no_go；不得无条件 go |

---

## 8. UI 规格变更

### 8.1 顶部定位

```
主标题: 企业 AI 项目部署前风险预评估 Demo
副说明: 本系统输出风险分析与部署建议，不替代企业正式审批、专业判断或合规认证。
```

### 8.2 部署决策卡片

Stage 4 和报告页面展示：

| 字段 | 展示 |
|---|---|
| decision | 彩色标签（go=绿/conditional_go=黄/pilot_only=橙/no_go=红） |
| decision_scope | 范围说明 |
| unresolved_risk_ids | 未解决风险列表 |
| required_conditions | 前置条件清单 |
| human_accountable_role | 人工责任角色 |
| prohibited_uses | 禁止用途 |
| monitoring_requirements | 监控指标 |
| rollback_conditions | 回滚条件 |
| is_demo_recommendation | "仅为 Demo 决策支持"提示 |

`no_go` 使用明确阻断展示，不渲染为程序异常。

### 8.3 场景预期结论

| 场景 | 预期结论提示 |
|---|---|
| 通用 RAG | 适合展示附条件试点 |
| 课程问答 | 适合展示学术诚信与内容治理 |
| 学生选课 | 适合展示教务权威数据和人工确认 |
| 心理健康 | 适合展示高风险阻断、专家升级或受限试点 |

---

## 9. 报告规格变更

Markdown 和 JSON 报告必须包含以下章节（按顺序）：

1. Demo 声明
2. 项目与场景摘要
3. 风险等级及理由（含领域下限理由）
4. Stage 1 失败模式
5. Stage 2 人机监督映射
6. Stage 3 测试覆盖和结果（含 overall_passed 计算理由）
7. 未关闭风险
8. 未完成的人工动作
9. 部署门禁结论（decision + scope + rationale）
10. 部署范围
11. 前置条件
12. 禁止用途
13. 监控要求
14. 回滚条件
15. 人工责任角色
16. 评测证据类型（demo_evidence 标注）
17. Mock 演示证据声明
18. 审计摘要
19. "评估完成 ≠ 正式批准部署"声明

报告禁止出现：
- "已获得企业正式批准"
- "已符合 ISO 42001"
- "已完成生产验收"
- "所有风险已消除"
- 将 Mock fixture 结果描述成真实生产评测证据

---

## 10. 测试规格

### 10.1 场景语义测试

```
test_university_mental_health_fixture():
    fixture = load_fixture("university_mental_health")
    # 必须包含
    assert any("自伤" in fm.description or "危机" in fm.description for fm in fixture.stage_1.failure_modes)
    assert any("隐私" in fm.description for fm in fixture.stage_1.failure_modes)
    # 不得以学术诚信为主风险
    assert not all("学术诚信" in fm.category for fm in fixture.stage_1.failure_modes)

test_student_course_selection_fixture():
    fixture = load_fixture("student_course_selection")
    assert any("先修" in fm.description for fm in fixture.stage_1.failure_modes)
    assert any("时间冲突" in fm.description for fm in fixture.stage_1.failure_modes)
    assert any("学分" in fm.description or "毕业" in fm.description for fm in fixture.stage_1.failure_modes)
```

### 10.2 风险下限测试

```
test_mental_health_with_demo_keyword():
    ctx = ProjectContext(domain="心理健康辅助学习 Demo", goal="...")
    tier, reasons = classify_project_risk(ctx)
    assert tier in (ProjectGateRiskTier.HIGH, ProjectGateRiskTier.CRITICAL)

test_medical_diagnosis_prototype():
    ctx = ProjectContext(domain="医疗诊断原型", goal="...")
    tier, reasons = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.CRITICAL
```

### 10.3 跨阶段一致性测试

```
test_stage2_references_valid_failure_mode_ids():
    # Stage 2 引用不存在的 FM ID → 阻断
    ctx = build_ctx_with_invalid_s2_reference()
    result = evaluate_stage_gate(ctx, stage=2)
    assert not result.can_continue

test_high_risk_fm_must_have_oversight():
    ctx = build_ctx_with_uncovered_high_risk()
    result = evaluate_stage_gate(ctx, stage=2)
    assert not result.can_continue
```

### 10.4 Stage 4 决策测试

```
test_critical_open_risk_blocks_go():
    ctx = build_ctx_with_critical_open_risk()
    decision = generate_deployment_decision(ctx)
    assert decision.decision != "go"

test_failed_eval_blocks_go():
    ctx = build_ctx_with_failed_eval()
    decision = generate_deployment_decision(ctx)
    assert decision.decision in ("no_go", "conditional_go")

test_conditional_go_requires_conditions():
    ctx = build_ctx_conditional_go()
    decision = generate_deployment_decision(ctx)
    assert decision.required_conditions  # 非空

test_no_go_is_valid():
    ctx = build_ctx_no_go()
    decision = generate_deployment_decision(ctx)
    assert decision.decision == "no_go"
    # no_go 不应导致程序异常
```
