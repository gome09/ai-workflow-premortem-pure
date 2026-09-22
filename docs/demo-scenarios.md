# Demo Scenarios Guide

> **Last updated:** 2026-07-31

本文专门说明当前项目中的“可插拔 Demo 场景机制”，面向两个读者：

- **毕设验收者**：需要快速判断系统是否真正支持“新增场景无需修改核心流程代码”
- **后续开发者**：需要基于现有机制继续扩展新的演示场景或领域场景

---

## 机制概述

当前项目的 Demo 场景不是写死在前端下拉框或后端判断分支中的。

系统采用的是一套**注册式、可插拔**的场景机制：

- 场景注册入口：`scenarios/registry.py`
- 场景定义文件：`scenarios/manifests/*.json`
- 场景输入样例：通常放在 `examples/`
- 领域提示词：`stages/domain_profiles/`
- mock fixture：`core/llm/adapters/mock_fixtures/`

工作方式如下：

1. 后端启动后，通过 `scenarios/registry.py` 扫描 `scenarios/manifests/*.json`
2. 每个 manifest 描述一个可用场景，包括输入样例、领域 profile、mock fixture 和默认配置
3. 前端通过 `/sessions/scenarios` 动态获取场景列表
4. 用户创建 session 时可选择某个场景，场景配置会挂载到当前 `ProjectContext`
5. 后续 INIT、Stage 1–4、mock mode、场景样例加载，都按当前 session 的场景配置执行

这意味着：

- 前端**不需要硬编码**某个 demo 名称
- 后端**不需要在核心流程里手写 if/else 切某个场景**
- 新增场景的主要工作是“加文件并注册”，不是改主流程

---

## 当前内置场景

当前仓库内置了 4 个场景。

### `generic_rag_demo`

用途：
- 通用企业知识库问答 / RAG 助手演示
- 适合展示平台的基础四阶段流程，不依赖行业专用 profile

特点：
- 输入样例：`examples/sample_project_input.md`
- `domain_profile=default`
- `mock_fixture=default`

适合：
- 答辩演示
- 通用能力展示
- 回归验证默认模式

### `university_course_qa`

用途：
- 演示高校课程知识问答系统的立项风险评估
- 重点展示高校场景下的学术诚信、课程内容治理、教学辅助风险

特点：
- 输入样例：`examples/university_ai_course_qa_input.md`
- `domain_profile=university_ai`
- `mock_fixture=university_ai`

适合：
- 展示领域可迁移性
- 演示同一平台在教育场景的 profile 切换能力

### `university_mental_health`

用途：
- 演示高校学生心理健康风险预测系统的立项风险评估
- 重点展示敏感数据、心理干预、公平性、高风险人工审核要求

特点：
- 输入样例：`examples/university_ai_mental_health_input.md`
- `domain_profile=university_ai`
- `mock_fixture=university_ai`

适合：
- 展示高敏感场景下的风险门禁
- 说明“同一领域 profile 可承载多个不同业务场景”

### `student_course_selection`

用途：
- 演示高校学生选课管理系统的 AI 辅助选课推荐场景
- 重点展示 AI 辅助选课系统在立项阶段的失败模式、人机协同审核流程和触发链路

特点：
- 输入样例：`examples/student_course_selection_input.md`
- `domain_profile=default`
- `mock_fixture=default`

适合：
- 展示 default profile 在非通用 RAG 场景下的复用能力
- 演示教育行业中一个更贴近业务流程（而非知识问答）的立项风险评估案例

---

## Manifest 字段说明

每个场景对应一个 `scenarios/manifests/*.json` 文件。

一个典型 manifest 结构如下：

```json
{
  "scenario_id": "generic_rag_demo",
  "name": "通用 RAG 知识库问答",
  "description": "通用企业知识库问答助手示例，使用通用领域配置和通用模拟数据。",
  "input_sample_path": "examples/sample_project_input.md",
  "domain_profile": "default",
  "mock_fixture": "default",
  "default_config": {
    "auto_bootstrap_input": true
  },
  "applicable_stages": ["init", "stage_1", "stage_2", "stage_3", "stage_4"]
}
```

各字段含义如下。

### `scenario_id`

- 场景唯一标识
- 用于 API、前端选择、session 绑定
- 建议保持简短、稳定、可读

例如：
- `generic_rag_demo`
- `university_course_qa`

### `name`

- 面向前端展示的人类可读名称
- 用于场景选择器中的标题显示

### `description`

- 对场景用途的简短说明
- 应突出该场景的业务语境和演示重点，而不是只描述技术参数

### `input_sample_path`

- 场景输入样例文件路径
- 一般指向 `examples/` 下的 `.md` 文件
- 前端可以用它来展示“加载/预览内置样例输入”

### `domain_profile`

- 指定该场景使用哪个领域提示词 profile
- 会影响 INIT 和 Stage 1–4 的提示词分发

当前已存在：
- `default`
- `university_ai`
- `medical_ai`（仅作为可复用 profile 存在，当前 4 个内置场景均未引用，尚无对应内置 manifest）

### `mock_fixture`

- 指定该场景在 `LLM_MODE=mock` 下使用哪个 fixture 模块
- 会影响 Stage 1–4 的 deterministic mock 输出

当前已存在：
- `default`
- `university_ai`
- `medical_ai`

### `default_config`

- 用于放置该场景的默认配置
- 这是一个扩展点，适合保存不应写死在核心流程里的场景偏好

当前实际使用的例子：
- `auto_bootstrap_input`
- `stage_context_note`

### `applicable_stages`

- 表示该场景适用哪些阶段
- 当前内置场景一般覆盖 `init` 到 `stage_4`

说明：
- 在本轮实现里，代码字段名使用的是 `applicable_stages`
- 若文档或后续设计中提到 `stages`，可以理解为同一类语义字段
- 后续如需统一命名，建议在兼容旧 manifest 的前提下演进，而不是直接破坏现有文件

---

## 新增一个场景的步骤

新增场景的目标不是“把新逻辑塞进主流程”，而是复用现有扩展点。

### 1. 新增输入样例

在 `examples/` 下新增一个输入样例文件，例如：

`your_scenario_input.md`

建议这个文件直接写出：

- 系统名称 / 研究对象
- 应用场景 / 具体领域
- 核心目标
- 关键数据类型
- 风险重点或补充说明

这样更适合 INIT 阶段自动识别，也更方便答辩时展示“场景输入是什么”。

### 2. 复用或新增 domain profile

如果新场景属于已有领域，可以直接复用现有 profile：

- `default`
- `university_ai`
- `medical_ai`

如果新场景属于新领域，需要新增 domain profile。

> ⚠️ **domain profile 不是零改动扩展点。** profile 分发在代码中是硬编码分支，只认 `university_ai` 与 `medical_ai`。仅在 `stages/domain_profiles/` 下新增 `finance_ai.py` **不会生效**——四阶段会继续使用 default 提示词。`scenarios/registry.py` 只校验模块可导入，因此 manifest 校验也会通过。
>
> 自 2026-07-31 起，未注册的 profile 名会在 `get_stage_prompts` / `get_json_prompts` 打 WARNING，但行为仍是回落 default。

新增 profile 必须同步修改以下 **4 处分发点**，缺一处就会在该维度上静默回落 default：

| 分发点 | 作用 |
|---|---|
| `stages/prompts.py` — `KNOWN_PROFILES` + `get_stage_prompts` | Stage 1–4 / init / review 的 Markdown prompt |
| `stages/json_prompts.py` — `get_json_prompts` | JSON-first 模式的 Stage 1–4 prompt |
| `tools/risk_taxonomy.py` — `get_risk_descriptions` | 领域风险描述 |
| `graph/nodes.py` — `_extract_init_fields` / `_mock_init_response` | INIT 阶段的字段解析与 mock 响应 |

profile 文件本身应至少提供：

- `INIT_SYSTEM`
- Stage 1–4 prompts
- review prompts
- JSON prompt bundle

### 3. 复用或新增 mock fixture

如果新场景在 mock 模式下可复用已有输出结构，可直接使用现有 fixture：

- `default`
- `university_ai`
- `medical_ai`

如果需要新的 mock 输出，应在：

- `core/llm/adapters/mock_fixtures/`

新增 fixture 文件，例如：

- `finance_ai.py`

并提供：

- `stage_1_response()`
- `stage_2_response()`
- `stage_3_response()`
- `stage_4_response()`

### 4. 新增 manifest

在 `scenarios/manifests/` 下新增一个 `.json` 文件。

例如：

`finance_risk_demo.json`

只要 manifest 合法、路径存在、profile 和 fixture 可导入，前后端就会自动识别。

### 5. 运行测试

至少运行与场景机制直接相关的测试：

```bash
uv run pytest tests/test_scenarios_registry.py tests/test_scenario_session_flow.py -q
```

如修改了 mock fixture，也建议同时运行：

```bash
uv run pytest tests/test_mock_llm_mode.py -q
```

---

## 本地验收

启动命令、环境模板和端口以 [startup.md](startup.md) 为准；推荐使用 `.env.demo` 对应的 Mock + SQLite 模式。工作台选择内置场景后会创建场景会话并把样例输入送入 INIT；“新建空白会话”则保持无场景、无默认消息。

验收时确认场景列表来自后端注册表、样例输入进入 INIT、对应 profile 贯穿 Stage 1–4，且 Stage 3 的 redteam / safety / evidence 门禁仍然生效。相关自动化测试：

```bash
uv run pytest tests/test_scenarios_registry.py tests/test_scenario_session_flow.py tests/test_api.py tests/test_mock_llm_mode.py -q
```

---

## 注意事项

### 默认通用模式仍然保留

系统仍支持不选择任何场景直接运行。

这时会回到：

- `domain_profile=settings.domain_profile`
- 默认通用输入流程
- 默认 mock fixture / 默认真实模式配置

因此系统**不依赖某一个 demo 场景才能工作**。

### 旧 session 仍可回退到通用逻辑

老 session 可能没有 `selected_scenario_id` 或 `scenario_config`。

当前实现对这类旧上下文是兼容的：

- 若 session 中没有场景配置，则回退到默认 profile 解析逻辑
- 不会因为旧 session 缺少新字段而直接失效

### 路径必须安全且存在

manifest 中的 `input_sample_path` 必须指向仓库内真实存在的文件。

当前注册器会在加载时校验：

- 样例文件是否存在
- 对应的 domain profile 是否可导入
- 对应的 mock fixture 是否可导入

这可以避免“前端能看到场景，但一运行就崩”的情况。

### 缺失 mock fixture 的实际行为

当前 mock 层（`core/llm/adapters/mock.py`）的实际行为是：

- 若指定 fixture 可用，则按场景 fixture 返回结果
- 若只给出 profile 名称，mock adapter 会尝试按该名称加载 `core.llm.adapters.mock_fixtures.<name>`
- **对未知 fixture 名不做回退**：`importlib.import_module` 直接抛 `ModuleNotFoundError`，没有 try/except

这不是疏漏而是前移的校验：`scenarios/registry.py` 在加载 manifest 时就强校验 fixture 可导入，所以正常路径不会走到运行时报错。唯一的绕过口是旧 session 中已持久化的 `ctx.scenario_config["mock_fixture"]`（`core/scenario_context.py`），它不经过 registry 校验——删除或重命名 fixture 模块时需要留意存量 session。

与 domain profile 不同，**mock fixture 确实是零改动扩展点**：新增一个 `mock_fixtures/<name>.py` 即可被按名加载，无需修改分发代码。

对于后续开发者，这里的原则很重要：

- **场景是可插拔扩展**
- **核心流程必须保持通用**
- **fallback 应优先保证系统可运行，而不是让新增场景把全局流程绑死**

---

## 验收边界

- 前端和核心流程不硬编码具体场景；复用已有 domain profile 时，新增 manifest、输入样例和可选 fixture 即可扩展。
- 不选择场景时仍可运行通用流程；Mock 模式可稳定覆盖 INIT 至 Stage 4。
- 引入**新领域**仍须修改上文列出的 4 处分发点，domain profile 当前不是零改动扩展点。
