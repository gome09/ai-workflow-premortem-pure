# Upgrade State

## Current Phase

Phase 3 — **全部完成** (T3.1–T3.5, T3.7；T3.6 可选未启用)。Phase 2 全部完成 (T2.1–T2.6)。Phase 1 全部完成 (T1.1–T1.9)。

## Current Task

Phase 3 收尾完成（version bump 1.1.0→1.2.0、CHANGELOG、STATE.md、git tag）。等待进入 Phase 4（社区生态）。

## Last Completed

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
- `docs/plan/phase-1-security-compliance.md` — Phase 1 实施计划
- `docs/plan/phase-2-risk-taxonomy.md` — Phase 2 实施计划
- `docs/plan/phase-3-governance-platform.md` — Phase 3 实施计划
- `docs/plan/phase-4-community.md` — Phase 4 实施计划（下一步）
- `docs/plan/improvement-roadmap.md` — roadmap
- `docs/spec/governance-platform.md` — 治理平台设计规格
- `docs/compliance/iso42001-mapping.md` — ISO/IEC 42001 条款映射表
- `.upgrade/logs/standard-tracking-2026-07-14.md` — 标准动态跟踪记录

## Blockers

- Phase 3 T3.6 (LLM Judge) gated on user confirming real demand for automated evaluation (roadmap §8 preserved condition). 设计完成（spec §5），flag 默认关，待确认后作为独立 Wave 启动。
- NIST AI 600-1 中 4 项动作项编号标 [存疑]（MS-2.10-002 / MS-2.5-005 / MS-2.5-003 / GV-1.3-002），待 NIST 发布修订版后核对。
- TC260《智能体部署使用安全指引》条款文字基于二手摘要，待补全文核对。
- ISO 42001 映射 4 项未覆盖缺口：系统停用/退役阶段、LLM Judge 校准闭环、跨租户集团视图、第三方供应链风险集成。

## Active Stage Report

Phase 3 组织级治理平台全部完成。核心成果：

### 门禁规则治理（T3.1–T3.3）
| 能力 | 实现 | 状态 |
|---|---|---|
| 规则元数据清单 | `core/gates/rules/manifest.py`（13 条 RuleMeta） | ✅ |
| 规则版本携带 | `GateReport.rules[].rule_version` | ✅ |
| 评估记录持久化 | `gate_evaluation_records` 表（alembic V005） | ✅ |
| 规则禁用治理 | `GATE_RULES_DISABLED` + 7 条安全底线不可禁用 | ✅ |
| expert_review 落地 | `core/gates/rules/expert_review.py`（补历史欠账） | ✅ |

### 组织级治理视图（T3.4–T3.5）
| 能力 | 实现 | 状态 |
|---|---|---|
| 治理聚合 API | `/governance/overview` + `/gate-trends` + `/actions-backlog` | ✅ |
| Streamlit 治理页 | `frontend/components/governance_overview.py` | ✅ |
| Prometheus 业务指标 | `api/metrics.py`（6 个 premortem_* 指标） | ✅ |
| Grafana 治理面板 | `monitoring/grafana/dashboards/governance-overview.json` | ✅ |

### ISO 42001 对齐（T3.7）
| 审计提问 | 回答来源 |
|---|---|
| 规则谁定的、改过几次 | manifest + git 历史 + changelog |
| 评估依据什么规则版本 | 报告内嵌 rule_versions |
| 高风险是否经专家复核 | expert_review 动作记录 |
| 门禁通过率趋势 | `/governance/gate-trends` |

### 测试验证
- 全量测试：642 passed, 1 skipped
- e2e-mock：63 passed
- 新增测试文件：5 个（共 115 个新测试用例）
- lint + format：clean

## Validation Commands

- `git status --short`
- `uv run python scripts/version_check.py`
- `uv run ruff check . && uv run ruff format --check .`
- `Copy-Item -Force .env.demo .env; uv run pytest tests/ -q`
- `git tag --list` (expect `v1.0.2`, `v1.0.3`, `v1.1.0`, `v1.2.0`)

## Next Action

Enter Phase 4 (community ecosystem) per `docs/plan/phase-4-community.md`.

## Last Updated

- Date: 2026-07-14
- By: trae-agent (Wave 6 收尾)
- Summary: Phase 3 全部完成（T3.1–T3.5, T3.7；T3.6 可选未启用），4 commits: fbcfdfe / b534929 / 16c3439 / 0bca456，version v1.2.0。642 unit tests + 63 e2e-mock passed。Phase 2 全部完成 (v1.1.0)，Phase 1 全部完成 (v1.0.3)。
