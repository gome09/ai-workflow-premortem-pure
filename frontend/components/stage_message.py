# frontend/components/stage_message.py
from __future__ import annotations

import json
import re

import streamlit as st

SEVERITY_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}


def _extract_json_object(text: str) -> dict | None:
    """Best-effort extraction of a single top-level JSON object from *text*.

    Mirrors stages/validators.py::extract_json_object without importing the
    backend package from the frontend process.
    """
    text = (text or "").strip()
    if not text:
        return None

    candidates: list[str] = []
    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]+?)```", text, flags=re.IGNORECASE)
    candidates.extend(block.strip() for block in fenced_blocks)
    candidates.append(text)

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                loaded = json.loads(candidate[start : end + 1])
                if isinstance(loaded, dict):
                    return loaded
            except json.JSONDecodeError:
                continue
    return None


def _raw_json_expander(payload: dict) -> None:
    with st.expander("查看原始 JSON", expanded=False):
        st.json(payload)


def _render_failure_modes(payload: dict) -> None:
    failure_modes = payload.get("failure_modes") or []
    st.markdown(f"**识别到 {len(failure_modes)} 个失败模式**")
    for fm in failure_modes:
        severity = str(fm.get("severity", "low")).lower()
        icon = SEVERITY_ICON.get(severity, "⚪")
        title = f"{icon} {fm.get('category', '未分类')} · {severity.upper()}"
        with st.expander(title, expanded=severity in {"high", "critical"}):
            st.markdown(fm.get("description", ""))
            mitigation = fm.get("mitigation_hint")
            if mitigation:
                st.caption(f"缓解建议：{mitigation}")
            if fm.get("requires_human_review"):
                st.caption("⚠️ 需要人工复核")
            evidence = fm.get("evidence")
            if evidence:
                st.caption(f"依据：{evidence}")

    conclusion = payload.get("direct_conclusion")
    if conclusion:
        st.markdown(f"**结论：** {conclusion}")

    open_questions = payload.get("open_questions") or []
    if open_questions:
        with st.expander(f"待澄清问题（{len(open_questions)}）", expanded=False):
            for q in open_questions:
                st.markdown(f"- {q}")


def _render_workflow_nodes(payload: dict) -> None:
    nodes = payload.get("workflow_nodes") or []
    st.markdown(f"**设计了 {len(nodes)} 个工作流节点**")
    for node in nodes:
        risk = str(node.get("oversight_risk_level", "medium")).lower()
        icon = SEVERITY_ICON.get(risk, "⚪")
        title = f"{icon} {node.get('stage_name', node.get('node_id', '节点'))} · 风险 {risk}"
        with st.expander(title, expanded=risk in {"high", "critical"}):
            st.caption(f"分配模型/模式：{node.get('model_assigned', '')}")
            st.markdown(f"人工动作：{node.get('human_action', '')}")
            criteria = node.get("check_criteria") or []
            if criteria:
                st.markdown("检查标准：")
                for c in criteria:
                    st.markdown(f"- {c}")
            if node.get("human_review_required"):
                st.caption("⚠️ 需要人工复核")

    rationale = payload.get("design_rationale")
    if rationale:
        st.markdown(f"**设计理由：** {rationale}")

    open_questions = payload.get("open_questions") or []
    if open_questions:
        with st.expander(f"待澄清问题（{len(open_questions)}）", expanded=False):
            for q in open_questions:
                st.markdown(f"- {q}")


def _render_test_cases(payload: dict) -> None:
    cases = payload.get("test_cases") or []
    overall_passed = payload.get("overall_passed")
    badge = "✅ 整体通过" if overall_passed else "❌ 整体未通过"
    st.markdown(f"**压测完成，共 {len(cases)} 个用例 · {badge}**")
    for case in cases:
        passed = case.get("passed")
        icon = "✅" if passed else "❌"
        title = f"{icon} {case.get('scenario_type', 'normal')} · {case.get('case_id', '')}"
        with st.expander(title, expanded=not passed):
            st.markdown(f"测试输入：{case.get('test_input', '')}")
            st.caption(f"预期行为：{case.get('expected_behavior', '')}")
            predicted_failure = case.get("predicted_failure")
            if predicted_failure:
                st.caption(f"预测失败点：{predicted_failure}")
            correction_prompt = case.get("correction_prompt")
            if correction_prompt:
                st.caption(f"纠错建议：{correction_prompt}")

    risk_summary = payload.get("risk_summary")
    if risk_summary:
        st.markdown(f"**风险摘要：** {risk_summary}")


def _render_trigger_methods(payload: dict) -> None:
    methods = payload.get("trigger_methods") or []
    st.markdown(f"**生成了 {len(methods)} 条触发方式**")
    for method in methods:
        title = f"{method.get('node_id', '')} · {method.get('model_or_mode', '')}"
        with st.expander(title, expanded=bool(method.get("human_review_required"))):
            st.caption(f"入口：{method.get('entry_point', '')}")
            st.markdown(f"触发指令：{method.get('trigger_instruction', '')}")
            suggestion = method.get("execution_suggestion")
            if suggestion:
                st.caption(f"执行建议：{suggestion}")
            if method.get("human_review_required"):
                st.caption("⚠️ 需要人工复核")

    final_notes = payload.get("final_notes")
    if final_notes:
        st.markdown(f"**补充说明：** {final_notes}")


_RENDERERS = (
    ("failure_modes", _render_failure_modes),
    ("workflow_nodes", _render_workflow_nodes),
    ("test_cases", _render_test_cases),
    ("trigger_methods", _render_trigger_methods),
)


def render_assistant_message(content: str) -> None:
    """Render an assistant chat message, turning known stage-output JSON into
    a human-readable summary instead of dumping raw JSON text."""
    payload = _extract_json_object(content)
    if payload is None:
        st.markdown(content)
        return

    for key, renderer in _RENDERERS:
        if key in payload:
            renderer(payload)
            _raw_json_expander(payload)
            return

    # JSON-shaped but not a known stage schema — fall back to plain text.
    st.markdown(content)
