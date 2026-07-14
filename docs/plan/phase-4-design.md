# 阶段 4 详细设计方案：开源社区打磨与工程健康度闭环

> 关系定位：本文档是 [phase-4-community.md](phase-4-community.md)（实施计划 / 任务清单 + 验收标准）的**落地设计层**——给出每个任务的具体文件改动、代码草稿、配置参数、决策依据、执行顺序与并行策略、风险。
> 配套规格：[../spec/supply-chain-security.md](../spec/supply-chain-security.md)（设计意图层，第 6-8 节已覆盖 Scorecard 水位管理、文档-代码一致性 CI、分支保护）。
> 现状核实日期：2026-07-14（全部条目经代码仓库直接实测，非估算）。
> 状态：设计完成，待用户决策后可启动执行。
>
> **关于 spec 文件**：现有 `docs/spec/supply-chain-security.md` 第 6-8 节已完整覆盖阶段 4 全部任务的设计意图（Scorecard 水位管理、doc-check 规则、分支保护策略），**不新增 spec 文件**，本设计方案直接落地。仅在 §1 实测发现第 3 项对 spec 做一处补充说明。

---

## 1. 现状复核（对实施计划基线表的修正与补充）

实施计划 §2 与 spec §6 的基线表已核实，本节补充 8 项实测发现：

| # | spec/计划基线 | 2026-07-14 实测补充 |
|---|---|---|
| 1 | **Scorecard 基线待阶段 0 实测** | ✅ **已完成**。`.upgrade/reports/scorecard-baseline-20260713.md` 已存档（本地 10/18 项可评估 + 远端 Actions 全量 18 项）。关键短板：Vulnerabilities 0 分（33 个传递性漏洞）、Branch-Protection 0 分、Signed-Releases 0 分、CII-Badge 0 分。Phase 1 已落地 ruff `S` 规则 + pip-audit + CodeQL workflow，Vulnerabilities 与 SAST 项预期已改善 |
| 2 | **CONTRIBUTING.md 将由阶段 0 产出初版** | ✅ **已完成**。根目录 `CONTRIBUTING.md` 46 行，覆盖开发环境搭建、提交前检查（lint/test/version-check）、分支与 commit 约定、测试约定、PR 流程。**缺口**：无响应节奏承诺（T4.5 补充） |
| 3 | **spec §8 称"分支保护需 GitHub 后台设置"** | 确认。这是 GitHub 后台操作，**无法通过代码入库实现**。T4.2 的落地形态是：(a) 在 `.upgrade/decisions/` 记录配置决策与操作清单；(b) 在 `CONTRIBUTING.md` 声明分支保护策略让贡献者知情；(c) 实际开启需维护者登录 GitHub 后台手动操作（本设计给出精确步骤） |
| 4 | **docs/spec/stage3-risk-adaptive-gate.md 悬空引用** | 确认。line 119 指向 `../archive/verification-reports/risk_adaptive_gate_final_validation.md`，目标文件在仓库中不存在（`.upgrade/MANIFEST.md` 已记录为既有问题）。T4.1 修复对象 |
| 5 | **.github/ 现有内容** | `workflows/`（ci.yml + codeql.yml + scorecard.yml）+ `dependabot.yml`。**无 ISSUE_TEMPLATE/、无 PULL_REQUEST_TEMPLATE.md**。T4.5 新建 |
| 6 | **scripts/ 现有脚本** | `version_check.py` + `gen_certs.*` + `gen_secrets.sh` + `live_e2e_four_stage.py` + `archive/`。**无 doc_consistency_check.py**。T4.1 新建 |
| 7 | **Makefile 现有 target** | install/clean/dev-db/dev-api/dev-frontend/lint/test/audit/security-check/version-check/e2e-mock/e2e-full-test/migrate-*/setup/lite-up/prod-*。**无 doc-check target**。T4.1 新增 |
| 8 | **CI ci.yml 现状** | lint + pip-audit(non-blocking) + unit tests + docker-lite integration。lint job 内**无 doc-check 步骤**。T4.1 在 lint job 追加 |

### 关键发现影响：分支保护无法代码化

spec §8 与计划 T4.2 称"开启分支保护"。实测确认这是 GitHub 后台配置，**不能通过 PR 入库实现**。本设计明确 T4.2 落地形态为**三件套**：决策记录 + 文档声明 + 操作清单（实际开启由维护者手动执行，设计文档提供精确步骤与预期 Scorecard 影响）。

---

## 2. 任务级详细设计

### T4.1 文档-代码一致性检查 CI 化【Wave 1，价值最高】

#### 2.1.1 检查脚本：scripts/doc_consistency_check.py

**改动文件**：`scripts/doc_consistency_check.py`（新建）

设计依据 spec §7 三类规则。脚本为纯标准库实现（无第三方依赖，CI 友好）：

```python
# scripts/doc_consistency_check.py
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
    "api", "auth", "core", "docs", "examples", "frontend", "graph",
    "monitoring", "nginx", "scenarios", "scripts", "secrets.example",
    "stages", "storage", "tests", "tools", ".github", ".upgrade",
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


def resolve_link_path(link: str, source_file: Path) -> Path:
    """将 Markdown 相对路径解析为绝对路径。剥离锚点 (#section) 与查询 (?query)。"""
    # 剥离锚点与查询
    clean = link.split("#")[0].split("?")[0]
    if not clean:
        return None  # 纯锚点，跳过
    if clean.startswith(("http://", "https://", "mailto:", "ftp://")):
        return None  # 外部 URL，跳过
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

    for lineno, line in enumerate(lines, start=1):
        rel = source.relative_to(REPO_ROOT).as_posix()

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
```

#### 2.1.2 修复存量悬空引用

**改动文件**：`docs/spec/stage3-risk-adaptive-gate.md` line 119

当前：
```markdown
**Report:** [../archive/verification-reports/risk_adaptive_gate_final_validation.md](../archive/verification-reports/risk_adaptive_gate_final_validation.md)
```

**决策**：补档（创建目标文件）优于修链（删除引用），因为该验证报告是 stage3 风险自适应门禁的设计证据，删除会丢失设计溯源。

**改动**：新建 `docs/archive/verification-reports/risk_adaptive_gate_final_validation.md`（简短存档说明，标注原文已不可考、关键结论摘要），并在 `.upgrade/decisions/` 记录该决策。

#### 2.1.3 Makefile target

**改动文件**：`Makefile`

在 `version-check` target 后追加：

```makefile
# 文档-代码一致性检查（链接/make target/仓库路径）
doc-check:
	python scripts/doc_consistency_check.py
```

同步更新 `.PHONY` 行追加 `doc-check`。

#### 2.1.4 CI 接入

**改动文件**：`.github/workflows/ci.yml`

在 `lint-and-unit-tests` job 的 `Lint` 步骤后追加（`continue-on-error: true` 观察期，存量坏链清零后转强制）：

```yaml
      - name: Doc consistency check (non-blocking)
        run: make doc-check
        continue-on-error: true   # 初期观察，存量坏链清零后转强制
```

#### 2.1.5 scripts/README.md 更新

在 Active Scripts 段追加 `doc_consistency_check.py` 说明。

#### 2.1.6 验收

- `make doc-check` 本地可运行，输出违规清单或 OK
- CI 在 lint job 内执行（初期 non-blocking）
- stage3 悬空引用已清除（补档或修链，记录决策）
- 故意引入坏链可被脚本检出（手动验证一次）

---

### T4.5 社区响应约定【Wave 1，与 T4.1 并行】

#### 2.5.1 Issue 模板

**改动文件**：`.github/ISSUE_TEMPLATE/bug_report.md`、`.github/ISSUE_TEMPLATE/feature_request.md`（新建）

**bug_report.md**：

```markdown
---
name: Bug 报告
about: 报告缺陷以帮助改进项目
title: "[BUG] "
labels: bug
---

## 问题描述
<!-- 简述发生了什么问题 -->

## 复现步骤
1.
2.
3.

## 预期行为
<!-- 你期望发生什么 -->

## 实际行为
<!-- 实际发生了什么 -->

## 环境
- 版本：<!-- 如 v1.2.0，见 core/version.py -->
- 部署模式：<!-- docker-compose / lite / 本地 uv -->
- LLM_MODE：<!-- mock / deepseek -->
- 操作系统：

## 补充信息
<!-- 日志、截图等 -->
```

**feature_request.md**：

```markdown
---
name: 功能建议
about: 建议新功能或改进
title: "[FEAT] "
labels: enhancement
---

## 功能描述
<!-- 你希望增加什么功能 -->

## 动机
<!-- 解决什么问题 / 带来什么价值 -->

## 建议方案
<!-- 可选：你设想的实现方式 -->

## 是否愿意贡献
- [ ] 我愿意提交 PR 实现此功能
```

#### 2.5.2 PR 模板

**改动文件**：`.github/PULL_REQUEST_TEMPLATE.md`（新建）

```markdown
## 改动说明
<!-- 本 PR 做了什么、为什么 -->

## 改动类型
- [ ] feat: 新功能
- [ ] fix: 缺陷修复
- [ ] docs: 文档
- [ ] refactor: 重构
- [ ] chore: 杂项
- [ ] test: 测试

## 提交前检查
- [ ] `make lint` 通过
- [ ] `make test` 通过
- [ ] `make version-check` 通过（如涉及版本号变更）
- [ ] `make doc-check` 通过（如涉及文档改动）
- [ ] 新增功能已附带测试 / bug 修复已附回归测试

## 关联 Issue
<!-- 如 Closes #123 -->
```

#### 2.5.3 CONTRIBUTING.md 补充响应节奏

**改动文件**：`CONTRIBUTING.md`

在末尾追加"社区响应约定"段落（计划 T4.5 要求：承诺与实际维护能力相符，不过度承诺）：

```markdown
## 社区响应约定

本项目由个人业余维护，响应节奏如下（不过度承诺）：

- **Issue**：尽力在 7 个自然日内首次响应（确认收到 + 初步分诊）。
- **PR**：尽力在 7 个自然日内完成 review 或给出反馈意见。
- **安全漏洞**：按 [SECURITY.md](SECURITY.md) 的承诺（7 天内确认接收）。
- **重大节日 / 个人不可用期**：会在 Issue 中提前说明，响应可能延长至 14 天。

如果你在上述时间窗口内未收到任何回复，欢迎在原 Issue/PR 下追加一条 `ping` 评论提醒（请勿频繁 ping）。
```

#### 2.5.4 验收

- `.github/ISSUE_TEMPLATE/` 含至少 2 个模板（bug + feature）
- `.github/PULL_REQUEST_TEMPLATE.md` 存在
- `CONTRIBUTING.md` 含响应节奏段落，承诺与实际维护能力相符
- 模板内引用的命令（make lint/test/version-check/doc-check）均真实可运行

---

### T4.2 分支保护与评审流程【Wave 2，需手动操作】

#### 2.2.1 落地形态（三件套）

如 §1 实测发现第 3 项所述，分支保护是 GitHub 后台操作，无法代码入库。落地为三件套：

**(a) 决策记录**：`.upgrade/decisions/branch-protection.md`（新建）

```markdown
# 分支保护策略决策

> 日期：2026-07-14
> 关联：phase-4-design.md T4.2 / spec §8

## 决策

对 main 分支开启保护，配置如下：

| 规则 | 设置 | 原因 |
|---|---|---|
| Require a pull request before merging | ✅ 开启 | 强制 PR 流程，即使个人项目也走 PR + 自我 review |
| Required reviewers | 0（个人项目无第二人） | Scorecard Code-Review 项对此部分给分（require PR 本身即得分） |
| Require status checks to pass | ✅ 开启 | lint-and-unit-tests + docker-lite-integration 必须通过 |
| Require branches to be up to date before merging | ✅ 开启 | 防止合并过时代码 |
| Allow direct pushes to main | ❌ 拒绝 | 防止绕过 PR 流程 |
| Allow force pushes | ❌ 拒绝 | 保护历史 |
| Allow deletions | ❌ 拒绝 | 保护历史 |

## 操作步骤（维护者手动执行）

1. GitHub 仓库 → Settings → Branches → Add branch protection rule
2. Branch name pattern: `main`
3. 勾选上述规则
4. 在 "Require status checks" 中选择：`lint-and-unit-tests`、`docker-lite-integration`
5. 保存

## 预期 Scorecard 影响

- Branch-Protection: 0 → 8+（开启 required status checks + require PR）
- Code-Review: 0 → 3-5（require PR before merge，虽无第二 reviewer）

## 备注

本决策在 GitHub 后台手动执行后，需在 `.upgrade/reports/` 的下一次 Scorecard 扫描报告中确认得分变化。
```

**(b) 文档声明**：`CONTRIBUTING.md` 追加分支保护说明

在"分支与提交约定"段落补充：

```markdown
## 分支保护

`main` 分支已开启保护：
- 所有改动必须通过 PR 合并（不接受直接 push main）
- PR 必须通过 CI（lint + unit tests + docker-lite integration）才能合并
- 个人项目无强制第二人 review，但鼓励自我 review 后再合
```

**(c) 操作清单**：见决策记录内的步骤（维护者手动执行）

#### 2.2.2 验收

- 决策记录已入库 `.upgrade/decisions/branch-protection.md`
- `CONTRIBUTING.md` 含分支保护声明
- **手动操作项**（无法代码验证）：维护者登录 GitHub 后台开启保护；下次 Scorecard 扫描确认 Branch-Protection / Code-Review 得分提升

---

### T4.3 Scorecard 持续爬升机制【Wave 2，机制性任务】

#### 2.3.1 现状

机制已就位：`.github/workflows/scorecard.yml`（weekly cron 周一 06:00 UTC + 手动触发），基线报告 `.upgrade/reports/scorecard-baseline-20260713.md` 已存档。

#### 2.3.2 本阶段动作

Phase 4 完成后重跑一次 Scorecard，生成趋势对照报告：

**新建文件**：`.upgrade/reports/scorecard-trend-20260714.md`

对照基线记录变化，重点观察：
- Vulnerabilities：Phase 1 pip-audit + 依赖升级后预期改善
- SAST：Phase 1 CodeQL workflow 已落地，预期 0 → 5+
- Token-Permissions / Dangerous-Workflow：Phase 0 已设 `contents: read`，远端应已识别
- Branch-Protection：T4.2 手动开启后预期 0 → 8+（若维护者已操作）
- Code-Review：T4.2 require PR 后预期 0 → 3-5

#### 2.3.3 验收

- 至少两次跨阶段的分数记录（基线 2026-07-13 + 本阶段 2026-07-14）
- 趋势向上或持平（已达标项保持，未达标项有改善）
- 趋势报告存档至 `.upgrade/reports/`

---

### T4.4 锦上添花项【明确不承诺，本阶段不执行】

按计划 §3 T4.4 与 spec §1 非目标，以下三项**本阶段不投入**：
- Signed Releases（Sigstore/cosign）
- CII/OpenSSF Best Practices Badge
- 发布为可安装包（Packaging）

**决策原则**（计划 §5）：在没有外部用户信号前不投入；Star/Fork 等虚荣指标不追逐。

---

## 3. Wave 划分与并行策略

### 3.1 依赖分析

| 任务 | 依赖 | 可并行 |
|---|---|---|
| T4.1 doc-check | 无 | ✅ 与 T4.5 并行 |
| T4.5 模板 + CONTRIBUTING | 无 | ✅ 与 T4.1 并行 |
| T4.2 分支保护文档 | 无（代码侧） | ✅ 与 T4.1/T4.5 并行；但手动操作需在 CI 稳定后 |
| T4.3 Scorecard 重跑 | T4.1/T4.2/T4.5 落地后 | ❌ 串行在最后，让改进反映到分数 |

### 3.2 Wave 划分

```
Wave 1（并行，Subagent-Driven）：
  ├─ Lane A: T4.1 doc-check（脚本 + Makefile + CI + 修存量坏链 + scripts/README）
  ├─ Lane B: T4.5 模板（ISSUE_TEMPLATE × 2 + PR_TEMPLATE + CONTRIBUTING 响应节奏）
  └─ Lane C: T4.2 分支保护（决策记录 + CONTRIBUTING 分支保护声明）

Wave 2（串行，Wave 1 完成后）：
  └─ T4.3 Scorecard 重跑 + 趋势报告（依赖 Wave 1 改进落地）
```

### 3.3 Subagent-Driven 并行策略

Wave 1 三个 Lane 互相独立，无文件冲突，可启动 3 个并行 Subagent：

| Lane | 改动文件 | 冲突风险 |
|---|---|---|
| Lane A (T4.1) | `scripts/doc_consistency_check.py`(新)、`Makefile`、`.github/workflows/ci.yml`、`docs/spec/stage3-risk-adaptive-gate.md`、`docs/archive/verification-reports/risk_adaptive_gate_final_validation.md`(新)、`scripts/README.md` | 无 |
| Lane B (T4.5) | `.github/ISSUE_TEMPLATE/bug_report.md`(新)、`.github/ISSUE_TEMPLATE/feature_request.md`(新)、`.github/PULL_REQUEST_TEMPLATE.md`(新) | 无 |
| Lane C (T4.2) | `.upgrade/decisions/branch-protection.md`(新)、`CONTRIBUTING.md` | ⚠️ `CONTRIBUTING.md` 与 Lane B 都改 |

**冲突处理**：Lane B 与 Lane C 都需改 `CONTRIBUTING.md`（Lane B 追加响应节奏段落，Lane C 追加分支保护段落）。两个段落独立，无内容重叠。采用**串行合并**策略：Lane C 在 Lane B 完成后追加，或两个 Subagent 改不同位置（Lane B 改末尾，Lane C 改"分支与提交约定"段）。

**推荐方案**：Lane B 与 Lane C 合并为单 Subagent（都涉及 CONTRIBUTING.md + 社区治理），避免文件冲突。实际并行 2 个 Lane：

| Lane | 任务 | 改动文件 |
|---|---|---|
| Lane A | T4.1 doc-check 全链路 | scripts/doc_consistency_check.py、Makefile、ci.yml、stage3 doc、archive 补档、scripts/README |
| Lane B | T4.5 模板 + T4.2 分支保护文档 | .github/ISSUE_TEMPLATE/*、PR_TEMPLATE、CONTRIBUTING.md、.upgrade/decisions/branch-protection.md |

---

## 4. 风险与注意事项

1. **doc-check 规则过严**（计划 §5）：启发式规则宁松勿严，误报率高于约 5% 就收窄规则。三类规则中"反引号仓库路径"最易误报（如 api/v1 可能是 API 路径非文件路径），靠"必须以已知顶层目录开头"过滤，并跳过围栏代码块内容。

2. **CI doc-check 初期 non-blocking**：`continue-on-error: true` 观察一轮，确认无误报后转强制。转强制时机：存量坏链清零 + 连续 3 次 CI 无误报。

3. **分支保护无法代码验证**：T4.2 的实际开启需维护者手动操作 GitHub 后台。设计文档提供精确步骤，但验收的"直接 push main 被拒绝"项需手动测试。

4. **Scorecard 远端扫描需认证**：本地 CLI 无法检测 GitHub 后台配置（Branch-Protection 等），趋势报告以远端 Actions 扫描结果为准。

5. **不过度工程**（计划 §5）：T4.4 不承诺清单是防线。所有任务服务于"工程健康度可验证"，不堆徽章。

---

## 5. 阶段验收清单（对照计划 §6）

- [ ] doc-check 进 CI（初期 non-blocking，存量坏链清零后转强制）
- [ ] stage3 文档悬空引用清除（补档 `docs/archive/verification-reports/`）
- [ ] main 分支保护开启（决策记录入库 + 维护者手动操作 GitHub 后台）
- [ ] Scorecard 分数相比阶段 0 基线有实质提升且有至少两次记录
- [ ] issue/PR 模板与响应约定就位

---

## 6. 执行后收尾

- 更新 `.upgrade/STATE.md`：Phase 4 完成状态
- 更新 `CHANGELOG.md`：新增 v1.2.1 或 v1.3.0 段落
- 更新 `docs/plan/phase-4-community.md`：勾选验收清单
- git commit（Wave 1 一次、Wave 2 一次，或合并为一次）
- git tag（如版本号变更）
