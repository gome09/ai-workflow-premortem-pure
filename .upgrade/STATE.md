# Upgrade State

## Current Phase

Phase 4 — **代码侧全部完成** (T4.1 / T4.2 文档 / T4.3 / T4.5；T4.4 明确不承诺)。Phase 3 全部完成 (T3.1–T3.7，T3.6 已于 v1.3.0 落地、flag 默认关)。Phase 2 全部完成 (T2.1–T2.6)。Phase 1 全部完成 (T1.1–T1.9)。正式项目升级（formal-project-uplift，计划 `.upgrade/plans/2026-07-17-formal-project-uplift.md`）进行中——Wave A–D 已完成（Wave D：合规映射 2026-07-17 复核落账，Task 13–14，实施方案 `.upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md`）；**Wave E 已完成（Task 15–18，实施方案 `.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md`），formal-project-uplift 全部收尾，v1.3.0 已 bump + tag**。Task 19（CodeQL 转正）待仓库公开后执行。

## Current Task

**计划已完成（Task 19 除外，待公开后）**：`.upgrade/plans/2026-07-17-formal-project-uplift.md`（正式个人项目升级：门面治理文件 / mypy 渐进式类型检查 / T3.6 LLM Judge 落地 / 合规映射 2026-07-17 复核落账 / 公开前检查，目标版本 v1.3.0，Task 0–19）。**Wave A–E（Task 0–18）全部完成**。此前遗留：GitHub 后台开启 main 分支保护（步骤见 `.upgrade/decisions/branch-protection.md`，已并入新计划 Task 15 公开后动作清单）。

## Last Completed

- **Wave E 公开前检查与 CI/发布收尾 (2026-07-17)**：公开前全历史敏感信息扫描通过（仅 DEMO_PASSWORD 演示凭据 + secrets.example 占位符两类良性命中，报告含公开后 10 步人工动作清单）；CI 覆盖率产出（pytest-cov + make test-cov + GitHub job summary，不接 codecov）；doc-check 转强制、mypy 维持 non-blocking（从未在远端跑过，转正条件未满足——评估结论见报告第 4 节）；docs/plan/ecosystem-positioning.md 生态定位文档（赛道三层地图 / SynthBoard.ai 差异化 / 门面对标结论，数字与 2026-07-16 JSON 快照逐字段一致）；v1.3.0 收尾（version 三件套 + README :14 + CHANGELOG + tag v1.3.0 打在收尾 commit）。对父计划六处记录性偏差（预扫描良性清单 / doc-check 转正范围 / commit message / README 版本行 / STATE 段落名 / tag 位置）见实施方案。commits: 63f4c31/955c0ef/622edc7/d23aa6a+本 commit。实施计划：`.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md`。
- **Wave D 合规映射复核落账 (2026-07-17)**：ISO/IEC 42005:2025（AI 系统影响评估，2025-05 发布）对标说明落入 docs/compliance/iso42001-mapping.md 第 6 节（初版对齐表，付费标准全文未核对处如实标注）；docs/plan/improvement-roadmap.md 新增 §10.7 复核增补（EU AI Act Omnibus 公报编号待回填 / TC260 正式发布确认但二手来源 / NIST AI 600-1 四动作项 [存疑] 维持 / OWASP ASI 无需改动 / 两个国内已生效法规锚点候选）；三个 taxonomy 模块 docstring 盖 2026-07-17 二次复核戳（仅注释零行为变更，87 项相关测试全绿；tc260 戳按质量评审意见做时间限定修正，避免与 [信源说明] 自相矛盾）。对父计划三处记录性偏差（§6 编号 / TC260 [信源说明] 措辞 / §10.7 插入位）见实施方案。commits: efef623/7c5702d。实施计划：`.upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md`。
- **Wave C T3.6 LLM Judge (2026-07-17)**：EVAL_LLM_JUDGE / EVAL_LLM_JUDGE_AUTOFINAL 两 flag（默认 off）+ EvalRun.llm_judge_suggestion 字段；core/eval_llm_judge.py 建议生成器（防注入模板、失败静默降级）+ judge 专用 mock fixture；eval_runner 风险分层 autofinal 门控（HIGH/CRITICAL 永不采纳、manual run 不生成建议——对父计划的记录性偏差见实施方案）；spec §5 翻转 Implemented (v1.3.0)。测试 tests/test_llm_judge_v130.py 8 条，全量回归 650 passed, 1 skipped。commits: 46fb178 / de76b04 / 6e5a372 + 文档收尾 commit。实施计划：`.upgrade/plans/2026-07-17-wave-c-llm-judge-implementation.md`。
- **Wave B mypy 渐进式类型检查 (2026-07-17)** — mypy 引入与全量清零：宽松档基线 108→0（inspect_ai 模式，files 限 7 核心包，排除 tests/frontend/scripts/examples/alembic），core.gates/graph 近 strict 13→0，`uv run mypy` = `Success: no issues found in 153 source files`。新增 `make typecheck` target + CI `Type check (non-blocking)` 接入 ci.yml（观察期，转正评估归 Wave E Task 16）。防漂移版本钉子：mypy>=1.14,<3、langgraph>=1.1,<2。修复含一处真实 bug（create_redteam_dataset/create_dataset_from_failed_traces 的不存在 note= 关键字，latent TypeError）+ SourceType 单一定义化。分片提交 B1–B6（873e256/57aec07/6a1fe93/cbc1193/d8ba8b4/0f64dd8 + 本收尾）。实施计划：`.upgrade/plans/2026-07-17-wave-b-mypy-implementation.md`；基线报告：`.upgrade/reports/mypy-baseline-20260717.md`。
- **Wave A 门面与治理文件 (2026-07-17)** — 对标调研快照归档至 `.upgrade/research/benchmarking-20260716/`；包名统一 `ai-workflow-premortem` + hatchling 可安装化（`uv pip install -e .` 验证通过）；SECURITY.md 报告渠道定稿（仅 GitHub 私密报告）；新增 CODE_OF_CONDUCT.md（Contributor Covenant 2.1）/ GOVERNANCE.md（BDFL）/ .github/CODEOWNERS / issue config.yml；README 门面改造（徽章 + origin story + 生态定位）+ README.en.md。实施计划：`.upgrade/plans/2026-07-17-wave-a-implementation.md`。
- **文档同步 + `.upgrade` 整理 (2026-07-16)** — 记录此前未纳入版本控制的单文件 Demo `ai_workflow_premortem_demo.html`（165KB 自包含离线可交互 Demo，真实四阶段实跑快照，`LLM_MODE=mock`/`STORAGE_BACKEND=sqlite`/`WORKFLOW_EXECUTION_MODE=single_step`），README「答辩演示模式」新增「零依赖单文件 Demo」小节登记两份 HTML；CHANGELOG 追加 2026-07-16 维护记录；`.upgrade/MANIFEST.md` File Inventory 补齐遗漏条目 `decisions/doc-alignment-and-frontend-polish.md`（此前已提交但未登记）。最小审查：version 1.2.1 一致 / ruff clean / doc-check 通过
- **GitHub CI 离线全流程验证 (2026-07-15)** — 远端 `.github/workflows/ci.yml` 实测两个 job 全绿：`lint-and-unit-tests`（ruff + doc-check[non-blocking] + pip-audit[non-blocking] + `.env.demo` mock+SQLite 全量 pytest）与 `docker-lite-integration`（`docker-compose.lite.yml` 构建 + API `/health/live`+`/health` + 前端 8501 smoke test）。全程离线无真实 LLM（`LLM_MODE=mock`）/无外部 DB（`STORAGE_BACKEND=sqlite`）。CI run #13 conclusion=success。附带修复：`tests/test_taxonomy_owasp_agentic_2026.py` 两处 docstring `\d` 改 raw string 消除 SyntaxWarning。本地验证：ruff clean / 615 passed,8 skipped / version 1.2.1
- **文档对齐 + 前端中文化收尾 (2026-07-14)** — 基于四维审计（路线图达成度 / 前端中文展示 / 文档-代码对齐 / 启动方式）做收尾对齐：①四份 spec 的 `Status:` 从 "Designed, not implemented" 翻转为 "Implemented"，CLAUDE.md 文档维护段同步；②phase-0~3 验收清单 + roadmap §6 诚实勾选（未完成项保留并注明）；③api-reference 补治理 API + 路由数 79→84，security-model 补 3 个新风险类型/字段加密/PII 掩码/数据分级，docs/README 补 iso42001 索引，startup 测试数 388→642；④doc-check 脚本新增"跳过围栏代码块"，存量违规 25→0；⑤前端 labels 新增 RISK_TYPE/EXEC_MODE/ADAPTER_STATUS 映射，修复侧边栏健康状态、欢迎页首屏、待处理动作/安全发现的英文泄漏。决策见 `.upgrade/decisions/doc-alignment-and-frontend-polish.md`。验证：ruff clean / doc-check 0 / version 1.2.1 / e2e-mock 63 passed / 全量 642 passed,1 skipped / 后端 app 加载 OK
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
- **Phase 4 T4.1 doc-check 转强制**：存量违规已清零（doc-check 0 处违规，脚本已支持跳过围栏代码块）。CI 仍为 non-blocking（`continue-on-error: true`），可择机移除该行转强制。
- Phase 3 T3.6 (LLM Judge)：~~gated on user confirming real demand~~ 已解除——用户确认需求后于 2026-07-17 作为 Wave C 落地（v1.3.0，flag 默认关）。真实 LLM 一致率数据待生产启用后经 human_calibrations 累计。
- NIST AI 600-1 中 4 项动作项编号标 [存疑]（MS-2.10-002 / MS-2.5-005 / MS-2.5-003 / GV-1.3-002），待 NIST 发布修订版后核对。
- TC260《智能体部署使用安全指引》条款文字基于二手摘要，待补全文核对。
- ISO 42001 映射未覆盖缺口（更新后 3 项）：系统停用/退役阶段、跨租户集团视图、第三方供应链风险集成。原第 4 项"LLM Judge 校准闭环"已随 T3.6 落地（v1.3.0）转为"机制就位、真实一致率数据待生产启用后累计"。

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
- doc-check：0 处违规（脚本新增跳过围栏代码块 + 修复真实坏链 + 消除行内误报）

## Validation Commands

- `git status --short`
- `uv run python scripts/version_check.py`
- `uv run ruff check . && uv run ruff format --check .`
- `Copy-Item -Force .env.demo .env; uv run pytest tests/ -q`
- `python scripts/doc_consistency_check.py`
- `git tag --list` (expect `v1.3.0`；历史 tag v1.0.x–v1.2.0 在仓库整理时未保留，见 CHANGELOG 追溯说明)

## Next Action

1. **维护者手动操作（公开序列）**：按 `.upgrade/reports/pre-publication-checklist-20260717.md` 文末清单执行——push（含 tags）→ 转 Public → 分支保护 → Private vulnerability reporting → Dependabot → CodeQL 转正（Task 19）→ Scorecard dispatch → 徽章核验 → GitHub Release v1.3.0
2. **远端首轮 CI 全绿后**：移除 ci.yml mypy 步骤 `continue-on-error: true` 转强制
3. **2026-08 下旬强制复核点**：《未成年人 AI 应用安全指南》征求意见截止（2026-08-16）后核对定稿内容（roadmap §10.7）

## Last Updated

- Date: 2026-07-17
- By: claude-code (Wave E publication readiness & v1.3.0 release closeout)
- Summary: formal-project-uplift Wave A–E 全部完成：公开前扫描通过、CI 覆盖率 + doc-check 转强制、生态定位文档、v1.3.0 bump + tag。仓库处于"待维护者点公开按钮"状态，公开后动作清单见 pre-publication-checklist 报告。
