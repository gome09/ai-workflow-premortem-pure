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
    version: str  # 语义化版本，如 "1.1.0"
    owner: str  # 责任方：project-owner / security / compliance
    since_app_version: str  # 该规则首次引入的应用版本
    rationale: str  # 为什么存在这条规则
    standard_refs: list[str] = field(default_factory=list)
    changelog: list[tuple[str, str, str]] = field(default_factory=list)  # (version, date, summary)
    safety_bottom_line: bool = False  # 是否属安全底线规则（不可禁用，T3.3 消费）


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
        standard_refs=[
            "OWASP_LLM_2025:LLM01",
            "NIST_AI_RMF:MEASURE",
            "TC260_AGENT:HUMAN_OVERSIGHT",
        ],
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
    "expert_review": RuleMeta(
        rule_id="expert_review",
        version="1.0.0",
        owner="compliance",
        since_app_version="1.1.0",
        rationale="CRITICAL 风险项目必须经专家复核批准，避免高风险自动放行。",
        standard_refs=[
            "NIST_AI_RMF:GOVERN",
            "ISO_42001:CLAUSE_8",
            "TC260_AGENT:HUMAN_OVERSIGHT",
        ],
        changelog=[("1.0.0", "2026-07-14", "初始版本——补 stage3-risk-adaptive-gate.md 历史欠账")],
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
