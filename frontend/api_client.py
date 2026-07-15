# frontend/api_client.py
from __future__ import annotations

import os

import requests


def _auth_headers() -> dict:
    token = os.environ.get("FRONTEND_SERVICE_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def api_get(base_url: str, path: str, **params):
    response = requests.get(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        params=params,
        headers=_auth_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def api_post(base_url: str, path: str, payload: dict | None = None):
    response = requests.post(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        json=payload or {},
        headers=_auth_headers(),
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def is_stage_operation_envelope(payload: object) -> bool:
    """Return True when a response contains the current StageOperationEnvelope fields."""
    return isinstance(payload, dict) and "stage_advancement_decision" in payload


def stage_operation_domain_result(payload: object) -> object:
    """Extract domain result while preserving raw envelopes for callers that need gate data."""
    if isinstance(payload, dict) and "result" in payload:
        return payload["result"]
    return payload


def stage_operation_items(payload: object) -> list[dict]:
    """Extract list domain results from envelope-capable endpoints."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return payload["items"]
        if isinstance(payload.get("result"), list):
            return payload["result"]
    return []


def get_stage_readiness(base_url: str, session_id: str) -> dict:
    return api_get(base_url, f"/sessions/{session_id}/stage-readiness")


def get_stage_resolution(base_url: str, session_id: str) -> dict:
    return api_get(base_url, f"/sessions/{session_id}/stage-resolution")


def get_stage_advancement_decision(base_url: str, session_id: str, stage_id: int) -> dict:
    return api_get(base_url, f"/sessions/{session_id}/stages/{stage_id}/advancement-decision")


def advance_stage_if_ready(
    base_url: str, session_id: str, stage_id: int, reason: str = "frontend_stage_advance"
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/stages/{stage_id}/advance",
            {"reason": reason, "source": "api_advance"},
        )
    except Exception:
        return None


def prepare_stage_operation(
    base_url: str, session_id: str, stage_id: int, operation: str, body: dict | None = None
) -> dict | None:
    try:
        return api_post(
            base_url, f"/sessions/{session_id}/stages/{stage_id}/{operation}", body or {}
        )
    except Exception:
        return None


def list_actions(base_url: str, session_id: str, status: str | None = "pending") -> list[dict]:
    try:
        path = f"/sessions/{session_id}/actions"
        if status:
            path += f"?status={status}"
        result = api_get(base_url, path)
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def get_action(base_url: str, session_id: str, action_id: str) -> dict | None:
    try:
        return api_get(base_url, f"/sessions/{session_id}/actions/{action_id}")
    except Exception:
        return None


def resolve_action(
    base_url: str,
    session_id: str,
    action_id: str,
    decision: str,
    note: str = "",
    payload_after: dict | None = None,
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/actions/{action_id}/resolve",
            {"decision": decision, "note": note, "payload_after": payload_after},
        )
    except Exception:
        return None


def list_interrupt_records(base_url: str, session_id: str) -> list[dict]:
    try:
        result = api_get(base_url, f"/sessions/{session_id}/interrupt-records")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def create_report_artifact(base_url: str, session_id: str) -> dict | None:
    try:
        return api_post(base_url, f"/sessions/{session_id}/reports", {})
    except Exception:
        return None


def list_report_artifacts(base_url: str, session_id: str) -> list[dict]:
    try:
        result = api_get(base_url, f"/sessions/{session_id}/reports")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def get_report_artifact(base_url: str, session_id: str, report_id: str) -> dict | None:
    try:
        return api_get(base_url, f"/sessions/{session_id}/reports/{report_id}")
    except Exception:
        return None


def export_report(base_url: str, session_id: str, format: str = "json") -> dict | None:
    try:
        return api_get(base_url, f"/sessions/{session_id}/export?format={format}")
    except Exception:
        return None


def list_evidence(base_url: str, session_id: str) -> list[dict]:
    try:
        result = api_get(base_url, f"/sessions/{session_id}/evidence")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def get_evidence(base_url: str, session_id: str, evidence_id: str) -> dict | None:
    try:
        return api_get(base_url, f"/sessions/{session_id}/evidence/{evidence_id}")
    except Exception:
        return None


def verify_evidence(
    base_url: str, session_id: str, evidence_id: str, note: str = ""
) -> dict | None:
    try:
        return api_post(
            base_url, f"/sessions/{session_id}/evidence/{evidence_id}/verify", {"note": note}
        )
    except Exception:
        return None


# ── Safety ────────────────────────────────────────────────────────────────────


def list_safety_findings(base_url: str, session_id: str, status: str | None = "open") -> list[dict]:
    try:
        path = f"/sessions/{session_id}/safety-findings"
        if status:
            path += f"?status={status}"
        result = api_get(base_url, path)
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def resolve_safety_finding(
    base_url: str, session_id: str, finding_id: str, status: str, note: str = ""
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/safety-findings/{finding_id}/resolve",
            {"status": status, "note": note},
        )
    except Exception:
        return None


# ── Eval ──────────────────────────────────────────────────────────────────────


def list_eval_cases(base_url: str, session_id: str) -> list[dict]:
    try:
        result = api_get(base_url, f"/sessions/{session_id}/eval-cases")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def list_eval_runs(base_url: str, session_id: str, eval_id: str | None = None) -> list[dict]:
    try:
        path = f"/sessions/{session_id}/eval-runs"
        if eval_id:
            path += f"?eval_id={eval_id}"
        result = api_get(base_url, path)
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def run_eval_cases(
    base_url: str, session_id: str, eval_ids: list[str] | None = None, run_mode: str = "manual"
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/eval-cases/run",
            {"eval_ids": eval_ids, "run_mode": run_mode},
        )
    except Exception:
        return None


def run_single_eval_case(
    base_url: str, session_id: str, eval_id: str, run_mode: str = "manual"
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/eval-cases/{eval_id}/run",
            {"eval_ids": [eval_id], "run_mode": run_mode},
        )
    except Exception:
        return None


def score_eval_case(
    base_url: str,
    session_id: str,
    eval_id: str,
    human_score: int | None,
    human_comment: str,
    passed: bool | None,
    actual_output: str | None = None,
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/eval-cases/{eval_id}/score",
            {
                "human_score": human_score,
                "human_comment": human_comment,
                "passed": passed,
                "actual_output": actual_output,
            },
        )
    except Exception:
        return None


# ── Audit ─────────────────────────────────────────────────────────────────────


def list_audit_events(base_url: str, session_id: str) -> list[dict]:
    try:
        result = api_get(base_url, f"/sessions/{session_id}/audit-events")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


# ── Traces ────────────────────────────────────────────────────────────────────


def list_traces(
    base_url: str,
    session_id: str,
    stage: int | None = None,
    trace_type: str | None = None,
    parser_status: str | None = None,
) -> list[dict]:
    try:
        params = []
        if stage is not None:
            params.append(f"stage={stage}")
        if trace_type:
            params.append(f"trace_type={trace_type}")
        if parser_status:
            params.append(f"parser_status={parser_status}")
        query = ("?" + "&".join(params)) if params else ""
        result = api_get(base_url, f"/sessions/{session_id}/traces{query}")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def list_eval_datasets(base_url: str, session_id: str) -> list[dict]:
    result = api_get(base_url, f"/sessions/{session_id}/eval-datasets")
    return result if isinstance(result, list) else []


def create_eval_dataset_from_stage3(
    base_url: str,
    session_id: str,
    name: str = "Stage 3 generated dataset",
    description: str = "",
) -> dict:
    return api_post(
        base_url,
        f"/sessions/{session_id}/eval-datasets/from-stage3",
        {"name": name, "description": description, "version": "0.1", "owner": "system"},
    )


def list_eval_experiments(base_url: str, session_id: str) -> list[dict]:
    result = api_get(base_url, f"/sessions/{session_id}/eval-experiments")
    return result if isinstance(result, list) else []


def create_eval_experiment(
    base_url: str,
    session_id: str,
    dataset_id: str,
    name: str,
    run_mode: str = "dry_run",
    baseline_experiment_id: str | None = None,
) -> dict:
    return api_post(
        base_url,
        f"/sessions/{session_id}/eval-experiments",
        {
            "dataset_id": dataset_id,
            "name": name,
            "run_mode": run_mode,
            "baseline_experiment_id": baseline_experiment_id,
            "run_config": {"runtime_validation": "deferred_by_instruction"},
        },
    )


def run_eval_experiment(
    base_url: str,
    session_id: str,
    experiment_id: str,
    dry_run_only: bool = True,
) -> dict:
    return api_post(
        base_url,
        f"/sessions/{session_id}/eval-experiments/{experiment_id}/run",
        {"dry_run_only": dry_run_only},
    )


def compare_eval_experiment(
    base_url: str,
    session_id: str,
    experiment_id: str,
    baseline_experiment_id: str | None = None,
) -> dict:
    return api_post(
        base_url,
        f"/sessions/{session_id}/eval-experiments/{experiment_id}/comparison",
        {"baseline_experiment_id": baseline_experiment_id},
    )


# ── Eval Judgment / Calibration ──────────────────────────────────────────────


def list_eval_judgments(base_url: str, session_id: str) -> list[dict]:
    try:
        result = api_get(base_url, f"/sessions/{session_id}/eval-judgments")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def list_human_calibrations(base_url: str, session_id: str) -> list[dict]:
    try:
        result = api_get(base_url, f"/sessions/{session_id}/human-calibrations")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def calibrate_eval_run(
    base_url: str,
    session_id: str,
    run_id: str,
    human_label: str,
    human_comment: str = "",
    reviewer_id: str = "human_reviewer",
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/eval-runs/{run_id}/calibrate",
            {
                "human_label": human_label,
                "human_comment": human_comment,
                "reviewer_id": reviewer_id,
            },
        )
    except Exception:
        return None


def trace_to_eval_case(
    base_url: str,
    session_id: str,
    trace_id: str,
    expected_behavior: str | None = None,
    target_node_id: str | None = None,
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/traces/{trace_id}/to-eval-case",
            {"expected_behavior": expected_behavior, "target_node_id": target_node_id},
        )
    except Exception:
        return None


def traces_to_eval_dataset(
    base_url: str,
    session_id: str,
    trace_ids: list[str] | None = None,
    name: str = "Trace backfill regression dataset",
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/traces/to-eval-dataset",
            {"trace_ids": trace_ids, "name": name},
        )
    except Exception:
        return None


def create_redteam_dataset(
    base_url: str,
    session_id: str,
    name: str = "Red Team generated dataset",
) -> dict | None:
    try:
        return api_post(
            base_url,
            f"/sessions/{session_id}/redteam/datasets",
            {"name": name},
        )
    except Exception:
        return None
