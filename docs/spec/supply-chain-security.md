# 供应链与 CI 安全设计规格

> Status: Designed, not implemented（落地任务见 [../plan/phase-0-repo-governance.md](../plan/phase-0-repo-governance.md) 与 [../plan/phase-4-community.md](../plan/phase-4-community.md)）
> Last updated: 2026-07-13
> 对标依据：OpenSSF Scorecard 18 项检查（v5.5.0，2026-04）、GitHub Actions 安全加固最佳实践

本规格定义仓库供应链安全与 CI 安全的目标形态，覆盖：CI 权限最小化、依赖自动更新、SAST、依赖漏洞审计、文档-代码一致性检查、Scorecard 水位管理。

---

## 1. 设计目标与范围

| 目标 | 对应 Scorecard 检查项 | 落地阶段 |
|---|---|---|
| CI token 权限最小化 | Token-Permissions (High) | 阶段 0 |
| 依赖自动更新 | Dependency-Update-Tool (High) | 阶段 0 |
| 安全导向静态分析 | SAST (Medium) | 阶段 1 |
| 依赖漏洞审计 | Vulnerabilities (High) | 阶段 1 |
| 文档-代码一致性 CI | —（中文社区维度） | 阶段 4 |
| 分支保护 + 强制评审 | Branch-Protection / Code-Review (High) | 阶段 4 |
| 签名发布 | Signed-Releases (High) | 阶段 4（可选） |

**非目标**：发布为可安装 PyPI 包（Packaging）、Fuzzing、CII 徽章——企业内部工具场景下优先级低，仅在阶段 4 视精力评估。

## 2. CI 权限最小化

现状：`.github/workflows/ci.yml` 未声明 `permissions:`，继承仓库默认权限（可能为 read-write）。

目标形态——workflow 顶层显式声明只读，需要额外权限的未来 workflow 各自单独声明：

```yaml
# .github/workflows/ci.yml 顶层（on: 与 jobs: 之间）
permissions:
  contents: read
```

设计约束：
- 现有两个 job（lint + docker-lite 集成）均只需 `contents: read`，收紧无副作用。
- 未来若新增 SAST（CodeQL）workflow，其需要 `security-events: write`，在该 workflow 内单独声明，不放宽 ci.yml。
- 未来若新增自动发布 workflow，同理单独声明 `contents: write`。

## 3. Dependabot 配置

目标形态（`.github/dependabot.yml`）：

```yaml
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

设计权衡：
- **分组小版本更新**：把 minor/patch 合并为单个 PR，major 版本单独开 PR 逐个评审——个人维护场景下控制 PR 噪音是可持续性的关键。
- `pyproject.toml` 当前 26 处 `>=` 下限约束 + `uv.lock` 锁定的组合**保持不变**：可复现性由 lock 文件保证，声明文件保持宽松便于依赖解析。不建议为 Scorecard Pinned-Dependencies 项改成精确 pin，那会与 uv 工作流冲突。

## 4. SAST 接入

选型对比：

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| CodeQL | GitHub 原生、免费（公开仓库）、Scorecard 直接认可、查询库覆盖 Python 注入/路径穿越等 | 私有仓库需 GHAS 付费；扫描较慢 | **首选**（若仓库公开） |
| Bandit | 轻量、本地可跑、无平台依赖 | 规则较浅，误报偏多 | 备选/补充 |
| Ruff `S` 规则集（flake8-bandit 移植） | 零新增依赖——项目已用 ruff；`make lint` 即可覆盖 | 覆盖面等同 Bandit 子集 | **无论选哪个都建议先开启**，成本最低 |

目标形态（两层）：
1. **第一层（立即）**：`pyproject.toml` 的 ruff 配置在现有 `E,F,I,UP` 基础上增加 `S`（安全规则），对 `tests/` 目录豁免 `S101`（assert 使用）。本层随 `make lint` 在现有 CI job 内生效，无需新 workflow。
2. **第二层（仓库公开后）**：新增 `.github/workflows/codeql.yml`，language: python，触发条件 push/PR 到 main + weekly cron，`permissions: security-events: write` 单独声明。结果仅告警不阻断合并（观察期一个月后再评估是否升级为 required check）。

## 5. 依赖漏洞审计

目标形态：CI lint job 内追加一步 `uv run pip-audit`（或 `uv audit`，以当时 uv 版本支持为准），策略：
- 发现漏洞时**先告警不阻断**（`continue-on-error: true`），避免上游未修复漏洞卡死所有 PR。
- 每次告警必须在 24h 内人工分诊：可升级则由 Dependabot PR 解决；不可升级则在 `.upgrade/reports/` 记录豁免理由与复查日期。

## 6. Scorecard 水位管理

18 项检查现状预估与目标（基线以阶段 0 T0.7 实际扫描为准）：

| 检查项 | 现状 | 阶段 0 后 | 阶段 4 目标 |
|---|---|---|---|
| Token-Permissions | ❌ | ✅ | ✅ |
| Dependency-Update-Tool | ❌ | ✅ | ✅ |
| Security-Policy | ❌ | ✅ | ✅ |
| License | ❌ | ✅（待协议决策） | ✅ |
| SAST | ❌ | ❌ | ✅（阶段 1 落地） |
| Vulnerabilities | ⚠️ 未知 | 基线可见 | ✅ 持续清零 |
| Branch-Protection / Code-Review | ⚠️ 待后台确认 | 记录现状 | ✅ 开启保护 |
| Signed-Releases | ❌ | ❌ | 视精力（可选） |
| Fuzzing / Packaging / CII-Badge | ❌ | 不做 | 视精力（可选） |
| Maintained / CI-Tests / Binary-Artifacts / Pinned-Dependencies(lock) | ✅ | 保持 | 保持 |

管理机制：每完成一个阶段重跑一次 `scorecard` CLI，结果追加存档到 `.upgrade/reports/`，趋势必须向上——这是阶段 4 的验收口径（"分数相比基线有实质提升且可追踪"）。

## 7. 文档-代码一致性检查 CI

动机：`.upgrade/decisions/RELEASE_CLEANUP.md` 记录过一轮"文档与代码不一致"的事后修复；已知 `docs/spec/stage3-risk-adaptive-gate.md` 中存在指向 `../archive/verification-reports/` 的悬空引用。需要把"事后修复"变成"CI 常态拦截"。

目标形态：`scripts/doc_consistency_check.py` + CI 步骤，检查规则：
1. **链接存在性**：扫描 `README.md`、`CLAUDE.md`、`docs/**/*.md` 中的相对路径 Markdown 链接，校验目标文件存在（外部 URL 跳过）。
2. **命令存在性**：扫描文档中 `make <target>` 引用，校验 target 在 Makefile 中定义。
3. **路径存在性**：扫描文档中反引号包裹的仓库路径（启发式：含 `/` 且以已知顶层目录开头），校验存在。
4. 版本一致性由现有 `make version-check` 覆盖，不重复。

输出：失败清单含文件、行号、坏引用。接入方式：`make doc-check` target + CI lint job 追加步骤；初期 `continue-on-error: true` 观察一轮，修完存量坏链后转为强制。

## 8. 分支保护与签名发布（阶段 4 后置项）

- **分支保护**：main 分支开启 required status checks（lint + 单测 job）；个人项目"强制 PR review"不可行（无第二人），退而求其次开启"require PR before merge + 自我 review"，Scorecard 对此部分给分。
- **签名发布**：若走到对外发布，采用 GitHub Release + `gh release create` 附 artifacts 校验和；Sigstore/cosign 签名仅在有真实分发需求时引入。

## 9. 验收标准

- 阶段 0 完成时：第 2、3 节配置已入库且 CI 全绿；Scorecard 基线报告存档。
- 阶段 1 完成时：ruff `S` 规则 + pip-audit 在 CI 真实运行且有输出记录（允许暂不阻断）。
- 阶段 4 完成时：doc-check 转为强制；Scorecard 分数较基线可见提升。
