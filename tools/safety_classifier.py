# tools/safety_classifier.py
from __future__ import annotations

import re
from collections.abc import Iterable

from core.models import EvidenceSource, ProjectContext, SafetyFinding
from tools.prompt_injection_scanner import has_prompt_injection
from tools.risk_taxonomy import RISK_DESCRIPTIONS
from tools.taxonomies.mapper import apply_taxonomy_to_safety_finding

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}",
]

# PII 检测（T1.4）— 命中产出 sensitive_info finding；身份证/银行卡 severity=high
PII_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, kind, severity)
    # 中国大陆身份证号（18 位，最后一位校验可为 X）
    (
        r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b",
        "cn_id_card",
        "high",
    ),
    # 中国大陆手机号
    (r"\b1[3-9]\d{9}\b", "cn_mobile", "medium"),
    # 邮箱
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email", "low"),
    # 银行卡号（16-19 位，Luhn 校验后置）
    (r"\b\d{16,19}\b", "bank_card", "high"),
]

OVER_AUTONOMY_PATTERNS = [
    r"无需人工(确认|审核|介入)",
    r"直接执行.*不需要.*人工",
    r"skip human review",
    r"without human approval",
]

UNSAFE_INSTRUCTION_PATTERNS = [
    r"绕过.*(审批|审核|权限|安全)",
    r"忽略.*(安全|策略|policy|规则)",
    r"自动.*(删除|支付|转账|发送).*无需.*人工",
    r"bypass.*(approval|review|permission|safety)",
]

STRONG_ASSERTION_PATTERNS = [
    r"必然",
    r"一定",
    r"保证",
    r"绝不会",
    r"100%",
    r"guaranteed",
    r"proven",
    r"will always",
    r"never fails",
]


def _mask_pii(text: str, kind: str) -> str:
    """掩码 PII：保留首尾字符，中间用 * 替换。"""
    if not text or len(text) <= 4:
        return "***"
    if kind == "email":
        # 邮箱掩码：u***@domain.com
        local, _, domain = text.partition("@")
        if not domain:
            return text
        return f"{local[0]}***@{domain}"
    if kind == "cn_id_card":
        return f"{text[:6]}********{text[-4:]}"
    if kind == "cn_mobile":
        return f"{text[:3]}****{text[-4:]}"
    if kind == "bank_card":
        return f"{text[:4]}************{text[-4:]}"
    return text[:2] + "*" * (len(text) - 4) + text[-2:]


def scan_pii(text: str) -> list[tuple[str, str, str]]:
    """检测文本中的 PII。返回 [(matched_text, kind, severity), ...]。"""
    findings: list[tuple[str, str, str]] = []
    for pattern, kind, severity in PII_PATTERNS:
        for match in re.finditer(pattern, text or ""):
            findings.append((match.group(0), kind, severity))
    return findings


def mask_pii_in_text(text: str) -> str:
    """对文本中的所有 PII 进行掩码（用于 prompt 路径）。"""
    masked = text or ""
    for pattern, kind, _severity in PII_PATTERNS:
        masked = re.sub(pattern, lambda m, k=kind: _mask_pii(m.group(0), k), masked)
    return masked


def _finding(
    ctx: ProjectContext,
    *,
    stage_id: int | None,
    risk_type: str,
    severity: str,
    location: str,
    description: str,
    recommended_action: str,
) -> SafetyFinding:
    finding = SafetyFinding(
        session_id=ctx.session_id,
        stage_id=stage_id,
        risk_type=risk_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        location=location,
        description=description,
        recommended_action=recommended_action,
        requires_human_review=severity in {"high", "critical"},
    )
    return apply_taxonomy_to_safety_finding(finding)


def _scan_unsupported_claims(
    ctx: ProjectContext,
    *,
    stage_id: int | None,
    location: str,
    text: str,
) -> list[SafetyFinding]:
    """轻量检测没有 evidence_id 的强断言。

    这是规则型兜底：只对强断言且同段落没有 EVID/USER-EVID 引用的内容告警。
    """
    findings: list[SafetyFinding] = []
    paragraphs = [
        p.strip() for p in re.split(r"\n{2,}|(?<=[。.!?！？])\s+", text or "") if p.strip()
    ]
    for idx, paragraph in enumerate(paragraphs):
        if re.search(r"(?:USER-)?EVID-[A-Za-z0-9_-]+", paragraph):
            continue
        if any(
            re.search(pattern, paragraph, flags=re.IGNORECASE | re.S)
            for pattern in STRONG_ASSERTION_PATTERNS
        ):
            findings.append(
                _finding(
                    ctx,
                    stage_id=stage_id,
                    risk_type="unsupported_claim",
                    severity="medium",
                    location=f"{location}.unsupported_claim[{idx}]",
                    description=RISK_DESCRIPTIONS.get(
                        "unsupported_claim",
                        "AI 输出包含缺少证据引用的强断言。",
                    ),
                    recommended_action="要求人工补充 evidence_id、降低表述强度，或将该结论标为需核验。",
                )
            )
    return findings


def scan_text(
    ctx: ProjectContext,
    *,
    stage_id: int | None,
    location: str,
    text: str,
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    content = text or ""
    if not content:
        return findings

    if has_prompt_injection(content):
        findings.append(
            _finding(
                ctx,
                stage_id=stage_id,
                risk_type="prompt_injection",
                severity="high",
                location=location,
                description=RISK_DESCRIPTIONS["prompt_injection"],
                recommended_action="人工检查该文本是否试图覆盖系统流程或绕过审核门。",
            )
        )

    if any(re.search(pattern, content, flags=re.S) for pattern in SECRET_PATTERNS):
        findings.append(
            _finding(
                ctx,
                stage_id=stage_id,
                risk_type="sensitive_info",
                severity="critical",
                location=location,
                description=RISK_DESCRIPTIONS["sensitive_info"],
                recommended_action="立即停止自动推进，人工确认是否包含真实敏感信息并进行脱敏。",
            )
        )

    # PII 检测（T1.4）— 仅对用户材料/证据源启用，避免 LLM 输出误报
    if location.startswith(("user_materials", "evidence_source")):
        pii_hits = scan_pii(content)
        if pii_hits:
            pii_kinds = sorted({kind for _, kind, _ in pii_hits})
            sev_rank = {"low": 0, "medium": 1, "high": 2}
            max_severity = max((sev for _, _, sev in pii_hits), key=lambda s: sev_rank.get(s, 0))
            findings.append(
                _finding(
                    ctx,
                    stage_id=stage_id,
                    risk_type="sensitive_info",
                    severity=max_severity,
                    location=location,
                    description=f"用户材料包含 PII：{', '.join(pii_kinds)}。",
                    recommended_action="确认 PII 是否必要；如必要，启用 PII_MASK_BEFORE_LLM 掩码后再发送 LLM。",
                )
            )
            # T1.1 联动：PII 命中自动升级数据分级到 sensitive_personal
            if hasattr(ctx, "data_classification"):
                if ctx.data_classification != "sensitive_personal":
                    ctx.data_classification = "sensitive_personal"

    if any(
        re.search(pattern, content, flags=re.IGNORECASE | re.S)
        for pattern in OVER_AUTONOMY_PATTERNS
    ):
        findings.append(
            _finding(
                ctx,
                stage_id=stage_id,
                risk_type="over_autonomy",
                severity="high",
                location=location,
                description=RISK_DESCRIPTIONS["over_autonomy"],
                recommended_action="要求人工确认该节点是否允许自动执行，并补充 HumanOversightPolicy。",
            )
        )

    if any(
        re.search(pattern, content, flags=re.IGNORECASE | re.S)
        for pattern in UNSAFE_INSTRUCTION_PATTERNS
    ):
        findings.append(
            _finding(
                ctx,
                stage_id=stage_id,
                risk_type="unsafe_instruction",
                severity="high",
                location=location,
                description=RISK_DESCRIPTIONS.get(
                    "unsafe_instruction", "文本包含可能绕过安全控制的高风险指令。"
                ),
                recommended_action="人工确认是否允许该指令进入后续阶段；必要时删除或改写。",
            )
        )

    if stage_id in {1, 2, 4}:
        findings.extend(
            _scan_unsupported_claims(
                ctx,
                stage_id=stage_id,
                location=location,
                text=content,
            )
        )

    return findings


def add_findings_dedup(ctx: ProjectContext, findings: list[SafetyFinding]) -> int:
    """按 stage/risk/location/description 去重，避免多轮对话重复刷屏。"""
    existing = {(f.stage_id, f.risk_type, f.location, f.description) for f in ctx.safety_findings}
    count = 0
    for finding in findings:
        key = (finding.stage_id, finding.risk_type, finding.location, finding.description)
        if key not in existing:
            apply_taxonomy_to_safety_finding(finding)
            ctx.safety_findings.append(finding)
            existing.add(key)
            count += 1
    return count


def scan_stage_io(
    ctx: ProjectContext,
    *,
    stage_id: int,
    user_message: str,
    ai_text: str,
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    findings.extend(
        scan_text(
            ctx, stage_id=stage_id, location=f"stage_{stage_id}.user_message", text=user_message
        )
    )
    findings.extend(
        scan_text(ctx, stage_id=stage_id, location=f"stage_{stage_id}.ai_output", text=ai_text)
    )
    return findings


def scan_user_materials(
    ctx: ProjectContext,
    materials: Iterable[str],
    *,
    stage_id: int | None = None,
    start_index: int = 0,
) -> list[SafetyFinding]:
    """扫描用户上传 / 粘贴资料。"""
    findings: list[SafetyFinding] = []
    for offset, material in enumerate(materials):
        findings.extend(
            scan_text(
                ctx,
                stage_id=stage_id,
                location=f"user_materials[{start_index + offset}]",
                text=material,
            )
        )
    return findings


def scan_evidence_sources(
    ctx: ProjectContext,
    evidence_sources: Iterable[EvidenceSource],
    *,
    stage_id: int | None = 1,
) -> list[SafetyFinding]:
    """扫描外部检索结果和 EvidenceSource 摘要 / claims。"""
    findings: list[SafetyFinding] = []
    for ev in evidence_sources:
        base_location = f"evidence_source.{ev.evidence_id}"
        findings.extend(
            scan_text(ctx, stage_id=stage_id, location=f"{base_location}.summary", text=ev.summary)
        )
        if ev.claims:
            findings.extend(
                scan_text(
                    ctx,
                    stage_id=stage_id,
                    location=f"{base_location}.claims",
                    text="\n".join(ev.claims),
                )
            )
        if ev.credibility_score < 0.4 or ev.source_type in {"unknown", "forum"}:
            findings.append(
                _finding(
                    ctx,
                    stage_id=stage_id,
                    risk_type="source_untrusted",
                    severity="medium",
                    location=base_location,
                    description=RISK_DESCRIPTIONS.get(
                        "source_untrusted", "证据来源可信度不足或来源类型未知。"
                    ),
                    recommended_action="降低该证据权重；若被高风险失败模式引用，必须人工核验。",
                )
            )
    return findings


def _failure_mode_severity_map(ctx: ProjectContext) -> dict[str, str]:
    if not ctx.stage_1_output:
        return {}
    return {fm.id: str(fm.severity).lower() for fm in ctx.stage_1_output.failure_modes}


def _node_risk_level(ctx: ProjectContext, node) -> str:
    severity_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    severities = _failure_mode_severity_map(ctx)
    risk = "low"
    for fm_id in getattr(node, "failure_modes_addressed", []) or []:
        severity = severities.get(fm_id, "low")
        if severity_rank.get(severity, 0) > severity_rank.get(risk, 0):
            risk = severity
    policy = getattr(node, "oversight_policy", None)
    if policy and severity_rank.get(policy.risk_level, 0) > severity_rank.get(risk, 0):
        risk = policy.risk_level
    return risk


def scan_policy_gaps(ctx: ProjectContext, *, stage_id: int) -> list[SafetyFinding]:
    """检测工作流/触发方式中缺失人工监督策略的 policy gap。"""
    findings: list[SafetyFinding] = []
    if stage_id == 2 and ctx.stage_2_output:
        high_risk_failure_modes = {
            fm.id
            for fm in (ctx.stage_1_output.failure_modes if ctx.stage_1_output else [])
            if str(fm.severity).lower() in {"high", "critical"}
        }
        covered_high_risk: set[str] = set()
        for node in ctx.stage_2_output.workflow_nodes:
            addressed = set(getattr(node, "failure_modes_addressed", []) or [])
            covered_high_risk.update(addressed.intersection(high_risk_failure_modes))
            node_risk = _node_risk_level(ctx, node)
            if node_risk in {"high", "critical"} and node.oversight_policy is None:
                findings.append(
                    _finding(
                        ctx,
                        stage_id=2,
                        risk_type="policy_gap",
                        severity="high",
                        location=f"stage_2.workflow_node.{node.node_id}",
                        description=f"高风险工作流节点 {node.node_id} 缺少 HumanOversightPolicy。",
                        recommended_action="为该节点补充人工审核策略、required_action 和 evidence_required 设置。",
                    )
                )

        uncovered = sorted(high_risk_failure_modes - covered_high_risk)
        for failure_mode_id in uncovered:
            findings.append(
                _finding(
                    ctx,
                    stage_id=2,
                    risk_type="policy_gap",
                    severity="high",
                    location=f"stage_2.failure_mode_coverage.{failure_mode_id}",
                    description=f"高风险 failure_mode {failure_mode_id} 未被任何 WorkflowNode 覆盖。",
                    recommended_action="补充 workflow node 或编辑现有节点的 failure_modes_addressed，使高风险失败模式有明确的人机监督路径。",
                )
            )

    if stage_id == 4 and ctx.stage_4_output and ctx.stage_2_output:
        nodes_by_id = {node.node_id: node for node in ctx.stage_2_output.workflow_nodes}
        for method in ctx.stage_4_output.trigger_methods:
            node = nodes_by_id.get(method.node_id)
            if not node:
                continue
            node_risk = _node_risk_level(ctx, node)
            if node_risk in {"high", "critical"} and not method.human_review_required:
                findings.append(
                    _finding(
                        ctx,
                        stage_id=4,
                        risk_type="policy_gap",
                        severity="high",
                        location=f"stage_4.trigger_method.{method.node_id}",
                        description=f"高风险节点 {method.node_id} 的触发方式未要求人工审核。",
                        recommended_action="将 human_review_required 设为 true，或人工解释为什么该触发方式可自动执行。",
                    )
                )

    return findings


def scan_stage3_test_cases(ctx: ProjectContext) -> list[SafetyFinding]:
    """扫描 Stage 3 生成的测试样例，尤其是 adversarial 用例。"""
    if not ctx.stage_3_output:
        return []

    findings: list[SafetyFinding] = []
    for idx, case in enumerate(ctx.stage_3_output.test_results):
        location_base = f"stage_3.test_case[{idx}].{case.tested_node_id}"
        findings.extend(
            scan_text(
                ctx,
                stage_id=3,
                location=f"{location_base}.test_input",
                text=case.test_input,
            )
        )
        findings.extend(
            scan_text(
                ctx,
                stage_id=3,
                location=f"{location_base}.expected_behavior",
                text=case.ai_output,
            )
        )
        if case.correction_prompts:
            findings.extend(
                scan_text(
                    ctx,
                    stage_id=3,
                    location=f"{location_base}.correction_prompts",
                    text="\n".join(case.correction_prompts),
                )
            )

        if case.scenario_type == "adversarial" and any(
            finding.location.startswith(location_base) and finding.risk_type == "prompt_injection"
            for finding in findings
        ):
            for finding in findings:
                if (
                    finding.location.startswith(location_base)
                    and finding.risk_type == "prompt_injection"
                ):
                    finding.severity = "high"
                    finding.requires_human_review = True
    return findings
