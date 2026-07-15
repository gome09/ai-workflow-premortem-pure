# 阶段 3 详细设计方案：从评估工具到组织级治理平台

> 关系定位：本文档是 [phase-3-governance-platform.md](phase-3-governance-platform.md)（实施计划 / 任务清单 + 验收标准）的**落地设计层**——给出每个任务的具体文件改动、代码草稿、配置参数、决策依据、执行顺序与并行策略、风险。
> 配套规格：[../spec/governance-platform.md](../spec/governance-platform.md)（设计意图层，已完整覆盖 T3.1–T3.7 的设计决策）。
> 现状核实日期：2026-07-14（全部条目经代码仓库直接实测，非估算）。
> 状态：设计完成，待用户决策后可启动执行。
>
> **关于 spec 文件**：现有 `docs/spec/governance-platform.md` 已完整覆盖阶段 3 全部 7 个任务的设计意图（规则版本化、组织=tenant 边界、LLM 只建议不终裁、ISO 42001 对齐），**不新增 spec 文件**，本设计方案直接落地。仅在两处对 spec 做补充修正（见 §1 实测发现第 2、5 项）。

---

## 1. 现状复核（对实施计划基线表的修正与补充）

实施计划 §2 与 spec §1 的基线表已核实准确，本节补充 10 项实测发现，其中第 2、5 项**直接修正 spec 表述**：

| # | spec/计划基线 | 2026-07-14 实测补充 |
|---|---|---|
| 1 | **12 条规则在 `core/gates/rules/__init__.py` 硬编码注册** | 确认。`registered_rules()`（line 21-35）返回 12 条；`GateRule` Protocol 在 `core/gates/base.py:10-23` 声明 `rule_id`/`applies_to_stages`/`evaluate`，**无 version/owner 字段**。`CollectorGateRule`（line 26-42）是遗留适配器。T3.1 manifest 与 Protocol 解耦——manifest 是旁挂的元数据清单，不改 Protocol 签名 |
| 2 | **spec §3.2 称"新增表走 alembic V004"** | ⚠️ **修正**：`alembic/versions/V004_audit_archive.py` 已被 T1.6 审计归档表占用（`audit_events_archive`）。`gate_evaluation_records` 必须用 **V005**。spec 该处表述过时，落地以本设计为准 |
| 3 | `GateReport`/`RuleDetail` 无 rule_version | 确认。`core/gates/report.py:16-39` 两个模型均无版本字段；`_RuleEvalRecord`（line 47-66）是引擎内部载体也无版本。`build_report()`（line 99-153）从 `_RuleEvalRecord` 构造 `RuleDetail`——T3.2 挂载点：载体加版本、模型加版本、builder 透传 |
| 4 | `evaluate_stage_gate()` 是纯计算无痕迹 | 确认。`core/gates/engine.py:62-170` 返回 `StageGateResult`，**无任何持久化写入**。`detailed=True` 分支（line 85-167）才构造 `GateReport`。T3.2 旁路落表挂载点：在 line 148 `result = StageGateResult(...)` 之后，`detailed` 分支内追加旁路写入（失败不阻断） |
| 5 | **spec §3.4 称"expert_review 自动创建 escalate 动作"** | 确认历史欠账。`core/gates/risk_profile.py:294` CRITICAL 档 `require_expert_review=True`，但 `registered_rules()` 12 条中**无任何规则消费该字段**（[stage3-risk-adaptive-gate.md](../spec/stage3-risk-adaptive-gate.md) line 72-74 已如实标注 "not implemented"）。T3.3 需新增一条 gate rule 消费此字段 |
| 6 | `PendingHumanAction.action_type` 支持 escalate | 确认。`core/models.py:239` Literal 含 `"escalate"`；`source_type`（line 237）是自由字符串，可加 `"expert_review"`。幂等键机制在 `core/stage_readiness_service.py` 的 `_find_pending_action_id` 已就绪——T3.3 复用 |
| 7 | 全仓无按 tenant 聚合查询 | 确认。`storage/backends/postgres.py:1035-1060` `list_sessions()` 是唯一带 tenant 过滤的查询，仅返回会话列表无聚合。`sqlite_store` 同构。T3.4 两后端各增聚合方法，强制 `WHERE tenant_id = ?` |
| 8 | 可观测性只有 HTTP 通用指标 | 确认。`api/main.py:74,94` 仅 `Instrumentator()` 自动指标；`/metrics` 端点在 lifespan（line 80）暴露。无 `api/metrics.py` 文件。T3.5 新建该文件，在 instrumentator 之上注册自定义 Counter/Gauge |
| 9 | Grafana 仅一块 fastapi-overview 面板 | 确认。`monitoring/grafana/dashboards/` 只有 `fastapi-overview.json`；provisioning（`monitoring/grafana/provisioning/dashboards/provider.yml`）已配置自动加载目录——T3.5 新增 `governance-overview.json` 即自动加载 |
| 10 | RBAC viewer 可读 | 确认。`auth/permissions.py:11-14` 三角色，`require_roles(Role.viewer)` 可用于治理只读端点。治理透明度=viewer 可读符合 spec §4.1 |

### 关键发现影响：迁移版本号修正

spec §3.2/§7 称「alembic V004」建 `gate_evaluation_records` 表。实测 V004 已被审计归档占用。**本设计明确：gate_evaluation_records 走 V005**，down_revision = "V004"。spec 该处表述将在 T3.7 收尾时一并修正（或本设计文档即权威，spec 留待收尾统一更新）。

---

## 2. 任务级详细设计

### T3.1 门禁规则元数据清单（manifest）【基础任务，Wave 1】

#### 2.1.1 RuleMeta 数据结构与 manifest 文件

**改动文件**：`core/gates/rules/manifest.py`（新建）

```python
# core/gates/rules/manifest.py
"""Gate rule metadata manifest — declarative governance provenance.

每条门禁规则一个声明式条目，回答 ISO/IEC 42001 式提问：
"这条规则谁定的、什么时候改过、为什么、对标哪个标准"。

设计原则（spec §3.1）：
- manifest 是代码文件 → git 历史即变更记录；changelog 字段补充语义化摘要
- 不引入数据库层规则存储——规则保持代码化是确定性架构原则的延伸
- version 语义化：判定逻辑变更 minor+，阈值调整 patch+
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleMeta:
    """单条门禁规则的治理元数据。"""

    rule_id: str
    version: str               # 语义化版本，如 "1.1.0"
    owner: str                 # 责任方：project-owner / security / compliance
    since_app_version: str     # 该规则首次引入的应用版本
    rationale: str             # 为什么存在这条规则
    standard_refs: list[str] = field(default_factory=list)  # 对标标准条款，与 taxonomy 前缀体系互通
    changelog: list[tuple[str, str, str]] = field(default_factory=list)  # (version, date, summary)
    safety_bottom_line: bool = False  # 是否属安全底线规则（不可禁用，T3.3 消费）


# 安全底线规则 6 类（spec §3.3）：硬阻断，GATE_RULES_DISABLED 配置也无法禁用
_SAFETY_BOTTOM_LINE = {
    "missing_output",
    "parser_error",
    "safety_finding",
    "action_state",
    "stale_dependency",
    "stage4_final_governance",
}


RULE_MANIFEST: dict[str, RuleMeta] = {
    "missing_output": RuleMeta(
        rule_id="missing_output",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="阶段必须有输出才能进入下一阶段；缺输出即工作流断裂。",
        standard_refs=["INTERNAL:AI_GOV:STAGE_COMPLETENESS"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
        safety_bottom_line=True,
    ),
    "stale_dependency": RuleMeta(
        rule_id="stale_dependency",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="依赖的上游产物已变更但未重新评估，结论可能基于过期信息。",
        standard_refs=["INTERNAL:AI_GOV:DEPENDENCY_FRESHNESS"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
        safety_bottom_line=True,
    ),
    "action_state": RuleMeta(
        rule_id="action_state",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="待处理或已驳回的阻断性人工动作必须先解决。",
        standard_refs=["INTERNAL:AI_GOV:HUMAN_OVERSIGHT", "NIST_AI_RMF:GOVERN"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
        safety_bottom_line=True,
    ),
    "parser_error": RuleMeta(
        rule_id="parser_error",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="阶段输出解析失败意味着无法结构化评估，等同缺输出。",
        standard_refs=["INTERNAL:AI_GOV:OUTPUT_INTEGRITY"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
        safety_bottom_line=True,
    ),
    "safety_finding": RuleMeta(
        rule_id="safety_finding",
        version="1.1.0",
        owner="security",
        since_app_version="1.0.2",
        rationale="high/critical 待人工复核的安全发现必须关闭才能推进。",
        standard_refs=["OWASP_LLM_2025:LLM01", "NIST_AI_RMF:MEASURE", "TC260_AGENT:HUMAN_OVERSIGHT"],
        changelog=[
            ("1.0.0", "2026-07-13", "初始版本"),
            ("1.1.0", "2026-07-13", "联通人工动作状态（v1.0.2 修复）"),
        ],
        safety_bottom_line=True,
    ),
    "stage1_evidence_gap": RuleMeta(
        rule_id="stage1_evidence_gap",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="阶段一证据不完整则失败模式分析不可信。",
        standard_refs=["INTERNAL:AI_GOV:EVIDENCE_COMPLETENESS"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
    ),
    "stage2_policy_gap": RuleMeta(
        rule_id="stage2_policy_gap",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="阶段二策略缺口必须补齐才能进入压力测试。",
        standard_refs=["INTERNAL:AI_GOV:POLICY_COVERAGE"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
    ),
    "stage3_eval_failure": RuleMeta(
        rule_id="stage3_eval_failure",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="阶段三评测失败必须解决，否则未经验证即上线。",
        standard_refs=["NIST_AI_RMF:MEASURE", "INTERNAL:AI_GOV:EVAL_COVERAGE"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
    ),
    "redteam_coverage": RuleMeta(
        rule_id="redteam_coverage",
        version="1.1.0",
        owner="security",
        since_app_version="1.0.2",
        rationale="高/关键风险项目必须有红队用例覆盖才能通过 Stage 3。",
        standard_refs=["OWASP_LLM_2025:LLM01", "NIST_AI_RMF:MEASURE", "OWASP_ASI_2026:ASI01"],
        changelog=[
            ("1.0.0", "2026-07-13", "初始版本"),
            ("1.1.0", "2026-07-13", "风险自适应：低/中风险仅在安全发现缺口时阻断"),
        ],
    ),
    "eval_regression": RuleMeta(
        rule_id="eval_regression",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="评测回归必须监控，防止能力倒退。",
        standard_refs=["NIST_AI_RMF:MEASURE", "INTERNAL:AI_GOV:REGRESSION_CONTROL"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
    ),
    "trace_backfill_gap": RuleMeta(
        rule_id="trace_backfill_gap",
        version="1.0.0",
        owner="project-owner",
        since_app_version="1.0.0",
        rationale="失败/解析错误/安全发现的追踪必须回填为 EvalCase。",
        standard_refs=["NIST_AI_RMF:MEASURE", "INTERNAL:AI_GOV:TRACEABILITY"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
    ),
    "stage4_final_governance": RuleMeta(
        rule_id="stage4_final_governance",
        version="1.0.0",
        owner="compliance",
        since_app_version="1.0.0",
        rationale="阶段四最终治理检查必须通过才能完成全流程。",
        standard_refs=["NIST_AI_RMF:GOVERN", "ISO_42001:CLAUSE_8"],
        changelog=[("1.0.0", "2026-07-13", "初始版本")],
        safety_bottom_line=True,
    ),
}


def get_rule_meta(rule_id: str) -> RuleMeta | None:
    """Return manifest entry for *rule_id*, or None if missing."""
    return RULE_MANIFEST.get(rule_id)


def get_rule_version(rule_id: str) -> str:
    """Return version string for *rule_id*; '0.0.0' if unknown (defensive)."""
    meta = RULE_MANIFEST.get(rule_id)
    return meta.version if meta else "0.0.0"


def is_safety_bottom_line(rule_id: str) -> bool:
    """Whether *rule_id* is a safety-bottom-line rule that cannot be disabled."""
    meta = RULE_MANIFEST.get(rule_id)
    return bool(meta and meta.safety_bottom_line)
```

> `standard_refs` 复用阶段 2 taxonomy 前缀体系（`OWASP_LLM_2025:` / `NIST_AI_RMF:` / `TC260_AGENT:` / `OWASP_ASI_2026:` / `INTERNAL:`），与 `tools/taxonomies/` 互通——治理页可双向跳转。

#### 2.1.2 registered_rules() 启动完整性校验

**改动文件**：[core/gates/rules/__init__.py](../../core/gates/rules/__init__.py)

```python
# core/gates/rules/__init__.py
from __future__ import annotations

import logging

from core.gates.base import GateRule
from core.gates.rules import (
    action_state,
    eval_regression,
    missing_output,
    parser_error,
    redteam_coverage,
    safety_finding,
    stage1_evidence_gap,
    stage2_policy_gap,
    stage3_eval_failure,
    stage4_final_governance,
    stale_dependency,
    trace_backfill_gap,
)
from core.gates.rules.manifest import RULE_MANIFEST

logger = logging.getLogger(__name__)


def registered_rules() -> list[GateRule]:
    rules = [
        missing_output.rule,
        stale_dependency.rule,
        action_state.rule,
        parser_error.rule,
        safety_finding.rule,
        stage1_evidence_gap.rule,
        stage2_policy_gap.rule,
        stage3_eval_failure.rule,
        redteam_coverage.rule,
        eval_regression.rule,
        trace_backfill_gap.rule,
        stage4_final_governance.rule,
    ]
    _verify_manifest_integrity(rules)
    return rules


def _verify_manifest_integrity(rules: list[GateRule]) -> None:
    """启动时校验：每条注册规则有 manifest 条目，每个 manifest 条目有实现。

    双向完整性失败只记 WARNING 不抛异常——避免新增 manifest 条目但实现未上线时
    阻断启动（前向兼容）。完整性由测试固化。
    """
    implemented_ids = {r.rule_id for r in rules}
    manifest_ids = set(RULE_MANIFEST.keys())
    missing_manifest = implemented_ids - manifest_ids
    missing_impl = manifest_ids - implemented_ids
    if missing_manifest:
        logger.warning("Rules without manifest entry: %s", sorted(missing_manifest))
    if missing_impl:
        logger.warning("Manifest entries without implementation: %s", sorted(missing_impl))
```

> 校验只 WARNING 不 raise：避免 manifest 先行落地（实现待补）时阻断启动。完整性由测试严格断言。

#### 2.1.3 测试

**改动文件**：`tests/test_rule_manifest_v110.py`（新建）

- 12 条 `registered_rules()` 的 rule_id 全部在 `RULE_MANIFEST` 有条目
- `RULE_MANIFEST` 每个条目的 rule_id 都有对应实现（双向完整性）
- 每条 `RuleMeta.version` 符合语义化版本格式 `\d+\.\d+\.\d+`
- 每条 `RuleMeta.rationale` 非空
- `is_safety_bottom_line("missing_output")` 为 True；`is_safety_bottom_line("redteam_coverage")` 为 False
- `get_rule_version("redteam_coverage")` 返回 `"1.1.0"`
- `standard_refs` 中每个 ref 含 `:` 前缀分隔符

**验收**：12 条规则全部有 manifest 条目；完整性测试固化；启动校验只 WARNING 不阻断。

**工作量**：M。

---

### T3.2 判定结果携带规则版本 + 评估记录持久化【依赖 T3.1，Wave 2】

#### 2.2.1 GateReport/RuleDetail 增加 rule_version

**改动文件**：[core/gates/report.py](../../core/gates/report.py)

`RuleDetail`（line 16-22）增加字段：
```python
class RuleDetail(BaseModel):
    rule_id: str
    display_name: str
    status: Literal["passed", "blocked", "skipped"]
    severity: Literal["critical", "high", "medium", "low"] | None = None
    reason: str | None = None
    skipped_reason: str | None = None
    rule_version: str = "0.0.0"  # T3.2: 来自 manifest
```

`_RuleEvalRecord`（line 47-66）增加 `rule_version` slot，`__init__` 增加参数。
`build_report()`（line 117-132）透传 `rule_version=rec.rule_version`。

#### 2.2.2 引擎填充版本 + 旁路落表

**改动文件**：[core/gates/engine.py](../../core/gates/engine.py)

`detailed=True` 分支内，构造 `_RuleEvalRecord` 时从 manifest 取版本：
```python
from core.gates.rules.manifest import get_rule_version
# 每个 _RuleEvalRecord 构造追加 rule_version=get_rule_version(rule.rule_id)
```

在 `result = StageGateResult(...)` 之后、`return result` 之前，追加**旁路落表**（无论 detailed 与否，只要有 session_id 就落一行——趋势数据需要所有评估记录）：

```python
# 旁路落表：失败不阻断主路径（spec §7）
_try_persist_gate_evaluation(ctx, stage, result, deduped)
```

新增模块级函数（同文件）：
```python
def _try_persist_gate_evaluation(ctx, stage, result, blockers) -> None:
    """旁路写入 gate_evaluation_records——治理趋势数据源。

    失败只打日志，不抛异常（治理数据缺一行可接受，评估被卡死不可接受）。
    """
    try:
        from core.gates.rules.manifest import get_rule_version
        from core.gates.risk_profile import classify_project_risk
        from storage.session_store import session_store as _store

        session_id = getattr(ctx, "session_id", "") or ""
        if not session_id:
            return
        tenant_id = getattr(ctx, "tenant_id", "") or ""
        risk_tier, _ = classify_project_risk(ctx)
        blocking_rule_ids = sorted({b.rule_id for b in blockers if b.rule_id})
        rule_versions = {
            rid: get_rule_version(rid) for rid in blocking_rule_ids
        } if blocking_rule_ids else {}
        _store.record_gate_evaluation(
            session_id=session_id,
            tenant_id=tenant_id,
            stage_id=stage,
            risk_tier=str(risk_tier),
            passed=not blockers,
            blocking_rule_ids=blocking_rule_ids,
            rule_versions=rule_versions,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "gate_evaluation_records persist failed; non-fatal", exc_info=True
        )
```

> 无论 `detailed` 真假都落表——趋势分析需要全量评估记录，不只是 detailed 调用。`detailed` 仅控制是否构造完整 `GateReport`。

#### 2.2.3 新表 gate_evaluation_records（alembic V005 + SQLite DDL）

**改动文件**：
- `alembic/versions/V005_gate_evaluation_records.py`（新建）
- [storage/backends/postgres.py](../../storage/backends/postgres.py)（新增 `record_gate_evaluation` + 聚合查询方法）
- [storage/backends/sqlite_store.py](../../storage/backends/sqlite_store.py)（同构 SQLite DDL + 方法）

**V005 迁移**（新建，down_revision="V004"）：
```python
"""gate_evaluation_records table for governance trend analytics.

Revision ID: V005
Revises: V004
"""
from alembic import op

revision = "V005"
down_revision = "V004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS gate_evaluation_records (
        record_id            TEXT PRIMARY KEY,
        session_id           TEXT NOT NULL,
        tenant_id            TEXT,
        stage_id             INTEGER NOT NULL,
        risk_tier            TEXT NOT NULL,
        passed               BOOLEAN NOT NULL,
        blocking_rule_ids    JSONB NOT NULL DEFAULT '[]',
        rule_versions        JSONB NOT NULL DEFAULT '{}',
        evaluated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gate_eval_tenant_time "
        "ON gate_evaluation_records (tenant_id, evaluated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gate_eval_session "
        "ON gate_evaluation_records (session_id, stage_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gate_evaluation_records CASCADE")
```

**存储层方法**（postgres.py，sqlite_store 同构）：
```python
def record_gate_evaluation(self, *, session_id, tenant_id, stage_id, risk_tier,
                           passed, blocking_rule_ids, rule_versions) -> None:
    """旁路写入评估记录。失败由调用方吞掉（engine._try_persist）。"""
    import json, uuid
    sql = """
        INSERT INTO gate_evaluation_records
            (record_id, session_id, tenant_id, stage_id, risk_tier,
             passed, blocking_rule_ids, rule_versions, evaluated_at)
        VALUES (%s, %s, %s::uuid, %s, %s, %s, %s, %s, NOW())
    """
    # SQLite 分支用 ? 占位符且无 ::uuid 强制转换；两后端在各自实现内处理
    ...

def gate_trends(self, tenant_id: str, weeks: int = 8) -> list[dict]:
    """按周聚合：评估次数 / 通过率 / Top 阻断规则。强制 tenant 过滤。"""
    # GROUP BY date_trunc('week', evaluated_at) -- postgres
    # strftime('%Y-W%W', evaluated_at)         -- sqlite

def governance_overview(self, tenant_id: str) -> dict:
    """租户内聚合：会话数/状态分布/风险分布/open 发现/pending 动作/报告数。"""

def actions_backlog(self, tenant_id: str, limit: int = 50) -> list[dict]:
    """待处理人工动作明细，按 risk_level 与等待时长排序。"""
```

> SQLite 后端在 `initialize()` 内同步内联 DDL 建 `gate_evaluation_records`（参照现有表建表模式），保持两后端行为一致。

#### 2.2.4 测试

**改动文件**：`tests/test_gate_evaluation_records_v110.py`（新建）

- `GateReport.rules[0].rule_version` 非空且等于 manifest 版本（detailed 模式）
- 旁路落表：mock store，调用 `evaluate_stage_gate` → `record_gate_evaluation` 被调用一次，参数正确
- **降级测试**：让 `record_gate_evaluation` 抛异常 → `evaluate_stage_gate` 仍正常返回 `StageGateResult`（不阻断），仅打 WARNING
- 两后端一致性：postgres/sqlite 的 `gate_trends`/`governance_overview`/`actions_backlog` 对同一数据集返回等价结构
- tenant 隔离：`gate_trends(tenant_id="A")` 不返回 tenant B 的记录

**验收**：导出报告含规则版本；评估落表失败不阻断主路径（有降级测试）；两后端行为一致。

**工作量**：L。

---

### T3.3 规则禁用显式治理 + expert_review 落地【依赖 T3.1+T3.2，Wave 3】

#### 2.3.1 GATE_RULES_DISABLED 配置

**改动文件**：[core/config.py](../../core/config.py) Settings 类追加：
```python
# T3.3 门禁规则禁用治理：显式禁用规则需配置；安全底线规则不可禁用（配置也忽略+告警）
gate_rules_disabled: str = ""  # 逗号分隔 rule_id，如 "redteam_coverage,eval_regression"
```

> 用 `str` 而非 `list[str]`：pydantic-settings 对 list 的 env 解析需 JSON 格式不友好；逗号分隔字符串在 .env 中更自然。提供 `@property` 解析为 set。

```python
@property
def gate_rules_disabled_set(self) -> set[str]:
    return {s.strip() for s in self.gate_rules_disabled.split(",") if s.strip()}
```

#### 2.3.2 引擎消费 disabled 配置 + /health 暴露

**改动文件**：[core/gates/engine.py](../../core/gates/engine.py)

`evaluate_stage_gate` 循环内（line 98），跳过被禁用规则：
```python
from core.config import settings
from core.gates.rules.manifest import is_safety_bottom_line

disabled = settings.gate_rules_disabled_set
for rule in registered_rules():
    if not rule.applies_to(stage):
        ...  # 原有 skipped 逻辑
        continue
    if rule.rule_id in disabled:
        if is_safety_bottom_line(rule.rule_id):
            logger.warning(
                "Rule %s is safety-bottom-line; GATE_RULES_DISABLED entry ignored.",
                rule.rule_id,
            )
        else:
            if detailed:
                rule_records.append(_RuleEvalRecord(
                    rule_id=rule.rule_id,
                    display_name=_display_name(rule.rule_id),
                    status="skipped",
                    skipped_reason="Rule disabled via GATE_RULES_DISABLED.",
                    rule_version=get_rule_version(rule.rule_id),
                ))
            continue  # 跳过评估
    ...  # 原有 evaluate 逻辑
```

> 评估记录的 `rule_versions` 标注 disabled：`_try_persist_gate_evaluation` 内对被禁用规则在 rule_versions 加 `"<rule_id>": "disabled"` 标记。

**/health 暴露**：[api/main.py](../../api/main.py) `health()` 返回追加：
```python
"gate_rules_disabled": sorted(settings.gate_rules_disabled_set) if settings.gate_rules_disabled_set else [],
```

#### 2.3.3 expert_review 落地（补历史欠账）

**改动文件**：`core/gates/rules/expert_review.py`（新建）

```python
# core/gates/rules/expert_review.py
"""Expert review gate rule — consumes Stage3GateProfile.require_expert_review.

补历史欠账：CRITICAL 档 require_expert_review=True 此前无规则消费
（见 stage3-risk-adaptive-gate.md line 72-74 "not implemented" 脚注）。
本规则在 Stage 3 评估时，若 profile.require_expert_review 且尚无 approved
专家复核动作，则产出阻断 blocker（action_type=escalate）。
"""
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.gates.risk_profile import build_stage3_gate_profile
from core.models import ProjectContext


class ExpertReviewRule:
    """Stage 3 expert-review enforcement for CRITICAL-risk projects."""

    rule_id = "expert_review"
    applies_to_stages = {3}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 3:
            return []

        profile = build_stage3_gate_profile(ctx)
        if not profile.require_expert_review:
            return []

        # 幂等：已有 pending 或 resolved 的 expert_review 动作则不重复创建
        existing = [
            a for a in ctx.pending_human_actions
            if a.source_type == "expert_review"
            and a.stage_id == stage
            and a.status in {"pending", "resolved"}
        ]
        if any(a.status == "resolved" and a.reviewer_decision == "approve" for a in existing):
            # 已批准 → 不阻断
            return []
        if any(a.status == "pending" for a in existing):
            # 已有 pending 动作 → 阻断（引用既有 action_id）
            action_id = next(a.action_id for a in existing if a.status == "pending")
        else:
            # 首次：创建 escalate 动作（幂等键机制由 readiness 处理）
            action_id = readiness._find_pending_action_id(
                ctx, stage, source_type="expert_review", source_id="critical_tier_review"
            )
            if action_id is None:
                # 通过 readiness 创建 PendingHumanAction
                action_id = readiness._ensure_pending_action(
                    ctx, stage=stage,
                    action_type="escalate",
                    source_type="expert_review",
                    source_id="critical_tier_review",
                    risk_level="critical",
                    title="CRITICAL 风险项目专家复核",
                    description=(
                        "项目判定为 CRITICAL 风险等级，必须经专家复核批准后才能通过 Stage 3。"
                        f" 依据：{profile.rationale}"
                    ),
                    trigger_reason=profile.rationale,
                    required_resolution="approve_expert_review",
                )

        blocker = readiness._blocker(
            ctx=ctx,
            stage=stage,
            blocker_type="expert_review",
            severity="critical",
            message="CRITICAL 风险项目须专家复核批准方可推进 Stage 3。",
            source_type="expert_review",
            source_id="critical_tier_review",
            action_id=action_id,
            required_resolution="approve_expert_review",
            can_be_overridden_by_approval=True,
            metadata={"risk_tier": "critical", "profile_rationale": profile.rationale},
        )
        return [blocker.model_copy(update={"rule_id": self.rule_id})]


rule = ExpertReviewRule()
```

> `readiness._ensure_pending_action` 若不存在则在该规则内直接构造 `PendingHumanAction` 并 append 到 `ctx.pending_human_actions`（幂等键=source_type+source_id+stage）。落地时核实 `stage_readiness_service` 现有 helper，优先复用。

#### 2.3.4 注册新规则 + 更新 stage3 spec 脚注

**改动文件**：
- [core/gates/rules/__init__.py](../../core/gates/rules/__init__.py)（注册 expert_review.rule + manifest 追加条目）
- [core/gates/rules/manifest.py](../../core/gates/rules/manifest.py)（追加 expert_review 条目）
- [docs/spec/stage3-risk-adaptive-gate.md](../spec/stage3-risk-adaptive-gate.md)（line 72 `⚠️ not implemented` → `✅ implemented (T3.3)`，line 74 脚注改写为"已由 expert_review 规则消费"）
- [docs/spec/governance-platform.md](../spec/governance-platform.md) §1 第 3 行"无消费方"更新为"已落地"

manifest 追加：
```python
"expert_review": RuleMeta(
    rule_id="expert_review",
    version="1.0.0",
    owner="compliance",
    since_app_version="1.1.0",
    rationale="CRITICAL 风险项目必须经专家复核批准，避免高风险自动放行。",
    standard_refs=["NIST_AI_RMF:GOVERN", "ISO_42001:CLAUSE_8", "TC260_AGENT:HUMAN_OVERSIGHT"],
    changelog=[("1.0.0", "2026-07-14", "初始版本——补 stage3-risk-adaptive-gate.md 历史欠账")],
    safety_bottom_line=True,  # CRITICAL 档强制，不可禁用
),
```

> registered_rules() 现在 13 条；完整性测试同步更新。

#### 2.3.5 测试

**改动文件**：`tests/test_expert_review_gate_v110.py`（新建）

- CRITICAL 场景 ctx → `expert_review.evaluate` 产出 1 个 critical blocker + 创建 1 个 escalate 动作
- 再次 evaluate 幂等：不重复创建动作，仍引用既有 action_id
- 动作 approved 后 evaluate 不再阻断
- HIGH/MEDIUM/LOW 场景 → 无 blocker（profile.require_expert_review=False）
- `GATE_RULES_DISABLED="redteam_coverage"` → redteam 被跳过；`GATE_RULES_DISABLED="missing_output"` → 仍评估（安全底线忽略禁用）+ WARNING
- `/health` 返回 `gate_rules_disabled` 字段
- 评估记录 rule_versions 对被禁用规则标注 `"disabled"`

**验收**：禁用规则在 `/health` 与评估记录中可见；CRITICAL 会话不经专家 approve 无法通过 Stage 3；stage3 spec 脚注更新。

**工作量**：M。

---

### T3.4 组织级聚合 API 与前端治理页【依赖 T3.2，Wave 3 并行】

#### 2.4.1 治理 API 路由

**改动文件**：`api/routers/governance.py`（新建）

```python
# api/routers/governance.py
"""Organization-level governance read-only API (spec §4.1).

三个只读端点，viewer 可读——治理透明度本身是价值，无写操作。
组织边界 = tenant；强制 WHERE tenant_id = ?，跨租户不可见。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from storage.session_store import session_store

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/overview")
def governance_overview(
    tenant: TenantContext = require_roles(Role.viewer, Role.editor, Role.admin),
) -> dict:
    """租户内：会话总数/状态分布/风险分布/open 发现/pending 动作/报告数。"""
    return session_store.governance_overview(tenant_id=tenant.tenant_id)


@router.get("/gate-trends")
def gate_trends(
    weeks: int = Query(8, ge=1, le=52),
    tenant: TenantContext = require_roles(Role.viewer, Role.editor, Role.admin),
) -> list[dict]:
    """按周的评估次数/通过率/Top 阻断规则（基于 gate_evaluation_records）。"""
    return session_store.gate_trends(tenant_id=tenant.tenant_id, weeks=weeks)


@router.get("/actions-backlog")
def actions_backlog(
    limit: int = Query(50, ge=1, le=200),
    tenant: TenantContext = require_roles(Role.viewer, Role.editor, Role.admin),
) -> list[dict]:
    """待处理人工动作明细，按 risk_level 与等待时长排序。"""
    return session_store.actions_backlog(tenant_id=tenant.tenant_id, limit=limit)
```

**改动文件**：[api/main.py](../../api/main.py) 注册路由：
```python
from api.routers import (
    ..., governance,
)
app.include_router(governance.router)
```

#### 2.4.2 存储层聚合查询（两后端）

**改动文件**：[storage/backends/postgres.py](../../storage/backends/postgres.py)、[storage/backends/sqlite_store.py](../../storage/backends/sqlite_store.py)

`governance_overview`（postgres 示例，sqlite 同构换占位符与函数）：
```python
def governance_overview(self, tenant_id: str) -> dict:
    """租户内聚合视图。强制 tenant 过滤。"""
    with self._get_conn() as conn:
        # 会话状态分布
        state_rows = conn.execute("""
            SELECT current_state, COUNT(*) AS cnt
            FROM sessions WHERE tenant_id = %s::uuid
            GROUP BY current_state
        """, (tenant_id,)).fetchall()
        # 风险 tier 分布（从最近评估记录取）
        risk_rows = conn.execute("""
            SELECT risk_tier, COUNT(DISTINCT session_id) AS cnt
            FROM gate_evaluation_records
            WHERE tenant_id = %s::uuid
            GROUP BY risk_tier
        """, (tenant_id,)).fetchall()
        # open 安全发现 + pending 动作（从 context_json 聚合）
        ...
    return {
        "sessions_total": ...,
        "state_distribution": {...},
        "risk_tier_distribution": {...},
        "open_safety_findings": ...,
        "pending_actions": ...,
        "reports_exported": ...,
    }
```

> 性能：内部工具租户内百级会话，实时聚合即可，不建物化视图（spec §4.1）。跨租户分支（`tenant_id=""`）**不开放**——安全边界，spec §2 明确。

#### 2.4.3 Streamlit 治理总览页

**改动文件**：
- `frontend/components/governance_overview.py`（新建）
- [frontend/app.py](../../frontend/app.py)（侧边栏新增"治理总览"导航项）

`governance_overview.py`：
```python
def render_governance_overview(api_base: str, token: str):
    import streamlit as st
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    st.header("治理总览")

    overview = requests.get(f"{api_base}/governance/overview", headers=headers, timeout=10).json()
    col1, col2, col3 = st.columns(3)
    col1.metric("项目数", overview["sessions_total"])
    col2.metric("待处理动作", overview["pending_actions"])
    col3.metric("Open 安全发现", overview["open_safety_findings"])

    st.subheader("风险等级分布")
    st.bar_chart(overview["risk_tier_distribution"])

    st.subheader("门禁通过率趋势（8 周）")
    trends = requests.get(f"{api_base}/governance/gate-trends", headers=headers, timeout=10).json()
    st.line_chart([{ "week": t["week"], "通过率": t["pass_rate"] } for t in trends])

    st.subheader("积压动作")
    backlog = requests.get(f"{api_base}/governance/actions-backlog", headers=headers, timeout=10).json()
    st.dataframe(backlog, use_container_width=True)
```

> 复用现有前端组件风格（参照 `frontend/components/*.py` 的 requests + token 模式）。

#### 2.4.4 测试

**改动文件**：`tests/test_governance_api_v110.py`（新建）

- 三个端点 200 返回结构正确
- tenant 隔离：tenant A 用户看不到 tenant B 数据（权限测试）
- viewer 角色可读（403 只对未认证）
- 聚合数值正确：构造 3 个会话（不同状态/风险）→ overview 计数正确
- gate-trends 按周聚合：构造跨 2 周的评估记录 → 返回 2 周桶

**验收**：一个界面看到租户内项目数/风险分布/通过率趋势/积压动作；跨租户不可见。

**工作量**：L。

---

### T3.5 业务指标接入 Prometheus/Grafana【依赖 T3.4，Wave 4】

#### 2.5.1 自定义指标

**改动文件**：`api/metrics.py`（新建）

```python
# api/metrics.py
"""Custom business metrics for Prometheus (spec §4.3).

注册在现有 Instrumentator 之上；基数控制：tenant 标签用名称非 UUID，
不加 session_id 级标签。
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge


# 会话状态（Gauge，定时刷新或按请求计算）
premortem_sessions_total = Gauge(
    "premortem_sessions_total",
    "Total sessions by tenant and state",
    ["tenant", "state"],
)

# 门禁评估（Counter，评估路径打点）
premortem_gate_evaluations_total = Counter(
    "premortem_gate_evaluations_total",
    "Gate evaluations by result",
    ["result"],  # passed | blocked
)

premortem_gate_blocked_total = Counter(
    "premortem_gate_blocked_total",
    "Gate blocks by rule_id",
    ["rule_id"],
)

# 待处理动作（Gauge）
premortem_pending_actions = Gauge(
    "premortem_pending_actions",
    "Pending human actions by risk level",
    ["risk_level"],
)

# LLM 用量（Counter，与阶段 2 LLM10 共用数据源）
premortem_llm_calls_total = Counter(
    "premortem_llm_calls_total",
    "LLM calls total",
)

premortem_llm_tokens_total = Counter(
    "premortem_llm_tokens_total",
    "LLM tokens total (input+output)",
)


def record_gate_evaluation_metrics(passed: bool, blocking_rule_ids: list[str]) -> None:
    """评估路径打点——在 engine._try_persist_gate_evaluation 内调用。"""
    premortem_gate_evaluations_total.labels(result="passed" if passed else "blocked").inc()
    if not passed:
        for rid in blocking_rule_ids:
            premortem_gate_blocked_total.labels(rule_id=rid).inc()


def refresh_gauge_metrics(tenant_name: str = "default") -> None:
    """定时/按需刷新 Gauge 指标（会话数、pending 动作）。

    在 /metrics 被 scrape 前由 lifespan 或后台任务刷新；MVP 阶段可按请求惰性刷新。
    """
    try:
        from storage.session_store import session_store
        overview = session_store.governance_overview(tenant_id="")
        # 注意：overview 需支持按 tenant_name 聚合；MVP 用 default tenant
        for state, cnt in overview.get("state_distribution", {}).items():
            premortem_sessions_total.labels(tenant=tenant_name, state=state).set(cnt)
        for risk, cnt in overview.get("risk_tier_distribution", {}).items():
            premortem_pending_actions.labels(risk_level=risk).set(cnt)
    except Exception:
        pass  # 指标刷新失败不影响主路径
```

**改动文件**：[api/main.py](../../api/main.py) lifespan 内启动时注册 + 暴露：
```python
from api.metrics import refresh_gauge_metrics
# lifespan 内 _instrumentator.expose(...) 之后：
# prometheus_client 默认指标在 /metrics 由 instrumentator 合并暴露
```

**改动文件**：[core/gates/engine.py](../../core/gates/engine.py) `_try_persist_gate_evaluation` 内追加：
```python
from api.metrics import record_gate_evaluation_metrics
record_gate_evaluation_metrics(passed=not blockers, blocking_rule_ids=[...])
```

> LLM 用量 Counter 在 `core/execution_service.py:execute_one_turn` 内 `llm_call_count` 递增处同步 `premortem_llm_calls_total.inc()` + token。

#### 2.5.2 Grafana 治理面板

**改动文件**：`monitoring/grafana/dashboards/governance-overview.json`（新建）

面板含 4 个 panel：
1. 门禁通过率趋势（`rate(premortem_gate_evaluations_total{result="passed"}[1h]) / rate(premortem_gate_evaluations_total[1h])`）
2. Top 阻断规则（`topk(10, sum by (rule_id) (increase(premortem_gate_blocked_total[24h]))`）
3. 待处理动作（`premortem_pending_actions`）
4. LLM 用量（`rate(premortem_llm_calls_total[5m])` + `rate(premortem_llm_tokens_total[5m])`）

provisioning 已配置自动加载目录（实测发现 #9），新增 JSON 即自动可见。

#### 2.5.3 测试

- `api/metrics.py` 导入无误；Counter/Gauge 注册不重复
- `record_gate_evaluation_metrics` 被调用后 `premortem_gate_evaluations_total` 计数增加
- `/metrics` 端点含 `premortem_*` 指标行
- Grafana JSON 合法（`json.load` 不抛异常）

**验收**：`/metrics` 暴露 premortem_* 指标；Grafana 面板 provisioning 自动加载可见。

**工作量**：M。

---

### T3.6 LLM Judge 建议判分（可选增强）【需求确认后启动，Wave 5】

> **启动条件**：spec §5 与计划 T3.6 明确"确认企业场景确有自动化评估需求再做"。本设计给出完整落地方案，但**默认不实施**，待用户显式确认。

#### 2.6.1 设计要点（确认后落地）

**改动文件**：
- [core/config.py](../../core/config.py)（`eval_llm_judge: bool = False` + `eval_llm_judge_autofinal: bool = False`）
- [core/models.py](../../core/models.py)（EvalRun 新增 `llm_judge_suggestion: dict | None`）
- [core/eval_judge.py](../../core/eval_judge.py)（第二层建议判分）
- `alembic/versions/V006_eval_llm_judge.py`（EvalRun 建议字段，down_revision="V005"）

**核心约束**（spec §5）：
- LLM 只建议，不终裁：`judge_result` 不被 LLM 直接改写
- HIGH/CRITICAL 永远人工终裁：`EVAL_LLM_JUDGE_AUTOFINAL=on` 只对 LOW/MEDIUM 生效
- 防注入 judge prompt：材料置于明确分隔引用块、指令置后
- 校准闭环：`human_calibrations` 表累计一致率，治理页展示

**工作量**：L。

---

### T3.7 ISO/IEC 42001 条款映射表（收尾）【纯文档，Wave 4 并行】

**改动文件**：`docs/compliance/iso42001-mapping.md`（新建）

展开 spec §6 表格为完整条款映射：条款 ↔ 平台能力 ↔ 证据端点/表/文档。如实标注未覆盖条款（如"停用阶段"产品缺口沿用阶段 2 TC260 记录）。

**同时修正 spec 两处过时表述**（实测发现 #2、#5）：
- [docs/spec/governance-platform.md](../spec/governance-platform.md) §3.2 "alembic V004" → "alembic V005"
- §1 第 3 行 expert_review 状态更新（T3.3 落地后同步）

**验收**：映射表存在且每条能力可指到具体端点/表/文档。

**工作量**：M（纯文档）。

---

## 3. 执行顺序与并行策略（Subagent-Driven）

### 依赖关系

```
Wave 1（基础，单 agent）：
  Agent A: T3.1 manifest（manifest.py + __init__.py 完整性校验 + test）
           ⚠️ 必须先行：rule_version 与 disabled 判定都依赖 manifest

Wave 2（依赖 T3.1，单 agent）：
  Agent B: T3.2 rule_version + gate_evaluation_records（report.py + engine.py
           + V005 迁移 + 两后端 record_gate_evaluation/gate_trends/governance_overview/actions_backlog + test）

Wave 3（依赖 T3.2，两任务并行——文件级冲突可控）：
  Agent C: T3.3 disabled 治理 + expert_review（config.py + engine.py[disabled 逻辑]
           + expert_review.py[新] + __init__.py[注册] + manifest.py[追加条目]
           + main.py[/health] + stage3 spec 脚注 + test）
  Agent D: T3.4 治理 API + 前端（governance.py[新] + main.py[路由注册]
           + 两后端[聚合查询，T3.2 已建方法签名] + frontend + test）
  ⚠️ C/D 共改 api/main.py（C 改 /health 字段，D 加 router 注册）——
     不同代码段，落地时由协调 agent 统一合并，或 D 先注册 router、C 后加 /health 字段

Wave 4（依赖 T3.4，两任务并行）：
  Agent E: T3.5 metrics + Grafana（metrics.py[新] + main.py[lifespan] + engine.py[打点]
           + execution_service.py[LLM 计数] + governance-overview.json[新] + test）
  Agent F: T3.7 ISO 42001 映射文档（纯文档，无代码冲突）+ spec 两处修正

Wave 5（可选，需求确认后）：
  Agent G: T3.6 LLM Judge（config + models + eval_judge + V006 迁移 + test）

Wave 6（全部完成后收尾）：
  Agent H: 集成验证、STATE.md / CHANGELOG / version bump / git tag
```

### 文件冲突分析（并行安全前提）

| 任务 | 改动文件 | 冲突风险 |
|------|----------|----------|
| T3.1 | `core/gates/rules/manifest.py`(新), `core/gates/rules/__init__.py`, `tests/...`(新) | 无（独占） |
| T3.2 | `core/gates/report.py`, `core/gates/engine.py`, `alembic/versions/V005_..`(新), `storage/backends/postgres.py`, `storage/backends/sqlite_store.py`, `tests/...`(新) | 无（T3.1 后独占） |
| T3.3 | `core/config.py`, `core/gates/engine.py`, `core/gates/rules/expert_review.py`(新), `core/gates/rules/__init__.py`, `core/gates/rules/manifest.py`, `api/main.py`, `docs/spec/stage3-risk-adaptive-gate.md`, `tests/...`(新) | ⚠️ engine.py/manifest.py/__init__.py 与 T3.2 共文件——Wave 2 完成后执行；api/main.py 与 T3.4 共文件 |
| T3.4 | `api/routers/governance.py`(新), `api/main.py`, `storage/backends/postgres.py`, `storage/backends/sqlite_store.py`, `frontend/components/governance_overview.py`(新), `frontend/app.py`, `tests/...`(新) | ⚠️ api/main.py 与 T3.3 共文件；storage backends 与 T3.2 共文件——T3.2 完成后执行 |
| T3.5 | `api/metrics.py`(新), `api/main.py`, `core/gates/engine.py`, `core/execution_service.py`, `monitoring/grafana/dashboards/governance-overview.json`(新), `tests/...`(新) | ⚠️ api/main.py/engine.py 与前 Wave 共文件——Wave 3 完成后执行 |
| T3.6 | `core/config.py`, `core/models.py`, `core/eval_judge.py`, `alembic/versions/V006_..`(新), `tests/...`(新) | 无（可选，独立 Wave） |
| T3.7 | `docs/compliance/iso42001-mapping.md`(新), `docs/spec/governance-platform.md`, `docs/spec/stage3-risk-adaptive-gate.md` | 无（纯文档） |

**冲突缓解策略**：
- **Wave 1/2 严格串行**：T3.1→T3.2 是规则治理链基础，manifest 与 rule_version 强依赖。
- **Wave 3 内 C/D 并行**：api/main.py 共文件，但 C 改 `/health` 字段、D 加 `include_router`，代码段不重叠。落地时 C 先提交，D 基于 C 的 main.py 再加 router——或由协调 agent 合并。storage backends 在 T3.2 已建方法签名，T3.4 只调用不改签名。
- **Wave 4 内 E/F 并行**：E 改代码（metrics），F 纯文档，零冲突。
- 每个 Wave 完成后**显式 `git add <specific-file>` + commit**（遵循 AGENTS.md，禁用 `git add .`），再启动下一个 Wave。

### Subagent 分工建议

| Wave | Agent | 负责任务 | 改动文件 | 备注 |
|------|-------|----------|----------|------|
| 1 | Agent A | T3.1 | manifest.py(新) + __init__.py + test | 基础，先行 |
| 2 | Agent B | T3.2 | report.py + engine.py + V005 + 两后端 + test | 依赖 T3.1 |
| 3 | Agent C | T3.3 | config + engine + expert_review(新) + __init__ + manifest + main.py + stage3 spec + test | 与 D 并行 |
| 3 | Agent D | T3.4 | governance.py(新) + main.py + 两后端 + frontend + test | 与 C 并行 |
| 4 | Agent E | T3.5 | metrics.py(新) + main.py + engine + execution_service + grafana json + test | 依赖 T3.4 |
| 4 | Agent F | T3.7 | iso42001-mapping.md(新) + spec 修正 | 纯文档，并行 |
| 5 | Agent G | T3.6 | config + models + eval_judge + V006 + test | 可选，需求确认后 |
| 6 | Agent H | 收尾 | STATE.md/CHANGELOG/version/tag | 全部完成后 |

**执行后统一校验**（每 Wave 结束）：
- `git status --short` 检查改动范围
- `make lint && make test && make e2e-mock` 三步全绿
- 提交策略：按 AGENTS.md 显式 `git add <file>`，每任务一个 commit

---

## 4. 风险与注意事项

| 风险 | 来源 | 缓解 |
|------|------|------|
| T3.2 旁路落表阻断主路径 | `evaluate_stage_gate` 是阶段推进关键路径 | 旁路写入 `try/except` 全包裹，失败只 WARNING（降级测试固化）；治理数据缺一行可接受，评估被卡死不可接受（spec §7） |
| T3.2 触碰引擎主路径 | `engine.py` 是核心评估逻辑 | `detailed` 签名不变；旁路落表在 `result` 构造后、`return` 前，不影响 `StageGateResult` 语义；全量回归 `make e2e-mock` |
| T3.3 expert_review 创建动作破坏幂等 | `_ensure_pending_action` 可能重复创建 | 复用 `_find_pending_action_id` 幂等键机制（source_type+source_id+stage）；测试覆盖"重复 evaluate 不重复创建" |
| T3.3 安全底线规则误被禁用 | `GATE_RULES_DISABLED` 配置错误 | `is_safety_bottom_line` 二次校验，底线规则配置也忽略 + WARNING；测试覆盖"配置禁用 missing_output 仍评估" |
| T3.4 跨租户数据泄露 | 聚合查询 tenant 过滤遗漏 | 所有聚合方法强制 `WHERE tenant_id = ?`；空 tenant_id 分支**不开放**（安全边界，spec §2）；权限测试覆盖"A 看不到 B" |
| T3.4 聚合查询性能 | context_json 内嵌聚合需解析 JSON | 内部工具百级会话，实时聚合可接受；若性能问题，评估记录表已索引（tenant_id+evaluated_at）提供趋势数据源 |
| T3.5 指标标签基数 | tenant 维度若用 UUID 或 session_id 会爆炸 | tenant 标签用名称非 UUID；**绝不加 session_id 级标签**（spec §4.3）；租户数有限 |
| T3.5 Gauge 刷新时机 | 会话数/pending 是状态量需刷新 | MVP 惰性刷新（/metrics scrape 前刷新）；后续可加后台任务 |
| T3.6 LLM Judge 建议变默认值 | 自动采纳建议破坏"人工终裁"原则 | `EVAL_LLM_JUDGE_AUTOFINAL` 默认 off；只对 LOW/MEDIUM 生效；HIGH/CRITICAL 永远人工；spec §5 张力已消解 |
| T3.6 judge prompt 注入 | eval 输入含对抗内容 | 材料置于明确分隔引用块、指令置后；judge 输出仅结构化字段入库 |
| api/main.py 多 agent 共改 | Wave 3 C/D、Wave 4 E 共文件 | 不同代码段；Wave 间串行 commit；必要时协调 agent 合并 |
| V005 与 V004 迁移链断裂 | spec 原称 V004 建表，实际 V004 已用 | 本设计明确 V005，down_revision="V004"；T3.7 收尾修正 spec 表述 |

---

## 5. 验收清单（对齐实施计划 §6，补充实测校验点）

- [ ] 任一门禁规则能回答"版本/owner/依据/变更历史"（manifest 13 条全覆盖）
- [ ] `tests/test_rule_manifest_v110.py` 通过：双向完整性 + 语义化版本 + safety_bottom_line 判定
- [ ] 报告与评估记录携带规则版本（`GateReport.rules[].rule_version` 非空）
- [ ] `gate_evaluation_records` 表存在（V005 迁移 + SQLite DDL 双后端）
- [ ] 评估落表失败不阻断主路径（降级测试：mock 抛异常 → evaluate 正常返回）
- [ ] CRITICAL 会话强制专家复核动作（expert_review 规则 + escalate 动作）
- [ ] `GATE_RULES_DISABLED` 配置生效：非底线规则跳过、底线规则忽略+WARNING
- [ ] `/health` 暴露 `gate_rules_disabled` 字段
- [ ] [stage3-risk-adaptive-gate.md](../spec/stage3-risk-adaptive-gate.md) line 72 脚注更新为 implemented
- [ ] 治理总览页可看到租户内项目数/风险分布/通过率趋势/积压动作
- [ ] 三个治理端点 tenant 隔离（权限测试：A 看不到 B）
- [ ] `/metrics` 有 `premortem_*` 业务指标
- [ ] Grafana `governance-overview.json` 面板 provisioning 自动加载
- [ ] （若启用 T3.6）LLM Judge 有一致率数据且 flag 关闭时行为不变
- [ ] `docs/compliance/iso42001-mapping.md` 映射表存档，每条能力可指到端点/表/文档
- [ ] spec 两处过时表述修正（V004→V005、expert_review 状态）
- [ ] **（新增）** `make lint && make test && make e2e-mock` 三步全绿
- [ ] **（新增）** `.upgrade/STATE.md` 更新为 Phase 3 complete
- [ ] **（新增）** `CHANGELOG.md` 追加新版本条目
- [ ] **（新增）** `core/version.py` / `pyproject.toml` / `README.md` 版本号 bump，打 git tag

---

## 6. 需用户决策项

1. **是否授权启动执行**：按本设计方案 Subagent-Driven 推进 5 个 Wave（Wave 1 T3.1 → Wave 2 T3.2 → Wave 3 T3.3+T3.4 并行 → Wave 4 T3.5+T3.7 并行 → Wave 6 收尾）。

2. **T3.6 LLM Judge 是否启用**：spec §5 与计划 T3.6 保留"如果企业场景确有自动化评估需求"条件。是否在本次 Phase 3 实施 T3.6？此决策不阻塞 Wave 1-4 启动——T3.6 作为可选 Wave 5，确认后再启动。

3. **安全底线规则清单确认**：本设计将 6 条规则标为 `safety_bottom_line=True`（missing_output / parser_error / safety_finding / action_state / stale_dependency / stage4_final_governance），外加 T3.3 新增的 expert_review。是否同意此清单为"不可禁用"集合？此决策影响 T3.3 的 `is_safety_bottom_line` 判定。

> 决策项 1 阻塞所有任务；决策项 2 不阻塞 Wave 1-4（T3.6 可选）；决策项 3 影响 T3.3 实现细节，建议与决策项 1 一并确认。
