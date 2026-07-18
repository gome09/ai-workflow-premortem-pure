"""文档-代码一致性检查。

检查规则（spec §7）：
1. 链接存在性：扫描 Markdown 相对路径链接，校验目标文件存在（外部 URL 跳过）
2. make target 存在性：扫描文档中 `make <target>` 引用，校验 target 在 Makefile 中定义
3. 仓库路径存在性：扫描反引号包裹的路径（启发式：含 / 且以已知顶层目录开头），校验存在

设计约束（计划 §5）：
- 启发式规则宁松勿严，误报率高于约 5% 就收窄规则
- 版本一致性由 make version-check 覆盖，不重复
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 扫描范围：README.md、CLAUDE.md、docs/**/*.md
SCAN_GLOBS = ["README.md", "CLAUDE.md", "docs/**/*.md"]

# 已知顶层目录（用于仓库路径启发式识别）
TOP_LEVEL_DIRS = {
    "api",
    "auth",
    "core",
    "docs",
    "examples",
    "frontend",
    "graph",
    "monitoring",
    "nginx",
    "scenarios",
    "scripts",
    "secrets.example",
    "stages",
    "storage",
    "tests",
    "tools",
    ".github",
    ".upgrade",
}

# Markdown 相对路径链接正则：[text](path)  排除外部 URL / 锚点 / 邮箱
LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)")

# make target 引用正则：`make <target>` 或行首 "make <target>"
MAKE_RE = re.compile(r"`?make\s+(?P<target>[a-z][a-z0-9-]*)`?")

# 反引号包裹的仓库路径正则：`path/to/something`
BACKTICK_PATH_RE = re.compile(r"`(?P<path>[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._*-]+)+)`")


def collect_make_targets() -> set[str]:
    """解析 Makefile，返回所有 target 名。"""
    targets: set[str] = set()
    makefile = REPO_ROOT / "Makefile"
    if not makefile.exists():
        return targets
    for line in makefile.read_text(encoding="utf-8").splitlines():
        # target 行格式：name: prerequisites （行首无 tab）
        m = re.match(r"^([a-zA-Z0-9._-]+)\s*:", line)
        if m:
            targets.add(m.group(1))
    return targets


def resolve_link_path(link: str, source_file: Path) -> Path | None:
    """将 Markdown 相对路径解析为绝对路径。剥离锚点 (#section) 与查询 (?query)。"""
    # 剥离锚点与查询
    clean = link.split("#")[0].split("?")[0]
    if not clean:
        return None  # 纯锚点，跳过
    if clean.startswith(("http://", "https://", "mailto:", "ftp://", "file://")):
        return None  # 外部 URL / 本地 file:// 链接，跳过
    if clean.startswith("/"):
        return REPO_ROOT / clean.lstrip("/")
    return (source_file.parent / clean).resolve()


def is_repo_path(path_str: str) -> bool:
    """启发式判断反引号内容是否为仓库内路径。"""
    first_segment = path_str.split("/")[0]
    return first_segment in TOP_LEVEL_DIRS


def check_file(source: Path, make_targets: set[str]) -> list[str]:
    """对单个 Markdown 文件执行三类检查，返回违规清单。"""
    violations: list[str] = []
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return violations

    in_fence = False
    fence_marker = ""
    for lineno, line in enumerate(lines, start=1):
        rel = source.relative_to(REPO_ROOT).as_posix()

        # 围栏代码块（``` 或 ~~~）内为示例代码/嵌入的文档草稿，不做链接/路径校验，
        # 否则示例内容会大量误报（设计约束：误报率高于约 5% 就收窄规则）。
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif stripped.startswith(fence_marker):
                in_fence, fence_marker = False, ""
            continue  # 围栏标记行本身不检查
        if in_fence:
            continue

        # 规则 1：链接存在性
        for m in LINK_RE.finditer(line):
            url = m.group("url")
            target = resolve_link_path(url, source)
            if target is None:
                continue
            if not target.exists():
                violations.append(
                    f"{rel}:{lineno} 坏链 [{m.group('text')}]({url}) -> {target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target}"
                )

        # 规则 2：make target 存在性（仅扫描反引号或代码块内的 make 引用）
        for m in MAKE_RE.finditer(line):
            target = m.group("target")
            if target not in make_targets:
                violations.append(f"{rel}:{lineno} 未知 make target: make {target}")

        # 规则 3：反引号仓库路径存在性
        for m in BACKTICK_PATH_RE.finditer(line):
            path_str = m.group("path")
            if not is_repo_path(path_str):
                continue
            # 通配符路径跳过（如 docs/**/*.md）
            if "*" in path_str:
                continue
            # 省略号占位路径跳过（如 tests/...、alembic/versions/V005_..）。
            # Windows 会忽略路径结尾的点号使 exists() 误判为 True，Linux 则报
            # 不存在——统一按占位符处理，两端行为一致。
            if path_str.rstrip().endswith(".."):
                continue
            target = REPO_ROOT / path_str
            if not target.exists():
                violations.append(f"{rel}:{lineno} 反引号路径不存在: `{path_str}`")

    return violations


def main() -> int:
    make_targets = collect_make_targets()
    if not make_targets:
        print("WARNING: Makefile 未找到或无 target，规则 2 跳过", file=sys.stderr)

    all_violations: list[str] = []
    files_scanned = 0
    for pattern in SCAN_GLOBS:
        for source in REPO_ROOT.glob(pattern):
            if source.is_file():
                files_scanned += 1
                all_violations.extend(check_file(source, make_targets))

    print(f"扫描 {files_scanned} 个 Markdown 文件，发现 {len(all_violations)} 处违规")
    if all_violations:
        print("\n".join(all_violations))
        return 1
    print("OK: 文档-代码一致性检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
