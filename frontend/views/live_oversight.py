# frontend/views/live_oversight.py
from __future__ import annotations

import re

import streamlit as st
from components.stage_message import render_assistant_message
from labels import action_source_zh, blocker_type_zh, severity_zh

# ─────────────────────────────────────────────────────────────────────────────
# 实时人工监督占位标记（与 graph.nodes.live_oversight_marker 对应）
#
# 助手消息里不再写死「N 项待处理监督事项 / 阻断原因」，只留一个标记；渲染时用
# 当前实时的 pending_actions / stage_readiness 展开，保证对话区与左侧面板永远
# 一致，不再出现历史快照漂移。
# ─────────────────────────────────────────────────────────────────────────────

LIVE_OVERSIGHT_RE = re.compile(r"\[\[LIVE_OVERSIGHT(?:\s+stage=(\d+))?\]\]")


def _pending_actions_for_stage(stage_id: int | None) -> list[dict]:
    actions = [
        a
        for a in (st.session_state.get("pending_actions") or [])
        if a.get("status", "pending") == "pending"
    ]
    if stage_id is not None:
        actions = [a for a in actions if a.get("stage_id") == stage_id]
    return actions


def _blockers_for_stage(stage_id: int | None) -> list[dict]:
    if stage_id is None:
        return []
    readiness = st.session_state.get("stage_readiness") or {}
    stage_readiness = readiness.get(f"stage_{stage_id}", {}) or {}
    return stage_readiness.get("blockers", []) or []


def render_live_oversight(stage_id: int | None) -> None:
    """按来源实时汇总某阶段的待处理人工动作与阻断器（占位标记的展开体）。"""
    actions = _pending_actions_for_stage(stage_id)
    blockers = _blockers_for_stage(stage_id)

    if not actions and not blockers:
        st.success("✅ 没有待处理的人工监督事项。")
        return

    if actions:
        grouped: dict[str, dict] = {}
        for action in actions:
            key = action.get("source_type") or "human_action"
            entry = grouped.setdefault(key, {"count": 0, "risks": set(), "blocking": False})
            entry["count"] += 1
            entry["risks"].add(action.get("risk_level", "medium"))
            entry["blocking"] = entry["blocking"] or action.get("blocking", True)

        st.warning(f"🚦 有 {len(actions)} 项待处理的人工监督事项：")
        for source_type, info in grouped.items():
            label = action_source_zh(source_type)
            risks = "、".join(severity_zh(r) for r in sorted(info["risks"], key=str))
            count_note = f"（{info['count']} 项）" if info["count"] > 1 else ""
            blocking_note = "" if info["blocking"] else "（不阻断推进）"
            st.markdown(f"- {label}{count_note}{blocking_note}，风险等级：{risks}")

    if blockers:
        st.markdown(f"**当前阶段推进阻断（{len(blockers)} 项）：**")
        for blocker in blockers[:8]:
            st.markdown(
                f"- [{severity_zh(blocker.get('severity'))} · "
                f"{blocker_type_zh(blocker.get('blocker_type'))}] "
                f"{blocker.get('message', '')}"
            )

    st.caption(
        "存在阻断型事项时，输入「确认」暂时无法进入下一阶段；"
        "请先在左侧「待处理人工动作」面板中处理，或输入「修改」/「回退」调整当前阶段。"
    )


def render_message_with_oversight(content: str) -> None:
    """渲染助手消息；若含实时监督标记，则在原位展开为实时监督摘要。"""
    match = LIVE_OVERSIGHT_RE.search(content or "")
    if not match:
        render_assistant_message(content)
        return

    stage_id = int(match.group(1)) if match.group(1) else None
    before = content[: match.start()].rstrip()
    after = content[match.end() :].strip()

    if before:
        render_assistant_message(before)
    render_live_oversight(stage_id)
    if after:
        render_assistant_message(after)
