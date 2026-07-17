# Wave B — mypy 渐进式类型检查 具体实施部署方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地父计划（`.upgrade/plans/2026-07-17-formal-project-uplift.md`）Wave B（Task 7–8）：引入 mypy 全局宽松基线并清零 108 个基线错误，对 `core.gates` + `graph` 上近 strict（清零 25 个错误），CI 接入非阻断 typecheck。

**Architecture:** inspect_ai 模式渐进式类型检查——`[tool.mypy]` 全局宽松（files 限 7 个核心包，排除 tests/frontend/scripts/examples/alembic）+ `[[tool.mypy.overrides]]` 对门禁引擎与状态机近 strict。修复阶段按包分片（storage / core+stages / graph+tools+api），三片文件集互不相交，可由并行 subagent 分别产出修复、由主控按序提交。

**Tech Stack:** mypy（`>=1.14` 约束，2026-07-17 实测解析到 **mypy 2.3.0**，无需 pydantic 插件即可跑通）、uv、make、GitHub Actions。

**探索基线（2026-07-17，三个并行调研 subagent 产出，原始数据已存档）：**

| 事实 | 数值 / 位置 |
|---|---|
| 宽松档基线 | **108 errors / 27 files / 153 files checked**（raw: `.upgrade/tmp/mypy-dryrun-lenient-20260717.txt`，文件头 ~4 行是 uv 下载进度噪声） |
| 宽松档按包分布 | storage 46（postgres.py 独占 44）· core 29 · stages 15 · graph 13 · tools 3 · api 2 · auth 0 |
| 宽松档按 error code | arg-type 33 · call-overload 24 · assignment 20 · unused-ignore 12 · attr-defined 9 · union-attr 4 · call-arg 2 · var-annotated 1 · return-value 1 · no-redef 1 · misc 1 |
| 近 strict（core/gates+graph） | **25 errors / 9 files**（raw: `.upgrade/tmp/mypy-dryrun-strict-gates-graph-20260717.txt`）；其中 10 条 no-untyped-def 纯缺注解，15 条真类型问题 |
| 注解现状 | 两包 96 个 def 中仅 5 个缺返回注解、5 个函数含未注解参数；27/29 文件已有 `from __future__ import annotations`；仅有的装饰器是 4 处 stdlib `@dataclass(frozen=True)`，不会触发 `disallow_untyped_decorators` |
| pyproject 现状 | Wave A 已应用（name=ai-workflow-premortem，hatchling 就位）；**无** `[tool.mypy]`；文件共 113 行，最后一节是 `[tool.coverage.report]`；`scripts/version_check.py` 的正则 `^version\s*=` 不受追加节影响 |
| Makefile 现状 | 无 `typecheck` target；`lint:` 块之后是 `audit:`；recipe 用 TAB；`.PHONY` 是第 3 行单行声明 |
| ci.yml 现状 | `Lint` 步骤在 `lint-and-unit-tests` job 内，step 列表项 6 空格缩进、步骤体 8 空格 |

**任务依赖图：**

```
B1（配置+基线报告）
 ├→ B2（storage 清零，可与 B3/B4 并行探索）
 ├→ B3（core+stages 清零，可与 B2/B4 并行探索）
 └→ B4（graph+tools+api 清零，可与 B2/B3 并行探索）
      B2+B3+B4 全部完成（宽松档 Success）
       └→ B5（近 strict overrides + 25 错误清零）
            └→ B6（CI 接入 + 基线报告收尾 + STATE.md + 父计划勾选）
```

**并行部署方式（用户已授权 Subagent-Driven）：** B2/B3/B4 的文件集互不相交，允许三个 subagent **并行产出修复**；但为满足 CLAUDE.md「每任务一个 commit、显式 staging」纪律，并行时 subagent **只改文件不提交**，由主控在三片各自验证后按 B2→B3→B4 顺序逐片 `git add <明确文件> && git commit`。若选择稳妥的顺序执行（每任务一个新 subagent、任务内自行提交），效果等价、耗时略长。B1/B5/B6 必须串行。

**全局纪律（每个任务适用）：**
- 修复原则按 error code 分类：真类型错误（arg-type/assignment/union-attr/call-arg/return-value/var-annotated/no-redef）→ **修代码**；第三方/动态误报 → 行尾 `# type: ignore[<code>]`（**必须带具体 code，禁止裸 ignore**）；`unused-ignore` → 删除或改窄既有 ignore 注释；`attr-defined` 中「does not explicitly export」类 → 在被引用模块的 `__init__.py` 用 `from x import y as y` 显式 re-export 或改从源模块导入。
- **只修类型不改运行时行为**；每片修复后 `make test` 必须全绿（615+ passed）。
- 禁止 `git add .`；每任务完成后勾选本文件及父计划对应 checkbox。

---

## Task B1: mypy 依赖 + 配置 + Makefile target + 基线报告

**Files:**
- Modify: `pyproject.toml`（dev 依赖 + 文末追加 `[tool.mypy]`）
- Modify: `Makefile`（`.PHONY` + `typecheck` target）
- Modify: `uv.lock`（自动再生成）
- Create: `.upgrade/reports/mypy-baseline-20260717.md`

- [x] **Step 1: 添加 dev 依赖**

`pyproject.toml` 的 `[project.optional-dependencies]` 现状（第 46–52 行）：

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "pip-audit>=2.7.0",  # T1.8 依赖漏洞审计
]
```

在 `"pip-audit>=2.7.0",  # T1.8 依赖漏洞审计` 行之后追加一行：

```toml
    "mypy>=1.14",
```

- [x] **Step 2: 文末追加 `[tool.mypy]`**

`pyproject.toml` 当前以 `[tool.coverage.report]` 的 `exclude_lines` 列表结尾（第 113 行 `]`，无尾随空行）。在文件末尾追加（先空一行）：

```toml

[tool.mypy]
python_version = "3.11"
# 渐进式引入（inspect_ai 模式）：全局宽松基线，核心包用 overrides 收紧
warn_unused_configs = true
warn_redundant_casts = true
warn_unused_ignores = true
strict_equality = true
no_implicit_reexport = true
# 第三方库缺 stub 时不阻塞
ignore_missing_imports = true
# 先只检查核心逻辑包；frontend（Streamlit 脚本风格）与 tests 暂不纳入
files = ["core", "graph", "stages", "tools", "storage", "auth", "api"]
exclude = ["tests/", "frontend/", "scripts/", "examples/", "alembic/"]
```

- [x] **Step 3: Makefile 新增 target**

Makefile 现状（第 52–59 行附近，recipe 必须用 TAB）：

```make
# 代码检查
lint:
	uv run ruff check .
	uv run ruff format --check .

# 依赖漏洞审计（非阻断）
audit:
	uv run pip-audit --strict
```

在 `lint:` 块与 `# 依赖漏洞审计（非阻断）` 之间插入：

```make
# mypy 类型检查（全局宽松 + core.gates/graph 收紧，配置见 pyproject.toml）
typecheck:
	uv run mypy

```

同时在第 3 行 `.PHONY` 声明中 `lint` 之后插入 ` typecheck`：

```make
.PHONY: install clean dev-db dev-api dev-frontend dev docker-up docker-down lint typecheck test setup setup-win prod-up prod-down prod-logs demo-api demo-frontend demo-ui lite-up e2e-mock e2e-full-test version-check doc-check audit security-check
```

- [x] **Step 4: 同步依赖并首跑，核对基线**

```bash
uv lock && uv sync --all-extras
uv run mypy 2>&1 | tail -5
```

Expected: `Found 108 errors in 27 files (checked 153 source files)`（±个位数偏差可接受——正式安装的 mypy 版本或与 2026-07-17 干跑的 2.3.0 有差；若偏差 >10，先 diff `uv run mypy` 全量输出与 `.upgrade/tmp/mypy-dryrun-lenient-20260717.txt` 找原因再继续）。

- [x] **Step 5: 写基线报告 `.upgrade/reports/mypy-baseline-20260717.md`**

```markdown
# mypy 基线报告（Wave B Task 7）

- 日期：2026-07-17；mypy 版本：<以 `uv run mypy --version` 实际输出为准，干跑为 2.3.0>
- 宽松档基线：108 errors / 27 files / 153 checked（正式首跑实际值：<回填>）
- 按包：storage 46（postgres.py 44）· core 29 · stages 15 · graph 13 · tools 3 · api 2 · auth 0
- 按 code（top）：arg-type 33 · call-overload 24 · assignment 20 · unused-ignore 12 · attr-defined 9
- 近 strict 干跑（core/gates+graph）：25 errors / 9 files（no-untyped-def 10 + 真类型问题 15）
- 原始输出：`.upgrade/tmp/mypy-dryrun-lenient-20260717.txt` / `.upgrade/tmp/mypy-dryrun-strict-gates-graph-20260717.txt`

## 欠账登记（豁免类 override，随修复任务追加）

（B2–B5 中若登记临时豁免，逐条列在此处：module / disable_error_code / 原因 / 清偿条件）
```

- [x] **Step 6: 回归 + 提交**

```bash
make lint && make test
git status --short   # 确认改动仅上述 4 个文件
git add pyproject.toml uv.lock Makefile .upgrade/reports/mypy-baseline-20260717.md
git commit -m "chore: introduce mypy with lenient global baseline (inspect_ai-style gradual typing)"
```

> 注意：此时 `make typecheck` 有 108 个错误属预期，**不要**把 typecheck 加进本次回归命令；宽松档清零由 B2–B4 完成。

---

## Task B2: storage 包清零（46 errors，postgres.py 热点决策）

**Files:**
- Modify: `storage/backends/postgres.py`（44 errors）及 storage 下另 2 处报错文件（以 `uv run mypy | grep "^storage"` 实际输出为准）
- Modify（仅热点走豁免路线时）: `pyproject.toml`（追加 override）
- Modify: `.upgrade/reports/mypy-baseline-20260717.md`（欠账登记）

- [x] **Step 1: 定位本片错误清单**

```bash
uv run mypy 2>&1 | grep "^storage" > .upgrade/tmp/mypy-fix-storage.txt
wc -l .upgrade/tmp/mypy-fix-storage.txt
```

Expected: 46 行（44 条集中在 `postgres.py`，典型如 `postgres.py:885 [call-overload] No overload of tuple.__getitem__ matches argument type "str"`、`postgres.py:882 [attr-defined] "tuple[Any, ...]" has no attribute "get"`）。

- [x] **Step 2: 判定 postgres.py 热点根因**

读 `storage/backends/postgres.py` 的连接/游标构造代码，确认行对象的运行时类型：报错模式（对 row 用字符串下标/`.get()`）说明运行时是 dict 风格行（psycopg `dict_row` 或等价 row_factory），而 mypy 推断为 `tuple[Any, ...]`。

- **若** fetch 调用点少（≤10 处集中函数），优先修代码：在 fetch 边界统一收窄类型，例如：

```python
from typing import Any, cast

row = cast(dict[str, Any], cur.fetchone())
rows = cast(list[dict[str, Any]], cur.fetchall())
```

- **否则**（fetch 点分散、逐行 ignore 将超 30 处）：按父计划「单文件 >20 条同一非关键模式可豁免」规则，在 `pyproject.toml` 的 `[tool.mypy]` 之后追加模块豁免，并在基线报告欠账段登记：

```toml
[[tool.mypy.overrides]]
# postgres 行对象运行时为 dict 风格（row_factory），mypy 推断为 tuple 的系统性误报；
# 清偿条件：fetch 边界统一 cast 或引入 typed row helper 后移除本豁免
module = "storage.backends.postgres"
disable_error_code = ["call-overload", "arg-type", "attr-defined"]
```

> 豁免 code 列表以 Step 1 实际输出为准裁剪；**不得**为掩盖真 bug 而把 `assignment` 等其余 code 加进豁免。storage 其余 2 条错误必须修代码，不入豁免。

- [x] **Step 3: 验证本片清零**

```bash
uv run mypy 2>&1 | grep -c "^storage" || echo 0
```

Expected: `0`

- [x] **Step 4: 回归 + 提交**

```bash
make lint && make test
git status --short
git add storage/backends/postgres.py .upgrade/reports/mypy-baseline-20260717.md
# 走豁免路线时追加：git add pyproject.toml
# storage 其余被改文件逐一显式 add
git commit -m "chore(types): zero mypy lenient-baseline errors in storage (postgres row-typing hotspot)"
```

---

## Task B3: core + stages 清零（29 + 15 errors）

**Files:**
- Modify: `uv run mypy | grep -E "^(core|stages)"` 输出中的文件——已知热点：`core/reviewed_output_service.py`（9 条，含 `:85 [assignment] Stage2Schema 赋给 Stage1Schema 变量`）、`stages/validators.py:137 [arg-type] "Any | str" vs Literal['low','medium','high','critical']`、`stages/stage_4_trigger.py:27 [union-attr]`、`core/oversight_service.py:1305 [call-arg] create_redteam_dataset 意外关键字 "note"`、`core/evidence_service.py:118 [var-annotated]`、`core/eval_service.py:40 [unused-ignore]`

- [x] **Step 1: 定位本片错误清单**

```bash
uv run mypy 2>&1 | grep -E "^(core|stages)" > .upgrade/tmp/mypy-fix-core-stages.txt
```

Expected: 44 行（core 29 + stages 15；若 B2 已合入且加了 override，总数不变——override 只作用于 storage 模块）。

- [x] **Step 2: 按全局纪律逐条修复**

本片特别注意两条**疑似真 bug**，必须人工判断而非 ignore：
- `core/oversight_service.py:1305 [call-arg]`：`create_redteam_dataset(note=...)` 传了签名不存在的关键字——查该函数定义，确认是调用点写错（删参/改名）还是签名缺参（补参数）。**这是 mypy 引入价值的直接体现，修完在 commit message 里注明。**
- `core/reviewed_output_service.py:85 [assignment]`：变量先绑定 `Stage1Schema` 又赋 `Stage2Schema`——若是分支复用同名变量，改为独立变量名或标注 union 类型 `Stage1Schema | Stage2Schema`。

`stages/validators.py` 的 Literal 收窄用显式校验而非 cast：

```python
_ALLOWED_RISK_LEVELS = ("low", "medium", "high", "critical")

if risk_level not in _ALLOWED_RISK_LEVELS:
    raise ValueError(f"invalid risk_level: {risk_level!r}")
```

（若该处已有等价校验逻辑，用 `typing.cast` 收窄即可，不重复造校验。）

- [x] **Step 3: 验证本片清零 + 回归**

```bash
uv run mypy 2>&1 | grep -cE "^(core|stages)" || echo 0
make test
```

Expected: `0`；全量测试通过（尤其 `tests/` 中 oversight / reviewed_output / validators 相关用例）

- [x] **Step 4: 提交**

```bash
make lint
git status --short
# 逐一显式 add 本片实际修改的文件，例如：
git add core/reviewed_output_service.py core/oversight_service.py core/evidence_service.py core/eval_service.py stages/validators.py stages/stage_4_trigger.py
git commit -m "chore(types): zero mypy lenient-baseline errors in core and stages"
```

---

## Task B4: graph + tools + api 清零（13 + 3 + 2 errors）

**Files:**
- Modify: `uv run mypy | grep -E "^(graph|tools|api)"` 输出中的文件——已知热点：`graph/langgraph_interrupt_runner.py`（7 条）、`core/gates/rules/__init__.py:44 [return-value] list[object] vs list[GateRule]`（归属 core 但与 graph 近 strict 复现，若 B3 未修则本任务修）、`tools/safety_classifier.py:105 [misc] lambda 推断失败`

- [x] **Step 1: 定位本片错误清单**

```bash
uv run mypy 2>&1 | grep -E "^(graph|tools|api)" > .upgrade/tmp/mypy-fix-graph-tools-api.txt
```

Expected: 18 行

- [x] **Step 2: 按全局纪律逐条修复**

graph 包注意事项：
- `graph/langgraph_interrupt_runner.py` 的 langgraph 惰性导入已有裸 `# type: ignore`——在 `ignore_missing_imports = true` 下会转为 `[unused-ignore]` 报错，**直接删除**这些 ignore 注释（而非加 code）。
- `StateGraph.add_node` 的 `[call-overload]` 若源于 langgraph 第三方签名与 `ProjectContext` 状态模型的 overload 不匹配（非本仓代码错误），行尾 `# type: ignore[call-overload]` 并附一行原因注释。
- `tools/safety_classifier.py:105` lambda 推断失败：把 lambda 提升为带注解的具名函数，或给接收变量加显式 `Callable[[...], ...]` 注解。

- [x] **Step 3: 验证全局宽松档 Success + 回归**

```bash
uv run mypy
make test
```

Expected: `Success: no issues found in 153 source files`（B2/B3/B4 全部合入后；若本任务先于其他片完成，先验 `grep -cE "^(graph|tools|api)"` 为 0 即可，全局 Success 由最后合入的片验证）

- [x] **Step 4: 提交**

```bash
make lint
git status --short
# 逐一显式 add 本片实际修改的文件
git add graph/langgraph_interrupt_runner.py tools/safety_classifier.py
git commit -m "chore(types): zero mypy lenient-baseline errors in graph, tools, api"
```

---

## Task B5: core.gates + graph 近 strict（overrides + 25 errors 清零）

**Files:**
- Modify: `pyproject.toml`（追加 overrides）
- Modify: 近 strict 报错的 9 个文件（见 Step 2 清单）

- [x] **Step 1: 在 `[tool.mypy]` 块之后（若 B2 加了 postgres 豁免则在其后）追加**

```toml
[[tool.mypy.overrides]]
# 门禁引擎与状态机：确定性架构主张的核心载体，近 strict
module = ["core.gates.*", "graph.*"]
disallow_untyped_defs = true
disallow_incomplete_defs = true
disallow_untyped_decorators = true
warn_return_any = true
check_untyped_defs = true
```

- [x] **Step 2: 跑 `uv run mypy`，清零近 strict 错误**

干跑基线 25 条（宽松档清零后剩余以实际输出为准，graph 宽松档 13 条已在 B4 修掉，预计剩 ~12–15 条）。两类处理：

**(a) 纯缺注解（干跑 10 条 no-untyped-def），逐个补注解（file:line 为 2026-07-17 快照，执行时以 mypy 输出为准）：**

| 位置 | 函数 | 补法 |
|---|---|---|
| `core/gates/engine.py:37` | `append_gate_evaluation_trace` | 按函数体实际返回补 `-> dict[str, Any]`（无 return 则 `-> None`） |
| `core/gates/engine.py:210` | `_try_persist_gate_evaluation` | `blockers` 参数按调用点传入类型注解（大概率 `list[Any]` 或具体 blocker 列表类型） |
| `graph/interrupt_gate.py:17` | `_load_langgraph_interrupt` | 返回第三方 helper 或 None → `-> Any`（附注释：langgraph 无类型） |
| `graph/langgraph_interrupt_runner.py:52` | `_load_command_type` | `-> Any` |
| `graph/langgraph_interrupt_runner.py:89` | `_build_one_turn_graph` | `-> Any`（编译后 LangGraph 图对象，第三方无 stub） |
| `graph/langgraph_interrupt_runner.py:131` | `get_one_turn_interrupt_graph` | `-> Any`（与既有 `_GRAPH_CACHE: Any \| None` 一致） |
| `graph/interrupts.py:28,39,49,98` | `_node_name_for_action` 等 4 个 | `action` 参数全经 `getattr` 鸭子类型读取 → 注解为 `action: Any`，不引入 Protocol（YAGNI） |

**(b) 真类型问题（干跑 15 条）：** 分布在 `graph/nodes.py`(5) / `graph/interrupts.py`(5，与上表部分重叠) / `core/gates/engine.py`(2) / `core/gates/rules/__init__.py`(2) / `core/gates/rules/stage4_final_governance.py`(1) / `core/gates/rules/expert_review.py`(1) / `core/gates/__init__.py`(1) / `graph/interrupt_gate.py`(1)。重点：
- `core/gates/rules/__init__.py:44 [return-value] list[object] vs list[GateRule]`：给聚合列表加显式注解 `rules: list[GateRule] = [...]`，不 ignore。
- `graph/nodes.py` 与 langgraph 交互处的 `[arg-type]`/`[call-overload]`：本仓代码错则修，第三方签名不匹配则 `# type: ignore[<code>]` + 原因注释。
- `warn_return_any` 触发的 `[no-any-return]`：在返回边界 `cast` 到声明类型，或把返回类型如实改为 `Any`。

原则重申：**只加注解与类型收窄，不改运行时逻辑**；`engine.py` 的 `result.__dict__["report"] = ...` 动态写属性等既有模式保持原样（`__dict__` 赋值 mypy 不查，不需要动）。

- [x] **Step 3: 验证 + 回归**

```bash
uv run mypy
make test
```

Expected: `Success: no issues found in 153 source files`；全量测试通过（重点 `tests/` 中 gates / graph / transition 相关用例，门禁行为不得有任何变化）

- [x] **Step 4: 提交**

```bash
make lint
git status --short
git add pyproject.toml
# Step 2 实际修改的 core/gates/ 与 graph/ 文件逐一显式 add，例如：
git add core/gates/engine.py core/gates/__init__.py core/gates/rules/__init__.py core/gates/rules/stage4_final_governance.py core/gates/rules/expert_review.py graph/interrupt_gate.py graph/interrupts.py graph/langgraph_interrupt_runner.py graph/nodes.py
git commit -m "chore: tighten mypy for core.gates and graph to near-strict"
```

---

## Task B6: CI 接入（非阻断）+ 收尾落账

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.upgrade/reports/mypy-baseline-20260717.md`（终态回填）
- Modify: `.upgrade/STATE.md`
- Modify: `.upgrade/plans/2026-07-17-formal-project-uplift.md`（勾选 Task 7–8 checkbox）

- [x] **Step 1: ci.yml 插入 typecheck 步骤**

在 `lint-and-unit-tests` job 的 `Lint` 步骤之后、`Doc consistency check` 之前插入（step 项 6 空格、步骤体 8 空格缩进，与现有 `Lint` 步骤对齐）：

```yaml
      - name: Type check (non-blocking)
        run: make typecheck
        continue-on-error: true   # 观察一轮后转强制
```

即该段变为：

```yaml
      - name: Lint
        run: make lint

      - name: Type check (non-blocking)
        run: make typecheck
        continue-on-error: true   # 观察一轮后转强制

      - name: Doc consistency check (non-blocking)
        run: make doc-check
        continue-on-error: true   # 初期观察，存量坏链清零后转强制
```

- [x] **Step 2: 基线报告终态回填**

在 `.upgrade/reports/mypy-baseline-20260717.md` 末尾追加：

```markdown
## 终态（Wave B 完成）

- 宽松档 + core.gates/graph 近 strict：`Success: no issues found in 153 source files`
- 修复分片：storage（B2）/ core+stages（B3）/ graph+tools+api（B4）/ 近 strict 补注解（B5）
- CI：`Type check (non-blocking)` 已接入 ci.yml，观察一轮后移除 continue-on-error 转强制
- 遗留欠账：<列出 B2 是否登记了 postgres override 豁免；无则写"无">
```

- [x] **Step 3: 更新 `.upgrade/STATE.md` 与父计划 checkbox**

- `.upgrade/STATE.md`：Last Completed 顶部追加 Wave B 条目（mypy 引入、基线 108→0、近 strict 25→0、CI non-blocking 接入）。
- `.upgrade/plans/2026-07-17-formal-project-uplift.md`：Task 7 全部 6 个 Step 与 Task 8 全部 4 个 Step 的 `- [ ]` 改为 `- [x]`。

- [x] **Step 4: 终验 + 提交**

```bash
make lint && make typecheck && make test && make doc-check
git status --short
git add .github/workflows/ci.yml .upgrade/reports/mypy-baseline-20260717.md .upgrade/STATE.md .upgrade/plans/2026-07-17-formal-project-uplift.md
git commit -m "ci: wire mypy typecheck into CI (non-blocking) and close out Wave B"
```

Expected: lint clean、`Success: no issues found`、615+ passed、doc-check 通过。

> commit 拆分说明：父计划 Task 7/8 原定两个 commit；本方案按实际修复分片拆成 6 个 commit（B1–B6 各一），粒度更细但每个都满足「一任务一 commit、显式 staging」纪律，回滚单元更小。

---

## 主动不做项（Wave B 范围内）

| 项 | 理由 |
|---|---|
| pydantic mypy 插件 | 干跑无插件已通过，pydantic v2 对 mypy 原生友好；上插件属加严，留待 typecheck 转强制后评估 |
| `graph/interrupts.py` 的 `action` 参数引入 Protocol | 现为 getattr 鸭子类型，注解 `Any` 即满足近 strict；Protocol 化是行为无关的重构，YAGNI |
| tests/frontend/scripts 纳入检查 | 父计划明确排除；frontend 为 Streamlit 脚本风格，投入产出比低 |
| typecheck 立即转 CI 阻断 | 父计划要求观察一轮（与 doc-check 同模式）；转正评估归 Wave E Task 16 |
| `__dict__` 动态写属性重构（engine.py:189,203,205） | mypy 不检查 `__dict__` 赋值，近 strict 下无报错；改它属行为风险，不动 |
