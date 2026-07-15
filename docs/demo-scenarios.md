# Demo Scenarios Guide

> **Last updated:** 2026-06-08

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

当前仓库内置了 2 个场景。

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

### `university_mental_health`

用途：
- 演示高校学生心理健康风险预测系统的立项风险评估
- 重点展示敏感数据、心理干预、公平性、高风险人工审核要求

特点：
- 输入样例：`examples/university_ai_mental_health_input.md`
- `domain_profile=university_ai`
- `mock_fixture=university_mental_health`

适合：
- 展示高敏感场景下的风险门禁
- 说明”同一领域 profile 可承载多个不同业务场景”

---

## Manifest 字段说明

每个场景对应一个 `scenarios/manifests/*.json` 文件。

一个典型 manifest 结构如下：

```json
{
  "scenario_id": "generic_rag_demo",
  "name": "Generic RAG Demo",
  "description": "通用企业知识库问答助手示例，使用 default profile 和 default mock fixture。",
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
- `university_mental_health`

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
- `medical_ai`（仅作为可复用 profile 存在，当前 2 个内置场景均未引用，尚无对应内置 manifest）

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

如果新场景属于新领域，应在 `stages/domain_profiles/` 下新增 profile 文件。

例如：

- `finance_ai.py`

该 profile 应至少提供：

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

## 本地启动与验收步骤

这一部分适合毕设答辩演示，也适合开发者自测。

### 1. 使用 `.env.demo`

```bash
cp .env.demo .env
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
```

`.env.demo` 的关键配置是：

- `LLM_MODE=mock`
- `STORAGE_BACKEND=sqlite`
- `DEFAULT_SCENARIO_ID=generic_rag_demo`
- `JWT_SECRET=<demo-only local secret>`

这意味着：

- 不依赖真实 DeepSeek / Tavily
- 不依赖 PostgreSQL / Redis
- 不依赖任何私钥证书
- 新建 session 时默认可挂载一个可演示场景

### 2. 启动前端

```bash
uv run streamlit run frontend/app.py --server.port 8501
```

打开前端后：

- 在左侧“新建会话”区域选择内置场景
- 场景列表来自后端动态接口
- 不需要在 UI 中额外写死某个 demo 名称

### 3. 加载内置场景

选择一个场景后：

- 前端会展示场景描述
- 可展开查看样例输入
- 新建会话时可自动把样例输入送入 INIT

这一步是验收重点：

- 说明“前端只是消费注册表，不知道具体有哪些场景”
- 说明“新增 manifest 后 UI 会自然出现新场景”

### 4. 验证 INIT 到 Stage 4 跑通

在 mock 模式下，建议按如下思路验收：

1. 新建场景会话
2. 观察 INIT 是否正确读取样例输入
3. 进入 Stage 1，检查是否生成对应 profile 的结构化输出
4. 继续推进到 Stage 2 / 3 / 4
5. 在 Stage 3 注意 redteam / safety / evidence 等真实 gate 逻辑仍然生效

当前测试层面已经验证了：

- 场景可枚举
- 场景可加载
- 场景输入可进入工作流
- mock 模式下从 INIT 到 Stage 4 的链路可完成

对应测试：

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

### 缺失 mock fixture 时应回退到通用实现

当前 mock 层的设计是：

- 若指定 fixture 可用，则按场景 fixture 返回结果
- 若只给出 profile 名称，mock adapter 会尝试按该名称加载 fixture
- 对未知 profile / fixture，应回退到 `default` / generic fixture，而不是让核心流程直接依赖某个特定 demo

对于后续开发者，这里的原则很重要：

- **场景是可插拔扩展**
- **核心流程必须保持通用**
- **fallback 应优先保证系统可运行，而不是让新增场景把全局流程绑死**

---

## 验收视角总结

从毕设验收角度，这套机制要证明的是：

1. 场景不是硬编码在前端下拉框里的
2. 场景不是硬编码在后端主流程里的
3. 新增场景主要通过“新增 manifest + 输入样例 + profile/mock fixture 文件”完成
4. 默认无场景模式仍可用
5. mock 模式下可以稳定演示完整阶段链路

如果以上五点成立，那么这个“可插拔 Demo 场景机制”就不仅是一个演示功能，而是一个可复用、可扩展、可维护的系统设计点。
