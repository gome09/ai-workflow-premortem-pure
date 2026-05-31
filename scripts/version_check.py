"""Check project version metadata consistency.

Usage:
    python scripts/version_check.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def find(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"Missing version marker: {label}")
    return match.group(1)


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
pyproject_version = find(
    r'^version\s*=\s*"(' + VERSION_PATTERN + r')"',
    read("pyproject.toml"),
    "pyproject.toml version",
)
manifest_text = read("PACKAGE_MANIFEST.txt")
manifest_version = find(
    r"^(?:-\s*)?(?:Version|Source version):\s*`?v?(" + VERSION_PATTERN + r")`?",
    manifest_text,
    "PACKAGE_MANIFEST.txt Version or Source version",
)
readme_status = find(
    r"Status:\s*v(" + VERSION_PATTERN + r")\b",
    read("README.md"),
    "README.md Status",
)

versions = {
    "core/version.py APP_VERSION": core_app_version,
    "core/version.py REPORT_SCHEMA_VERSION": core_report_version,
    "pyproject.toml": pyproject_version,
    "PACKAGE_MANIFEST.txt": manifest_version,
    "README.md Status": readme_status,
}

if len(set(versions.values())) != 1:
    for path, version in versions.items():
        print(f"{path}: {version}")
    raise SystemExit("Version metadata mismatch.")

print(f"Version metadata OK: {core_app_version}")
