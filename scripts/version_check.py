"""Check project version metadata consistency.

Compares core/version.py, pyproject.toml and the editable root package in uv.lock.
Stdlib only, so CI can run it with a bare Python interpreter before `uv sync` or
any `uv run` (which may refresh uv.lock and hide drift).

Usage:
    python scripts/version_check.py
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def find(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"Missing version marker: {label}")
    return match.group(1)


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


VERSION_PATTERN = r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*)?"

core_app_version = find(
    r'APP_VERSION\s*=\s*["\'](' + VERSION_PATTERN + r')["\']',
    read("core/version.py"),
    "core/version.py APP_VERSION",
)
core_report_version = find(
    r'REPORT_SCHEMA_VERSION\s*=\s*["\'](' + VERSION_PATTERN + r')["\']',
    read("core/version.py"),
    "core/version.py REPORT_SCHEMA_VERSION",
)

pyproject = tomllib.loads(read("pyproject.toml"))
project = pyproject.get("project", {})
project_name = str(project.get("name", ""))
pyproject_version = str(project.get("version", ""))
if not project_name or not re.fullmatch(VERSION_PATTERN, pyproject_version):
    raise SystemExit("Missing version marker: pyproject.toml [project] name/version")

lock = tomllib.loads(read("uv.lock"))
root_packages = [
    package
    for package in lock.get("package", [])
    if isinstance(package.get("source"), dict) and package["source"].get("editable") == "."
]
if len(root_packages) != 1:
    raise SystemExit(
        f"uv.lock editable root package entries: expected 1, found {len(root_packages)}"
    )
lock_root_name = str(root_packages[0].get("name", ""))
lock_root_version = str(root_packages[0].get("version", ""))
if normalize_name(lock_root_name) != normalize_name(project_name):
    raise SystemExit(f"uv.lock root package name mismatch: {lock_root_name!r} != {project_name!r}")

versions = {
    "core/version.py APP_VERSION": core_app_version,
    "core/version.py REPORT_SCHEMA_VERSION": core_report_version,
    "pyproject.toml": pyproject_version,
    "uv.lock (editable root)": lock_root_version,
}

if len(set(versions.values())) != 1:
    for path, version in versions.items():
        print(f"{path}: {version}")
    raise SystemExit("Version metadata mismatch.")

print(f"Version metadata OK: {core_app_version}")
