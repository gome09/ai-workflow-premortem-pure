# OpenSSF Scorecard 趋势报告

> 仓库：gome09/ai-workflow-premortem-pure
> 报告日期：2026-07-14
> 基线对照：[../archive/scorecard-baseline-20260713.md](../archive/scorecard-baseline-20260713.md)（2026-07-13，已归档）
> 扫描机制：`.github/workflows/scorecard.yml`（weekly cron + 手动触发）
> 用途：Phase 4 T4.3 验收——记录跨阶段分数趋势

---

## 1. 趋势概览

本报告记录自基线扫描（2026-07-13）以来，仓库在 Phase 0–4 期间完成的供应链与工程健康度改进，及其对 Scorecard 18 项检查的预期影响。

**实际远端重跑**：维护者可通过 GitHub Actions 手动触发 `scorecard.yml` workflow（Actions 页 → OpenSSF Scorecard → Run workflow），扫描结果上传为 artifact `scorecard-baseline`。本报告的"预期得分"为基于已落地改动的推断，远端实测分数以下次 Actions 运行为准。

---

## 2. 基线→当前 改进映射

| # | 检查项 | 基线得分(2026-07-13) | 已落地改进 | 预期得分 | 趋势 |
|---|--------|---------------------|-----------|----------|------|
| 1 | Token-Permissions | -1（本地）/ 预期 8（远端） | Phase 0 T0.4：ci.yml 顶层 `permissions: contents: read`；codeql.yml 单独声明 `security-events: write`；scorecard.yml `contents: read` | 8-10 | ↑ |
| 2 | Dangerous-Workflow | -1（本地）/ 预期 8（远端） | 同上——CI 权限最小化消除危险 workflow 风险 | 8-10 | ↑ |
| 3 | Dependency-Update-Tool | 0（本地）/ 预期 5（远端） | Phase 0 T0.5：`.github/dependabot.yml` 已入库（pip + github-actions 双生态，weekly，分组小版本） | 5-7 | ↑ |
| 4 | Security-Policy | 4（本地）/ 预期 8（远端） | Phase 0 T0.2：`SECURITY.md` 已存在（漏洞报告渠道 + 支持版本 + 7 天响应承诺） | 8-10 | ↑ |
| 5 | License | 9（本地）/ 预期 10（远端） | Phase 0 T0.1：Apache-2.0 LICENSE 已入库，README 首屏声明协议 | 10 | ↑ |
| 6 | SAST | 0 | Phase 1：`.github/workflows/codeql.yml` 已落地（language: python，weekly cron + manual）；ruff `S` 规则集在 `make lint` 内生效 | 5-8 | ↑↑ |
| 7 | Vulnerabilities | 0（33 个 PYSEC 传递性漏洞） | Phase 1：CI 接入 `uv run pip-audit --strict`（non-blocking）；Dependabot weekly 自动开 PR | 视漏洞修复进度，预期 3-7 | ↑ |
| 8 | Branch-Protection | 0 | Phase 4 T4.2：决策记录已入库（`.upgrade/decisions/branch-protection.md`），**需维护者手动在 GitHub 后台开启** | 0（未操作）/ 8+（已操作） | 待操作 |
| 9 | Code-Review | 0-3 | Phase 4 T4.2：require PR before merging（个人项目无第二 reviewer） | 3-5（开启后） | 待操作 |
| 10 | CI-Tests | ~8 | Phase 1-3 期间 CI 持续运行，测试覆盖扩大（642 unit + 63 e2e-mock） | 8-10 | →/↑ |
| 11 | Maintained | ~5-7 | 仓库活跃（Phase 1-4 频繁提交，v1.0.3→v1.2.0） | 7-9 | ↑ |
| 12 | Contributors | ~3-5 | 个人项目，贡献者数量有限（设计决策：不追逐虚荣指标） | 3-5 | → |
| 13 | Pinned-Dependencies | 0 | 设计决策保持：`pyproject.toml` `>=` 下限 + `uv.lock` 锁定（spec §3 权衡） | 0-3 | → |
| 14 | Binary-Artifacts | 0（本地误判）/ 预期 10（远端） | 远端 CI checkout 不含 `.venv/`，无二进制产物 | 10 | → |
| 15 | Fuzzing | 10（本地误判）/ 预期 0（远端） | 无 fuzzing 集成（spec §1 非目标） | 0 | → |
| 16 | Packaging | -1 / 0 | 无 packaging workflow（spec §1 非目标，T4.4 不承诺） | 0 | → |
| 17 | CII-Best-Practices | 0 | 未参与 OpenSSF CII 徽章计划（T4.4 不承诺） | 0 | → |
| 18 | Signed-Releases | 0 | 无签名 release（T4.4 不承诺） | 0 | → |

---

## 3. 关键改进详述

### 3.1 Phase 0（仓库治理最小闭环）— 已完成

| 任务 | 改进检查项 | 落地证据 |
|---|---|---|
| T0.1 LICENSE | License 9→10 | 根目录 `LICENSE`（Apache-2.0），README 首屏声明 |
| T0.2 SECURITY.md | Security-Policy 4→8+ | 根目录 `SECURITY.md`（GitHub Security Advisories + 7 天响应） |
| T0.4 CI 权限最小化 | Token-Permissions / Dangerous-Workflow | `ci.yml` `permissions: contents: read` |
| T0.5 Dependabot | Dependency-Update-Tool 0→5+ | `.github/dependabot.yml`（pip + github-actions） |

### 3.2 Phase 1（安全与合规）— 已完成

| 任务 | 改进检查项 | 落地证据 |
|---|---|---|
| ruff `S` 规则 + CodeQL | SAST 0→5+ | `.github/workflows/codeql.yml`；`pyproject.toml` ruff select 含 `S` |
| pip-audit CI | Vulnerabilities（机制就位） | `ci.yml` `uv run pip-audit --strict`（non-blocking） |

### 3.3 Phase 4（社区打磨）— 本阶段

| 任务 | 改进检查项 | 落地证据 |
|---|---|---|
| T4.1 doc-check CI | —（中文社区维度） | `scripts/doc_consistency_check.py` + `make doc-check` + ci.yml 步骤 |
| T4.2 分支保护 | Branch-Protection / Code-Review | `.upgrade/decisions/branch-protection.md`（**需手动操作 GitHub 后台**） |
| T4.5 社区模板 | —（贡献者体验） | `.github/ISSUE_TEMPLATE/*` + `PULL_REQUEST_TEMPLATE.md` + CONTRIBUTING 响应节奏 |

---

## 4. 趋势结论

### 已确认改善（远端应识别）

- **Token-Permissions / Dangerous-Workflow**：Phase 0 权限最小化 → 预期 8-10
- **Dependency-Update-Tool**：Phase 0 Dependabot 配置 → 预期 5-7
- **Security-Policy**：Phase 0 SECURITY.md → 预期 8-10
- **License**：Phase 0 Apache-2.0 → 预期 10
- **SAST**：Phase 1 CodeQL + ruff `S` → 预期 5-8（从 0 实质提升）
- **Vulnerabilities**：Phase 1 pip-audit 机制就位，实际清零取决于依赖升级进度

### 待操作项（需维护者手动执行）

- **Branch-Protection / Code-Review**：T4.2 决策记录已入库，但实际开启需登录 GitHub 后台 → Settings → Branches 操作。操作后预期 Branch-Protection 0→8+、Code-Review 0→3-5

### 设计决策保持项（不追逐）

- **Pinned-Dependencies**：保持 `>=` 下限 + uv.lock（spec §3 权衡，不改为 hash pin）
- **Signed-Releases / CII-Badge / Packaging / Fuzzing**：T4.4 明确不承诺（无外部用户信号前不投入）

### 总体趋势

**向上**。基线 18 项中明确达标约 4-5 项，当前预期达标 10-12 项（含待操作的 Branch-Protection）。核心改善来自 Phase 0 治理文件 + Phase 1 SAST/漏洞审计 + Phase 4 doc-check/分支保护。

---

## 5. 下一步

1. **维护者操作**：登录 GitHub 后台开启 main 分支保护（步骤见 `.upgrade/decisions/branch-protection.md`）
2. **触发远端扫描**：GitHub Actions → OpenSSF Scorecard → Run workflow，下载 artifact 确认实测分数
3. **转强制 doc-check**：清理 doc-check 存量坏链（当前 26 处，多为设计文档代码示例误报 + 既有相对路径问题）后，将 ci.yml 的 `continue-on-error: true` 移除
4. **持续机制**：scorecard.yml weekly cron 每周自动扫描，后续每个阶段收尾时手动触发一次存档对照

---

## 附录

- 基线报告：[../archive/scorecard-baseline-20260713.md](../archive/scorecard-baseline-20260713.md)（已归档）
- 分支保护决策：[../decisions/branch-protection.md](../decisions/branch-protection.md)
- doc-check 悬空引用决策：[../decisions/doc-check-stage3-dangling-ref.md](../decisions/doc-check-stage3-dangling-ref.md)
- GitHub Actions 历史运行：https://github.com/gome09/ai-workflow-premortem-pure/actions/runs/29261154816
