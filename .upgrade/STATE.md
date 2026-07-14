# Upgrade State

## Current Phase

Phase 4 — **代码侧全部完成** (T4.1 / T4.2 文档 / T4.3 / T4.5；T4.4 明确不承诺)。Phase 3 全部完成 (T3.1–T3.5, T3.7；T3.6 可选未启用)。Phase 2 全部完成 (T2.1–T2.6)。Phase 1 全部完成 (T1.1–T1.9)。

## Current Task

Phase 4 收尾完成（version bump 1.2.0→1.2.1、CHANGELOG、STATE.md、验收清单更新）。**待维护者手动操作**：GitHub 后台开启 main 分支保护（步骤见 `.upgrade/decisions/branch-protection.md`）。

## Last Completed

- **E2E 全流程复测 (2026-07-14)** — v1.2.1 本地离线全流程 E2E 复测 PASS：四阶段全部 advanced=True、hard_blockers=0、16 个 panel 端点全部 200、前端 Streamlit 渲染正常 + JWT 自动登录、后端日志无错误。会话 `91e799e4-15d1-4af3-baa9-79a8be890eb5`，耗时 18s。`.gitignore` 补 `artifacts/`；`docs/acceptance_report.md` 同步更新至 v1.2.1；`.upgrade/MANIFEST.md` File Inventory 补齐 7 个遗漏条目
- **Phase 4 (2026-07-14, v1.2.1)** — T4.1 doc-check CI 化 + T4.5 社区模板 + T4.2 分支保护文档 + T4.3 Scorecard 趋势报告；T4.4 不承诺
- **Phase 3 Wave 6 (2026-07-14)** — 收尾：version bump 1.1.0→1.2.0、CHANGELOG v1.2.0、STATE.md 更新、git tag v1.2.0
- **Phase 3 Wave 4 (2026-07-14, commit 0bca456)** — T3.5 Prometheus 业务指标 + Grafana 治理面板（6 个 premortem_* 指标 + governance-overview.json）+ T3.7 ISO/IEC 42001 条款映射表（25 条款映射 + 4 缺口 + spec 两处修正）
- **Phase 3 Wave 3 (2026-07-14, commit 16c3439)** — T3.3 expert_review 规则落地（补 stage3 历史欠账）+ GATE_RULES_DISABLED 治理；T3.4 治理 API 三端点 + Streamlit 治理页
- **Phase 3 Wave 2 (2026-07-14, commit b534929)** — T3.2 rule_version 携带 + gate_evaluation_records 表（alembic V005）+ 存储层聚合方法
- **Phase 3 Wave 1 (2026-07-14, commit fbcfdfe)** — T3.1 门禁规则元数据清单 manifest（13 条规则 version/owner/rationale/changelog）
- **Phase 3 Design Plan (2026-07-14)** — 详细设计方案 `docs/plan/phase-3-design.md`
- **Phase 2 全部完成 (2026-07-14, v1.1.0)** — T2.1–T2.6 AI 风险分类体系补强，5 Waves
- **Phase 1 全部完成 (2026-07-14, v1.0.3)** — T1.1–T1.9 安全与合规硬缺口修复

## Required Context Files

- `.upgrade/MANIFEST.md`
- `docs/plan/phase-1-design.md` — Phase 1 详细设计方案
- `docs/plan/phase-2-design.md` — Phase 2 详细设计方案
- `docs/plan/phase-3-design.md` — Phase 3 详细设计方案
- `docs/plan/phase-4-design.md` — Phase 4 详细设计方案
- `docs/plan/phase-1-security-compliance.md` — Phase 1 实施计划
- `docs/plan/phase-2-risk-taxonomy.md` — Phase 2 实施计划
- `docs/plan/phase-3-governance-platform.md` — Phase 3 实施计划
- `docs/plan/phase-4-community.md` — Phase 4 实施计划
- `docs/plan/improvement-roadmap.md` — roadmap
- `docs/spec/governance-platform.md` — 治理平台设计规格
- `docs/spec/supply-chain-security.md` — 供应链与 CI 安全设计规格
- `docs/compliance/iso42001-mapping.md` — ISO/IEC 42001 条款映射表
- `.upgrade/logs/standard-tracking-2026-07-14.md` — 标准动态跟踪记录

## Blockers

- **Phase 4 T4.2 分支保护**：决策记录已入库（`.upgrade/decisions/branch-protection.md`），但实际开启需维护者登录 GitHub 后台手动操作（Settings → Branches → main → Enable protection）。操作后预期 Scorecard Branch-Protection 0→8+、Code-Review 0→3-5。
- **Phase 4 T4.1 doc-check 转强制**：当前 CI non-blocking（`continue-on-error: true`），存量 26 处违规清理后转强制。
- Phase 3 T3.6 (LLM Judge) gated on user confirming real demand for automated evaluation (roadmap §8 preserved condition). 设计完成（spec §5），flag 默认关，待确认后作为独立 Wave 启动。
- NIST AI 600-1 中 4 项动作项编号标 [存疑]（MS-2.10-002 / MS-2.5-005 / MS-2.5-003 / GV-1.3-002），待 NIST 发布修订版后核对。
- TC260《智能体部署使用安全指引》条款文字基于二手摘要，待补全文核对。
- ISO 42001 映射 4 项未覆盖缺口：系统停用/退役阶段、LLM Judge 校准闭环、跨租户集团视图、第三方供应链风险集成。

## Active Stage Report

Phase 4 开源社区打磨代码侧全部完成。核心成果：

### 文档-代码一致性 CI（T4.1）
| 能力 | 实现 | 状态 |
|---|---|---|
| 检查脚本 | `scripts/doc_consistency_check.py`（三类规则：链接/make target/仓库路径） | ✅ |
| Makefile target | `make doc-check` | ✅ |
| CI 接入 | ci.yml lint job 追加 doc-check 步骤（non-blocking 观察期） | ✅ |
| 存量坏链修复 | stage3 悬空引用补档 `docs/archive/verification-reports/` | ✅ |

### 社区响应约定（T4.5）
| 能力 | 实现 | 状态 |
|---|---|---|
| Issue 模板 | `.github/ISSUE_TEMPLATE/bug_report.md` + `feature_request.md` | ✅ |
| PR 模板 | `.github/PULL_REQUEST_TEMPLATE.md` | ✅ |
| 响应节奏 | CONTRIBUTING.md 追加"社区响应约定"（7 天响应承诺） | ✅ |

### 分支保护（T4.2）
| 能力 | 实现 | 状态 |
|---|---|---|
| 决策记录 | `.upgrade/decisions/branch-protection.md` | ✅ |
| 文档声明 | CONTRIBUTING.md 追加"分支保护"段落 | ✅ |
| 实际开启 | GitHub 后台手动操作 | ⏳ 待维护者操作 |

### Scorecard 持续爬升（T4.3）
| 能力 | 实现 | 状态 |
|---|---|---|
| 扫描机制 | `.github/workflows/scorecard.yml`（weekly cron + manual） | ✅ |
| 基线报告 | `.upgrade/reports/scorecard-baseline-20260713.md` | ✅ |
| 趋势报告 | `.upgrade/reports/scorecard-trend-20260714.md` | ✅ |

### 测试验证
- 全量测试：642 passed, 1 skipped（回归确认无破坏）
- e2e-mock：63 passed
- lint + format：clean
- doc-check：26 处存量违规（既有问题 + 设计文档代码示例误报，CI non-blocking）

## Validation Commands

- `git status --short`
- `uv run python scripts/version_check.py`
- `uv run ruff check . && uv run ruff format --check .`
- `Copy-Item -Force .env.demo .env; uv run pytest tests/ -q`
- `python scripts/doc_consistency_check.py`
- `git tag --list` (expect `v1.0.2`, `v1.0.3`, `v1.1.0`, `v1.2.0`)

## Next Action

1. **维护者手动操作**：GitHub 后台开启 main 分支保护（步骤见 `.upgrade/decisions/branch-protection.md`）
2. **触发远端 Scorecard 扫描**：GitHub Actions → OpenSSF Scorecard → Run workflow，确认实测分数
3. **清理 doc-check 存量坏链**：逐步修复 26 处违规后，移除 ci.yml 的 `continue-on-error: true`
4. 路线图全部 5 阶段（Phase 0-4）已完成，进入持续维护模式

## Last Updated

- Date: 2026-07-14
- By: trae-agent (E2E 全流程复测 + 文档同步)
- Summary: v1.2.1 本地离线全流程 E2E 复测 PASS（四阶段 + 16 panel 端点 + 前后端链路 + 浏览器渲染）。`.gitignore` 补 `artifacts/`；`docs/acceptance_report.md` 更新至 v1.2.1；`.upgrade/MANIFEST.md` File Inventory 补齐。Phase 0-4 全部完成，进入持续维护模式。
