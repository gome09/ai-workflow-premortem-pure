"""frontend MVC 分层导入与入口装配顺序契约。"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
APP_PATH = FRONTEND_DIR / "app.py"

MODULES = [
    "models.config",
    "models.auth",
    "models.stage_envelope",
    "models.mappings",
    "models.api_client",
    "models.session_state",
    "controllers.auth_controller",
    "controllers.session_controller",
    "controllers.stage_controller",
    "controllers.governance_controller",
    "controllers.eval_controller",
    "controllers.report_controller",
    "views.pages",
]


def _import_frontend_module(name: str):
    if str(FRONTEND_DIR) not in sys.path:
        sys.path.insert(0, str(FRONTEND_DIR))
    return importlib.import_module(name)


def test_mvc_modules_import_cleanly():
    for name in MODULES:
        assert _import_frontend_module(name) is not None


def test_app_entry_calls_in_order():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    calls = []
    for node in tree.body:
        call = None
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
        if call is None:
            continue
        func = call.func
        if isinstance(func, ast.Attribute):
            calls.append(func.attr)
        elif isinstance(func, ast.Name):
            calls.append(func.id)
    assert calls == [
        "set_page_config",
        "ensure_auth",
        "init_session_state",
        "navigation",
        "run",
    ]
