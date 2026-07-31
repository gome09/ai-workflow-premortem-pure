# 文档—代码矛盾复核与结构性去重（2026-07-31）

## 背景

用户要求读取项目文件，判定 Markdown 与业务代码是否矛盾，并对冗余/矛盾/失效内容做删除、合并、更新。方法：4 个只读子代理分区审查（根目录门面 / `docs/spec` / 运行部署 / 合规+计划+`.upgrade`），主代理对每条发现做代码实证复核后才落笔。涉及取舍的 5 组问题逐项询问用户后执行。

基线：commit `a3d0aec` / v1.3.0 / Alembic V005 / ProjectContext 0.9.0。

## 关键发现与处置

### H1 测试基线是用错解释器录进去的（已修正）

`AGENTS.md` / `CLAUDE.md` / `docs/acceptance_report.md` / `.upgrade/STATE.md` 四处把 `623 passed, 8 skipped` 记为当前基线。

根因：`acceptance_report.md` 记录的命令是裸 `python -m pytest tests/ -q` 而非 `uv run`。系统 Python 未安装 `prometheus-fastapi-instrumentator`（`pyproject.toml:43` 的正式依赖），触发 7 处 `importorskip` 跳过（`tests/test_api.py:14`、`test_data_classification.py:24`、`test_session_lifecycle.py:26`、`test_gate_report.py:361/371/391/405`）。2026-07-25 一轮据此还把 `startup.md` / `local_setup.md` 中原本正确的 650/1 改错。

处置：更正为实测值，并在 `AGENTS.md` 增加"基线必须走 `uv run`"的硬性约定，避免再次复现。

### H2 `sensitive_personal` 升档不是地板值（改文档，代码缺口保留）

`docs/spec/data-classification-and-privacy.md` 称 `sensitive_personal` 会话"至少 HIGH"。实测反例：

```python
ctx = ProjectContext(research_target="个人读书笔记助手", goal="学习计划整理")
ctx.data_classification = "sensitive_personal"
classify_project_risk(ctx)   # → (low, ['sensitive_personal data classification', 'low_scope: ...'])
```

`core/gates/risk_profile.py` 第 3.5 步升档后，第 4 步 low-scope 会再降一级，第 5 步还会无条件置 LOW。代码自身注释 `# → raise to at least HIGH` 同样不准确。

**用户决策：只改文档，如实记录现状。** spec 已改为描述真实行为并附可复现示例与⚠️告警。**代码缺口未修复**——如需"敏感个人信息必进 HIGH"的强制下限，需另行改 `risk_profile.py` 并补回归测试。

### H3 报告 Markdown 转义从未实现（改文档，代码缺口保留）

`docs/spec/risk-taxonomy-engine.md` 称 `core/report_service.py` 的 Markdown 导出对危险模式做转义。该文件 `escape` / `sanit` / `markupsafe` / `html` / `UNSAFE` 全部零命中，`build_markdown_report` 直接 f-string 拼接 finding description。

同段关于 `scan_text` 的第一条陈述是**真的**（`UNSAFE_OUTPUT_PATTERNS` 确在 `tools/safety_classifier.py:63`），只有转义这一条是假的。

**用户决策：只改文档。** spec 已标注"未实现（已知缺口）"，并写明当前唯一防线是 `improper_output_handling` finding（检测而非阻断），报告消费方需自行做输出净化。**代码缺口未修复。**

### H4 domain profile 不是零改动扩展点（改文档 + 补告警）

`docs/demo-scenarios.md` 教用户新增 `stages/domain_profiles/finance_ai.py` 即可支持新领域。实测 `get_stage_prompts('finance_ai')` 静默返回 default bundle——分发是只认 `university_ai` / `medical_ai` 的硬编码 if 链，共 4 处（`stages/prompts.py`、`stages/json_prompts.py`、`tools/risk_taxonomy.py`、`graph/nodes.py`）。`scenarios/registry.py` 只校验模块可导入，manifest 校验也会通过。

同文称未知 mock fixture 会"回退 default"，实测直接 `ModuleNotFoundError`（无 try/except）。

**用户决策：改文档 + 补未知 profile 告警。**
- 文档列出 4 处分发点，并区分「mock fixture 是真正的零改动扩展点」与「domain profile 不是」。
- 代码：`stages/prompts.py` 新增 `KNOWN_PROFILES`，`get_stage_prompts` / `get_json_prompts` 对未注册 profile 打 WARNING（行为仍是回落 default，不改变既有语义）。
- 测试：新增 `tests/test_unknown_domain_profile_warning.py`（10 条），覆盖回落行为不变、未知 profile 告警、已注册 profile 静默。

## 结构性去重（用户逐项确认）

| 动作 | 理由 |
|---|---|
| `CLAUDE.md` 去重，只保留目录结构表 / Ruff-pytest 细则 / `docs/spec` 状态清单三块独有内容 | 与 `AGENTS.md` 重复承载 5 组可漂移事实，H1 正是在两处同步错的。`AGENTS.md` 补充说明分工，明确新增可漂移事实只写 AGENTS。`project-upgrade` 受控块原文保留 |
| `docs/local_setup.md` 重写，启动步骤改为引用 `startup.md` | 原文约 52% 逐字重复 startup.md，且已分叉（登录示例 host 不同）。现只保留环境模板、密钥职责划分、环境变量清单、仓库边界 |
| `docs/lite-mode.md` 并入 `startup.md` 后删除 | 约 49% 与另两份重复；独有的适用边界与代码对应关系表已并入 startup.md「轻量 Docker 模式」。全仓仅 `docs/README.md` 一处引用，已同步 |

## 删除（用户确认）

| 文件/内容 | 理由 |
|---|---|
| `examples/sample_report.json`、`examples/stage_gate_scenarios.json` | `schema_version` 停在 `0.8.0-alpha.11`（当前 `REPORT_SCHEMA_VERSION=1.3.0`），全仓零引用、无测试消费。用户在互斥选项中明确选择删除而非刷新版本号 |
| `docs/local_setup.md` 的 `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` 两行 | 这两个变量全仓只存在于该文件自身，作为"已删除"条目无对照价值 |
| `storage/README.md` 的 "Note on removed code" 段 | 所述 `storage/migrations/` 在可见 git 历史中无任何痕迹（仓库历史起点是压缩基线），无法证实也无追溯价值 |

## 其他事实性修正

- `CHANGELOG.md` 头部：远端"2026-05-31 起 21 次提交"不成立——全部 ref 中最早提交是 `5ecffaf`（2026-06-13），远端与本地共享同一根提交，不含更早历史。
- `README.en.md`：ISO/IEC 42001 从 taxonomy engine 表述中移出（`tools/` 中 42001 零命中，它只是 `docs/compliance/` 的人工映射文档）。
- `README.md`：技术栈表补 SQLite；"Audit Workbench" 统一为 "Review Workbench"；LOW/MEDIUM 门禁描述按实现改写（两档 `require_*` 标志逐字段相同）；`gen_secrets` 说明改为"4 个随机化、3 个同步 .env"；新增 `make demo-api/demo-ui` 无条件覆盖 `.env` 的警告。
- `.github/ISSUE_TEMPLATE/bug_report.md`：`LLM_MODE` 候选值 `deepseek` → `real / mock`（实际 `Literal["real","mock"]`）；示例版本 v1.2.0 → v1.3.0。
- `docs/spec/governance-platform.md`：V005 不含 `ALTER TABLE eval_runs`，`llm_judge_suggestion` 无独立列（随 `context_json` 与 `eval_judgments.metadata` 落库）；规则禁用 WARNING 的真实时机；字段名 `disable_allowed` → `safety_bottom_line`。
- `docs/spec/stage3-risk-adaptive-gate.md`：「心理健康」「军事」从 CRITICAL 行移到 HIGH 行；补注 LOW 档并非只有安全底线。
- `docs/spec/architecture.md`：补复数入口 `sync_execution_after_action_resolutions`。
- `docs/spec/supply-chain-security.md`：悬空引用改过去时；补记 `.github/workflows/scorecard.yml` 已入库。
- `docs/spec/risk-taxonomy-engine.md`：去掉漂移的 `mapper.py:139-163` 行号。
- `docs/compliance/iso42001-mapping.md`：证据路径 `.upgrade/logs/` → `.upgrade/reports/standard-tracking-2026-07-14.md`。
- `scripts/README.md`：补登 `live_e2e_four_stage.py`（此前唯一"存在但未登记"的脚本，`BASE_URL` 硬编码无覆盖手段）；`gen_secrets.sh` 描述由"生成 .env 值"修正为"以 `secrets/` 为主产物，三项同步回 .env"。

## 明确保留、未改动

- `docs/plan/` 11 份历史计划：历史定位标注齐全，用户未要求处理。
- `.upgrade/plans/` 7 份：MANIFEST 标 `permanent`，整批归档已有 defer 决策（仓库公开 + Task 19 闭环后）。
- 8 份 `docs/spec/` 无职责重叠可合并者；`security-model.md` 对 data-classification 是"摘要 + 链接"的正确分层。
- 三条安全边界（字段加密未默认启用 / 留存无自动清理器 / PII 掩码默认关）在 `docs/compliance/` 中表述正确，未改动。
- `api/metrics.py` 中 `premortem_pending_actions` 被喂会话风险档位数据的语义错配：属代码缺陷，本轮未在用户确认范围内，留待后续。

## 验证

| 项 | 结果 |
|---|---|
| `python scripts/doc_consistency_check.py` | 扫描 50 份 Markdown，0 违规 |
| `python scripts/version_check.py` | Version metadata OK: 1.3.0 |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 258 files already formatted |
| `uv run pytest tests/ -q` | **660 passed, 1 skipped** |
| `uv run mypy` | Success: no issues found in 155 source files |
| `git diff --check` | 无空白错误 |

本机 Windows 无 `make` 可执行文件，直接运行 Makefile 对应的底层命令。
