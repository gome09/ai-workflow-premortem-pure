# Wave A — 门面与治理文件 具体实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 完成主计划（`.upgrade/plans/2026-07-17-formal-project-uplift.md`）Wave A（Task 0–6）：归档根目录调研快照、统一包元数据并可安装化、补齐 SECURITY/CODE_OF_CONDUCT/GOVERNANCE/CODEOWNERS/issue config、完成 README 门面改造与英文 README。

**Architecture:** 纯文档 + 打包元数据改动，不触及任何运行时代码。7 个任务按序执行、每任务一个 commit。基于 2026-07-17 三个并行探索 Agent 的仓库实况核实，本计划相对主计划有三处**已确认的修正**（见下方"与主计划的差异"）。

**Tech Stack:** 现有栈不变。新增 build backend：hatchling（仅本地 `pip install -e .`，不发 PyPI）。环境实测：Windows + Git Bash（MINGW64），`mv`/`mkdir -p`/`curl` 均可用；`uv 0.11.12`。

---

## 与主计划的差异（探索核实后的修正，执行者必须遵守）

1. **Task A5/A6 执行顺序对调**：`scripts/doc_consistency_check.py` 扫描 `README.md`、`CLAUDE.md`、`docs/**/*.md` 并校验相对链接存在性。README.md 加 `[English](README.en.md)` 链接前 README.en.md 必须已存在，否则 `make doc-check` 退出码 1。因此**先创建 README.en.md（A5），后改 README.md（A6）**，与主计划 Task 5→6 顺序相反；commit 顺序同理。
2. **MANIFEST File Inventory 是四列表格**（`| File | Status | Lifecycle | Notes |`），不是列表。Task A0 追加的是表格行，非主计划写的列表条目。
3. **README 插入锚点**：实际标题为 `### 核心创新：风险自适应阶段门禁`（带后缀），主计划字面的 `### 核心创新` 匹配不到。生态定位段插在解决方案表格之后、该标题之前的空行处。

**其他已核实事实（执行时无需再探索）：**
- 15 个待归档文件全部存在于根目录；`git status` 中另有 `M .upgrade/STATE.md` 与 `?? .upgrade/plans/`，**不属于本次归档范围，不要动**。
- `.upgrade/research/` 目录不存在，需创建。
- `ai-workflow-tool` 活引用仅 `pyproject.toml:3` 一处（另两处在 `.upgrade/plans/` 计划文档内，不改）。
- `pyproject.toml` 无 `[build-system]`/`license`/`authors`/`classifiers`/`[project.urls]`/`[tool.mypy]`；`[project.optional-dependencies]` 在 35–41 行，其后紧跟 43 行 `[tool.pytest.ini_options]`。
- `scripts/version_check.py` 用 `^version\s*=\s*"(...)"` 匹配 pyproject 版本，要求双引号，`version = "1.2.1"` 行不能动。
- `.github/` 已有 `workflows/{ci,codeql,scorecard}.yml`、`ISSUE_TEMPLATE/{bug_report,feature_request}.md`、`PULL_REQUEST_TEMPLATE.md`、`dependabot.yml`；**无** CODEOWNERS、无 `ISSUE_TEMPLATE/config.yml`。
- 根目录已有 CONTRIBUTING.md / LICENSE / CHANGELOG.md / SECURITY.md；**无** CODE_OF_CONDUCT.md / GOVERNANCE.md / README.en.md。
- `curl https://www.contributor-covenant.org/version/2/1/code_of_conduct/code_of_conduct.md` 实测 HTTP 200，可直接下载。
- SECURITY.md 第 7–8 行占位符段、第 10–15 行 v1.0.x 支持表已逐字核实与主计划引用一致。
- 根目录 demo HTML 确为 `ai_workflow_premortem_demo.html`（勿与 `trae_ai_risk_premortem_submission.html` 混淆）。
- docs/README.md「使用指南」表最后一行是 `| [acceptance_report.md](acceptance_report.md) | 四阶段全流程 E2E 测试验收报告 |`（第 11 行）。

**全局约束：** 工作目录 = 仓库根（`D:\BackendDevelopment\Project\Projest_Test-4\ai-workflow-premortem\ai-workflow-premortem\ai-workflow-premortem`，下称 `<ROOT>`，Git Bash 下即启动目录）。禁止 `git add .`；每任务结束跑 `make lint`（涉及文档链接的任务再跑 `make doc-check`）；提交前 `git status --short` 检查。

---

### Task A0: 根目录对标研究材料归档（对应主计划 Task 0）

**Files:**
- Move: 根目录 15 个 untracked 文件 → `.upgrade/research/benchmarking-20260716/`
- Modify: `.upgrade/MANIFEST.md`（File Inventory 表格追加一行）

- [x] **Step 1: 创建目录并移动 15 个文件**

```bash
mkdir -p .upgrade/research/benchmarking-20260716
mv readme_deepeval.md readme_deepeval_full.md readme_guardrails.md readme_inspect.md readme_nemo.md \
   rel_NVIDIA_NeMo-Guardrails.json rel_UKGovernmentBEIS_inspect_ai.json rel_confident-ai_deepeval.json rel_guardrails-ai_guardrails.json \
   repo_NVIDIA_NeMo-Guardrails.json repo_UKGovernmentBEIS_inspect_ai.json repo_confident-ai_deepeval.json repo_guardrails-ai_guardrails.json \
   tags_deepeval.json tags_inspect.json \
   .upgrade/research/benchmarking-20260716/
```

- [x] **Step 2: 验证移动结果**

Run: `ls .upgrade/research/benchmarking-20260716/ | wc -l && git status --short`
Expected: 计数 `15`；git status 中不再有根目录 `?? readme_*` / `?? rel_*` / `?? repo_*` / `?? tags_*`；仍会看到 `M .upgrade/STATE.md`、`?? .upgrade/plans/`、`?? .upgrade/research/`——前两者属正常残留，**不要处理**。

- [x] **Step 3: 在 `.upgrade/MANIFEST.md` 的 `## File Inventory` 表格末尾追加一行**

当前表格最后一行是：

```markdown
| `.upgrade/reports/tc260-agent-deployment-summary.md` | active | keep-until-superseded | Phase 2 T2.4 TC260 智能体部署使用安全指引映射摘要 |
```

在其后追加：

```markdown
| `.upgrade/research/benchmarking-20260716/` | active | keep-until-superseded | 对标调研原始数据快照（deepeval / guardrails-ai / inspect_ai / NeMo-Guardrails 的 GitHub repo/releases/tags API 采集 + README 快照，采集日 2026-07-16），供开源门面对齐与竞品定位分析引用 |
```

- [x] **Step 4: 提交**

```bash
git add .upgrade/research/benchmarking-20260716 .upgrade/MANIFEST.md
git status --short
git commit -m "chore: archive benchmarking research snapshots into .upgrade/research"
```

---

### Task A1: pyproject.toml 元数据统一与可安装化（对应主计划 Task 1）

**背景：** 当前 `name = "ai-workflow-tool"`（pyproject.toml:3）与仓库名不一致；无 `[build-system]`，不可 pip install。统一为 `ai-workflow-premortem`，暂不发 PyPI。**已知限制（记录不修复，YAGNI）：** flat layout 多顶层包，发 PyPI 前需 src-layout 重构，本次仅保证 `pip install -e .` 可用。

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`（由 `uv lock` 自动再生成）

- [x] **Step 1: 修改 `pyproject.toml` 的 `[project]` 头部**

将（第 2–7 行）：

```toml
[project]
name = "ai-workflow-tool"
version = "1.2.1"
description = "A human-AI collaborative workflow tool for project inception"
readme = "README.md"
requires-python = ">=3.11"
```

替换为：

```toml
[project]
name = "ai-workflow-premortem"
version = "1.2.1"
description = "AI Workflow Premortem — pre-mortem failure-mode analysis and human oversight platform for AI projects"
readme = "README.md"
requires-python = ">=3.11"
license = "Apache-2.0"
authors = [{ name = "gome09" }]
keywords = ["ai-governance", "premortem", "risk-assessment", "human-oversight", "llm-evaluation", "langgraph"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Topic :: Software Development :: Quality Assurance",
]
```

> `version = "1.2.1"` 行保持原样——`scripts/version_check.py` 用 `^version\s*=\s*"..."`（双引号）校验它与 `core/version.py` 一致。

- [x] **Step 2: 在 `[project.optional-dependencies]` 段（35–41 行）之后、`[tool.pytest.ini_options]`（43 行）之前插入**

```toml
[project.urls]
Repository = "https://github.com/gome09/ai-workflow-premortem-pure"
Changelog = "https://github.com/gome09/ai-workflow-premortem-pure/blob/main/CHANGELOG.md"
Documentation = "https://github.com/gome09/ai-workflow-premortem-pure/blob/main/docs/README.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
# Flat layout 多顶层包。仅用于本地可编辑安装；发布 PyPI 前需 src-layout 重构（见 .upgrade/decisions）。
packages = ["api", "auth", "core", "graph", "stages", "storage", "tools", "scenarios"]
```

- [x] **Step 3: 重新生成锁文件并验证安装**

```bash
uv lock
uv sync --all-extras
uv pip install -e . --no-deps
python -c "import core.version; print(core.version.APP_VERSION)"
```

Expected: 无报错，输出 `1.2.1`

- [x] **Step 4: 全量回归**

Run: `make lint && make version-check && make test`
Expected: lint clean；`Version metadata OK: 1.2.1`；615+ passed（skip 不算失败）

- [x] **Step 5: 提交**

```bash
git add pyproject.toml uv.lock
git status --short
git commit -m "build: unify package name to ai-workflow-premortem, add metadata and hatchling build backend"
```

---

### Task A2: SECURITY.md 移除邮箱占位符（对应主计划 Task 2）

**Files:**
- Modify: `SECURITY.md`

- [x] **Step 1: 替换报告渠道段（第 7–8 行，原文已逐字核实）**

将：

```markdown
- **首选**：GitHub Security Advisories（仓库 Security 标签页 → Report a vulnerability）。该渠道端到端私有，支持协作修复与 CVE 申请。
- **备选**：发送邮件至 <SECURITY_EMAIL>（待维护者填入真实邮箱），主题加前缀 `[SECURITY]`。
```

替换为：

```markdown
- **唯一渠道**：GitHub Security Advisories（仓库 Security 标签页 → Report a vulnerability）。该渠道端到端私有，支持协作修复与 CVE 申请。
- 本项目不提供邮箱报告渠道；如无法使用 GitHub 私密报告，可开一个**不含漏洞细节**的公开 Issue 请求维护者联系。
```

- [x] **Step 2: 更新支持版本表（第 12–15 行）**

将：

```markdown
| 版本 | 是否支持 |
|---|---|
| v1.0.x | ✅ |
| < v1.0 | ❌ |
```

替换为：

```markdown
| 版本 | 是否支持 |
|---|---|
| 最新 minor（当前 v1.3.x） | ✅ |
| 更早版本 | ❌（请升级到最新版） |
```

> 注：主计划 Wave E Task 18 会把版本 bump 到 1.3.0，此处按主计划直接写 v1.3.x。

- [x] **Step 3: 验证并提交**

```bash
make doc-check
git add SECURITY.md
git commit -m "docs: finalize SECURITY.md reporting channel (GitHub private reporting only)"
```

---

### Task A3: CODE_OF_CONDUCT.md（Contributor Covenant 2.1，对应主计划 Task 3）

**Files:**
- Create: `CODE_OF_CONDUCT.md`

- [x] **Step 1: 下载官方英文文本（网络可达性已实测 HTTP 200）**

```bash
curl -fsSL https://www.contributor-covenant.org/version/2/1/code_of_conduct/code_of_conduct.md -o CODE_OF_CONDUCT.md
```

若届时网络不可达，退路：从 `https://github.com/EthicalSource/contributor_covenant/blob/release/content/version/2/1/code_of_conduct.md` 获取原始文本手工创建。**不要凭记忆默写全文。**

- [x] **Step 2: 替换 Enforcement 段联系方式**

找到 `[INSERT CONTACT METHOD]` 占位符，替换为：

```text
GitHub private vulnerability reporting or a direct message to the maintainer (@gome09) via GitHub
```

- [x] **Step 3: 验证占位符已清除且文件非空**

Run: `grep -c "INSERT CONTACT METHOD" CODE_OF_CONDUCT.md; wc -l CODE_OF_CONDUCT.md`
Expected: grep 输出 `0`（exit code 1）；行数 > 100（完整 2.1 全文约 130 行）

- [x] **Step 4: 提交**

```bash
git add CODE_OF_CONDUCT.md
git commit -m "docs: add Contributor Covenant 2.1 code of conduct"
```

---

### Task A4: GOVERNANCE.md + CODEOWNERS + issue 模板 config.yml（对应主计划 Task 4）

**已核实：** `.github/ISSUE_TEMPLATE/` 目录已存在（含 bug_report.md、feature_request.md，不动它们）；CODEOWNERS 与 config.yml 均不存在，为新建。

**Files:**
- Create: `GOVERNANCE.md`
- Create: `.github/CODEOWNERS`
- Create: `.github/ISSUE_TEMPLATE/config.yml`

- [x] **Step 1: 创建 `GOVERNANCE.md`（完整内容）**

```markdown
# 项目治理

## 现行模式：单一维护者（BDFL）

本项目当前由单一维护者 [@gome09](https://github.com/gome09) 维护，持有仓库全部管理权限与技术方向最终决定权。

## 决策方式

- 常规改动：直接以 PR + CI 全绿合入 main（受分支保护约束）。
- 重大决策（架构、合规映射口径、破坏性变更）：决策记录写入 `.upgrade/decisions/` 或 `docs/plan/`，理由留档可追溯。
- 外部贡献：按 [CONTRIBUTING.md](CONTRIBUTING.md) 提交 Issue/PR，维护者承诺 7 个自然日内响应。

## 如何成为维护者

持续提交高质量 PR（3 个以上被合入）并表达长期维护意愿后，可在 Issue 中申请 maintainer 权限，由现任维护者评估授予 triage/write 权限。

## 项目连续性

若项目获得稳定外部用户，维护者将把仓库迁移至 GitHub Organization 并至少增加一名备份管理员，避免单点风险。
```

- [x] **Step 2: 创建 `.github/CODEOWNERS`**

```text
# 默认所有文件由维护者审查
* @gome09
```

- [x] **Step 3: 创建 `.github/ISSUE_TEMPLATE/config.yml`**

```yaml
blank_issues_enabled: false
contact_links:
  - name: 安全漏洞报告（私密）
    url: https://github.com/gome09/ai-workflow-premortem-pure/security/advisories/new
    about: 请勿在公开 Issue 中提交漏洞细节，使用 GitHub Security Advisories 私密报告。
```

- [x] **Step 4: 验证并提交**

```bash
make doc-check
git add GOVERNANCE.md .github/CODEOWNERS .github/ISSUE_TEMPLATE/config.yml
git commit -m "docs: add governance model, CODEOWNERS, and issue template config"
```

> GOVERNANCE.md 中 `[CONTRIBUTING.md](CONTRIBUTING.md)` 链接：CONTRIBUTING.md 已核实存在；且 GOVERNANCE.md 不在 doc-check 扫描范围（README.md/CLAUDE.md/docs/**），无链接校验风险。

---

### Task A5: README.en.md（英文门面，对应主计划 Task 6，**提前执行**）

**顺序修正原因：** doc-check 校验 README.md 与 docs/README.md 中的相对链接存在性，两者都会新增指向 README.en.md 的链接，故本任务必须先于 Task A6。

**Files:**
- Create: `README.en.md`
- Modify: `docs/README.md`（「使用指南」表格追加一行）

- [x] **Step 1: 创建 `README.en.md`（完整内容如下；如与 README.md 中文版事实有出入以中文版为准）**

````markdown
# AI Workflow Premortem

[![CI](https://github.com/gome09/ai-workflow-premortem-pure/actions/workflows/ci.yml/badge.svg)](https://github.com/gome09/ai-workflow-premortem-pure/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

English | [简体中文](README.md)

> Before an AI system ships, answer one question systematically: **where will it fail?**

## Why

In early 2026 alone, AI agents deleted production databases and moved millions of dollars without human approval. The common root cause was not model capability — it was that **foreseeable failure modes were never tested before deployment**. AI Workflow Premortem applies the software-engineering *pre-mortem* methodology to the inception phase of AI projects: assume the system has failed, then work backwards to find out how.

## What it does

A guided four-stage analysis pipeline with risk-adaptive gates and mandatory human oversight:

| Stage | Purpose |
|-------|---------|
| 1. Failure Mode Identification | Live web research + LLM reasoning to enumerate domain-specific failure modes |
| 2. Human-AI Workflow Design | Decide which decisions require human review; design oversight nodes |
| 3. Zero-Shot Stress Testing | Auto-generate EvalCases probing boundary behaviors |
| 4. Trigger Strategy | Deployment timing, trigger conditions, and monitoring strategy |

**Risk-adaptive stage gates** (LOW / MEDIUM / HIGH / CRITICAL) tighten pass conditions as project risk rises — a CRITICAL-tier project (e.g. medical diagnosis) cannot pass Stage 3 without red-team tests, regression evals, and explicit expert approval. Blocking a high-risk project is **by design, not a defect**.

**Architecture principle:** workflow state transitions are deterministic and code-controlled. The LLM generates analysis content; it never decides flow transitions. Evidence, safety findings, eval runs, human interventions, and audit events are first-class records.

## Quick start (offline demo, no API key)

```bash
cp .env.example .env
# uncomment in .env: LLM_MODE=mock, STORAGE_BACKEND=sqlite, DEFAULT_SCENARIO_ID=generic_rag_demo
uv sync --all-extras
make demo-api   # backend on :8000
make demo-ui    # Streamlit frontend on :8501
```

Or zero-dependency: open `ai_workflow_premortem_demo.html` directly in a browser.

## Tech stack

FastAPI · LangGraph · Streamlit · PostgreSQL/SQLite · Redis · JWT/RBAC · Docker Compose · Prometheus/Grafana

## Compliance mapping

The risk taxonomy engine maps findings to NIST AI RMF / NIST AI 600-1, OWASP LLM Top 10 (2025) & Agentic Top 10 (ASI, 2026), TC260 agent-deployment guidance, and ISO/IEC 42001 clauses. See [docs/](docs/README.md) (Chinese).

## Documentation

Full documentation (architecture, API reference, security model, compliance mappings) is currently in Chinese under [docs/](docs/README.md). The codebase uses English identifiers throughout; issues and PRs in English are welcome.

## License

Apache-2.0
````

> 与主计划的两处微调（基于 .env.example 实况核实）：quick start 注释写明 "uncomment in .env"——mock/sqlite/generic_rag_demo 在 .env.example 中是被注释的演示态取值（默认是 real/postgres），照主计划原文 "set:" 容易误导。demo HTML 文件名 `ai_workflow_premortem_demo.html` 已核实存在。

- [x] **Step 2: 在 `docs/README.md`「使用指南」表格末尾追加一行**

当前该表最后一行是：

```markdown
| [acceptance_report.md](acceptance_report.md) | 四阶段全流程 E2E 测试验收报告 |
```

在其后追加：

```markdown
| [../README.en.md](../README.en.md) | English project overview |
```

- [x] **Step 3: 校验并提交**

```bash
make doc-check
git add README.en.md docs/README.md
git commit -m "docs: add English README"
```

Expected: doc-check 0 违规（README.en.md 已存在，docs/README.md 的相对链接可解析）

---

### Task A6: README.md 门面改造（对应主计划 Task 5，**置后执行**）

**背景：** 徽章此时仓库仍私有，CI/Scorecard 徽章公开前显示不了——先写上，公开后自动生效（主计划 Task 19 核验）。

**Files:**
- Modify: `README.md`

- [x] **Step 1: 替换 README.md 头部（第 1–8 行，含空行，原文已逐字核实）**

将：

```markdown
# AI 工作流预验尸与人机监督平台

> 本科毕业设计项目 · 计算机科学与技术专业

**版本：** v1.2.1
**协议：** Apache-2.0

---
```

替换为：

```markdown
# AI Workflow Premortem — AI 工作流预验尸与人机监督平台

[![CI](https://github.com/gome09/ai-workflow-premortem-pure/actions/workflows/ci.yml/badge.svg)](https://github.com/gome09/ai-workflow-premortem-pure/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/gome09/ai-workflow-premortem-pure/badge)](https://scorecard.dev/viewer/?uri=github.com/gome09/ai-workflow-premortem-pure)

[English](README.en.md) | 简体中文

> 在 AI 系统上线之前，系统性地回答一个问题：**它会在哪里失败？**

2026 年上半年，AI agent 删除生产数据库、越权转移资金等事故屡见报端——共同根因不是模型能力不足，而是**可预见的失败模式在部署前从未被系统性测试过**。本项目将软件工程的预验尸（Pre-mortem）方法论应用于 AI 项目立项阶段：四阶段引导式分析（失败模式识别 → 人机协同工作流设计 → 压力测试 → 触发策略），配合风险自适应门禁（LOW/MEDIUM/HIGH/CRITICAL）与强制人工审核，让高风险 AI 项目在完成充分评估之前无法推进。

**版本：** v1.2.1 · **协议：** Apache-2.0 · 源于本科毕业设计，现作为长期维护的开源项目演进

---
```

- [x] **Step 2: 插入「生态定位」段**

**锚点（已核实）：** 「项目背景」章节内，`### 解决方案` 的 Stage 1–4 表格（原第 24–29 行）之后、`### 核心创新：风险自适应阶段门禁` 标题（原第 31 行，**注意标题带后缀**，非主计划字面的 `### 核心创新`）之前的空行处插入：

```markdown
### 生态定位

| 相邻项目 | 定位 | 与本项目的关系 |
|---|---|---|
| [deepeval](https://github.com/confident-ai/deepeval) / [inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | LLM 评估框架（运行时/回归） | 互补：本项目的 EvalCase 是"事前生成的假设检验"，可导出到评估框架持续回归 |
| [guardrails-ai](https://github.com/guardrails-ai/guardrails) / [NeMo-Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | 运行时护栏 | 互补：预验尸预测出的失败模式，可落地为运行时护栏的具体校验器 |
| 对话式 AI 顾问团类产品 | 事前风险头脑风暴 | 差异：本项目工作流状态转换是**确定性代码控制**的，LLM 只生成分析内容不决定流程；门禁判定、人工审核、审计记录均为一等公民数据 |
```

（"生态定位"字样已核实全文不存在，插入不会重复。）

- [x] **Step 3: 校验并提交**

```bash
make doc-check
git add README.md
git commit -m "docs: rework README front matter with badges, origin story, and ecosystem positioning"
```

Expected: doc-check 0 违规——`README.en.md`（Task A5 已创建）、`LICENSE`、`pyproject.toml` 链接目标均存在。

---

### Task A7: Wave A 收尾——STATE.md 同步与计划文件入库

**背景：** CLAUDE.md 要求每任务完成后更新 `.upgrade/STATE.md`（允许 Wave 收尾批量更新，本任务即批量落账）。同时 `.upgrade/plans/` 目前 untracked，计划文件属永久记录，纳入版本控制并登记 MANIFEST。

**Files:**
- Modify: `.upgrade/STATE.md`
- Modify: `.upgrade/MANIFEST.md`（File Inventory 登记两份计划文件）
- Add: `.upgrade/plans/2026-07-17-formal-project-uplift.md`、`.upgrade/plans/2026-07-17-wave-a-implementation.md`

- [x] **Step 1: 更新 `.upgrade/STATE.md`**

- `## Current Phase` 段：追加说明"正式项目升级（formal-project-uplift）进行中——Wave A（门面与治理文件，Task 0–6）已完成；Wave B–E 待执行"。
- `## Last Completed` 列表**顶部**追加一条（保持既有 `- **标题 (日期)** — 说明` 格式）：

```markdown
- **Wave A 门面与治理文件 (2026-07-17)** — 对标调研快照归档至 `.upgrade/research/`；包名统一 `ai-workflow-premortem` + hatchling 可安装化（`uv pip install -e .` 验证通过）；SECURITY.md 报告渠道定稿（仅 GitHub 私密报告）；新增 CODE_OF_CONDUCT.md（Contributor Covenant 2.1）/ GOVERNANCE.md（BDFL）/ CODEOWNERS / issue config.yml；README 门面改造（徽章 + origin story + 生态定位）+ README.en.md。计划：`.upgrade/plans/2026-07-17-wave-a-implementation.md`。
```

- [x] **Step 2: `.upgrade/MANIFEST.md` File Inventory 表格追加两行**

```markdown
| `.upgrade/plans/2026-07-17-formal-project-uplift.md` | active | permanent | 正式项目升级主计划（Wave A–E，Task 0–19，目标 v1.3.0） |
| `.upgrade/plans/2026-07-17-wave-a-implementation.md` | active | permanent | Wave A 具体实施计划（探索核实修正版：A5/A6 顺序对调、MANIFEST 表格格式、README 锚点） |
```

- [x] **Step 3: 终验（Wave A 全量回归）**

```bash
make lint && make version-check && make doc-check && make test
git status --short
```

Expected: 全部通过；git status 仅剩本任务待 add 的文件，无计划外改动。

- [x] **Step 4: 提交**

```bash
git add .upgrade/STATE.md .upgrade/MANIFEST.md .upgrade/plans/2026-07-17-formal-project-uplift.md .upgrade/plans/2026-07-17-wave-a-implementation.md
git commit -m "chore: complete Wave A (facade & governance files), sync upgrade state and plans"
```

---

## 执行顺序与依赖

- **严格按 A0 → A1 → A2 → A3 → A4 → A5 → A6 → A7 执行**。
- 硬依赖：**A5 必须先于 A6**（doc-check 链接校验，见"与主计划的差异"第 1 条）；A7 必须最后（批量落账）。
- A2/A3/A4 之间无技术依赖，但按序执行便于追踪。
- 每任务一个 commit，禁止 `git add .`，提交前 `git status --short` 自查。
- 本 Wave 不改任何 `*.py` 运行时代码；若某步意外要求改代码，停下来向维护者确认。

## 与主计划的验收对照

完成后在主计划 `.upgrade/plans/2026-07-17-formal-project-uplift.md` 中勾选 Task 0–6 的全部 checkbox（注意主计划 Task 5/6 与本计划 A6/A5 的对应关系）。
