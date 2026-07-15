# core/gates/rules/stage1_evidence_gap.py
from __future__ import annotations

import core.stage_readiness_service as readiness
from core.models import ProjectContext


class Stage1EvidenceGapRule:
    """Direct GateRule: high/critical Stage 1 claims require verified evidence."""

    rule_id = "stage1_evidence_gap"
    applies_to_stages = {1}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if stage != 1 or not ctx.stage_1_output:
            return []

        evidence_by_id = {ev.evidence_id: ev for ev in ctx.evidence_sources}
        blockers: list[readiness.StageBlocker] = []

        for fm in ctx.stage_1_output.failure_modes:
            severity = str(fm.severity).lower()
            if severity not in {"high", "critical"}:
                continue

            evidence_ids = list(dict.fromkeys(getattr(fm, "evidence_ids", []) or []))
            if not evidence_ids:
                action_id = readiness._find_pending_action_id(
                    ctx, 1, source_type="evidence_gap", source_id=fm.id
                )
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=1,
                        blocker_type="evidence_gap",
                        severity=fm.severity,
                        message=f"阶段1高风险失败模式 {fm.id} 缺少 evidence_id，必须编辑结构化 Stage1 输出补充证据引用。",
                        source_type="failure_mode",
                        source_id=fm.id,
                        action_id=action_id,
                        required_resolution="edit_stage_output",
                        can_be_overridden_by_approval=False,
                        metadata=readiness._with_action_history(
                            {
                                "gap_type": "missing_evidence_id",
                                "requires_structured_output": True,
                                "expected_schema": "Stage1Schema",
                            },
                            ctx=ctx,
                            stage=1,
                            source_type="evidence_gap",
                            source_id=fm.id,
                            pending_action_id=action_id,
                        ),
                    )
                )
                continue

            for evidence_id in evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    action_id = readiness._find_pending_action_id(
                        ctx, 1, source_type="evidence_gap", source_id=fm.id
                    )
                    blockers.append(
                        readiness._blocker(
                            ctx=ctx,
                            stage=1,
                            blocker_type="evidence_gap",
                            severity=fm.severity,
                            message=(
                                f"阶段1高风险失败模式 {fm.id} 引用了不存在的证据 {evidence_id}，"
                                "必须编辑结构化 Stage1 输出，不能调用 evidence verify。"
                            ),
                            source_type="failure_mode",
                            source_id=fm.id,
                            action_id=action_id,
                            required_resolution="edit_stage_output",
                            can_be_overridden_by_approval=False,
                            metadata=readiness._with_action_history(
                                {
                                    "gap_type": "unknown_evidence_id",
                                    "missing_evidence_id": evidence_id,
                                    "requires_structured_output": True,
                                    "expected_schema": "Stage1Schema",
                                },
                                ctx=ctx,
                                stage=1,
                                source_type="evidence_gap",
                                source_id=fm.id,
                                pending_action_id=action_id,
                            ),
                        )
                    )
                    continue

                if getattr(evidence, "verified", False):
                    continue

                action_id = None
                for source_type in {
                    "evidence_unverified_for_high_risk",
                    "evidence_low_credibility",
                }:
                    action_id = readiness._find_pending_action_id(
                        ctx, 1, source_type=source_type, source_id=fm.id
                    )
                    if action_id:
                        break
                blockers.append(
                    readiness._blocker(
                        ctx=ctx,
                        stage=1,
                        blocker_type="evidence_gap",
                        severity=fm.severity,
                        message=(
                            f"阶段1高风险失败模式 {fm.id} 引用的证据 {evidence_id} "
                            "尚未核验。仅关闭（dismiss）人工动作不会解除该证据门控。"
                        ),
                        source_type="evidence",
                        source_id=evidence_id,
                        action_id=action_id,
                        required_resolution="verify_evidence",
                        can_be_overridden_by_approval=False,
                        metadata=readiness._with_action_history(
                            {
                                "gap_type": "unverified_evidence_id",
                                "failure_mode_id": fm.id,
                                "evidence_exists": True,
                                "source_type": getattr(evidence, "source_type", None),
                                "credibility_score": getattr(evidence, "credibility_score", None),
                            },
                            ctx=ctx,
                            stage=1,
                            source_type="evidence_unverified_for_high_risk",
                            source_id=fm.id,
                            pending_action_id=action_id,
                        ),
                    )
                )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = Stage1EvidenceGapRule()
