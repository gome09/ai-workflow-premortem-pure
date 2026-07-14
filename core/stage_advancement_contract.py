# core/stage_advancement_contract.py
"""Shared Stage Advancement Contract.

This module is intentionally declarative. It documents the blocker/action/
resolution contract used by stage_readiness_service, stage_resolution_service,
graph.nodes, reports, and the review workbench. It does not execute workflow
logic and must remain safe to import without external services.
"""

from __future__ import annotations

from typing import Final

STAGE_LIFECYCLES: Final[tuple[str, ...]] = (
    "not_started",
    "running",
    "review",
    "blocked",
    "ready_to_advance",
    "approved",
    "stale",
)

BLOCKER_TYPES: Final[tuple[str, ...]] = (
    "missing_stage_output",
    "stale_dependency",
    "pending_action",
    "rejected_action",
    "unresolved_escalation",
    "parser_error",
    "safety_finding",
    "evidence_gap",
    "policy_gap",
    "eval_failure",
    "redteam_coverage",
    "eval_regression",
    "trace_backfill_gap",
    "final_governance",
    "expert_review",
)

REQUIRED_RESOLUTIONS: Final[tuple[str, ...]] = (
    "run_stage",
    "rerun_stage",
    "resolve_action",
    "verify_evidence",
    "edit_stage_output",
    "revise_stage",
    "back_stage",
    "approve_escalation",
    "resolve_safety_finding",
    "create_eval_dataset_from_stage3",
    "add_eval_cases_to_dataset",
    "set_eval_baseline",
    "create_eval_experiment",
    "run_eval_experiment",
    "compare_eval_experiment",
    "generate_redteam_cases",
    "approve_redteam_case",
    "sync_redteam_eval_case",
    "create_redteam_dataset",
    "trace_to_eval_case",
    "create_trace_backfill_dataset",
    "approve_expert_review",
)

# Source of truth for blocker -> expected resolution semantics.
STAGE_ADVANCEMENT_CONTRACT: Final[dict[str, dict[str, object]]] = {
    "missing_stage_output": {
        "required_resolution": "run_stage",
        "description": "当前阶段还没有生成结构化结果。",
        "approval_override_allowed": False,
    },
    "stale_dependency": {
        "required_resolution": "rerun_stage",
        "description": "当前阶段结果依赖的上游版本已更新，需要重新生成。",
        "approval_override_allowed": False,
    },
    "pending_action": {
        "required_resolution": "resolve_action",
        "description": "当前阶段版本仍有阻断型人工动作尚未处理。",
        "approval_override_allowed": False,
    },
    "rejected_action": {
        "required_resolution": "revise_stage",
        "description": "有关键动作被驳回，需要修订当前阶段或回退。",
        "approval_override_allowed": False,
    },
    "unresolved_escalation": {
        "required_resolution": "approve_escalation",
        "description": "存在需要明确批准后才能推进的升级项。",
        "approval_override_allowed": False,
    },
    "parser_error": {
        "required_resolution": "edit_stage_output",
        "description": "结构化输出解析失败，需要通过编辑 / 修订更正。",
        "approval_override_allowed": False,
    },
    "safety_finding": {
        "required_resolution": "resolve_safety_finding",
        "description": "高危 / 危急安全发现必须处理或经明确批准。",
        "approval_override_allowed": True,
    },
    "evidence_gap": {
        "required_resolution": "verify_evidence",
        "description": "高风险失败模式需要有效的证据引用并核验证据来源；缺失 / 未知的证据需通过结构化编辑补充，已存在但未核验的证据需先核验。",
        "approval_override_allowed": False,
    },
    "policy_gap": {
        "required_resolution": "edit_stage_output",
        "description": "高风险工作流覆盖或人工审核策略存在缺口，需编辑 / 修订。",
        "approval_override_allowed": False,
    },
    "eval_failure": {
        "required_resolution": "resolve_action",
        "description": "失败的高风险评测必须先批准、编辑或重跑，才能推进。",
        "approval_override_allowed": True,
    },
    "redteam_coverage": {
        "required_resolution": "generate_redteam_cases",
        "description": "高危 / 危急风险在阶段三推进前，需要已批准的红队用例覆盖、已同步的评测用例记录，以及一个红队生成的评测数据集。",
        "approval_override_allowed": False,
    },
    "eval_regression": {
        "required_resolution": "create_eval_experiment",
        "description": "与门控相关的评测数据集在阶段三推进前，需要有用例、基线、一次已完成的当前评测实验，以及一次无回归的对比。具体解除操作由评测回归策略按阻断状态细化。",
        "approval_override_allowed": False,
    },
    "trace_backfill_gap": {
        "required_resolution": "trace_to_eval_case",
        "description": "失败 / 解析错误 / 安全类追踪记录必须回填为评测用例，并归入生产追踪评测数据集后，阶段三才能推进。",
        "approval_override_allowed": False,
    },
    "final_governance": {
        "required_resolution": "resolve_safety_finding",
        "description": "最终报告的完成被尚未闭环的治理事项阻断。",
        "approval_override_allowed": True,
    },
    "expert_review": {
        "required_resolution": "approve_expert_review",
        "description": "CRITICAL 风险项目必须经专家复核批准后才能通过 Stage 3。",
        "approval_override_allowed": True,
    },
}

# Every stage blocker maps to an explicit user-facing operation instead of only a raw enum.
RESOLUTION_OPERATION_CONTRACT: Final[dict[str, dict[str, object]]] = {
    "run_stage": {
        "frontend_hint": "运行当前阶段以生成结构化结果。",
        "api_hint": "Send user input through POST /chat/{session_id}.",
        "can_execute_via_api": False,
        "api_method": None,
        "api_path_template": None,
        "payload_hint": {},
    },
    "rerun_stage": {
        "frontend_hint": "先将这个已过期的阶段准备为重跑状态，再通过对话发送修订后的输入以重新生成。",
        "api_hint": "POST /sessions/{session_id}/stages/{stage_id}/rerun",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/stages/{stage_id}/rerun",
        "payload_hint": {"reason": "", "note": ""},
    },
    "resolve_action": {
        "frontend_hint": "请先处理关联的待处理人工动作，再推进阶段。",
        "api_hint": "POST /sessions/{session_id}/actions/{action_id}/resolve",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/actions/{action_id}/resolve",
        "payload_hint": {
            "decision": "approve | edit | reject | verify_evidence | dismissed",
            "note": "",
            "payload_after": {},
        },
    },
    "verify_evidence": {
        "frontend_hint": "请核验证据来源本身；仅关闭（dismiss）人工动作不会解除证据门控。",
        "api_hint": "POST /sessions/{session_id}/evidence/{evidence_id}/verify when the blocker source is an evidence id.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/evidence/{evidence_id}/verify",
        "payload_hint": {"note": ""},
    },
    "edit_stage_output": {
        "frontend_hint": "编辑结构化阶段输出，或请求修订当前阶段。",
        "api_hint": "Prefer POST /sessions/{session_id}/actions/{action_id}/resolve with decision=edit and payload_after.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/actions/{action_id}/resolve",
        "payload_hint": {
            "decision": "edit",
            "note": "",
            "payload_after": {"structured_output": {}, "edited_text": "optional explanation"},
        },
    },
    "revise_stage": {
        "frontend_hint": "将当前阶段准备为修订状态；重新生成仍通过确定性的对话执行器完成。",
        "api_hint": "POST /sessions/{session_id}/stages/{stage_id}/revise",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/stages/{stage_id}/revise",
        "payload_hint": {"reason": "", "note": ""},
    },
    "back_stage": {
        "frontend_hint": "回退到更早的阶段，并作废过期动作，不触发运行时执行。",
        "api_hint": "POST /sessions/{session_id}/stages/{stage_id}/rollback",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/stages/{stage_id}/rollback",
        "payload_hint": {"to_stage": 0, "reason": "", "note": "", "target_running": False},
    },
    "approve_escalation": {
        "frontend_hint": "升级项需要由负责的审核人明确批准。",
        "api_hint": "POST /sessions/{session_id}/actions/{action_id}/resolve with decision=approve.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/actions/{action_id}/resolve",
        "payload_hint": {"decision": "approve", "note": "负责人已明确批准"},
    },
    "resolve_safety_finding": {
        "frontend_hint": "处理或关闭关联的安全发现，并保留审计记录。",
        "api_hint": "POST /sessions/{session_id}/safety-findings/{finding_id}/resolve when the blocker source is a safety finding.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/safety-findings/{finding_id}/resolve",
        "payload_hint": {"status": "resolved | dismissed", "note": ""},
    },
    "create_eval_dataset_from_stage3": {
        "frontend_hint": "从阶段三生成的评测用例记录中，创建一个与门控相关的评测数据集。",
        "api_hint": "POST /sessions/{session_id}/eval-datasets/from-stage3",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-datasets/from-stage3",
        "payload_hint": {
            "name": "Stage 3 generated dataset",
            "description": "",
            "version": "0.1",
            "owner": "system",
        },
    },
    "add_eval_cases_to_dataset": {
        "frontend_hint": "在运行回归检查前，先把已有的评测用例加入关联的评测数据集。",
        "api_hint": "POST /sessions/{session_id}/eval-datasets/{dataset_id}/cases",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-datasets/{dataset_id}/cases",
        "payload_hint": {"eval_ids": []},
    },
    "set_eval_baseline": {
        "frontend_hint": "在对比当前运行前，先为关联的评测数据集设定基线实验。",
        "api_hint": "POST /sessions/{session_id}/eval-datasets/{dataset_id}/baseline",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-datasets/{dataset_id}/baseline",
        "payload_hint": {"baseline_experiment_id": ""},
    },
    "create_eval_experiment": {
        "frontend_hint": "为关联的评测数据集创建一个当前评测实验，然后运行它。",
        "api_hint": "POST /sessions/{session_id}/eval-experiments",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-experiments",
        "payload_hint": {
            "dataset_id": "{source_id}",
            "name": "Current regression experiment",
            "run_mode": "dry_run",
            "run_config": {"runtime_validation": "deferred_by_instruction"},
        },
    },
    "run_eval_experiment": {
        "frontend_hint": "推进前先运行关联的评测实验。如果阻断项只指向某个数据集，请先为该数据集创建一个当前实验。",
        "api_hint": "POST /sessions/{session_id}/eval-experiments/{experiment_id}/run when the blocker source is an EvalExperiment.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-experiments/{experiment_id}/run",
        "payload_hint": {"dry_run_only": True},
    },
    "compare_eval_experiment": {
        "frontend_hint": "推进前，将当前评测实验与其基线进行对比。",
        "api_hint": "POST /sessions/{session_id}/eval-experiments/{experiment_id}/comparison",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/eval-experiments/{experiment_id}/comparison",
        "payload_hint": {"baseline_experiment_id": "optional"},
    },
    "generate_redteam_cases": {
        "frontend_hint": "基于当前高风险安全发现、失败模式和工作流节点信号，确定性地生成红队用例草稿。",
        "api_hint": "POST /sessions/{session_id}/redteam/generate",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/redteam/generate",
        "payload_hint": {"stage": 3},
    },
    "approve_redteam_case": {
        "frontend_hint": "先批准关联的红队用例，之后才能同步为评测用例。",
        "api_hint": "POST /sessions/{session_id}/redteam/cases/{case_id}/approve",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/redteam/cases/{case_id}/approve",
        "payload_hint": {"note": "reviewer approved redteam coverage"},
    },
    "sync_redteam_eval_case": {
        "frontend_hint": "将已批准的红队用例同步为一条对抗性评测用例。",
        "api_hint": "POST /sessions/{session_id}/redteam/cases/{case_id}/to-eval-case",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/redteam/cases/{case_id}/to-eval-case",
        "payload_hint": {},
    },
    "create_redteam_dataset": {
        "frontend_hint": "从已同步的红队评测用例中，创建一个红队生成的评测数据集，供回归门控使用。",
        "api_hint": "POST /sessions/{session_id}/redteam/datasets",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/redteam/datasets",
        "payload_hint": {"name": "Red Team generated dataset", "version": "0.1"},
    },
    "trace_to_eval_case": {
        "frontend_hint": "推进前，把关联的失败 / 解析错误 / 安全类追踪记录转换为一条生产回归评测用例。",
        "api_hint": "POST /sessions/{session_id}/traces/{trace_id}/to-eval-case",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/traces/{trace_id}/to-eval-case",
        "payload_hint": {"expected_behavior": "optional", "target_node_id": "optional"},
    },
    "create_trace_backfill_dataset": {
        "frontend_hint": "从追踪回填的评测用例中，创建一个生产追踪评测数据集，供回归门控使用。",
        "api_hint": "POST /sessions/{session_id}/traces/to-eval-dataset",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/traces/to-eval-dataset",
        "payload_hint": {"name": "Trace backfill regression dataset", "version": "0.1"},
    },
    "approve_expert_review": {
        "frontend_hint": "CRITICAL 风险项目须由专家复核批准后才能推进。",
        "api_hint": "POST /sessions/{session_id}/actions/{action_id}/resolve with decision=approve.",
        "can_execute_via_api": True,
        "api_method": "POST",
        "api_path_template": "/sessions/{session_id}/actions/{action_id}/resolve",
        "payload_hint": {"decision": "approve", "note": "专家复核已批准"},
    },
}


def required_resolution_for(blocker_type: str) -> str:
    item = STAGE_ADVANCEMENT_CONTRACT.get(blocker_type)
    if not item:
        return "resolve_action"
    return str(item["required_resolution"])


def operation_contract_for(required_resolution: str) -> dict[str, object]:
    """Return the user-facing operation metadata for a required resolution."""
    return dict(
        RESOLUTION_OPERATION_CONTRACT.get(
            required_resolution, RESOLUTION_OPERATION_CONTRACT["resolve_action"]
        )
    )


def contract_summary() -> dict[str, object]:
    """Machine-readable contract snapshot for docs, reports, and API diagnostics."""
    return {
        "stage_lifecycles": STAGE_LIFECYCLES,
        "blocker_types": BLOCKER_TYPES,
        "required_resolutions": REQUIRED_RESOLUTIONS,
        "stage_advancement_contract": STAGE_ADVANCEMENT_CONTRACT,
        "resolution_operation_contract": RESOLUTION_OPERATION_CONTRACT,
    }
