# OpenSSF Scorecard 基线报告

> 仓库：gome09/ai-workflow-premortem-pure
> 扫描日期：2026-07-13
> Scorecard 版本：v5.5.0
> 扫描模式：本地 CLI（`--local=.`）+ GitHub Actions 远端确认
> 基线用途：Phase 0 仓库治理最小闭环验收 + 后续阶段改进对照

---

## 总体评估

| 维度 | 本地 CLI | 远端 GitHub Actions |
|------|----------|---------------------|
| 可用检查 | 10 / 18 | 18 / 18（全量） |
| 运行状态 | ✅ 完成 | ✅ 成功（run #29261154816） |

本地模式因无 GitHub API 访问权限，7 项检查返回 -1（不可评估），1 项未包含。远端 Actions 运行使用 `GITHUB_TOKEN` 完成全量 18 项扫描，结果已上传为 artifact（需 GitHub 认证下载）。

**注**：本地扫描包含 `.venv/` 目录，导致 Binary-Artifacts 与 Fuzzing 结果存在误判。远端扫描使用 `actions/checkout` 不会包含 `.venv/`，结果更准确。

---

## 逐项得分

### 本地 CLI 可评估项（10 项）

| # | 检查项 | 得分 | 原因 | Phase 0 关联 |
|---|--------|------|------|-------------|
| 1 | Binary-Artifacts | 0 | 本地 `.venv/` 含 2445 个 `.pyd` 二进制文件（误判：远端 CI checkout 不含 .venv，预期得分为 10） | — |
| 2 | Dependency-Update-Tool | 0 | 本地无法检测 GitHub Dependabot 配置（误判：已添加 `.github/dependabot.yml`，远端预期 ≥5） | T0.5 |
| 3 | Fuzzing | 10 | 检测到 `.venv/` 内 jsonschema Atheris 集成（误判：非项目自身 fuzz，远端预期 0） | — |
| 4 | License | 9 | 检测到 LICENSE 文件，但未识别为 FSF/OSI 标准（可能因纯文本格式，远端预期 10） | T0.1 |
| 5 | Pinned-Dependencies | 0 | `pyproject.toml` 使用 `>=` 下限声明，非 hash pin（符合设计决策：uv.lock 保证可复现） | — |
| 6 | SAST | 0 | 未检测到静态分析工具（如 CodeQL） | Phase 1 |
| 7 | Security-Policy | 4 | 检测到 SECURITY.md（远端预期 ≥8，因文件路径与命名更规范） | T0.2 |
| 8 | Vulnerabilities | 0 | 33 个 PYSEC 已知漏洞（依赖链中的传递性漏洞） | Phase 1 |
| 9 | Dangerous-Workflow | -1 | 本地无 workflows 可分析（远端预期 ≥8，因 CI 权限已最小化） | T0.4 |
| 10 | Packaging | -1 | 本地未检测到 packaging 工作流 | — |
| 11 | Token-Permissions | -1 | 本地无 tokens 可分析（远端预期 ≥8，因 CI 已设 `contents: read`） | T0.4 |

### 远端 GitHub Actions 独有检查（8 项，需认证下载 artifact 获取精确分数）

| # | 检查项 | 预期得分 | 依据 |
|---|--------|----------|------|
| 12 | Maintained | ~5-7 | 仓库活跃（近期频繁提交），但贡献者数量有限 |
| 13 | CII-Best-Practices | 0 | 未参与 OpenSSF CII/Best Practices 徽章计划 |
| 14 | Code-Review | ~0-3 | 未强制 PR review，手动合并存在 |
| 15 | Contributors | ~3-5 | 贡献者数量有限 |
| 16 | CI-Tests | ~8 | CI 含 lint + unit tests + docker-lite integration |
| 17 | Branch-Protection | 0 | main 分支未配置 Branch Protection（需 GitHub 后台设置） |
| 18 | Signed-Releases | 0 | 无 GPG/SSH 签名 release（tag v1.0.2 未签名） |

---

## 关键发现与改进优先级

### 高优先级

1. **Vulnerabilities: 0 分 — 33 个传递性依赖漏洞**
   - 原因：依赖链中的已知 CVE
   - 行动：Phase 1 执行 `uv audit` + 依赖升级，设置 CI 漏洞扫描门控
   - 影响检查：Vulnerabilities

2. **Branch-Protection: 预期 0 分 — main 无分支保护**
   - 原因：未配置 required status checks / PR review
   - 行动：GitHub 后台 → Settings → Branches → main → Enable protection
   - 影响检查：Branch-Protection、Code-Review

3. **Pinned-Dependencies: 0 分 — 依赖未 hash pin**
   - 原因：`pyproject.toml` 使用 `>=` 下限（设计决策：uv.lock 保证可复现性）
   - 行动：远端 Scorecard 可识别 `uv.lock` 并给予部分分数；完全修复需 hash pin（与 uv 工作流冲突，暂不执行）
   - 影响检查：Pinned-Dependencies

### 中优先级

4. **SAST: 0 分 — 无静态分析工具**
   - 行动：Phase 1 添加 CodeQL 或 Semgrep workflow
   - 影响检查：SAST

5. **Signed-Releases: 0 分 — tag 未签名**
   - 行动：配置 GPG 签名密钥 + `git tag -s`
   - 影响检查：Signed-Releases

6. **CII-Best-Practices: 0 分 — 未参与徽章计划**
   - 行动：提交 OpenSSF Best Practices 申请（低优先级，仓库成熟度不足）
   - 影响检查：CII-Best-Practices

### 低优先级 / 设计决策

7. **Dependency-Update-Tool: 远端预期 ≥5**
   - Phase 0 T0.5 已添加 `.github/dependabot.yml`，远端应识别
   - 影响检查：Dependency-Update-Tool

8. **Token-Permissions: 远端预期 ≥8**
   - Phase 0 T0.4 已设 `permissions: contents: read`，远端应识别
   - 影响检查：Token-Permissions

---

## Phase 0 任务对 Scorecard 得分的改善映射

| 任务 | 改善检查项 | 本地→远端预期变化 |
|------|-----------|------------------|
| T0.1 Apache-2.0 LICENSE | License | 9→10 |
| T0.2 SECURITY.md | Security-Policy | 4→8+ |
| T0.4 CI 权限最小化 | Token-Permissions | -1→8 |
| T0.4 CI 权限最小化 | Dangerous-Workflow | -1→8 |
| T0.5 Dependabot | Dependency-Update-Tool | 0→5 |

---

## 人工确认项（需登录 GitHub 后台记录）

- [ ] main 分支 Branch Protection 状态（required status checks）
- [ ] PR review 策略（require PR before merge / required reviewers）
- [ ] 仓库可见性（已确认：Public）

---

## 附录

- 本地 JSON 原始文件：`.upgrade/tmp/scorecard-baseline-2026-07-13.json`
- GitHub Actions 运行：https://github.com/gome09/ai-workflow-premortem-pure/actions/runs/29261154816
- GitHub Actions artifact：`scorecard-baseline`（2.35 KB，需认证下载）
