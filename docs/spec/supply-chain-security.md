# 供应链与 CI 安全设计规格

> Status: Implemented（Phase 0 + Phase 4 落地：CI 权限最小化 / Dependabot / SAST / pip-audit / 文档一致性检查 / Scorecard；分支保护待维护者在 GitHub 后台开启。落地任务见 [../archive/plan/phase-0-repo-governance.md](../archive/plan/phase-0-repo-governance.md) 与 [../archive/plan/phase-4-community.md](../archive/plan/phase-4-community.md)）
> Last updated: 2026-07-27（按当前 workflow / Ruff 配置复核）
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

历史基线（Phase 0 实施前）：`.github/workflows/ci.yml` 未声明 `permissions:`，继承仓库默认权限（可能为 read-write）。

目标形态——workflow 顶层显式声明只读，需要额外权限的未来 workflow 各自单独声明：

```yaml
# .github/workflows/ci.yml 顶层（on: 与 jobs: 之间）
permissions:
  contents: read
```

当前实现与约束：
- `.github/workflows/ci.yml` 已在顶层声明 `contents: read`；当前三个 job（lint/unit、docker-lite、docker-full）均继承该最小权限。
- `.github/workflows/codeql.yml` 已独立声明 `contents: read` 与 `security-events: write`，没有放宽主 CI workflow。
- 未来若新增自动发布 workflow，同理单独声明 `contents: write`。

## 3. Dependabot 配置

已实现形态（`.github/dependabot.yml`）：

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
- `pyproject.toml` 的下限约束 + `uv.lock` 锁定组合**保持不变**：可复现性由 lock 文件保证，声明文件保持宽松便于依赖解析。不建议为 Scorecard Pinned-Dependencies 项改成精确 pin，那会与 uv 工作流冲突；依赖条目数量会随版本演进，不在规格中硬编码。

## 4. SAST 接入

选型对比：

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| CodeQL | GitHub 原生、免费（公开仓库）、Scorecard 直接认可、查询库覆盖 Python 注入/路径穿越等 | 私有仓库需 GHAS 付费；扫描较慢 | **首选**（若仓库公开） |
| Bandit | 轻量、本地可跑、无平台依赖 | 规则较浅，误报偏多 | 备选/补充 |
| Ruff `S` 规则集（flake8-bandit 移植） | 零新增依赖——项目已用 ruff；`make lint` 即可覆盖 | 覆盖面等同 Bandit 子集 | **无论选哪个都建议先开启**，成本最低 |

当前实现（两层）：
1. **第一层（已启用）**：`pyproject.toml` 的 Ruff 规则集包含 `S`（安全规则），并对 `tests/` 豁免 `S101` / `S110`；本层随 `make lint` 在主 CI 中执行。
2. **第二层（workflow 已入库，转正待远端治理）**：`.github/workflows/codeql.yml` 已配置 Python 分析、手动触发与 weekly cron，并独立声明 `security-events: write`。将触发范围扩展到 main 的 push/PR，以及是否设为 required check，仍按 `.upgrade/STATE.md` 的公开后 Task 19 执行；不得仅凭本地文件宣称已完成远端转正。

## 5. 依赖漏洞审计

当前形态：CI lint job 已运行 `uv run pip-audit --strict`，策略：
- 发现漏洞时**先告警不阻断**（`continue-on-error: true`），避免上游未修复漏洞卡死所有 PR。
- 每次告警必须在 24h 内人工分诊：可升级则由 Dependabot PR 解决；不可升级则在 `.upgrade/reports/` 记录豁免理由与复查日期。

## 6. Scorecard 水位管理

以下表格是 Phase 0 制定时的基线预估与阶段目标，不代表 2026-07-27 的远端实时状态；当前远端状态应以新的 Scorecard 扫描为准：

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

管理机制：`.github/workflows/scorecard.yml` 已入库（weekly cron + `workflow_dispatch` 手动触发，Scorecard CLI v5.5.0，`permissions: contents: read`）；此外每完成一个阶段重跑一次并把结果追加存档到 `.upgrade/reports/`，趋势必须向上——这是阶段 4 的验收口径（"分数相比基线有实质提升且可追踪"）。

## 7. 文档-代码一致性检查 CI

动机：`.upgrade/decisions/RELEASE_CLEANUP.md` 记录过一轮"文档与代码不一致"的事后修复；立项当时 `docs/spec/stage3-risk-adaptive-gate.md` 中存在指向 `../archive/verification-reports/` 的悬空引用（该引用已补档修复，见 `.upgrade/decisions/doc-check-stage3-dangling-ref.md`）。需要把"事后修复"变成"CI 常态拦截"。

目标形态：`scripts/doc_consistency_check.py` + CI 步骤，检查规则：
1. **链接存在性**：扫描当前项目全部 Markdown（排除 `.upgrade/` 历史记录、archive 树、运行时产物和工具缓存）中的相对路径链接，校验目标文件存在（外部 URL 跳过）。
2. **命令存在性**：扫描文档中 `make <target>` 引用，校验 target 在 Makefile 中定义。
3. **路径存在性**：扫描文档中反引号包裹的仓库路径（启发式：含 `/` 且以已知顶层目录开头），校验存在。
4. 版本一致性由现有 `make version-check` 覆盖，不重复。

输出：失败清单含文件、行号、坏引用。接入方式：`make doc-check` target + CI lint job 阻断步骤；存量坏链清零后已移除早期观察期的 `continue-on-error`。

## 8. 分支保护与签名发布（远端后置项）

- **分支保护目标**：为 main 开启 required status checks（lint + 单测 job）。本地仓库不能证明 GitHub 后台规则已启用；按 `.upgrade/STATE.md`，当前仍待维护者执行并用远端 Scorecard 复核。个人项目无第二名 reviewer，目标策略以 require PR before merge + required checks 为主。
- **签名发布**：若走到对外发布，采用 GitHub Release + `gh release create` 附 artifacts 校验和；Sigstore/cosign 签名仅在有真实分发需求时引入。

## 9. 验收标准

- 阶段 0 完成时：第 2、3 节配置已入库且 CI 全绿；Scorecard 基线报告存档。
- 阶段 1 完成时：ruff `S` 规则 + pip-audit 在 CI 真实运行且有输出记录（允许暂不阻断）。
- 阶段 4 完成时：doc-check 转为强制；Scorecard 分数较基线可见提升。
