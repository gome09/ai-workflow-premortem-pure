# core/gates/rules/stale_dependency.py
from __future__ import annotations

from typing import Any

import core.stage_readiness_service as readiness
from core.models import ProjectContext


class StaleDependencyRule:
    """Direct GateRule: block stages whose upstream dependency versions changed."""

    rule_id = "stale_dependency"
    applies_to_stages = {1, 2, 3, 4}

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[readiness.StageBlocker]:
        if not readiness._stage_output_exists(ctx, stage):
            return []

        key = readiness._stage_key(stage)
        blockers: list[readiness.StageBlocker] = []

        stale_meta: dict[str, Any] = getattr(ctx, "stage_staleness", {}).get(key) or {}
        if stale_meta.get("stale"):
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="stale_dependency",
                    severity="high",
                    message=(
                        f"阶段{stage}输出已过期：{stale_meta.get('reason') or '上游阶段已更新'}。"
                        "请重跑该阶段后再继续。"
                    ),
                    source_type="stage",
                    source_id=key,
                    required_resolution="rerun_stage",
                    can_be_overridden_by_approval=False,
                    metadata=stale_meta,
                )
            )

        dependency_versions = getattr(ctx, "stage_dependency_versions", {}).get(key, {}) or {}
        stale_dependencies: dict[str, dict[str, int]] = {}
        for upstream_key, recorded_version in dependency_versions.items():
            current_version = int(ctx.stage_output_versions.get(upstream_key, 1))
            if current_version > int(recorded_version):
                stale_dependencies[upstream_key] = {
                    "recorded_version": int(recorded_version),
                    "current_version": current_version,
                }

        if stale_dependencies:
            blockers.append(
                readiness._blocker(
                    ctx=ctx,
                    stage=stage,
                    blocker_type="stale_dependency",
                    severity="high",
                    message=f"阶段{stage}依赖的上游输出版本已更新，请重跑阶段{stage}。",
                    source_type="stage_dependency_versions",
                    source_id=key,
                    required_resolution="rerun_stage",
                    can_be_overridden_by_approval=False,
                    metadata={"stale_dependencies": stale_dependencies},
                )
            )

        return [blocker.model_copy(update={"rule_id": self.rule_id}) for blocker in blockers]


rule = StaleDependencyRule()
