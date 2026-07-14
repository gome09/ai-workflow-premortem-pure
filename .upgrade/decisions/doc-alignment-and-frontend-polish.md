# 决策记录：文档对齐 + 前端中文化收尾（demo 可运行性打磨）

- **日期**：2026-07-14
- **触发**：基于四维审计（路线图达成度 / 前端中文展示 / 文档-代码对齐 / 启动方式）发现的"文档元数据漂移 + 前端英文泄漏"欠债，做一次收尾对齐，使项目成为一个干净、可运行、以中文展示的 demo。
- **约束**：只修文档与前端展示层 + 一处 dev 工具（doc-check 脚本）；不改业务逻辑、不改门禁/状态机/存储。

## 背景（发现的问题）

1. 四份 `docs/spec/` 规格（governance-platform / risk-taxonomy-engine / data-classification-and-privacy / supply-chain-security）代码已随 Phase 1–4 落地，但文件头仍标 `Status: Designed, not implemented`，违反 CLAUDE.md 自身规则；`CLAUDE.md` 亦仍把这四份列为"设计态"。
2. phase-0~3 实施计划验收清单与 `improvement-roadmap.md` §6 未勾选（代码已完成）。
3. `api-reference.md` 缺失治理 API（`/governance/*`），路由总数偏低（79 → 实际 84）。
4. `security-model.md` 落后约两个阶段：缺 3 个新增 SafetyFinding 风险类型、字段加密、PII 掩码、数据分级。
5. `docs/README.md` 索引漏列 `iso42001-mapping.md`；`startup.md` 测试数（388）过时（实际 642）。
6. `doc-check` 报 25 处违规（其中约 15 处为围栏代码块内示例的误报，约 10 处为文档重构遗留的真实坏链）。
7. 前端英文泄漏：侧边栏健康状态（常驻）、欢迎页（首屏）、待处理动作/安全发现的裸英文枚举。

## 决策

### 1. doc-check：改脚本而非改文档去消除误报
- **决策**：在 `scripts/doc_consistency_check.py` 中新增"跳过围栏代码块（``` / ~~~）"逻辑。
- **理由**：脚本自身设计约束写明"误报率高于约 5% 就收窄规则"；25 处违规中约 60% 是围栏内的示例代码/嵌入文档草稿（如 phase-*-design.md 内嵌的提议脚本源码、CONTRIBUTING.md 草稿）。对这些示例内容做链接/路径校验本就无意义，改文档会破坏合法的设计文档。
- **真实坏链**（围栏外的散文）逐条修复：如 `incident-response.md` 的 `../SECURITY.md`（应为 `../../SECURITY.md`）。
- **围栏外的行内误报**（模块点号引用、YYYYMMDD 占位符、"例如"示例路径、"make target"规则名）做最小文档改写消除。
- **结果**：doc-check 从 25 → 0，为后续把 CI 的 `continue-on-error: true` 转强制铺平道路（路线图 Next Action #3）。

### 2. Spec Status 表头翻转
- 四份规格 Status 行改为 `Implemented（<版本>）`，`Last updated` 更新为 2026-07-14；`CLAUDE.md` 文档维护段同步改为"全部已实现"，并保留"今后新增设计态规格仍用 Designed 标注"的约定。

### 3. 验收清单勾选（诚实勾选，未完成项保留 `[ ]` 并注明原因）
- phase-0/1/2 全勾；phase-3 勾 6 项、保留"LLM Judge（T3.6 可选未启用）"未勾。
- roadmap §6 勾 18 项，保留 5 项：TC260/未成年人指南"持续跟踪"、LLM Judge 评估、分支保护（待 GitHub 后台手动）、Signed Releases/CII Badge 可选项。

### 4. 前端中文化（展示层，零业务改动）
- `frontend/labels.py` 新增 `RISK_TYPE_ZH` / `EXEC_MODE_ZH` / `ADAPTER_STATUS_ZH` 映射 + 对应 `*_zh()` helper（沿用"查不到回退原值"策略）。
- `frontend/app.py`：侧边栏健康状态 caption、欢迎页首屏、待处理人工动作标题、安全发现 risk_type 均改走中文映射；`action_type` 复用已有 `resolution_zh`。
- 未处理的深层面板（redteam / eval 的 run_mode/scenario_type 等）留待后续，均有 `zh()` 回退兜底，不影响可读性。

## 验证（2026-07-14 实测）
- `ruff check` / `ruff format --check`：clean（257 files）
- `py_compile` app.py / labels.py / doc_consistency_check.py：OK
- `version_check`：1.2.1 OK
- `doc_consistency_check`：0 violations
- e2e-mock：63 passed；全量 `pytest tests/`：642 passed, 1 skipped
- 后端 `api.main:app` 加载 OK；前端 labels 新增 helper 导入 OK

## 未闭环（保留给维护者）
- GitHub 后台开启 main 分支保护（见 [[branch-protection]]）
- doc-check 已清零，可择机移除 `.github/workflows/ci.yml` 的 `continue-on-error: true` 转强制
- 前端深层面板剩余英文枚举（低优先，已有回退兜底）
