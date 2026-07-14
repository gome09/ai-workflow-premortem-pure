# Upgrade State

## Current Phase

Phase 3 Wave 3 — T3.4 完成。Phase 2 全部完成 (T2.1–T2.6, 5 Waves)。Phase 1 全部完成 (T1.1–T1.9)。

## Current Task

T3.4（组织级聚合 API 与前端治理页）已完成。

## Last Completed

- **Phase 3 Wave 3 (2026-07-14)** — T3.4 组织级聚合 API 与前端治理页：api/routers/governance.py 三个只读端点（overview/gate-trends/actions-backlog，viewer 可读）；api/main.py 接入 governance router；frontend/components/governance_overview.py 治理总览页（三卡片+风险分布+通过率趋势+积压动作表）；frontend/app.py 侧边栏追加"治理总览"导航；tests/test_governance_api_v110.py 24 测试全通过
- **Phase 3 Wave 1 (2026-07-14)** — T3.1 门禁规则元数据清单（manifest）：core/gates/rules/manifest.py + get_rule_version/is_safety_bottom_line + 11 测试
- **Phase 2 Wave 5 (2026-07-14)** — 收尾：version bump 1.0.3→1.1.0、CHANGELOG v1.1.0、STATE.md 更新
- **Phase 2 Wave 4 (2026-07-14)** — T2.6 标准动态跟踪记录（`.upgrade/logs/standard-tracking-2026-07-14.md`，7 标准基线 + 6 跟踪项）
- **Phase 2 Wave 3 (2026-07-14, commit 56272f2)** — T2.5 领域扩展标签接入生产链路：`apply_taxonomy_to_safety_finding` 加 domain 参数；`_finding`/`add_findings_dedup`/`resolve_safety_finding` 透传 domain；20 新测试
- **Phase 2 Wave 2 (2026-07-14, commit 318d58a)** — mapper.py 三表聚合接入（NIST_GAI+ASI+TC260）+ 17 集成测试
- **Phase 2 Wave 1 (2026-07-14, commit ca42811)** — T2.1+T2.2+T2.3+T2.4 四任务并行：32 files +2115/-29；OWASP LLM 2025 补齐(LLM05/07/10) + Context schema v0.9.0 + NIST AI 600-1 + OWASP ASI 2026 + TC260 智能体指引
- **Phase 2 Design Plan (2026-07-14)** — 详细设计方案 `docs/plan/phase-2-design.md`
- **Phase 1 全部完成 (2026-07-14, v1.0.3)** — T1.1–T1.9 安全与合规硬缺口修复，7 commits across 6 Waves

## Required Context Files

- `.upgrade/MANIFEST.md`
- `docs/plan/phase-1-design.md` — Phase 1 详细设计方案
- `docs/plan/phase-2-design.md` — Phase 2 详细设计方案
- `docs/plan/phase-1-security-compliance.md` — Phase 1 实施计划
- `docs/plan/phase-2-risk-taxonomy.md` — Phase 2 实施计划
- `docs/plan/phase-3-governance-platform.md` — Phase 3 实施计划（下一步）
- `docs/plan/improvement-roadmap.md` — roadmap（第 10 节为 2026-07-13 外部标准复核增补）
- `docs/spec/risk-taxonomy-engine.md` — 风险分类体系升级设计规格
- `docs/compliance/` — PIA 文档 + 应急响应 + 备份指引
- `.upgrade/logs/standard-tracking-2026-07-14.md` — 标准动态跟踪记录
- `.upgrade/reports/nist-ai-600-1-action-summary.md` — NIST AI 600-1 动作项摘要
- `.upgrade/reports/tc260-agent-deployment-summary.md` — TC260 智能体部署指引摘要

## Blockers

- Phase 3 T3.6 (LLM Judge) gated on user confirming real demand for automated evaluation (roadmap §8 preserved condition).
- NIST AI 600-1 中 4 项动作项编号标 [存疑]（MS-2.10-002 / MS-2.5-005 / MS-2.5-003 / GV-1.3-002），待 NIST 发布修订版后核对。
- TC260《智能体部署使用安全指引》条款文字基于二手摘要，待补全文核对。

## Active Stage Report

Phase 2 AI 风险分类体系补强全部完成。核心成果：

### OWASP LLM Top 10 2025 补齐
| LLM 条目 | 对应 risk_type | 状态 |
|---|---|---|
| LLM01 Prompt Injection | prompt_injection | ✅ 既有 |
| LLM02 Sensitive Information | sensitive_info | ✅ 既有 |
| LLM05 Improper Output Handling | improper_output_handling | ✅ T2.1 新增 |
| LLM06 Excessive Agency | over_autonomy | ✅ 既有 |
| LLM07 System Prompt Leakage | system_prompt_leakage | ✅ T2.1 新增 |
| LLM09 Misinformation | unsupported_claim | ✅ 既有 |
| LLM10 Unbounded Consumption | unbounded_consumption | ✅ T2.1 新增 |
| LLM08 Vector/Embeddings | — | ⏸️ 暂缓（项目无 RAG 组件） |

### 新标准映射
| 标准 | 代码位置 | 覆盖 | 备注 |
|---|---|---|---|
| NIST AI 600-1 GAI Profile | `nist_ai_600_1.py` | 10 risk_type 全覆盖 | 4 项 [存疑] |
| OWASP ASI 2026 | `owasp_agentic_2026.py` | 5 risk + 8 attack | ASI07 已修正 |
| TC260 智能体指引 | `tc260_agent_deployment.py` | 5 阶段 + 6 control + 6 risk | 停用=None |

### 领域扩展标签
- `apply_taxonomy_to_safety_finding(finding, domain)` 命中 university_ai/medical_ai 时叠加 PIPL/HIPAA 等领域专属标签
- 生产链路三处调用点（_finding / add_findings_dedup / resolve_safety_finding）均透传 domain

### Context schema 升级
- v0.8.0 → v0.9.0（ProjectContext 新增 llm_call_count / llm_token_estimate）
- 迁移链：v0.6.0 → v0.7.0 → v0.8.0 → v0.9.0

### 测试验证
- 全量测试：524 passed, 1 skipped
- e2e-mock：63 passed
- 新增测试文件：7 个（共 90 个新测试用例）
- lint + format：clean

## Validation Commands

- `git status --short`
- `uv run python scripts/version_check.py`
- `uv run ruff check . && uv run ruff format --check .`
- `Copy-Item -Force .env.demo .env; uv run pytest tests/ -q`
- `git tag --list` (expect `v1.0.2`, `v1.0.3`, `v1.1.0`)

## Next Action

Phase 3 Wave 3 后续：T3.3/T3.5/T3.6 等治理平台任务（core/ 层 + LLM Judge 等）。

## Last Updated

- Date: 2026-07-14
- By: trae-agent (Phase 3 Wave 3, Agent D)
- Summary: T3.4 完成——治理只读 API 三端点（viewer 可读、tenant 隔离）、前端治理总览页、24 新测试全通过，e2e-mock 63 通过，lint clean。
