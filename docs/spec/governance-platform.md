# 组织级治理平台设计规格

> Status: Implemented（v1.2.0 落地 T3.1–T3.5、v1.2.0 落地 T3.7、v1.3.0 落地 T3.6（flag 默认关）。落地任务见 [../plan/phase-3-governance-platform.md](../plan/phase-3-governance-platform.md)）
> Last updated: 2026-07-27
> 对标依据：ISO/IEC 42001:2023（AI 管理体系）——从"单次评估工具"升级为"可审计的组织级 AI 治理台账"

---

> **阅读提示**：第 1 节是 2026-07-13 落地前历史基线。当前已实现 13 条版本化门禁规则、治理聚合 API/前端、业务指标和可选 LLM Judge，具体状态见后续各节及代码链接。

## 1. 落地前历史基线（2026-07-13）

| # | 事实 | 证据 |
|---|---|---|
| 1 | 门禁规则纯硬编码：12 条规则类在 `core/gates/rules/` 中实现，`registered_rules()` 硬编码列表注册；无版本号、无 owner、无"谁定的/何时改过"的应用层记录 | `core/gates/rules/__init__.py:21-35`、`core/gates/engine.py:98` |
| 2 | `AuditEvent`/`ActionResolutionLog` 只审计运行时人工动作，不审计规则定义变更 | `core/models.py:271-300` |
| 3 | CRITICAL 档已有 `require_expert_review` 配置，但当时尚无规则消费该开关 | `core/gates/risk_profile.py`；后续落地状态见 §3.4 |
| 4 | 可观测性只有 HTTP 通用指标（prometheus_fastapi_instrumentator 自动生成），无任何业务指标；Grafana 仅一块 FastAPI Overview 面板 | `api/main.py:37-48,72-92`、`monitoring/grafana/dashboards/fastapi-overview.json` |
| 5 | 全仓无按 tenant/项目的聚合查询（唯一 GROUP BY 是数用户总数）；存储层 `list_sessions(tenant_id="")` 跨租户分支存在但无 API 暴露 | `storage/backends/postgres.py:947-972,1024` |
| 6 | `eval_judge.py` 纯规则判分、刻意不做语义判定；`human_calibrations` 表已建但校准闭环未成体系 | `core/eval_judge.py:7-67`、`alembic/versions/V003_schema_alignment.py` |
| 7 | RBAC 三角色（viewer/editor/admin），admin 相比 editor 仅多用户管理端点 | `auth/permissions.py:11-14`、`auth/router.py:50-63` |

## 2. 范围决策

- **"组织" = tenant（MVP）**：现有多租户模型中一个 tenant 即一个组织/团队，组织级视图=租户内跨会话聚合。跨租户的集团视图**不做**（存储层那个未暴露的空 tenant_id 分支继续保持未暴露，属安全边界而非待开发功能）。
- 三个子系统按依赖排序：**③ 规则治理是①②的语义基础**（没有规则版本，"门禁通过率趋势"就无法回答"趋势变化是因为项目变好了还是规则变了"）。

```
③ 门禁规则治理（版本化/可审计/expert_review 落地）
① 组织级治理视图（聚合 API + 前端页 + 业务指标）
② LLM Judge（可选增强，flag 默认关）
```

## 3. 子系统③：门禁规则治理

### 3.1 规则元数据清单（manifest）

新增 `core/gates/rules/manifest.py`——每条规则一个声明式条目：

```python
RULE_MANIFEST = {
    "redteam_coverage": RuleMeta(
        rule_id="redteam_coverage",
        version="1.1.0",            # 语义化：判定逻辑变更 minor+，阈值调整 patch+
        owner="project-owner",
        since_app_version="1.0.2",
        rationale="高/关键风险项目必须有红队用例覆盖才能通过 Stage 3",
        standard_refs=["OWASP_LLM_2025:LLM01", "NIST_AI_RMF:MEASURE"],  # 与 taxonomy 体系互通
        changelog=[("1.1.0", "2026-07-13", "联通人工动作状态（v1.0.2 修复）")],
    ),
    ...
}
```

- `registered_rules()` 启动时校验：每条注册规则必须在 manifest 有条目、每个 manifest 条目必须有对应实现（完整性测试固化）。
- **变更审计路径**：manifest 是代码文件 → git 历史即变更记录；配合 changelog 字段，可回答 ISO 42001 式提问"这条规则谁定的、什么时候改过、为什么"。不引入数据库层规则存储——规则保持代码化是本项目确定性架构原则的延伸。

### 3.2 判定结果携带规则版本

- `GateReport`/`RuleDetail`（`core/gates/report.py`）增加 `rule_version` 字段；`build_report_dict` 导出的报告随之携带——历史报告可回答"这份结论是哪个版本的规则判的"。
- 新增轻量持久化表 `gate_evaluation_records`（alembic V005）：每次阶段推进评估落一行 `(session_id, tenant_id, stage_id, risk_tier, passed, blocking_rule_ids, rule_versions, evaluated_at)`。这是①中"门禁通过率趋势"的数据源；现有 evaluate 路径是纯计算无痕迹，趋势分析必须有这张表。

### 3.3 规则禁用的显式治理

- 新增环境配置 `GATE_RULES_DISABLED`（默认空、逗号分隔字符串；代码通过 `gate_rules_disabled_set` 转为集合）：禁用任何规则需显式配置，`/health` 暴露当前禁用集合，每次评估的 `gate_evaluation_records.rule_versions` 标注 disabled——"弱化门禁"永远留痕。
- 告警时机以实现为准（`core/gates/engine.py`）：WARNING 只在**评估时**触发，且仅针对"试图禁用安全底线规则"这一种情况；普通规则被禁用时是**静默跳过**，不打启动告警也不打评估告警。应用启动（`api/main.py` lifespan）不检查该配置。依赖告警发现误配置的部署方需自行监控 `/health` 的 `gate_rules_disabled` 字段。
- 安全底线规则（当前 manifest 中 `safety_bottom_line=True` 的 7 条规则）**不允许禁用**（配置了也忽略并告警）；具体清单以 `core/gates/rules/manifest.py` 为准，避免数量随规则演进后失真。

### 3.4 expert_review 落地（补历史欠账）

CRITICAL 档 `require_expert_review=True` 时，Stage 3 就绪评估自动创建一条 `escalate` 类型的阻断 `PendingHumanAction`（source_type=`expert_review`，幂等键复用现有机制）；按 `graph/transition_policy.py` 既有约束，escalate 必须显式 approve 才能放行。已落地（T3.3）；[stage3-risk-adaptive-gate.md](stage3-risk-adaptive-gate.md) 中"计划中/未实现"的脚注已同步更新为"已落地"。

## 4. 子系统①：组织级治理视图

### 4.1 聚合 API

新增 `api/routers/governance.py`（prefix `/governance`，viewer 可读——治理透明度本身是价值，写操作不存在）：

| 端点 | 内容 |
|---|---|
| `GET /governance/overview` | 租户内：会话总数/各状态分布、风险 tier 分布、open 安全发现数、pending 人工动作积压数、报告导出数 |
| `GET /governance/gate-trends` | 基于 `gate_evaluation_records`：按周的评估次数/通过率/Top 阻断规则 |
| `GET /governance/actions-backlog` | 待处理人工动作明细（跨会话），按 risk_level 与等待时长排序 |

- 存储层：两后端各增聚合查询方法（`GROUP BY` state / risk_tier 等），全部强制 `WHERE tenant_id = ?`。
- 性能：租户内会话量级（内部工具，百级）直接实时聚合即可，不建物化视图。

### 4.2 前端治理页

Streamlit 新增"治理总览"页：三张卡片（项目数/风险分布/积压动作）+ 通过率趋势折线 + 积压动作表格（点击跳转会话）。复用现有前端组件风格。

### 4.3 业务指标接入 Prometheus/Grafana

- 在现有 instrumentator 之上注册自定义指标（`api/metrics.py`）：
  - `premortem_sessions_total{tenant,state}`（Gauge；当前仅在 API 启动时用空租户刷新一次，属于零值 scaffold，尚不是实时多租户统计）
  - `premortem_gate_evaluations_total{result}` / `premortem_gate_blocked_total{rule_id}`（Counter，评估路径打点）
  - `premortem_pending_actions{risk_level}`（Gauge；与 sessions Gauge 一样尚未接入周期性真实聚合）
  - `premortem_llm_calls_total` / `premortem_llm_tokens_total`（Counter，与阶段 2 LLM10 计数共用数据源）
- Grafana 新增 `governance-overview.json` 面板（与现有 fastapi-overview.json 并列，provisioning 自动加载）。
- 注意基数控制：tenant 标签用 tenant 名而非 UUID，且内部工具租户数有限，无高基数风险。

## 5. 子系统②：LLM Judge（可选增强）

> **Status: Implemented (v1.3.0)** — `EVAL_LLM_JUDGE` / `EVAL_LLM_JUDGE_AUTOFINAL` 默认均为 off；实现见 `core/eval_llm_judge.py` 与 `core/eval_runner.py`，测试见 `tests/test_llm_judge_v130.py`。manual run（人工评分外壳，无输出可判）不在建议范围内。

设计原则：LLM 只提供**建议判分**，最终裁决权始终在人工或确定性规则——与全局架构原则一致。

- 新增 `judge_mode="llm"`：`core/eval_judge.py` 保持现有规则分支为第一层；新增第二层——配置 `EVAL_LLM_JUDGE=on`（默认 off）时，对规则层判为 `needs_review` 的 run 调用 LLM（走 `core/llm/provider.py` 现有工厂，mock 模式天然可测）生成结构化建议：`{"suggested_result": "passed|failed", "rationale": str, "confidence": float}`，写入 `EvalRun.llm_judge_suggestion`（`core/models.py:522` 的 Pydantic 字段）。**该字段没有独立的数据库列**：它随 `ProjectContext` 序列化进 `context_json` 落库，并镜像一份到 `eval_judgments` 的 `metadata`（`core/eval_runner.py:190-193`）。因此无法直接对它做 SQL 聚合查询。
- **judge_result 本身不被 LLM 直接改写**：HIGH/CRITICAL 风险会话的 run 永远保持 `needs_review` 待人工；LOW/MEDIUM 会话允许配置 `EVAL_LLM_JUDGE_AUTOFINAL=on` 后采纳 LLM 建议为终值（该开关的启用属于 3.3 同级的显式治理决策）。
- **校准闭环**：人工最终判定与 LLM 建议的一致率通过 `human_calibrations` 累计，并在 Eval 实验/报告链路展示。当前治理总览的三个 `/governance/*` 端点尚未聚合该一致率；它仍是决定是否扩大 AUTOFINAL 范围的量化依据。
- Prompt 注入面：eval 输入本身可能含对抗内容，judge prompt 采用防注入模板（材料置于明确分隔的引用块、指令置后），且 judge 输出仅结构化字段入库。

## 6. ISO/IEC 42001 对齐说明

本设计交付后，对管理体系审计的典型提问可给出系统性回答：

| 审计提问 | 回答来源 |
|---|---|
| 组织内有多少 AI 项目、风险分布如何 | `/governance/overview` |
| 这条门禁规则谁定的、改过几次、为什么 | 规则 manifest + git 历史 + changelog 字段 |
| 这份评估报告当时依据什么规则版本 | 报告内嵌 rule_versions |
| 高风险项目是否经过专家复核 | expert_review 动作记录 + 审计事件 |
| 自动化判分是否可信、如何校准 | human_calibrations 一致率指标 |

完整的 42001 条款映射表在阶段 3 收尾时另行整理（放 `docs/compliance/`），不在本规格展开。

## 7. 兼容性与验证

- alembic V005 只创建 `gate_evaluation_records` 一张表；SQLite 内联 DDL 同步。**`eval_runs` 表没有 `llm_judge_suggestion` 列**——V005 不含任何 `ALTER TABLE eval_runs`，两个后端的 `_sync_eval_runs` INSERT 列清单也不含该列。
- 现有 `evaluate_stage_gate` 签名不变，落表为旁路写入（失败不阻断评估主路径，只打日志）。
- 验收口径（对应路线图阶段 3）：一个界面看到"几个项目在评估、各处于什么风险等级、通过率如何"；任一规则能回答版本与变更历史；LLM Judge 若启用，有一致率数据支撑。
