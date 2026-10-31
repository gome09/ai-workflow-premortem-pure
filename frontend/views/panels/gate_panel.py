# frontend/views/panels/gate_panel.py
from __future__ import annotations

import streamlit as st
from controllers.stage_controller import execute_stage_operation, sync_missing_review_action
from labels import (
    blocker_type_zh,
    decision_reason_zh,
    hard_blocker_zh,
    lifecycle_zh,
    resolution_zh,
    severity_zh,
)
from models.api_client import (
    get_stage_advancement_decision,
    get_stage_readiness,
    get_stage_resolution,
)


def _stage_advancement_decision(stage_id: int) -> dict:
    """推进判定是只读派生视图：优先复用已缓存结果，缺失时才回源并回填。"""
    decisions = st.session_state.get("stage_advancement_decisions") or {}
    cached = decisions.get(f"stage_{stage_id}")
    if isinstance(cached, dict) and cached:
        return cached
    decision = get_stage_advancement_decision(st.session_state.session_id, stage_id)
    if decision:
        decisions = dict(st.session_state.get("stage_advancement_decisions", {}))
        decisions[f"stage_{stage_id}"] = decision
        st.session_state.stage_advancement_decisions = decisions
    return decision


def render_gate_panel(state: str) -> None:
    """Stage Readiness / Gate Blockers 面板。"""
    readiness = st.session_state.stage_readiness or get_stage_readiness(st.session_state.session_id)
    st.session_state.stage_readiness = readiness
    stage_resolution = st.session_state.stage_resolution or get_stage_resolution(
        st.session_state.session_id
    )
    st.session_state.stage_resolution = stage_resolution
    state_stage_map = {
        "s1_running": 1,
        "s1_review": 1,
        "s2_running": 2,
        "s2_review": 2,
        "s3_running": 3,
        "s3_review": 3,
        "s4_running": 4,
        "s4_review": 4,
        "complete": 4,
    }
    current_stage_id = state_stage_map.get(state)
    if current_stage_id:
        current_readiness = readiness.get(f"stage_{current_stage_id}", {})
        advancement_decision = _stage_advancement_decision(current_stage_id)
        blockers = current_readiness.get("blockers", []) or []
        can_continue = advancement_decision.get(
            "can_advance", current_readiness.get("can_continue", False)
        )
        gate_label = "✅ 当前阶段可推进" if can_continue else f"🧭 阶段推进阻断器 ({len(blockers)})"
        with st.expander(gate_label, expanded=bool(blockers)):
            st.caption(
                f"阶段 {current_stage_id} · 输出版本 v{current_readiness.get('stage_output_version', 1)}"
            )
            if advancement_decision:
                hard_cnt = advancement_decision.get("hard_blockers_count", 0)
                exec_cnt = advancement_decision.get("executable_operations_count", 0)
                st.caption(
                    f"当前状态：{lifecycle_zh(advancement_decision.get('stage_lifecycle'))} · "
                    f"必须处理 {hard_cnt} 项 · 可执行操作 {exec_cnt} 项"
                )
            if current_readiness.get("block_reason"):
                st.warning(current_readiness["block_reason"])
            if blockers:
                for blocker in blockers[:8]:
                    st.markdown(
                        f"- [{severity_zh(blocker.get('severity'))} · "
                        f"{blocker_type_zh(blocker.get('blocker_type'))}] "
                        f"{blocker.get('message')}"
                    )
                    st.caption(f"建议操作：{resolution_zh(blocker.get('required_resolution'))}")

                stage_ops = advancement_decision.get("required_operations") or (
                    stage_resolution.get("by_stage") or {}
                ).get(f"stage_{current_stage_id}", [])
                if stage_ops:
                    st.markdown("**可执行解除操作：**")
                    for op in stage_ops[:8]:
                        label = (
                            f"{resolution_zh(op.get('required_resolution'))} · "
                            f"{blocker_type_zh(op.get('blocker_type'))} · "
                            f"{hard_blocker_zh(op.get('hard_blocker'))}"
                        )
                        with st.expander(label, expanded=False):
                            st.markdown(op.get("frontend_hint") or "")
                            payload_hint = op.get("payload_hint") or {}
                            if (
                                op.get("can_execute_via_api")
                                and op.get("api_path")
                                and op.get("required_resolution")
                                in {"rerun_stage", "revise_stage", "back_stage"}
                            ):
                                stage_op = {
                                    "rerun_stage": "rerun",
                                    "revise_stage": "revise",
                                    "back_stage": "rollback",
                                }[op.get("required_resolution")]
                                default_body = (
                                    payload_hint if isinstance(payload_hint, dict) else {}
                                )
                                if st.button(
                                    "执行该阶段操作",
                                    key=f"stage_op_{op.get('operation_id')}",
                                    use_container_width=True,
                                ):
                                    execute_stage_operation(
                                        op.get("stage_id"),
                                        stage_op,
                                        default_body,
                                    )
                            if not op.get("action_id") and op.get("required_resolution") in {
                                "resolve_action",
                                "edit_stage_output",
                                "approve_escalation",
                            }:
                                if st.button(
                                    "同步缺失审核动作",
                                    key=f"sync_actions_{op.get('operation_id')}",
                                    use_container_width=True,
                                ):
                                    sync_missing_review_action(op.get("stage_id"))

                            # ── 技术详情（原始 ID / 枚举 / API 路径 / 参数）──
                            with st.expander("🔧 技术详情", expanded=False):
                                if op.get("action_id"):
                                    st.code(op.get("action_id"), language="text")
                                if op.get("api_path"):
                                    st.caption(f"API：{op.get('api_method')} {op.get('api_path')}")
                                elif op.get("api_hint"):
                                    st.caption(op.get("api_hint"))
                                if payload_hint:
                                    st.json(payload_hint)
                else:
                    st.caption(
                        "当前阻断项暂无可一键解除的操作，请按上面的「建议操作」逐项处理；"
                        "已处理 / 已被替代的历史动作不会显示为可执行操作。"
                    )

                # ── 阻断项技术详情（原始标识，供排查）────────────────────
                with st.expander("🔧 技术详情（阻断项原始信息）", expanded=False):
                    if advancement_decision:
                        st.caption(
                            f"decision_reason=`{advancement_decision.get('decision_reason')}`"
                            f"（{decision_reason_zh(advancement_decision.get('decision_reason'))}） · "
                            f"lifecycle=`{advancement_decision.get('stage_lifecycle')}` · "
                            f"hard={advancement_decision.get('hard_blockers_count', 0)} · "
                            f"executable={advancement_decision.get('executable_operations_count', 0)}"
                        )
                    for blocker in blockers[:8]:
                        bits = [f"blocker_id={blocker.get('blocker_id')}"]
                        if blocker.get("action_id"):
                            bits.append(f"action_id={blocker.get('action_id')}")
                        bits.append(
                            f"source={blocker.get('source_type') or '-'}:"
                            f"{blocker.get('source_id') or '-'}"
                        )
                        bits.append(f"required_resolution={blocker.get('required_resolution')}")
                        st.caption(" · ".join(bits))
            else:
                st.success("当前阶段没有阻断项。")

            operations = current_readiness.get("recommended_next_operations") or []
            if operations:
                st.markdown("**下一步建议操作：**")
                for op in operations:
                    st.caption(f"- {op}")

            metadata = current_readiness.get("stage_metadata") or {}
            if current_stage_id == 2 and metadata.get("stage_2_coverage_matrix"):
                st.caption("阶段二高风险覆盖矩阵已生成，可在报告 / 接口中查看。")
            if current_stage_id == 3 and metadata.get("stage_3_coverage_warning", {}).get(
                "coverage_warning"
            ):
                missing = metadata["stage_3_coverage_warning"].get(
                    "missing_eval_coverage_node_ids", []
                )
                st.warning(
                    "高风险节点缺少评测用例覆盖，需补充阶段三结构化输出或回退重跑："
                    f"{', '.join(missing)}"
                )
            if current_stage_id == 4 and metadata.get("final_governance_summary"):
                summary = metadata["final_governance_summary"]
                st.caption(
                    "最终治理："
                    f"待处理危急安全发现 {len(summary.get('open_critical_safety_findings', []))} 项，"
                    f"待处理阻断动作 {len(summary.get('pending_blocking_action_ids', []))} 项"
                )
