# tests/test_frontend_release_wiring.py
"""Static contract: the Streamlit workbench exposes the full release workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"


def _read(path: str) -> str:
    return (FRONTEND / path).read_text(encoding="utf-8")


def test_api_client_wires_target_deployment_calibration_and_invitations():
    source = _read("models/api_client.py")
    assert "/target-deployment" in source
    assert "/human-calibrations" in source
    assert "/eval-runs/{run_id}/calibrate" in source
    assert "/auth/invitations" in source
    assert "/auth/invitations/accept" in source


def test_closure_panel_exposes_target_deployment_and_approval_binding():
    source = _read("views/panels/closure_panel.py")
    assert "handle_set_target_deployment" in source
    assert "target_deployment_version" in source
    assert "保存目标部署" in source
    assert "批准绑定目标版本" in source


def test_eval_panel_supports_real_experiment_run_and_calibration():
    source = _read("views/panels/eval_panels.py")
    assert "dry_run_only=not real_run" in source
    assert "真实执行" in source
    assert "handle_calibrate_eval_run" in source
    assert "保存人工校准" in source


def test_sidebar_and_login_wire_invitation_flow():
    sidebar = _read("views/sidebar.py")
    assert "_render_team_invitations" in sidebar
    assert "create_invitation" in sidebar
    assert "list_invitations" in sidebar

    auth = _read("controllers/auth_controller.py")
    assert "accept_invitation" in auth
    assert "使用邀请码加入工作区" in auth
