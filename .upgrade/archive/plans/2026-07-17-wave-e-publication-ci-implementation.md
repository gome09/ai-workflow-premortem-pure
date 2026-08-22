# Wave E — 公开前检查与 CI/发布收尾 具体实施部署方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地父计划（`.upgrade/plans/2026-07-17-formal-project-uplift.md`）Wave E（Task 15–18）：公开前全历史安全扫描与检查清单、CI 覆盖率产出 + doc-check 转正、生态定位与竞品分析文档、v1.3.0 版本收尾（CHANGELOG / STATE / tag）。Task 19（CodeQL 转正）为公开后延期任务，本方案附其完整内容但不在本轮执行。

**Architecture:** 四个任务严格串行（共享 git index，每任务 1–2 个 commit）：E1 纯报告产出（`.upgrade/reports/`）；E2 改 CI/构建三件套（pyproject + Makefile + ci.yml，唯一涉代码配置的任务）；E3 纯文档（docs/plan/ 新文件 + 索引）；E4 主控收尾（版本 bump + CHANGELOG + STATE/MANIFEST/父计划勾选 + 终验 + tag）。E4 必须最后。

**Tech Stack:** 新增 dev 依赖 pytest-cov>=6.0（配套 coverage 已有 `[tool.coverage.*]` 配置）。验证工具：`make lint` / `make typecheck` / `make version-check` / `make doc-check` / `make test`（650 passed, 1 skipped 基线）/ `make e2e-mock`（63 passed 基线）。

---

## 探索基线（2026-07-17，三个并行调研 subagent + 主控直读/实测交叉核实）

| # | 事实 | 位置 / 数值 |
|---|---|---|
| 1 | `ci.yml` 共 93 行，两个 job（`lint-and-unit-tests` :17、`docker-lite-integration` :56）。Unit tests 步骤在 :51-54，名称 `Unit tests (sqlite + mock)`，run 块为 `cp -f .env.demo .env` + `uv run pytest tests/ -v` | 已逐字核对 |
| 2 | ci.yml :39-41 已有 `Type check (non-blocking)`（`continue-on-error: true   # 观察一轮后转强制`）；:43-45 为 `Doc consistency check (non-blocking)`（`continue-on-error: true   # 初期观察，存量坏链清零后转强制`）；:47-49 为 pip-audit non-blocking | 已逐字核对 |
| 3 | **分支领先 origin/main 26 commits 未 push**——mypy typecheck 步骤从未在远端 CI 真实跑过（Wave B 之后无 push）；doc-check 已在远端 CI run #13（2026-07-15）观察过且存量违规清零 | git status / STATE.md |
| 4 | `pyproject.toml`：dev 列表 :47-53（pytest / pytest-asyncio / ruff / pip-audit / mypy，**无 pytest-cov**）；`[tool.coverage.run]` :100-106（`source=["."]`，omit tests/frontend/.venv）与 `[tool.coverage.report]` :108-113 **已存在**；`[tool.pytest.ini_options]` :68-77 无 `addopts`；`version = "1.2.1"` 在 :4 | 已逐字核对 |
| 5 | `.gitignore` :27-29 已含 `.coverage` / `coverage.xml` / `htmlcov/`，无需改动；Makefile `clean` target（:13）已预留清理这三者 | 已核对 |
| 6 | `Makefile`：`.PHONY` 在 :3（无 test-cov）；`test:` 在 :76-78（`uv run pytest tests/ -v`）；其后 :80 是 `# ── 答辩验收 ──` 分隔线 → test-cov 插在 test 块与分隔线之间 | 已逐字核对 |
| 7 | **预扫描已实测**（主控直跑）：密钥模式全历史扫描命中 5 行 `DEMO_PASSWORD = "demo-password-123"`（`scripts/live_e2e_four_stage.py` 演示凭据，带 `noqa: S105` 注释）；高熵前缀扫描命中 2 行 `CHANGE_ME_sk-xxxx...`（`secrets.example/deepseek_api_key` 模板占位符）。**均为已知良性，无真实密钥** | 2026-07-17 实测 |
| 8 | `git check-ignore -v secrets/ data/ .env` 三者均被 ignore（:44/:77/:12）；`docs/internal/`、`secrets/` 目录不存在；`git ls-files \| grep -E "^docs/internal\|^secrets/\|\.env$"` 输出为空（exit 1 = 通过）。`.env.demo` / `.env.example` 被 `.gitignore` :14-15 显式豁免跟踪，内含值均为演示占位（`JWT_SECRET=demo-only-local-secret-32-chars!!` 有"仅用于本地演示"注释） | 2026-07-17 实测 |
| 9 | 提交邮箱全历史唯一一组：`3567039961@qq.com`（author = committer）——个人 QQ 邮箱，需在报告中提示维护者决策 | 2026-07-17 实测 |
| 10 | `core/version.py` 共 7 行 5 常量：APP_VERSION/REPORT_SCHEMA_VERSION = "1.2.1"、APP_STATUS = "release"、PACKAGE_STAGE = "v1.2.1"、RUNTIME_VALIDATION = "local_pass"。`scripts/version_check.py` 只校验 APP_VERSION / REPORT_SCHEMA_VERSION / pyproject version 三者相等（不校验 PACKAGE_STAGE） | 已逐字核对 |
| 11 | `git tag --list` 输出为**空**——仓库当前零 tag（STATE.md :103 期望的 v1.0.2/v1.0.3/v1.1.0/v1.2.0 实际不存在，为状态漂移）；STATE.md :107 Next Action 仍写"执行 Wave D"（已过时） | 2026-07-17 实测 |
| 12 | CHANGELOG.md 头部结构：`# Changelog`（:1）→ 追溯说明 blockquote（:3-5）→ `## 维护记录 (2026-07-16)`（:7）→ ... → `## v1.2.1 (2026-07-14)`（:17）。条目格式为 `## vX.Y.Z (YYYY-MM-DD)` + 中文粗体行内标签 bullet（无英文 Added/Changed 小节）。v1.3.0 条目插入点：:5 追溯说明之后、:7 维护记录之前 | 已逐字核对 |
| 13 | `README.md` :14 为 `**版本：** v1.2.1 · **协议：** Apache-2.0 · 源于本科毕业设计，现作为长期维护的开源项目演进`——对外版本展示行，v1.3.0 收尾时须同步（父计划未列，见偏差 E-4）。README.en.md / SECURITY.md 无 v1.2.1 残留（SECURITY 已写 v1.3.x） | 已核对 |
| 14 | `docs/README.md` plan 索引区 :38-47：表头 `\| 文档 \| 说明 \|` + 分隔行 `\|------\|------\|`，链接用相对路径 `plan/xxx.md`；新行追加在 :47（phase-4-community 行）之后 | 已逐字核对 |
| 15 | 对标 JSON 快照精确数据（`.upgrade/research/benchmarking-20260716/`）：deepeval 16894★/Apache-2.0/v4.1.0(2026-07-12，tag v4.1.1 领先)；inspect_ai 2360★/MIT/无 GitHub Releases（日期式 tag `release/2025-11-28`）；guardrails 7157★/Apache-2.0/v0.10.2(2026-06-04)；NeMo-Guardrails 6717★/NOASSERTION（README 徽章声明 Apache-2.0）/v0.23.0(2026-07-01) | 已逐字段核对 |
| 16 | 四项目 README 门面观察：文档站链接 4/4 标配；Discord 仅 deepeval/guardrails（社群驱动型）；citation/arXiv 仅 NeMo；inspect_ai 零徽章（机构背书型）；徽章密度 guardrails≈NeMo > deepeval > inspect_ai | 快照 README 前 40 行归纳 |
| 17 | 本项目 README「生态定位」表（:39-45 附近，`### 生态定位` 三级标题）已定调：评估层/护栏层=互补、对话式顾问团=差异（确定性代码控制）；NeMo 链接用新组织路径 `github.com/NVIDIA-NeMo/Guardrails` | 已逐字核对 |
| 18 | 测试基线：651 collected；全量 650 passed, 1 skipped；e2e-mock 63 passed；`make typecheck` = Success in 153 files；doc-check 0 违规；工作树干净、HEAD=`f191e8a`（Wave D 收尾）、Wave A–D 全部已提交 | 2026-07-17 实测 |
| 19 | `.upgrade/MANIFEST.md` File Inventory 表末行为 wave-d 计划登记行（:74）；STATE.md 行（:56）备注仍写"Wave A–C 已完成"（漂移，E4 一并修正）。`codeql.yml` 共 23 行，`on:` 块 :3-6，cron `'22 3 * * 1'`，:4 注释预告"仓库公开后改 push/PR + weekly cron" | 已逐字核对 |
| 20 | 环境：Windows + Git Bash（`cp -f`、grep 管道可用）；所有目标文件 CRLF——**改既有文件一律先 Read 再 Edit，锚点逐字复制，不用 shell 重定向写文件**；新建文件用 Write 工具 | 环境实测 |

## 对父计划的六处记录性偏差（决策留档）

1. **E-1：Task 15 Step 1 "输出为空 = 通过"改为"输出仅含已知良性项 = 通过"。** 预扫描实测（基线 #7）命中 7 行，全部为演示凭据/模板占位符（父计划的排除正则不含 `demo` 和 `CHANGE_ME` 关键词所致）。执行者比对下文"已知良性清单"，逐条一致即通过；出现清单之外的命中才停下人工判断。不为迁就扫描结果修改排除正则（保持扫描灵敏度）。
2. **E-2：Task 16 范围补上标题承诺的"doc-check 转正"。** 父计划 Task 16 标题为"覆盖率产出 + mypy/doc-check 转正评估"但 Steps 只写了覆盖率。转正评估结论（基于基线 #2/#3）：**doc-check 转强制**（存量违规清零 + 远端 CI run #13 已观察，STATE.md Next Action #4 早已授权此步）；**mypy 保持 non-blocking**（该步骤从未在远端 CI 跑过——26 commits 未 push，"观察一轮"条件未满足，待公开后首轮远端全绿再转）。E2 落地 doc-check 翻转，mypy 结论写入 E1 报告与 STATE。
3. **E-3：Task 16 commit message 扩展**为 `ci: produce coverage report in CI job summary, promote doc-check to blocking`（覆盖 E-2 的额外改动，父计划原文只提覆盖率）。
4. **E-4：Task 18 文件清单补 `README.md`。** README :14 是对外版本展示行（基线 #13），bump 后不改会自相矛盾；`core/version.py` 的 `PACKAGE_STAGE` 同步改 `"v1.3.0"`（version_check 不校验它，但同文件不同步是明显疏漏）。`docs/acceptance_report.md` 中的 v1.2.1 为带日期的测试快照存档，**不改**。
5. **E-5：Task 18 Step 3 "待维护者手动操作"段落不存在。** STATE.md 无此字面标题（内容分散在 Blockers / Active Stage Report :81 / Next Action 三处）——E4 改为刷新 `## Next Action` 整节 + 修正两处既有漂移：:103 tag 期望值（实际零 tag，基线 #11）与 :107 "执行 Wave D"过时项。
6. **E-6：tag 打在 Wave 收尾 commit 上。** E4 分两个 commit（发布文件 commit + `.upgrade` 工作区收尾 commit），`git tag v1.3.0` 打在收尾 commit（HEAD）上，保证 tag 快照包含完整的升级留痕。push 与 GitHub Release 仍按父计划留待维护者确认后执行。

## 任务依赖图（严格串行）

```
E1（公开前安全扫描与检查清单，父计划 Task 15）
 └→ E2（CI 覆盖率 + doc-check 转强制，父计划 Task 16）
     └→ E3（生态定位与竞品分析文档，父计划 Task 17）
         └→ E4（v1.3.0 收尾：版本/CHANGELOG/STATE/MANIFEST/父计划勾选/终验/tag，父计划 Task 18，主控执行）

E5（CodeQL 触发器转正 + 徽章核验，父计划 Task 19）—— 前置条件：仓库已公开。本轮不执行，内容见附录。
```

**部署方式（用户已授权 Subagent-Driven）：** 并行探索已在制定本计划时完成（3 个并行调研 subagent + 主控实测预扫描）。执行阶段 E1–E3 虽然改动文件互不相交，但共享 git index 且各含 commit，**必须串行派发**——推荐每任务一个全新 subagent（携带该任务全文 + 探索基线 + 偏差记录），任务间主控 review + 核对 commit；E4 为版本与工作区收尾，由主控直接执行。

**全局纪律（每个任务适用）：**
- 禁止 `git add .`，逐文件显式 staging；提交前 `git status --short` 核对。
- 写入内容以本文件代码块为唯一事实来源；竞品数据只取基线 #15/#16（与 JSON 快照一致），不得凭记忆增补数字。
- 工作目录：仓库根（Git Bash 路径 `/d/BackendDevelopment/Project/Projest_Test-4/ai-workflow-premortem/ai-workflow-premortem/ai-workflow-premortem`），命令均在仓库根执行。
- 既有文件均 CRLF：先 Read 再 Edit（基线 #20）；新建文件用 Write。
- 每任务结束跑 `make lint`；改动涉及文档链接/make target 的任务跑 `make doc-check`。

---

## Task E1: 公开前安全扫描与检查清单（父计划 Task 15）

**背景：** 仓库将从私有转公开，公开不可逆（内容可能被缓存/索引）。本任务只产出**检查报告**，实际"点公开按钮"由维护者人工执行。预扫描已由主控完成（基线 #7-#9），执行者复跑确认并落账。

**Files:**
- Create: `.upgrade/reports/pre-publication-checklist-20260717.md`

- [x] **Step 1: 复跑全历史敏感信息扫描，比对已知良性清单**

```bash
git log --all -p | grep -inE "(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}" | grep -ivE "(example|placeholder|your[_-]|template|fixture|mock|test|<.*>|\{\{)" | head -50
git log --all -p | grep -inE "(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})" | head -20
```

**已知良性清单（偏差 E-1，预扫描 2026-07-17 实测）：**

| 命中内容 | 出处 | 判定 |
|---|---|---|
| `DEMO_PASSWORD = "demo-password-123"`（第一条命令，约 5 行，含 +/- diff 变体） | `scripts/live_e2e_four_stage.py:51` 本地 e2e 演示凭据，行尾有 `noqa: S105  # demo credential for local e2e, not a real secret` | 良性，无需处置 |
| `CHANGE_ME_sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`（第二条命令，约 2 行） | `secrets.example/deepseek_api_key` 模板占位符 | 良性，无需处置 |

Expected: 两条命令的输出**逐条落在上表内**（行号可不同，内容必须一致）。若出现表外命中：**立即停止本任务**，逐条人工判断；真实密钥需先在对应平台吊销、再评估是否需要历史重写（历史重写是破坏性动作，必须先向维护者确认）。

- [x] **Step 2: 工作区与敏感文件检查**

```bash
git status --short
git check-ignore -v secrets/ data/ .env 2>/dev/null
ls docs/internal/ 2>/dev/null && echo "WARNING: docs/internal exists (gitignored, confirm not committed)" || echo OK
git ls-files | grep -E "^docs/internal|^secrets/|\.env$" && echo "LEAK: tracked sensitive file" || echo OK
```

Expected（基线 #8 预核）：`git status --short` 仅出现本 Wave 计划外的 untracked 应为零（本计划文件自身在 E4 入库前会显示 untracked，属预期）；check-ignore 三行输出（`.gitignore:44 secrets/`、`.gitignore:77 data/`、`.gitignore:12 .env`）；后两条均输出 `OK`。

另核对两个**有意跟踪**的 env 文件（写入报告"已审查接受"段）：`.env.demo` 与 `.env.example` 被 `.gitignore:14-15` 显式豁免（`!.env.example` / `!.env.demo`），内含值全部为演示占位（`LLM_MODE=mock`、`JWT_SECRET=demo-only-local-secret-32-chars!!` 带"仅用于本地演示"注释、`DEEPSEEK_API_KEY=mock`）。

- [x] **Step 3: 提交邮箱核查**

```bash
git log --format="%ae %ce" | sort -u
```

Expected（基线 #9）：唯一一组 `3567039961@qq.com 3567039961@qq.com`。这是个人 QQ 邮箱——写入报告"维护者决策项"：可在 GitHub 开启 email privacy 并将本地 `git config user.email` 改为 `<id>+gome09@users.noreply.github.com`（只影响未来提交）；历史邮箱不追改（历史重写为破坏性动作，默认不做，仅提示）。

- [x] **Step 4: 用 Write 工具创建 `.upgrade/reports/pre-publication-checklist-20260717.md`（完整内容如下，三处 `<实测输出>` 用 Step 1–3 的实际输出回填）**

```markdown
# 公开前检查报告（2026-07-17）

> 父计划：`.upgrade/plans/2026-07-17-formal-project-uplift.md` Task 15；实施方案：`.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md` E1。
> 结论先行：**三项检查全部通过（含 2 类已知良性命中，判定留档如下），可以公开**。公开动作与后台配置由维护者按文末清单人工执行。

## 1. 全历史敏感信息扫描 — ✅ 通过（仅已知良性项）

- 密钥模式扫描（api_key/secret/password/token 赋值 + 排除模板类关键词）：命中 `DEMO_PASSWORD = "demo-password-123"` 共 <N> 行——`scripts/live_e2e_four_stage.py` 本地 e2e 演示凭据，源码行尾带 `noqa: S105 # demo credential for local e2e, not a real secret`，非真实密钥，无需处置。
- 高熵前缀扫描（sk- / ghp_ / AKIA）：命中 `CHANGE_ME_sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 共 <N> 行——`secrets.example/deepseek_api_key` 模板占位符，无需处置。
- 上述之外命中：**0**。无真实密钥，无需吊销，无需历史重写。

<实测输出>

## 2. 工作区与敏感文件检查 — ✅ 通过

- `secrets/`、`data/`、`.env` 均被 .gitignore 覆盖（:44 / :77 / :12）；`docs/internal/`、`secrets/` 目录不存在。
- `git ls-files` 无 `docs/internal`、`secrets/`、根 `.env` 被跟踪。
- 已审查接受的例外：`.env.demo` / `.env.example` 有意跟踪（`.gitignore` `!` 豁免），内含值全部为 mock/演示占位（JWT_SECRET 带"仅用于本地演示"注释）；`secrets.example/` 为模板目录，6 个文件均为 CHANGE_ME 占位。

<实测输出>

## 3. 提交邮箱核查 — ⚠️ 提示项（不阻塞公开）

- 全历史唯一提交邮箱：`3567039961@qq.com`（author = committer）。
- 维护者决策项：如不愿公开个人邮箱，可开启 GitHub email privacy（Settings → Emails → Keep my email addresses private）并将本地 `git config user.email` 改为 noreply 地址——只影响未来提交；历史邮箱无法追改（除非重写历史，默认不做）。

<实测输出>

## 4. CI 门槛转正评估结论（父计划 Task 16 标题承诺，Wave E 落账）

| 步骤 | 现状 | 结论 | 依据 |
|---|---|---|---|
| doc-check | non-blocking（ci.yml `continue-on-error`） | **本 Wave 转强制**（E2 落地） | 存量违规已清零；远端 CI run #13（2026-07-15）已观察一轮 |
| mypy typecheck | non-blocking | **暂不转强制** | 该步骤从未在远端 CI 运行（Wave B 后 26+ commits 未 push）；待公开后首轮远端 CI 全绿再移除 continue-on-error |
| pip-audit | non-blocking | 维持（本 Wave 不动） | 依赖漏洞告警需人工评估升级路径，转强制会被上游 CVE 披露节奏绑架 |

## 公开后维护者人工动作清单（按序）

0. **先 push**：`git push origin main --tags`（本地领先 origin/main 30+ commits，含 v1.3.0 tag；公开前后均可，公开时远端必须已是 v1.3.0 状态）。
1. Settings → General → 转 Public。
2. Settings → Branches → 按 `.upgrade/decisions/branch-protection.md` 开启 main 分支保护（Scorecard Branch-Protection 项依赖此步）。
3. Settings → Security → 启用 Private vulnerability reporting（SECURITY.md 与 issue config.yml 均指向此渠道）。
4. Settings → Security → 启用 Dependency graph / Dependabot alerts（公开仓库免费）。
5. `.github/workflows/codeql.yml`：把触发器从"仅手动+cron"改为加上 push/PR（文件内注释已预告此步；执行内容见实施方案附录 E5 / 父计划 Task 19）。
6. 手动 dispatch 一次 `scorecard.yml`，拿公开后首个真实分数，记入 `.upgrade/reports/`。
7. 核对 README 徽章全部渲染正常（CI/Scorecard 徽章需公开+首跑后才生效）。
8. 创建 GitHub Release v1.3.0（tag 已在本地打好；Release notes 直接复用 CHANGELOG v1.3.0 段），同时解决"0 release"的作品集短板。
9. 远端首轮 CI 全绿后：移除 ci.yml mypy 步骤的 `continue-on-error: true` 转强制（见上表）。
10. （可选）GitHub → About 栏填 description + topics：`ai-governance, premortem, risk-assessment, human-oversight, langgraph, llm-evaluation`。
```

- [x] **Step 5: 提交**

```bash
git status --short   # 预期仅 ?? .upgrade/reports/pre-publication-checklist-20260717.md（+ 本计划文件 untracked，E4 处理）
git add .upgrade/reports/pre-publication-checklist-20260717.md
git commit -m "chore: add pre-publication security scan results and post-publication action list"
```

---

## Task E2: CI 覆盖率产出 + doc-check 转强制（父计划 Task 16）

**Files:**
- Modify: `pyproject.toml`（dev 依赖加 pytest-cov）
- Modify: `uv.lock`（由 `uv lock` 再生成）
- Modify: `Makefile`（`.PHONY` + `test-cov` target）
- Modify: `.github/workflows/ci.yml`（unit tests 步骤 + doc-check 转强制）

**不需要的改动（已预核，防止画蛇添足）：** `.gitignore` 已含 coverage 三产物（基线 #5）；`[tool.coverage.run/report]` 已存在（基线 #4）——本任务**不加**任何 `[tool.coverage.*]` 配置、不加 pytest `addopts`。

- [x] **Step 1: pyproject.toml 加 pytest-cov 依赖**

先 Read `pyproject.toml`。用 Edit，`old_string`：

```
    "mypy>=1.14,<3",  # 基线在 2.3.0 测得；major 升级需重新核对基线
]
```

`new_string`：

```
    "mypy>=1.14,<3",  # 基线在 2.3.0 测得；major 升级需重新核对基线
    "pytest-cov>=6.0",  # CI 覆盖率产出（Wave E Task 16）
]
```

然后：

```bash
uv lock && uv sync --all-extras
```

Expected: lock 更新无报错；`uv run python -c "import pytest_cov; print('ok')"` 输出 `ok`。

- [x] **Step 2: Makefile 加 test-cov target**

先 Read `Makefile`。两处 Edit：

(a) `.PHONY` 行（:3），`old_string` 中的 ` typecheck test ` 片段替换——`old_string`：

```
.PHONY: install clean dev-db dev-api dev-frontend dev docker-up docker-down lint typecheck test setup setup-win prod-up prod-down prod-logs demo-api demo-frontend demo-ui lite-up e2e-mock e2e-full-test version-check doc-check audit security-check
```

`new_string`：

```
.PHONY: install clean dev-db dev-api dev-frontend dev docker-up docker-down lint typecheck test test-cov setup setup-win prod-up prod-down prod-logs demo-api demo-frontend demo-ui lite-up e2e-mock e2e-full-test version-check doc-check audit security-check
```

(b) `test:` 块之后（:76-78 与 :80 分隔线之间），`old_string`：

```
# 运行测试
test:
	uv run pytest tests/ -v

# ── 答辩验收 ────────────────────────────────────────────────────────────────
```

`new_string`（注意 recipe 行必须是 **Tab** 缩进，与既有 target 一致）：

```
# 运行测试
test:
	uv run pytest tests/ -v

# 带覆盖率的测试（CI 用；本地看行覆盖明细可加 --cov-report=html）
test-cov:
	uv run pytest tests/ --cov --cov-report=term --cov-report=xml -q

# ── 答辩验收 ────────────────────────────────────────────────────────────────
```

- [x] **Step 3: 本地验证覆盖率可跑**

```bash
make test-cov
uv run coverage report --format=markdown | head -5
```

Expected: 650 passed, 1 skipped（基线 #18，测试数不变）+ 末尾 `TOTAL ... NN%` 覆盖率表 + 生成 `coverage.xml`（`git status --short` 中**不**出现——已被 .gitignore 覆盖）；第二条命令输出 markdown 表格前几行（验证 CI job summary 用法可行）。

- [x] **Step 4: ci.yml unit tests 步骤改为带覆盖率 + job summary**

先 Read `.github/workflows/ci.yml`。用 Edit，`old_string`（:51-54，YAML 缩进逐字）：

```
      - name: Unit tests (sqlite + mock)
        run: |
          cp -f .env.demo .env
          uv run pytest tests/ -v
```

`new_string`：

```
      - name: Unit tests with coverage (sqlite + mock)
        run: |
          cp -f .env.demo .env
          make test-cov

      - name: Coverage summary to job summary
        if: always()
        run: |
          uv run coverage report --format=markdown >> "$GITHUB_STEP_SUMMARY" || true
```

> 不接 codecov 外部服务（父计划主动不做项：公开初期用 GitHub job summary 零依赖呈现，有需要再接）。

- [x] **Step 5: doc-check 转强制（偏差 E-2）**

同文件再一处 Edit，`old_string`（:43-45）：

```
      - name: Doc consistency check (non-blocking)
        run: make doc-check
        continue-on-error: true   # 初期观察，存量坏链清零后转强制
```

`new_string`：

```
      - name: Doc consistency check
        run: make doc-check
```

**mypy 的 `Type check (non-blocking)` 步骤（:39-41）保持原样不动**——转正条件未满足（从未在远端跑过，基线 #3），结论已写入 E1 报告第 4 节。

- [x] **Step 6: 回归 + 提交**

```bash
make lint && make doc-check
git status --short   # 预期 modified：pyproject.toml uv.lock Makefile .github/workflows/ci.yml
git add pyproject.toml uv.lock Makefile .github/workflows/ci.yml
git commit -m "ci: produce coverage report in CI job summary, promote doc-check to blocking"
```

Expected: lint clean；doc-check 0 违规（本任务新增 make target，未新增文档引用）。

---

## Task E3: 生态定位与竞品分析文档（父计划 Task 17）

**背景：** Task 0 归档的对标数据 + 父计划调研结论 #12（SynthBoard.ai 直接竞品、MIT AI Risk Repository v4 / AIID 候选数据源）沉淀为正式文档。**所有数字必须与基线 #15 一致（即与 JSON 快照一致），禁止凭记忆写数字。**

**Files:**
- Create: `docs/plan/ecosystem-positioning.md`
- Modify: `docs/README.md`（plan 索引区补一行）

- [x] **Step 1: 用 Write 工具创建 `docs/plan/ecosystem-positioning.md`（完整内容如下，逐字）**

```markdown
# 生态定位与竞品分析（2026-07）

> 文档定位：本项目作为长期开源产品的赛道坐标与差异化依据，供 README「生态定位」章节背书、未来 roadmap 输入与求职作品集叙事引用。
> 数据快照：2026-07-16 GitHub API 采集，原始数据见 `.upgrade/research/benchmarking-20260716/`（未随对外分发）。stars 等数字为采集日快照值，会随时间漂移，引用时以本文落款日期为准。
> 编写时间：2026-07-17。竞品事实来源：GitHub API 快照（一手）+ 2026-07-17 联网调研（父计划 `.upgrade/plans/2026-07-17-formal-project-uplift.md`"联网调研关键结论"#11/#12，二手来源已标注）。

---

## 1. 赛道地图

AI 可靠性工程可分三层，本项目占据最上游的"事前分析层"：

| 层 | 时机 | 代表项目 | 回答的问题 |
|------|------|------|------|
| **事前分析层（本项目）** | 立项阶段，写代码之前 | AI Workflow Premortem | 这个 AI 系统会在哪里失败？哪些决策必须有人审核？ |
| 评估层 | 开发/回归阶段 | deepeval、inspect_ai | 模型/系统在测试集上表现如何？ |
| 护栏层 | 运行时 | guardrails-ai、NeMo-Guardrails | 这一次的输入/输出是否越界？ |

### 相邻项目对照（2026-07-16 快照）

| 项目 | stars | License | 最新版本（发布日） | 发版节奏观察 |
|------|------|------|------|------|
| [deepeval](https://github.com/confident-ai/deepeval) | 16,894 | Apache-2.0 | v4.1.0（2026-07-12；tag v4.1.1 已领先 release） | 4.x 成熟期，高频发版，商业公司（Confident AI）驱动 |
| [guardrails-ai](https://github.com/guardrails-ai/guardrails) | 7,157 | Apache-2.0 | v0.10.2（2026-06-04） | 0.x，月度级节奏，社群（Discord）驱动 |
| [NeMo-Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | 6,717 | NOASSERTION（GitHub 未识别；README 徽章声明 Apache-2.0） | v0.23.0（2026-07-01） | 0.x，企业（NVIDIA）官方项目，含 arXiv 论文背书 |
| [inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | 2,360 | MIT | 日期式 tag `release/2025-11-28`（不使用 GitHub Releases） | 政府机构（UK AISI）驱动，文档站为中心 |

与 README「生态定位」章节的定调一致：评估层、护栏层与本项目均为**互补**关系，不构成竞争——本项目产出的 EvalCase 是"事前生成的假设检验"，可导出到评估框架持续回归；预验尸预测出的失败模式，可落地为运行时护栏的具体校验器。

## 2. 直接竞品

**SynthBoard.ai**（商业 SaaS，多智能体顾问团式 AI Pre-Mortem；来源：2026-07-17 联网调研，二手信息）——同样做"事前风险分析"，路线是对话式 AI 顾问团头脑风暴。

本项目差异化（架构级，非功能级）：

1. **确定性代码控制状态机**——工作流状态转换由代码决定，LLM 只生成分析内容，不自主决定流程跳转；顾问团类产品的流程由 LLM 对话驱动。
2. **风险自适应门禁**——LOW/MEDIUM/HIGH/CRITICAL 分档收紧通过条件，高风险项目未完成评估**无法**推进（阻断是设计而非缺陷）。
3. **审计与人工干预一等公民**——Evidence / SafetyFinding / EvalRun / InterruptRecord / ReportArtifact 均为结构化记录，可导出可追溯。
4. **可自部署开源**——Apache-2.0，离线 Mock 模式可完整跑通，不绑定 SaaS。

## 3. 互补集成机会（未来 roadmap 候选，本文档只记录不承诺）

- EvalCase 导出为 deepeval / inspect_ai 可消费格式（事前假设 → 持续回归）
- Stage 4 触发策略导出为 guardrails validator 配置骨架（预测失败模式 → 运行时校验器）
- MIT AI Risk Repository v4（1700+ 风险分类）/ AI Incident Database 作为 Stage 1 失败模式检索的候选数据源

## 4. 开源门面对标结论

对标四项目 README 门面标配元素（快照 README 前 40 行逐项核对）：

| 元素 | deepeval | guardrails | NeMo-Guardrails | inspect_ai | 本项目现状 |
|------|------|------|------|------|------|
| 徽章 | 有（社区/release） | 最密集（CI/coverage/PyPI/社群） | 最全 CI 矩阵 + arXiv | **无** | ✅ 已补齐（CI/License/Python/Scorecard，公开后生效） |
| 文档站链接 | ✅ | ✅ | ✅ | ✅ | 以 docs/ 目录承担（主动不做独立文档站） |
| 社区渠道（Discord 等） | Discord/Reddit | Discord/X | 无（官方文档站） | 无（官方文档站） | 无——单人维护期走 GitHub Issues（GOVERNANCE.md 已声明响应节奏） |
| 论文引用（citation） | 无 | 无 | ✅ arXiv | 无 | 无——主动不做项 |
| Logo/wordmark | ✅ | ✅ | 纯文字 | 机构 logo | 纯文字标题（可后补，低优先级） |

结论：徽章与文档链接为硬标配（已补齐）；社群渠道与 citation 在机构/企业驱动型项目（inspect_ai / NeMo）中同样缺席，单人项目不补不构成短板。inspect_ai 证明"零徽章 + 强文档"路线可行，但其有机构背书，本项目不具备，故保留徽章路线。
```

- [x] **Step 2: `docs/README.md` plan 索引区追加一行**

先 Read `docs/README.md`。用 Edit，`old_string`（现表末行，:47）：

```
| [plan/phase-4-community.md](plan/phase-4-community.md) | 阶段 4 实施计划：开源社区打磨（文档一致性 CI / 分支保护 / Scorecard 爬升） |
```

`new_string`：

```
| [plan/phase-4-community.md](plan/phase-4-community.md) | 阶段 4 实施计划：开源社区打磨（文档一致性 CI / 分支保护 / Scorecard 爬升） |
| [plan/ecosystem-positioning.md](plan/ecosystem-positioning.md) | 生态定位与竞品分析（2026-07 对标快照：赛道地图 / SynthBoard 差异化 / 门面对标结论） |
```

- [x] **Step 3: 校验 + 提交**

```bash
make doc-check && make lint
git status --short   # 预期：?? docs/plan/ecosystem-positioning.md + modified docs/README.md
git add docs/plan/ecosystem-positioning.md docs/README.md
git commit -m "docs: add ecosystem positioning and competitive analysis"
```

Expected: doc-check 0 违规（新文档的相对链接与反引号路径 `.upgrade/research/benchmarking-20260716/` 均存在——注意 doc-check 会校验反引号仓库路径，该目录已在 git 中）。

> ⚠️ 若 doc-check 对 `docs/plan/ecosystem-positioning.md` 内的反引号路径 `.upgrade/plans/2026-07-17-formal-project-uplift.md` 报"路径不存在"类违规（该文件此时已在仓库，应可通过；若因扫描规则误报），处置原则：改写文档内表述规避误报（如去掉反引号改为普通文字），**不修改 doc-check 脚本**。

---

## Task E4: v1.3.0 版本收尾（父计划 Task 18，主控执行）

**Files:**
- Modify: `core/version.py`（5 常量中 4 个 bump）
- Modify: `pyproject.toml`（:4 `version = "1.3.0"`）
- Modify: `README.md`（:14 版本展示行，偏差 E-4）
- Modify: `CHANGELOG.md`（v1.3.0 条目）
- Modify: `.upgrade/STATE.md`
- Modify: `.upgrade/MANIFEST.md`
- Modify: `.upgrade/plans/2026-07-17-formal-project-uplift.md`（勾选 Task 15–18 checkbox）
- Add: `.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md`（本文件）

- [x] **Step 1: bump 版本三件套**

先 Read `core/version.py`（7 行）。用 Edit 将全文替换——`old_string`：

```
APP_VERSION = "1.2.1"
REPORT_SCHEMA_VERSION = "1.2.1"
APP_STATUS = "release"
PACKAGE_STAGE = "v1.2.1"
```

`new_string`：

```
APP_VERSION = "1.3.0"
REPORT_SCHEMA_VERSION = "1.3.0"
APP_STATUS = "release"
PACKAGE_STAGE = "v1.3.0"
```

（`RUNTIME_VALIDATION = "local_pass"` 不动。）

`pyproject.toml` :4，Edit：`version = "1.2.1"` → `version = "1.3.0"`。

`README.md` :14，Edit——`old_string`：

```
**版本：** v1.2.1 · **协议：** Apache-2.0 · 源于本科毕业设计，现作为长期维护的开源项目演进
```

`new_string`：

```
**版本：** v1.3.0 · **协议：** Apache-2.0 · 源于本科毕业设计，现作为长期维护的开源项目演进
```

Run: `make version-check`
Expected: `Version metadata OK: 1.3.0`

- [x] **Step 2: CHANGELOG.md 插入 v1.3.0 条目（追溯说明之后、`## 维护记录 (2026-07-16)` 之前）**

先 Read `CHANGELOG.md` 前 30 行。用 Edit，`old_string`（:5-7 连续三行）：

```
> 其中 v0.1（2026-05-01）/ v0.5（2026-05-20）的日期早于可见最早 commit（2026-05-31），为里程碑回溯记录，非逐次提交日志。

## 维护记录 (2026-07-16)
```

`new_string`（中间插入 v1.3.0 段；**两处 `<N passed, M skipped>` 以 Step 4 终验的实际 `make test` 输出回填**——按基线 #18 预期为 650 passed, 1 skipped，若实际不同以实际为准）：

```
> 其中 v0.1（2026-05-01）/ v0.5（2026-05-20）的日期早于可见最早 commit（2026-05-31），为里程碑回溯记录，非逐次提交日志。

## v1.3.0 (2026-07-17)
- **正式个人项目升级（formal-project-uplift，Wave A–E）**：从"毕设闭环"提升为可对外公开的正式开源项目
  - **包名统一与可安装化（Wave A）**：`pyproject.toml` 包名 `ai-workflow-tool` → `ai-workflow-premortem`，补 license/authors/classifiers/urls 元数据 + hatchling build backend，`uv pip install -e .` 可用（发 PyPI 前需 src-layout 重构，主动不做）
  - **治理文件补齐（Wave A）**：CODE_OF_CONDUCT.md（Contributor Covenant 2.1）/ GOVERNANCE.md（单一维护者 BDFL）/ .github/CODEOWNERS / ISSUE_TEMPLATE config.yml（禁空白 issue + 安全报告导流）；SECURITY.md 报告渠道定稿（仅 GitHub 私密报告，支持版本表对齐 v1.3.x）
  - **README 门面改造（Wave A）**：徽章（CI/License/Python/Scorecard）+ origin story + 生态定位表 + 新增 README.en.md 英文门面
  - **mypy 渐进式类型检查（Wave B）**：inspect_ai 模式——全局宽松基线 108→0 + core.gates/graph 近 strict 13→0，`make typecheck` target + CI non-blocking 接入；修复一处真实 bug（不存在的 note= 关键字，latent TypeError）
  - **T3.6 LLM Judge（Wave C）**：`EVAL_LLM_JUDGE` / `EVAL_LLM_JUDGE_AUTOFINAL` 两 flag 默认 off；LLM 仅建议判分不终裁，HIGH/CRITICAL 会话永远待人工；`core/eval_llm_judge.py` + mock fixture + eval_runner 风险分层门控；spec governance-platform §5 翻转 Implemented
  - **合规映射 2026-07-17 复核落账（Wave D）**：ISO/IEC 42005:2025（AI 系统影响评估）对标说明入 iso42001-mapping.md 第 6 节；roadmap §10.7 复核增补（EU AI Act Omnibus 公报编号待回填 / TC260 二手来源限定 / NIST [存疑] 维持 / 两个国内新法规锚点）；三个 taxonomy docstring 盖二次复核戳
  - **公开前检查与 CI 增强（Wave E）**：全历史敏感信息扫描通过（仅演示凭据/模板占位良性命中，报告 `.upgrade/reports/pre-publication-checklist-20260717.md`）；CI 覆盖率产出（pytest-cov + `make test-cov` + job summary）；doc-check 转强制（mypy 维持 non-blocking 待远端首轮观察）；生态定位与竞品分析文档 `docs/plan/ecosystem-positioning.md`
- **新增测试**：tests/test_llm_judge_v130.py 8 条（Wave C）
- **测试验证**：<N passed, M skipped>（全量，mock+SQLite）；lint/format/typecheck/doc-check/version-check 全绿；e2e-mock 63 passed
- **实施计划**：`.upgrade/plans/2026-07-17-formal-project-uplift.md`（父计划）+ Wave A–E 五份实施方案

## 维护记录 (2026-07-16)
```

- [x] **Step 3: 更新 `.upgrade/STATE.md`（六处 Edit，先 Read 全文）**

(a) `## Current Phase`（:5）——`old_string`（行尾子串）：

```
；下一步 Wave E（公开前检查与 CI 收尾，Task 15–18），Task 19 待仓库公开后执行。
```

`new_string`：

```
；**Wave E 已完成（Task 15–18，实施方案 `.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md`），formal-project-uplift 全部收尾，v1.3.0 已 bump + tag**。Task 19（CodeQL 转正）待仓库公开后执行。
```

(b) `## Current Task`（:9）——`old_string`：

```
**计划执行中**：`.upgrade/plans/2026-07-17-formal-project-uplift.md`
```

`new_string`：

```
**计划已完成（Task 19 除外，待公开后）**：`.upgrade/plans/2026-07-17-formal-project-uplift.md`
```

同行的 `**Wave A（...）与 Wave D（合规映射复核落账，Task 13–14）已完成**，下一步 Wave E（Task 15–18）。` Edit 为 `**Wave A–E（Task 0–18）全部完成**。`

(c) `## Last Completed` 顶部（:13 Wave D 条目之前）插入（`<E1>`–`<E4b>` 用 `git log --oneline -6` 实际短哈希回填；E4 的两个哈希在 Step 5/6 提交后补——**可先提交再回填本行所在文件属于收尾 commit 自身，故 E4b 哈希写"本 commit"即可**）：

```markdown
- **Wave E 公开前检查与 CI/发布收尾 (2026-07-17)**：公开前全历史敏感信息扫描通过（仅 DEMO_PASSWORD 演示凭据 + secrets.example 占位符两类良性命中，报告含公开后 10 步人工动作清单）；CI 覆盖率产出（pytest-cov + make test-cov + GitHub job summary，不接 codecov）；doc-check 转强制、mypy 维持 non-blocking（从未在远端跑过，转正条件未满足——评估结论见报告第 4 节）；docs/plan/ecosystem-positioning.md 生态定位文档（赛道三层地图 / SynthBoard.ai 差异化 / 门面对标结论，数字与 2026-07-16 JSON 快照逐字段一致）；v1.3.0 收尾（version 三件套 + README :14 + CHANGELOG + tag v1.3.0 打在收尾 commit）。对父计划六处记录性偏差（预扫描良性清单 / doc-check 转正范围 / commit message / README 版本行 / STATE 段落名 / tag 位置）见实施方案。commits: <E1>/<E2>/<E3>/<E4a>+本 commit。实施计划：`.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md`。
```

(d) `## Validation Commands`（:103）——`old_string`：

```
- `git tag --list` (expect `v1.0.2`, `v1.0.3`, `v1.1.0`, `v1.2.0`)
```

`new_string`：

```
- `git tag --list` (expect `v1.3.0`；历史 tag v1.0.x–v1.2.0 在仓库整理时未保留，见 CHANGELOG 追溯说明)
```

(e) `## Next Action` 整节（:107-110 四行）替换为：

```markdown
1. **维护者手动操作（公开序列）**：按 `.upgrade/reports/pre-publication-checklist-20260717.md` 文末清单执行——push（含 tags）→ 转 Public → 分支保护 → Private vulnerability reporting → Dependabot → CodeQL 转正（Task 19）→ Scorecard dispatch → 徽章核验 → GitHub Release v1.3.0
2. **远端首轮 CI 全绿后**：移除 ci.yml mypy 步骤 `continue-on-error: true` 转强制
3. **2026-08 下旬强制复核点**：《未成年人 AI 应用安全指南》征求意见截止（2026-08-16）后核对定稿内容（roadmap §10.7）
```

(f) `## Last Updated`（:114-116）替换为：

```markdown
- Date: 2026-07-17
- By: claude-code (Wave E publication readiness & v1.3.0 release closeout)
- Summary: formal-project-uplift Wave A–E 全部完成：公开前扫描通过、CI 覆盖率 + doc-check 转强制、生态定位文档、v1.3.0 bump + tag。仓库处于"待维护者点公开按钮"状态，公开后动作清单见 pre-publication-checklist 报告。
```

- [x] **Step 4: 更新 `.upgrade/MANIFEST.md`（两处 Edit，先 Read）**

(a) File Inventory 表 STATE.md 行（:56）备注刷新——`old_string`：

```
| `.upgrade/STATE.md` | active | permanent | 当前升级状态（Phase 0-4 全部完成；formal-project-uplift Wave A–C 已完成，目标 v1.3.0） |
```

`new_string`：

```
| `.upgrade/STATE.md` | active | permanent | 当前升级状态（Phase 0-4 全部完成；formal-project-uplift Wave A–E 全部完成，v1.3.0 已发布待公开） |
```

(b) 表末尾（wave-d 行 :74 之后）追加两行：

```markdown
| `.upgrade/reports/pre-publication-checklist-20260717.md` | active | keep-until-superseded | Wave E 公开前安全扫描报告（三项检查通过 + 已知良性命中判定留档 + 公开后 10 步人工动作清单 + CI 门槛转正评估结论） |
| `.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md` | active | permanent | Wave E 公开前检查与 CI/发布收尾实施计划（E1–E4 + 附录 E5，含 20 条探索基线与六处对父计划的记录性偏差决策） |
```

- [x] **Step 5: 勾选父计划 Task 15–18 的 checkbox 并提交发布文件**

在 `.upgrade/plans/2026-07-17-formal-project-uplift.md` 中把 Task 15（5 个）、Task 16（5 个）、Task 17（3 个）、Task 18（5 个）共 18 个 `- [ ] **Step N...` 翻为 `- [x]`（逐个 Edit，携带前后行唯一锚定；Task 19 的 3 个**不勾**——未执行）。

然后终验 + 发布 commit：

```bash
make lint && make typecheck && make version-check && make doc-check && make test && make e2e-mock
```

Expected: lint clean；typecheck Success；`Version metadata OK: 1.3.0`；doc-check 0 违规；全量 650 passed, 1 skipped（数字回填 CHANGELOG Step 2 的 `<N passed, M skipped>`）；e2e-mock 63 passed。**任何失败先修复再继续。**

```bash
git status --short   # 核对：core/version.py pyproject.toml README.md CHANGELOG.md 为 modified
git add core/version.py pyproject.toml README.md CHANGELOG.md
git commit -m "chore: release v1.3.0 — formal project uplift (governance, typing, LLM judge, compliance refresh)"
```

- [x] **Step 6: 工作区收尾 commit + 打 tag（偏差 E-6：tag 打在收尾 commit）**

回填 STATE.md Wave E 条目中的 commit 哈希（`git log --oneline -6`），然后：

```bash
git status --short   # 预期：.upgrade/STATE.md .upgrade/MANIFEST.md 父计划 + ?? 本计划文件
git add .upgrade/STATE.md .upgrade/MANIFEST.md .upgrade/plans/2026-07-17-formal-project-uplift.md .upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md
git commit -m "docs: close out Wave E and formal project uplift in upgrade workspace records"
git tag v1.3.0
git tag --list   # 预期输出：v1.3.0
```

> push 与 GitHub Release 创建在维护者确认后进行（`git push origin main --tags`；Release notes 直接复用 CHANGELOG v1.3.0 段）。首个 GitHub Release 建议在仓库公开后创建，同时解决"0 tag 0 release"的作品集短板。

---

## 附录 E5:（公开后）CodeQL 触发器转正 + 徽章核验（父计划 Task 19，本轮不执行）

**前置条件：** 维护者已完成 pre-publication-checklist 清单第 0–4 步（已 push、仓库已公开）。届时另行执行，此处备好精确改法。

- [ ] **Step 1: `codeql.yml` 触发器改造**

先 Read `.github/workflows/codeql.yml`（23 行）。用 Edit，`old_string`（:3-6，注释逐字）：

```
on:
  workflow_dispatch:   # 阶段 1 先手动触发；仓库公开后改 push/PR + weekly cron
  schedule:
    - cron: '22 3 * * 1'  # 每周一 03:22 UTC
```

`new_string`（保留原 cron 时间 `22 3 * * 1`）：

```
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '22 3 * * 1'  # 每周一 03:22 UTC
  workflow_dispatch:
```

- [ ] **Step 2: 核验 README 徽章**：CI / Scorecard 徽章渲染出真实状态；Scorecard 徽章若因未跑过而 404，手动 dispatch `scorecard.yml` 一次。

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/codeql.yml
git commit -m "ci: enable CodeQL on push/PR now that the repository is public"
```

---

## Self-Review 核对记录（制定时完成）

1. **父计划覆盖**：Task 15 Step 1→E1 Step 1、Step 2→E1 Step 2、Step 3→E1 Step 3、Step 4→E1 Step 4、Step 5→E1 Step 5；Task 16 Step 1→E2 Step 1、Step 2→E2 Step 2、Step 3→E2 Step 3、Step 4→E2 Step 4、Step 5→E2 Step 6（+标题承诺的转正评估→E2 Step 5 与 E1 报告第 4 节，偏差 E-2）；Task 17 Step 1→E3 Step 1、Step 2→E3 Step 2、Step 3→E3 Step 3；Task 18 Step 1→E4 Step 1、Step 2→E4 Step 2、Step 3→E4 Step 3-4、Step 4→E4 Step 5（终验）、Step 5→E4 Step 5-6；Task 19→附录 E5（本轮不执行，与父计划一致）。父计划全局约束（STATE 更新/显式 staging/lint/doc-check）→ E4 与各任务收尾步。无遗漏。
2. **占位符扫描**：报告模板中 `<实测输出>`/`<N>` 与 CHANGELOG 的 `<N passed, M skipped>`、STATE 的 `<E1>`-`<E4a>` 均为执行时回填项，已逐处注明回填来源与预期值；无 TBD/TODO/"适当处理"。
3. **一致性**：`test-cov` 命名在 Makefile `.PHONY`/target/ci.yml 三处一致；`pre-publication-checklist-20260717.md` 文件名在 E1 Step 4/5、E4 STATE/MANIFEST、CHANGELOG 五处一致；本计划文件名 `2026-07-17-wave-e-publication-ci-implementation.md` 在 E1 报告头、E4 STATE/MANIFEST/staging 四处一致；竞品数字与基线 #15 逐字段一致（16894/7157/6717/2360、v4.1.0/v0.10.2/v0.23.0/`release/2025-11-28`）；版本号 1.3.0 在 version.py 4 常量/pyproject/README :14/version-check 期望输出一致。E3 门面对标表初稿的 "covergae" 笔误已在定稿前更正为 "coverage"。

