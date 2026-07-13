# 阶段 0 详细设计方案：仓库治理最小闭环

> 关系定位：本文档是 [phase-0-repo-governance.md](phase-0-repo-governance.md)（实施计划 / 任务清单 + 验收标准）的**落地设计层**——给出每个任务的具体文件内容草稿、配置参数、决策依据、执行顺序与并行策略、风险。
> 配套规格：[../spec/supply-chain-security.md](../spec/supply-chain-security.md)（第 2、3 节为本方案 T0.4 / T0.5 的设计源头）。
> 现状核实日期：2026-07-13（全部条目经代码仓库直接实测，非估算）。
> 状态：设计完成，待用户决策 4 项后可启动执行。

---

## 1. 现状复核（对实施计划基线表的修正与补充）

实施计划 §2 的基线表已核实准确，本节补充 5 项实测发现，其中第 1 项直接影响 T0.8 设计：

| 项 | 实施计划基线 | 2026-07-13 实测补充 |
|---|---|---|
| Git tag | ❌ 无 | `git tag --list` 为空，确认。本地 `main` 最近 5 次提交均为 docs/chore 类，HEAD = `e7404ad` |
| 远程仓库 | 未提及 | `origin = git@github.com:gome09/ai-workflow-premortem-pure.git`，**已推送 GitHub**，T0.7 Scorecard CLI 具备执行前提（需确认仓库是否 public） |
| `.upgrade/reports/` | 未提及 | **已存在**（含 `release_manifest_v1.0.md`），T0.7 基线报告目标路径 `.upgrade/reports/scorecard-baseline-20260713.md` 无需新建目录 |
| CHANGELOG 版本覆盖 | 描述为「v0.1 / v0.5」 | 实际已含 `v1.0 (2026-06-10)` / `v1.0.2` / `v1.0.1` / `v0.5` / `v0.1`；T0.6 追溯说明需覆盖 v0.1–v0.7 早期「无 commit 证据」缺口，而非仅 v0.1/v0.5 |
| **版本元数据一致性（关键）** | 未识别 | ⚠️ `CHANGELOG.md` 最新 = `v1.0.2`，但 [core/version.py](../../core/version.py) `APP_VERSION="1.0.0"` / `PACKAGE_STAGE="v1.0.0"` 与 [pyproject.toml](../../pyproject.toml) `version="1.0.0"` 均为 1.0.0；[scripts/version_check.py](../../scripts/version_check.py) 只校验 version.py↔pyproject.toml 一致（当前均 1.0.0 → 通过），**不校验 CHANGELOG**；README 首屏版本声明 `v1.0`。三方漂移 |

### 关键发现影响：T0.8 设计需修正

实施计划 T0.8 原文「对当前 HEAD 补挂 `v1.0.2` annotated tag（与 CHANGELOG 最新版本对齐）」**若直接执行会制造新的不一致**：tag=v1.0.2 而 code=1.0.0。

正确设计：**先 bump 代码版本元数据到 1.0.2（让 version-check 仍绿），再打 tag**。详见 §2.8。

---

## 2. 任务级详细设计

### T0.1 LICENSE【阻塞：需用户决策 — 设计给出决策树】

**决策树**（不代为决定，见路线图 §8 问题 1）：

| 协议 | 适合场景 | 对本项目影响 | 依赖兼容性 |
|---|---|---|---|
| MIT | 希望被企业无阻力采用、允许闭源二次分发 | 最宽松，无专利条款 | 项目依赖（LangGraph MIT/Apache、FastAPI MIT 等）均兼容 |
| **Apache 2.0** | 含算法逻辑、希望提供显式专利授权 | 防止专利诉讼，对企业采用更稳妥 | 与所有主流依赖兼容 |
| AGPL-3.0 | 防止闭源 SaaS 二次分发、强 copyleft | 限制商业化采用，可能劝退企业内部使用 | 与 MIT/Apache 依赖兼容，但下游组合受限 |

**落地动作**（决策后）：
1. 根目录新建 `LICENSE`，内容为 OSI 官方协议全文（从 https://opensource.org/license 取 MIT/Apache-2.0/AGPL-3.0 对应全文，不做修改）。
2. `README.md` 首屏「版本：v1.0」一行下追加协议声明，例如：
   ```
   **协议：** Apache-2.0（示例，待决策后替换）
   ```
3. 若选 Apache 2.0，仓库根目录可补 `NOTICE` 文件（可选，本项目无第三方需归档的 NOTICE 义务，可不做）。

**验收**：LICENSE 存在且为 OSI 全文；README 首屏声明协议类型。

**工作量**：S（决策后 10 分钟）。

---

### T0.2 SECURITY.md

**完整内容草稿**：

```markdown
# 安全策略

## 报告漏洞

我们高度重视本项目安全问题。如发现漏洞，请通过以下**私有**渠道报告，勿在公开 Issue 中提交漏洞细节：

- **首选**：GitHub Security Advisories（仓库 Security 标签页 → Report a vulnerability）。该渠道端到端私有，支持协作修复与 CVE 申请。
- **备选**：发送邮件至 <SECURITY_EMAIL>（待维护者填入真实邮箱），主题加前缀 `[SECURITY]`。

## 支持的版本范围

| 版本 | 是否支持 |
|---|---|
| v1.0.x | ✅ |
| < v1.0 | ❌ |

## 响应承诺

- 收到报告后 **7 个自然日内**确认接收。
- 评估期间保持与报告者沟通，修复后发布安全公告与致谢（如报告者同意）。

## 不在范围内

- 通过 DeepSeek / Tavily 等第三方 API 触发的问题，请直报对应厂商。
- 本项目在 `LLM_MODE=mock` 演示模式下的非生产路径问题。
- 已在最新版本修复且已发布的问题。
```

**设计说明**：
- 渠道以 GitHub Security Advisories 为主——**无需用户提供邮箱即可落地**（邮箱为可选项，留占位 `<SECURITY_EMAIL>` 待用户决定是否填）。
- 响应承诺「7 天」对齐实施计划「个人项目建议承诺 7 天内确认」。
- 「支持的版本范围」与当前唯一发行线 v1.0.x 一致。

**验收**：文件存在、渠道真实可用、内容非模板占位。

**需用户决策**：是否提供真实安全联系邮箱（不提供则仅保留 GitHub Security Advisories 渠道）。

---

### T0.3 CONTRIBUTING.md

**完整内容草稿**（所有命令已与 [Makefile](../../Makefile) 实测对齐）：

```markdown
# 贡献指南

感谢你考虑为 AI 工作流预验尸平台贡献代码！本指南帮助你快速参与。

## 开发环境搭建

见 [docs/local_setup.md](docs/local_setup.md)。最快方式（离线 Mock + SQLite，零外部依赖）：

```bash
cp .env.demo .env
uv sync --all-extras --frozen
uv run uvicorn api.main:app --reload --port 8000
```

## 提交前检查

每次提交前请本地运行以下三步，CI 会执行相同检查：

```bash
make lint            # ruff check + ruff format --check
make test            # uv run pytest tests/ -v
make version-check   # pyproject.toml 与 core/version.py 版本一致性
```

> `make e2e-mock` 可跑离线场景验收（注册、Mock LLM、流程），约 5 秒。

## 分支与提交约定

- 从 `main` 拉分支，命名：`feat/<topic>` / `fix/<topic>` / `docs/<topic>` / `chore/<topic>`。
- Commit message 遵循 Conventional Commits（与现有历史一致）：
  - `feat:` 新功能 / `fix:` 缺陷修复 / `docs:` 文档 / `chore:` 杂项 / `refactor:` 重构
  - 示例：`fix: 联通红队测试覆盖门控与人工动作状态`
- 一个 PR 聚焦一件事；大改动拆分为多个小 PR。

## 测试约定

- 测试位于 `tests/`，使用内存存储 + monkeypatched LLM，**不依赖** PostgreSQL / Redis / 外部 API Key。
- 新增功能须附带测试；bug 修复须附回归测试。
- `pytest` 配置见 `pyproject.toml`（`asyncio_mode = "auto"`）。

## PR 流程

1. 确保本地三步检查全绿。
2. PR 描述说明：动机、改动点、测试方式。
3. 等待 CI（lint + 单测 + docker-lite 集成冒烟）通过后合并。
4. 个人项目无强制第二人 review，但鼓励自我 review 后再合。
```

**设计说明**：
- 引用的 `make lint` / `make test` / `make version-check` / `make e2e-mock` 均在 Makefile 中存在（已核实）。
- Commit 约定与 `git log` 实测风格（`docs:` / `fix:` / `chore:`）一致。
- 测试约定引用 `pyproject.toml` 实际配置。

**验收**：文件存在且引用命令均可运行。

---

### T0.4 CI 权限最小化

**具体改动**：在 [ci.yml](../../.github/workflows/ci.yml) 顶层 `on:` 块与 `concurrency:` 块之间插入显式 `permissions`：

```yaml
on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

**设计约束**（对齐 spec §2）：
- 两个 job（`lint-and-unit-tests`、`docker-lite-integration`）均只需 `contents: read`，收紧无副作用。
- 未来 SAST（CodeQL）workflow 需 `security-events: write` → 在**该 workflow 内**单独声明，不放宽 `ci.yml`。
- 未来自动发布 workflow 需 `contents: write` → 同理单独声明。

**验收**：workflow 顶层有显式 `permissions: contents: read`；CI 全绿。

---

### T0.5 dependabot.yml

**完整文件内容**（直接采用 spec §3 模板）：

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"          # uv 项目按 pip 生态识别 pyproject.toml
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      minor-and-patch:
        update-types: ["minor", "patch"]
    open-pull-requests-limit: 5
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

**设计权衡**（对齐 spec §3）：
- **分组小版本**：minor/patch 合并为单 PR，major 单独开 PR 逐个评审——个人维护场景控噪关键。
- `pyproject.toml` 26 处 `>=` 下限 + `uv.lock` 锁定的组合**保持不变**：可复现性由 lock 保证，声明文件保持宽松便于依赖解析。**不为** Scorecard Pinned-Dependencies 项改精确 pin（会与 uv 工作流冲突）。
- `open-pull-requests-limit: 5` 防止 PR 堆积。

**验收**：`.github/dependabot.yml` 存在且推送后 GitHub 后台 Dependabot 已激活。

---

### T0.6 CHANGELOG 追溯说明

**插入位置**：`CHANGELOG.md` 第 1 行 `# Changelog` 标题下、第一个版本条目（`## v1.0`）上。

**说明文字草稿**：

```markdown
# Changelog

> **历史追溯说明**：v0.1–v0.7 阶段的详细提交历史因仓库整理未完整保留于本地 `main` 分支。
> 远程 `origin`（github.com/gome09/ai-workflow-premortem-pure）保有 2026-05-31 起的完整提交历史（21 次提交），如需追溯请查阅远程分支。
> 其中 v0.1（2026-05-01）/ v0.5（2026-05-20）的日期早于可见最早 commit（2026-05-31），为里程碑回溯记录，非逐次提交日志。

## v1.0 (2026-06-10)
...
```

**设计说明**：
- 表述与事实一致（不夸大「完整保留」也不回避「本地丢失」），是对路线图 §1 所述「叙事与可验证证据缺口」的诚实修复。
- 同时纠正实施计划基线表「v0.1/v0.5」的措辞——实际早期里程碑范围是 v0.1–v0.7。

**验收**：说明文字已入库；表述与事实一致。

---

### T0.7 OpenSSF Scorecard 基线扫描

**前置条件**：
- 仓库已推送 GitHub（已确认）。
- **需确认仓库是否 public**：Scorecard CLI 对 public 仓库免鉴权直接跑；private 仓库需 GitHub PAT。
- 本地安装 scorecard CLI（`go install` 或下载 Release 二进制）+ 准备 GitHub PAT（`repo` scope，public 仓库可只用 public_repo）。

**执行命令**：

```bash
scorecard --repo=gome09/ai-workflow-premortem-pure \
  --format=json --show-details \
  > .upgrade/reports/scorecard-baseline-20260713.json
# 同时生成可读 Markdown 摘要
scorecard --repo=gome09/ai-workflow-premortem-pure \
  --format=html --show-details \
  > .upgrade/reports/scorecard-baseline-20260713.html
```

**存档产物**：`.upgrade/reports/scorecard-baseline-20260713.md`（人工整理的 18 项逐项分数 + 总分 + 人工确认项），原始 JSON/HTML 作为附件。

**人工确认项**（本地无法检测，需登录 GitHub 后台记录进基线报告）：
- main 分支是否开启 Branch Protection（required status checks）
- 是否强制 Code Review / PR before merge
- 仓库可见性（public / private）

**设计说明**（对齐 spec §6）：
- Scorecard v5.5.0（2026-04）起支持按仓库类型跳过不适用检查。
- 部分项（CI-Tests、Contributors、Dependency-Update-Tool）在公共周扫描中不计分，本地 CLI 全量跑一次才能拿完整基线。
- **建议放最后执行**：让 T0.4（Token-Permissions）、T0.5（Dependency-Update-Tool）、T0.2（Security-Policy）、T0.1（License）的改进先反映到分数里。

**验收**：基线报告存档，含总分与逐项分数；阶段 4 以此为对照基线。

**工作量**：M（含环境准备）。

---

### T0.8 Git tag 补挂【设计方案修正实施计划】

> ⚠️ 本节是对实施计划 T0.8 的设计修正，原因见 §1 关键发现。

**问题**：实施计划假设「直接打 v1.0.2 tag 对齐 CHANGELOG」，但实测代码版本元数据 = 1.0.0。直接打 tag 会造成 tag↔code 不一致。

**修正后两步执行**：

**步骤 1 — bump 版本元数据到 1.0.2**（让 `make version-check` 仍绿）：

| 文件 | 现值 | 改为 |
|---|---|---|
| [core/version.py](../../core/version.py) `APP_VERSION` | `"1.0.0"` | `"1.0.2"` |
| [core/version.py](../../core/version.py) `PACKAGE_STAGE` | `"v1.0.0"` | `"v1.0.2"` |
| [pyproject.toml](../../pyproject.toml) `version` | `"1.0.0"` | `"1.0.2"` |
| [README.md](../../README.md) 首屏 `**版本：**` | `v1.0` | `v1.0.2` |

> `REPORT_SCHEMA_VERSION` 维持 `"1.0.0"` 不动——它是报告 schema 版本，与 APP 发版解耦，version_check.py 会校验它也必须等于 APP_VERSION，因此**必须一并改为 1.0.2** 以保持 check 通过。

**修正上表**：`REPORT_SCHEMA_VERSION` 也需改为 `"1.0.2"`（version_check.py 第 50 行要求三值全等，否则 fail）。

执行后验证：

```bash
make version-check   # 期望输出: Version metadata OK: 1.0.2
```

**步骤 2 — 打 annotated tag**：

```bash
git tag -a v1.0.2 -m "v1.0.2: 红队测试覆盖门控与人工动作状态联通修复（含 v1.0.1 E2E 测试脚本与证据门控修复）"
git push origin v1.0.2
```

**设计说明**：
- CHANGELOG v1.0.1 / v1.0.2 对应的修复（commit `4c65ff5` 等）已在代码中，代码功能上确为 v1.0.2，只是版本元数据未同步——bump 是修正而非新发版。
- 签名（Signed Releases）留到阶段 4，本阶段不做。
- tag message 概括 v1.0.1 + v1.0.2 两版内容（v1.0.1 未打 tag，一并补追溯说明）。

**验收**：`git tag --list` 非空且含 `v1.0.2`；`make version-check` 通过；tag ↔ version.py ↔ pyproject.toml 三者一致。

---

## 3. 执行顺序与并行策略（Subagent-Driven）

### 依赖关系

```
并行批次 1（互相独立，可并行 subagent）：
  T0.2 SECURITY.md
  T0.3 CONTRIBUTING.md
  T0.4 CI permissions
  T0.5 dependabot.yml
  T0.6 CHANGELOG 追溯说明
  T0.8 版本 bump + tag（含 README 版本号）

T0.1 LICENSE — 等待用户协议决策，不阻塞其他任务

T0.7 Scorecard — 串行最后跑（让前面改进先反映到分数）
```

### 文件冲突分析（并行安全前提）

| 任务 | 改动文件 | 冲突风险 |
|---|---|---|
| T0.2 | 新建 `SECURITY.md` | 无 |
| T0.3 | 新建 `CONTRIBUTING.md` | 无 |
| T0.4 | 改 `ci.yml` | 无 |
| T0.5 | 新建 `.github/dependabot.yml` | 无 |
| T0.6 | 改 `CHANGELOG.md`（头部插说明） | ⚠️ 与 T0.8 无直接冲突（T0.8 不改 CHANGELOG），但若 T0.8 顺带补 tag 说明则需协调 |
| T0.8 | 改 `core/version.py` / `pyproject.toml` / `README.md` | 无（与其他任务无交集） |

**结论**：批次 1 六个任务**文件级无冲突**，可安全并行。T0.6 与 T0.8 改不同文件，无需串行。

### Subagent 分工建议（用户授权执行时）

| Agent | 负责任务 | 改动文件 |
|---|---|---|
| Agent A（文档） | T0.2 + T0.3 + T0.6 | `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` |
| Agent B（CI 配置） | T0.4 + T0.5 | `ci.yml`, `.github/dependabot.yml` |
| Agent C（版本/tag） | T0.8 | `core/version.py`, `pyproject.toml`, `README.md` + git tag |
| Agent D（基线） | T0.7（串行，A/B/C 完成后启动） | `.upgrade/reports/scorecard-baseline-20260713.*` |

**执行后统一校验**：
- `git status --short` 检查改动范围
- `make lint && make test && make version-check` 三步全绿
- `git tag --list` 含 v1.0.2
- 提交策略：按 AGENTS.md 要求显式 `git add <file>`，**禁用** `git add .`；每任务一个 commit 或批次合并 commit 均可。

---

## 4. 风险与注意事项

| 风险 | 来源 | 缓解 |
|---|---|---|
| T0.4 权限收紧后未来 workflow 需写权限 | spec §2 | 在该 workflow 内单独声明，不放宽 ci.yml 全局默认 |
| Dependabot PR 维护负担 | T0.5 | 分组策略（minor/patch 合并）控噪；limit: 5 防堆积 |
| Scorecard 部分项不计分 | T0.7 | 本地 CLI 全量跑，不依赖公共周扫描 |
| 版本 bump 破坏 version-check | T0.8 | 三字段（APP_VERSION / REPORT_SCHEMA_VERSION / pyproject）必须同步改为 1.0.2 |
| 仓库可见性未知 | T0.7 | 需用户确认 public/private；private 需 PAT |
| CHANGELOG 早期日期无 commit 证据 | T0.6 | 追溯说明已诚实标注「里程碑回溯记录」 |

---

## 5. 验收清单（对齐实施计划 §6，补充实测校验点）

- [ ] LICENSE / SECURITY.md / CONTRIBUTING.md 三个文件都存在且内容非模板占位
- [ ] `ci.yml` 有显式 `permissions: contents: read` 最小化声明且 CI 全绿
- [ ] `.github/dependabot.yml` 已激活（GitHub 后台可见）
- [ ] CHANGELOG 头部有历史追溯说明
- [ ] Scorecard CLI 量化基线报告已存档至 `.upgrade/reports/`
- [ ] 当前版本已打 git tag（v1.0.2）
- [ ] **（新增）** `make version-check` 通过，输出 `Version metadata OK: 1.0.2`
- [ ] **（新增）** tag ↔ `core/version.py` ↔ `pyproject.toml` 三者版本一致
- [ ] **（新增）** README 首屏版本号与代码版本一致（v1.0.2）

---

## 6. 需用户决策项

1. **LICENSE 协议**：MIT / Apache 2.0 / AGPL-3.0（阻塞 T0.1，不阻塞其他任务）。
2. **SECURITY.md 联系邮箱**：是否提供真实安全邮箱（不提供则仅保留 GitHub Security Advisories 渠道）。
3. **GitHub 仓库可见性**：public / private（影响 T0.7 Scorecard 鉴权方式与阶段 1 CodeQL 可用性）。
4. **是否授权启动执行**：按本设计方案 Subagent-Driven 并行推进批次 1（T0.2/T0.3/T0.4/T0.5/T0.6/T0.8），T0.7 串行收尾。
