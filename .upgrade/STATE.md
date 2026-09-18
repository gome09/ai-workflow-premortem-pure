# Upgrade State

## Current Phase

Phase 0–4 代码侧已完成；formal-project-uplift Wave A–E（Task 0–18）已完成并收尾为 v1.3.0。仓库已公开。剩余远端治理动作：Task 19 CodeQL 转正、main 分支保护、发布设置及标准原文复核。

## Current Task

**计划已完成（Task 19 除外）**：`.upgrade/archive/plans/2026-07-17-formal-project-uplift.md`（正式个人项目升级：门面治理文件 / mypy 渐进式类型检查 / T3.6 LLM Judge 落地 / 合规映射 2026-07-17 复核落账 / 公开前检查，目标版本 v1.3.0，Task 0–19）。**Wave A–E（Task 0–18）全部完成，仓库已公开**。此前遗留：GitHub 后台开启 main 分支保护（步骤见 `.upgrade/decisions/branch-protection.md`，已并入 Task 15 公开后动作清单）。

## Last Completed

- **三个已知代码缺口修复 (2026-09-01 第二批)** — ①`core/gates/risk_profile.py`：sensitive_personal 升档改为 tier floor（HIGH），low-scope 降档与 LOW 覆盖分支尊重 floor（提交 a9f18a2，6 条回归测试）；②`core/report_service.py`：报告 Markdown 导出新增 `_sanitize_markdown` 出口净化（HTML 转义 + 伪协议中和 + AIGC 注释保留 + fenced 块保真，提交 57de39f，8 条测试）；③`api/metrics.py` + 双存储后端：`premortem_pending_actions` 语义修正为真实 pending 动作按 risk_level 计数，新增 `governance_metrics_all_tenants()` 跨租户聚合替代恒零的空租户查询（提交 8023d7c，改写固化错误语义的测试 + 新增后端聚合测试）。三个缺口的 spec 标注均已更新（data-classification-and-privacy §3.2 / risk-taxonomy-engine §3.3 / security-model / governance-platform §4.3），Blockers 条目移除。全量 681 passed / 1 skipped、ruff clean、doc-check 0 违规。
- **会话删除功能 + 死代码清理 + 文档压缩 (2026-09-01 第一批)** — 前端侧栏会话列表新增删除入口（`api_delete` helper + `@st.dialog` 二次确认 + admin 角色门控，角色经 JWT payload 本地解码；删除当前会话后 `_reset_session_state` 清空 11 个状态键回初始），后端复用既有 `DELETE /sessions/{id}` 链路零改动；治理总览图表横坐标中文化（11 个 SessionState + 4 个 risk tier 展示映射）。删除 2026-07-18 遗留的 11 个死代码文件（9 个未接线 panel + api_client.py + state.py，1157 行）。新增 `tests/test_frontend_session_delete.py` 6 条契约测试。浏览器实测三条删除路径通过。验证：666→672→680→681 passed / 1 skipped（分批递增）、ruff clean。提交：6d45f95 / 2d66d76 / 3e478f9。
- **缓存、临时产物与验收文档整理 (2026-08-15)** — 按用户确认删除 7 个未跟踪的一次性 demo 日志和历史 trace；将 v1.2.1 验收快照归档至 `docs/archive/verification-reports/acceptance-history-v1.2.1.md`，`docs/acceptance_report.md` 收缩为 v1.3.0 当前基线与回归摘要；README 启动说明压缩为入口与关键警告。验证以文档检查、版本检查和 `git diff --check` 为准。
- **文档—代码矛盾复核与结构性去重 (2026-07-31)** — 4 个只读子代理分区审查 + 主代理逐条代码实证复核。修正无效测试基线（`623/8` 系系统 Python 降级结果，更正并在 AGENTS.md 加"基线必须走 uv run"硬约定）；`sensitive_personal` 可落 LOW 与报告 Markdown 转义缺失两处按用户决策只改文档、缺口录入 Blockers；新增未知 domain profile WARNING + 10 条测试；结构性去重（CLAUDE.md / local_setup.md / lite-mode.md 并入 startup.md）；删除失效 examples JSON 等。验证：660 passed / 1 skipped、doc-check 50 份 0 违规、mypy 155 文件 0 issue。决策：`.upgrade/decisions/doc-code-reconciliation-20260731.md`。
- **2026-07-14 – 2026-07-27（摘要，详情见 CHANGELOG 对应日期条目与归档报告）**：
  - 文档—代码深度复核与失效脚本清理 (2026-07-27)、Git/Docker ignore 边界加固 (2026-07-25，决策 `ignore-boundary-hardening-20260725.md`)、代理指导文件同步 (2026-07-25)、文档与业务代码一致性整理 (2026-07-25)。
  - 本地 CI 复现 + 远端三 job 全绿 (2026-07-18，报告 `ci-run-20260718.md`)、四种启动方式全流程 E2E + 6 缺陷修复 (2026-07-18，报告 `startup-methods-e2e-20260718.md`)、生产启动链路加固 (2026-07-18)。
  - 启动方式审计与偏差修复、文档同步收尾、Mode 3/4 工作区清理 (2026-07-17)。
  - formal-project-uplift Wave A–E (2026-07-17，计划 `.upgrade/archive/plans/2026-07-17-formal-project-uplift.md`)：门面治理 / mypy 清零 / LLM Judge (v1.3.0) / 合规映射复核 / 公开前检查与 CI 增强。
  - 文档同步 + `.upgrade` 整理 (2026-07-16)、GitHub CI 离线全流程验证 (2026-07-15)、文档对齐 + 前端中文化收尾 (2026-07-14)、E2E 全流程复测 (2026-07-14)。
  - Phase 1 (v1.0.3) / Phase 2 (v1.1.0) / Phase 3 (v1.2.0) / Phase 4 (v1.2.1) 全部完成 (2026-07-14)。

## Current Authority and Historical Context

当前执行应优先读取 `AGENTS.md`、当前业务代码与测试、`docs/spec/`、`docs/startup.md`、`docs/local_setup.md`、`.upgrade/STATE.md` 和 `.upgrade/MANIFEST.md`。下列归档文件仅作为历史背景或证据，不代表当前计划、实现状态或待办：

- `.upgrade/MANIFEST.md`
- `docs/archive/plan/phase-1-design.md` — Phase 1 历史设计方案
- `docs/archive/plan/phase-2-design.md` — Phase 2 详细设计方案
- `docs/archive/plan/phase-3-design.md` — Phase 3 详细设计方案
- `docs/archive/plan/phase-4-design.md` — Phase 4 详细设计方案
- `docs/archive/plan/phase-1-security-compliance.md` — Phase 1 实施计划
- `docs/archive/plan/phase-2-risk-taxonomy.md` — Phase 2 实施计划
- `docs/archive/plan/phase-3-governance-platform.md` — Phase 3 实施计划
- `docs/archive/plan/phase-4-community.md` — Phase 4 实施计划
- `docs/archive/plan/improvement-roadmap.md` — roadmap
- `docs/spec/governance-platform.md` — 治理平台设计规格
- `docs/spec/supply-chain-security.md` — 供应链与 CI 安全设计规格
- `docs/compliance/iso42001-mapping.md` — ISO/IEC 42001 条款映射表
- `.upgrade/archive/reports/standard-tracking-2026-07-14.md` — 历史标准动态跟踪记录

## Blockers

- **旧 Docker 镜像敏感文件复核**：本次已修复 build context，但 Docker Desktop daemon 当前未运行，无法检查修复前构建的本地/远端镜像是否含 `/app/secrets`。daemon 恢复后需重建并检查；如旧镜像曾被推送或分享，应轮换相关密钥。步骤见 `.upgrade/decisions/ignore-boundary-hardening-20260725.md`。
- **Phase 4 T4.2 分支保护**：决策记录已入库（`.upgrade/decisions/branch-protection.md`），但实际开启需维护者登录 GitHub 后台手动操作（Settings → Branches → main → Enable protection）。操作后预期 Scorecard Branch-Protection 0→8+、Code-Review 0→3-5。
- ~~`sensitive_personal` 升档不是地板值~~（已修复，2026-09-01，提交 a9f18a2）。
- ~~报告 Markdown 导出无转义~~（已修复，2026-09-01，提交 57de39f；JSON 导出净化责任仍在消费端，见 `docs/spec/security-model.md`）。
- ~~`premortem_pending_actions` 指标语义错配~~（已修复，2026-09-01，提交 8023d7c；仍无周期性调度，仅启动时刷新）。
- Phase 3 T3.6 (LLM Judge)：已随 Wave C 落地（v1.3.0，flag 默认关）。真实 LLM 一致率数据待生产启用后经 human_calibrations 累计。
- NIST AI 600-1 中 4 项动作项编号标 [存疑]（MS-2.10-002 / MS-2.5-005 / MS-2.5-003 / GV-1.3-002），待 NIST 发布修订版后核对。
- TC260《智能体部署使用安全指引》条款文字基于二手摘要，待补全文核对。
- ISO 42001 映射未覆盖缺口（更新后 3 项）：系统停用/退役阶段、跨租户集团视图、第三方供应链风险集成。

## Active Stage Report

Phase 0–4 与 formal-project-uplift 代码侧全部完成。能力现状一览：

- 文档一致性 CI（doc-check）已转强制；mypy 与 docker-full-integration 维持 non-blocking 观察期。
- 社区模板（Issue/PR/CoC/GOVERNANCE/CODEOWNERS）齐备；分支保护待维护者 GitHub 后台操作。
- 前端侧栏会话删除（admin 门控 + 二次确认）与治理总览中文化已落地（2026-09-01）；死代码 panels 已清理。
- 三个已知代码缺口已修复（2026-09-01）：sensitive_personal 风险地板值、报告 Markdown 导出净化、pending_actions 指标语义。
- 当前测试基线：681 passed, 1 skipped（2026-09-01，`uv run pytest` / 项目 `.venv` 等价命令），详见 `docs/acceptance_report.md` 与 `CHANGELOG.md`；不从历史小节推断当前测试数量。

## Validation Commands

- `git status --short`
- `uv run python scripts/version_check.py`
- `uv run ruff check . && uv run ruff format --check .`
- `Copy-Item -Force .env.demo .env; uv run pytest tests/ -q`
- `python scripts/doc_consistency_check.py`
- `git tag --list` (expect `v1.3.0`；历史 tag v1.0.x–v1.2.0 在仓库整理时未保留，见 CHANGELOG 追溯说明)

## Next Action

1. **远端治理核验**：按 `.upgrade/decisions/branch-protection.md` 和当前 GitHub 设置逐项确认分支保护、Private vulnerability reporting、Dependabot、CodeQL required check、Scorecard、徽章及 GitHub Release；本地 workflow 和 tag 不能替代远端实查。
2. **观察期评估**：mypy 与 `docker-full-integration` 均继续 non-blocking；待远端稳定数轮并单独评估后再决定是否移除 `continue-on-error`
3. **【已过期，待执行】未成年人 AI 应用指南复核**：《未成年人 AI 应用安全指南》征求意见截止（2026-08-16）已过，需核对定稿内容并回填 roadmap §10.7（截至 2026-09-01 未执行）

## Last Updated

- Date: 2026-09-18（文档与配置生命周期审计）
- By: Codex（用户要求：读取当前权威文档与业务代码，盘点 Markdown、配置、说明和报告文件，并按压缩/更新/归档/需确认分类；本轮只读审计，未删除或移动文件）
- Summary: 核对 `AGENTS.md`、`.upgrade/STATE.md`、`core/version.py`、`pyproject.toml`、迁移链、`core/migrations/registry.py`、`docs/spec/` 与主要业务引用。当前代码权威事实未发现版本、schema 或迁移头冲突；确认 50 份 Markdown，当前文档与历史归档边界总体清晰。发现 `docs/acceptance_report.md` 尾部日期仍为 2026-08-15、`.upgrade/MANIFEST.md` 的“v1.3.0 已发布”措辞强于 STATE 可证明范围、若干 spec 复核日期和治理历史措辞滞后。未发现可仅凭本地证据安全删除的产品文档；远端发布/分支保护/CodeQL 转正、外部标准定稿复核和运行时产物归属列为需人工确认。

- Date: 2026-09-01（第二批）
- By: Trae Code（用户决策：按顺序依次修复三个已知代码缺口，每个修复完成后立即本地 git 提交）
- Summary: 修复①sensitive_personal 地板值（a9f18a2）、②报告 Markdown 导出净化（57de39f）、③pending_actions 指标语义（8023d7c）；新增/改写 15 条测试；三处 spec 同步；Blockers 移除三条已修复项；基线 681 passed / 1 skipped。

### 上一轮（2026-09-01 第一批）

- Date: 2026-09-01
- By: Trae Code（按用户 5 项决策执行：①先建自动化测试再落账——新增 6 条前端契约测试后记录；②删除 11 个死代码文件；③三个已知代码缺口当时维持文档登记；④STATE.md 历史条目压缩；⑤仅本地 git 提交不推送。基线 666 passed / 1 skipped。）
- Summary: 前端会话删除功能 + 治理图表中文化 + 契约测试；死代码清理（1157 行）；STATE.md 压缩 2026-07-14–07-27 条目为摘要；Next Action #3 标记已过期。

### 上一轮（2026-08-22）

- Date: 2026-08-22
- By: claude-code（用户确认 6 项处置建议：docs/plan/ → docs/archive/plan/ 归档、.upgrade/plans/ → .upgrade/archive/ 归档、.upgrade/reports/ → .upgrade/archive/ 归档、.upgrade/research/ 删除、pia-university-mental-health 归档、STATE.md 更新。同步更新全部交叉引用。）
- Summary: 文档整理与状态同步。Phase 0–4 全部历史计划文件归档至 `docs/archive/plan/`；.upgrade/ 已完成 Wave 计划与报告移至 `.upgrade/archive/`；对标调研数据快照删除；PIA 场景文档归档；STATE.md 更新为"仓库已公开"状态。同日以 Docker Lite 启动项目并完成治理总览视图隔离与图表修复。

### 上一轮（2026-07-31 及以前）

- 2026-07-31（Claude Code）：文档—代码矛盾复核与结构性去重，决策 `.upgrade/decisions/doc-code-reconciliation-20260731.md`。
- 2026-07-20（claude-code）：Mode 5+4+3 三路扫描整理，删除 12 个一次性 CI 日志。
- 2026-07-18（claude-code）：本地 CI 复现 + 远端 GitHub CI 三 job 全绿，报告 `ci-run-20260718.md`。
