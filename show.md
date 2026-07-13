# AI Workflow Pre-mortem & Human Oversight Platform

> 对话式 · 结构化 · 带人机监督的 AI 项目立项风险预评估平台
>
> v1.0 Release · 本科毕业设计项目（计算机科学与技术）

---

## 一、项目简介

随着 AI 系统在教育、医疗、金融等行业的快速落地，**如何在系统部署之前系统性地识别其可能失败的位置**，成为 AI 工程实践中的关键挑战。市面上现有的 AI 应用编排工具（Dify、Flowise、Langflow）聚焦于应用的构建与部署，却普遍缺少对 AI 系统本身进行结构化风险预评估的机制——团队往往在上线后才发现失败模式，此时修复成本极高。

本项目借鉴软件工程中的 **预验尸（Pre-mortem）** 方法论，将其系统性地引入 AI 项目立项阶段，构建了一个**四阶段引导式风险分析平台**。平台结合大语言模型的深度推理能力与人机协同监督机制，帮助团队在投入开发资源之前完成对 AI 系统的结构化风险预评估。

**核心问题：**

> 如何在 AI 系统部署之前，系统性地发现它可能在哪里失败？

---

## 二、核心特性

### 1. 四阶段引导式分析工作流

平台将 AI 风险评估拆解为四个连续的、确定性状态机驱动的阶段：

| 阶段 | 名称 | 内容 | 技术手段 |
|------|------|------|----------|
| Stage 1 | 失败模式识别 | 系统性地列出 AI 系统可能失败的位置 | 实时网络搜索（Tavily）+ LLM 深度推理 |
| Stage 2 | 人机协同工作流设计 | 明确哪些决策需要人工审核，设计监督节点 | 结构化 JSON Schema 引导 LLM 输出 |
| Stage 3 | Zero-Shot 压力测试 | 自动生成边界场景下的 EvalCase，评估模型行为 | EvalCase + EvalRun 评分与回归对比 |
| Stage 4 | 触发策略与部署建议 | 给出部署时机、触发方式和监控策略 | LLM 推理 + 风险等级感知 |

### 2. 风险自适应阶段门禁（Risk-Adaptive Stage Gate）

根据项目风险等级（LOW / MEDIUM / HIGH / CRITICAL），**动态调整每个阶段的通过条件**：

- **LOW**（个人/学习类）：通过基础安全检查即可推进
- **MEDIUM**（团队协作）：需 Eval 覆盖高风险节点
- **HIGH**（金融/法律/儿童）：需红队测试 + 回归评估 + 追踪记录
- **CRITICAL**（医疗/药物/诊断）：需全部门禁 + 专家评审，强制阻断

> 高风险项目的 Stage 3 安全阻断**不是产品缺陷，而是设计意图**——系统拒绝让高风险 AI 项目在未完成充分评估的情况下推进。

### 3. 人机监督闭环

平台内置完整的 **PendingHumanAction** 机制，针对门禁阻断提供四种处理方式：

- **escalate** — 升级到更高权限的处理人
- **edit** — 编辑 LLM 生成的结论
- **evidence** — 补充核验证据
- **parser** — 处理 LLM 解析失败的重试

所有人工动作通过 `OversightService` 进入统一队列，支持审计日志与回溯。

### 4. 多标准风险分类体系

平台内嵌权威风险分类标准，支持**确定性**的失败模式分类：

- **NIST AI RMF**（美国国家标准与技术研究院 AI 风险管理框架）
- **OWASP LLM Top 10 2025**（大语言模型应用最常见安全风险）
- **Microsoft Agent Failure Modes**
- **领域定制分类**（高校教育 AI、医疗 AI 临床、内部分类体系）

### 5. 端到端可观测性

- **证据核验**：EvidenceSource 采集、核验、门禁检查
- **安全发现**：SafetyFinding + 内置 Prompt Injection Scanner
- **Eval 评估体系**：EvalCase 覆盖率门禁 + EvalRun 评分 + 人工评审 + 回归对比
- **Red Team**：对抗测试用例生成、管理与转化为 EvalCase
- **审计追踪**：完整审计事件记录 + Streamlit Audit Workbench 可视化
- **报告导出**：JSON / Markdown ReportArtifact，含 readiness 与 governance 摘要

---

## 三、典型应用场景

平台内置可插拔的 **Scenario Manifest** 机制，针对不同行业的 AI 立项提供定制化的提示词、领域风险分类与示例数据：

- **通用 RAG 知识库**（generic_rag_demo）— 适用于企业内部知识助手类项目
- **高校课程问答 AI**（university_course_qa）— 教育领域，配套 OWASP / Microsoft Agent 分类
- **高校心理健康 AI**（university_mental_health）— 涉及未成年人与高敏感数据，自动升级为高风险流程

---

## 四、技术栈

| 层级 | 选型 |
|------|------|
| **后端框架** | FastAPI（Python 3.11+） |
| **前端框架** | Streamlit Review Workbench |
| **工作流引擎** | LangGraph（确定性状态机） |
| **大语言模型** | DeepSeek V4 Pro / V4 Flash（兼容 OpenAI Chat Completions 接口） |
| **结构化输出** | Pydantic v2 + LangChain |
| **数据库** | PostgreSQL（Alembic 迁移管理） / SQLite（轻量演示） |
| **缓存与限流** | Redis（slowapi 限流计数器） |
| **实时搜索** | Tavily Search API |
| **认证授权** | JWT Bearer + RBAC（viewer / editor / admin）+ 多租户隔离 |
| **容器化部署** | Docker Compose（Full + Lite 双模式） |
| **反向代理** | Nginx（TLS 终止） |
| **可观测性** | Prometheus + Grafana |
| **包管理与测试** | uv + pytest + ruff + mypy |
| **CI / 端到端测试** | Make 驱动（`make e2e-mock` / `make e2e-full-test`） |

---

## 五、系统架构

### 5.1 总体架构图

```
┌──────────────────────────────────────────────────────────────┐
│  前端   Streamlit Review Workbench  (前端组件: gate_panel,    │
│                                       evidence_panel, …)     │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS / HTTP
┌───────────────────────────▼──────────────────────────────────┐
│  API 层   FastAPI  +  Nginx 反向代理  +  限流 (slowapi/Redis) │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  认证授权   JWT + RBAC + 多租户隔离  (auth/)                  │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  核心业务层   Session / Stage / Oversight / Gate / Eval /     │
│              RedTeam / Report / Trace / Audit Services        │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌────────────┬────────────────▼──────────────┬────────────────┐
│  工作流引擎 │  LangGraph 状态机             │                │
│  (graph/)  │  - run_one_step (默认)         │                │
│            │  - langgraph_interrupt (实验)  │                │
└────────────┴────────────────┬──────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│  阶段执行器   Stage 1–4 执行器 + 领域提示词配置 (stages/)      │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────┬───────────────▼───────────────┬────────────────┐
│  门禁引擎  │  Stage Gate / Review Gate     │                │
│  (gates/)  │  插件化规则 (eval_regression, │                │
│            │  redteam_coverage, …)         │                │
└────────────┴───────────────┬───────────────┘
                             │
┌────────────┬───────────────▼───────────────┬────────────────┐
│  LLM 适配  │  DeepSeek V4 Pro / Flash      │  工具与分类    │
│  (llm/)    │  Mock LLM (演示模式)          │  (tools/,      │
│            │  Structured Output + Retry    │   taxonomies/) │
└────────────┴───────────────────────────────┴────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│  存储层   PostgreSQL (Alembic)  /  SQLite (Lite)  /  Redis    │
└──────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│  可观测性   Prometheus metrics  +  Grafana dashboards         │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 单次执行回合运行时路径

```
FastAPI / Streamlit
  └─→ SessionService
        └─→ ExecutionService.execute_one_turn(ctx)
              └─→ single_step (默认)
                    └─→ graph.runner.run_one_step(ctx)
                          └─→ graph.nodes
                                └─→ StageExecutor (Stage 1–4)
                                      └─→ Review Gate
                                            └─→ PendingHumanAction
                                              / SafetyFinding
                                              / EvidenceSource
                                              / EvalCase / EvalRun
              └─→ langgraph_interrupt (实验)
                    └─→ graph.langgraph_interrupt_runner
                          └─→ mark interrupt resumed/cancelled
```

### 5.3 人工动作处理路径

人工监督动作的处理由 `OversightService` 统一协调，**禁止由支持模块直接推进阶段**：

```
FastAPI / Streamlit
  └─→ SessionService
        └─→ OversightService.resolve_action(...)
              └─→ TransitionPolicy.evaluate_action_resolution(...)
                    └─→ ExecutionService.sync_execution_after_action_resolution(...)
                          └─→ stage gate re-evaluation
```

阶段 rerun / revise / rollback / sync-review-actions 作为**显式的阶段操作**集中在 `core/stage_operation_service` 与 `api/routers/stage`。

### 5.4 核心设计原则

- **工作流转移是确定性的、代码控制的**（不依赖 LLM 自主决策）
- **LLM 只生成分析，不推进工作流转移**
- **高风险决策必须人工审核**
- **Evidence / SafetyFinding / EvalCase / EvalRun / InterruptRecord / ReportArtifact 是一等公民持久化对象**
- **Graph、API、前端、报告消费同一份 Stage Readiness Contract**

---

## 六、功能模块详解

### 6.1 阶段执行器（stages/）

平台按 Stage 1–4 拆解为独立的执行器，每个阶段接收上下文、调用 LLM / 工具、产出符合 JSON Schema 的结构化结果：

- **stage_1_failure_mode** — 调用 Tavily 搜索 + DeepSeek 推理，输出 FailureMode 列表与证据
- **stage_2_workflow_design** — 设计 Human-in-the-Loop 工作流节点
- **stage_3_stress_test** — 生成 Zero-Shot 压力测试 EvalCase
- **stage_4_trigger** — 生成触发策略与部署建议

**领域定制**（`stages/domain_profiles/`）提供面向高校教育 AI 与医疗 AI 的提示词模板与风险分类。

### 6.2 门禁引擎（core/gates/）

可插拔的规则驱动门禁系统，所有规则集中在 `core/gates/rules/`：

- `action_state` — 人工动作状态校验
- `eval_regression` — Eval 回归门禁
- `missing_output` — 缺失输出检查
- `parser_error` — 解析失败处理
- `redteam_coverage` — 红队覆盖门禁
- `safety_finding` — 安全发现门禁
- `stage1_evidence_gap` — Stage 1 证据缺失门禁
- `stage2_policy_gap` — Stage 2 政策缺失门禁
- `stage3_eval_failure` — Stage 3 Eval 失败门禁
- `stage4_final_governance` — Stage 4 最终治理门禁
- `stale_dependency` — 陈旧依赖检查
- `trace_backfill_gap` — 追踪回填检查

门禁报告通过 `/sessions/{id}/gate-report?stage=…` 暴露详细诊断。

### 6.3 LLM 适配层（core/llm/）

统一的 LLM Provider 抽象：

- `provider.py` — Provider 抽象接口
- `structured_output.py` — 结构化 JSON 输出解析
- `retry.py` — 指数退避重试
- `adapters/openai_compatible.py` — DeepSeek 适配器（OpenAI Chat Completions 兼容）
- `adapters/mock.py` — Mock 适配器（基于 mock_fixtures 的确定性输出）
- `adapters/mock_fixtures/` — 内置 fixture 集（default / medical_ai / university_ai）

### 6.4 工作流引擎（graph/）

- `runner.py` — `run_one_step()`，生产级稳定执行路径
- `nodes.py` — Stage 节点分发
- `transition_policy.py` — 状态转移策略
- `review_gate.py` — Review Gate 协议
- `interrupt_gate.py` — Interrupt Gate 协议
- `interrupts.py` — Interrupt 记录映射
- `langgraph_interrupt_runner.py` — 实验性 interrupt 适配路径（仅当 `WORKFLOW_EXECUTION_MODE=langgraph_interrupt` 启用）

### 6.5 工具与风险分类（tools/）

- `risk_taxonomy.py` — 风险分类核心
- `safety_classifier.py` — 安全分类器
- `prompt_injection_scanner.py` — 提示词注入扫描
- `evidence_filters.py` / `evidence_ranker.py` — 证据过滤与排序
- `source_classifier.py` — 证据来源分类
- `material_parser.py` — 用户材料解析
- `search.py` — Tavily 搜索封装
- `taxonomies/` — 内置分类体系（NIST AI RMF / OWASP LLM 2025 / Microsoft Agent / 大学教育 AI / 医疗 AI / Internal）

### 6.6 存储层（storage/）

抽象的存储后端接口：

- `backends/postgres.py` — PostgreSQL 后端（生产）
- `backends/sqlite_store.py` — SQLite 后端（轻量演示 / 测试）
- `backends/memory_cache.py` — 内存缓存后端
- `session_store.py` — 会话存储抽象
- `cache.py` — 缓存抽象
- `alembic/` — 数据库 schema 迁移（V001–V003）

### 6.7 评估与红队（core/）

- `eval_service.py` / `eval_runner.py` / `eval_judge.py` — Eval 编排与执行
- `eval_dataset_service.py` — Eval 数据集管理
- `eval_experiment_service.py` / `eval_comparison_service.py` — Eval 实验与对比
- `eval_metrics_service.py` — 指标计算
- `eval_judgment_service.py` — 自动评判
- `eval_regression_policy.py` — 回归策略
- `redteam_service.py` — 红队测试用例生成与转化

### 6.8 人机监督（core/ + api/）

- `oversight_service.py` — 人工动作处理协调
- `report_diff.py` — 报告 diff
- `report_service.py` — 报告生成
- `reviewed_output_service.py` — 已审核输出持久化
- `audit_service.py` — 审计事件
- `api/routers/oversight.py` + `interrupts.py` — HTTP 接口

### 6.9 API 路由（api/routers/）

完整的 REST API 覆盖以下领域：

| 路由模块 | 职责 |
|----------|------|
| `chat.py` | 对话回合推进 |
| `session.py` | 会话 CRUD 与导出 |
| `stage.py` | 阶段 rerun / revise / rollback / sync-review |
| `oversight.py` | 人工动作管理 |
| `interrupts.py` | Interrupt 记录查询 |
| `evidence.py` | 证据采集与核验 |
| `safety.py` | 安全发现与处理 |
| `eval.py` / `eval_datasets.py` / `eval_experiments.py` | Eval 全链路 |
| `redteam.py` | 红队用例管理 |
| `reports.py` | 报告导出 |
| `traces.py` | LLM 调用追踪 |

### 6.10 前端（frontend/）

基于 Streamlit 的 Review Workbench，覆盖：

- `app.py` — 应用入口
- `api_client.py` — 后端 API 封装
- `state.py` — 会话状态管理
- `components/` — 领域组件
  - `gate_panel` / `gate_diagnosis` — 门禁面板
  - `evidence_panel` — 证据面板
  - `safety_panel` — 安全发现面板
  - `eval_panel` / `eval_experiment_panel` — Eval 面板
  - `redteam_panel` — 红队面板
  - `report_panel` — 报告面板
  - `trace_panel` — 追踪面板
  - `action_queue` / `audit_timeline` — 动作队列与审计时间线

---

## 七、部署与运行

平台支持 **两种运行模式**，满足从答辩演示到生产部署的完整需求：

### 7.1 离线演示模式（推荐用于答辩与本地体验）

零外部依赖：无需 API Key、无需 PostgreSQL / Redis、无需 Docker。

```bash
cp .env.example .env
# .env 中设置：
#   LLM_MODE=mock
#   STORAGE_BACKEND=sqlite
#   DEFAULT_SCENARIO_ID=generic_rag_demo

uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
# 另一终端
uv run streamlit run frontend/app.py --server.port 8501
```

打开 `http://localhost:8501` 即可体验完整四阶段流程。

### 7.2 Docker Full 模式（生产部署）

```bash
make setup        # 从 .env.example 与 secrets.example/ 生成 .env 与 secrets/
make prod-up      # 启动 PostgreSQL + Redis + API + Frontend + Nginx
curl -k https://localhost/api/health/live
```

### 7.3 Docker Lite 模式（快速演示）

```bash
make lite-up      # 自动应用 .env.demo，SQLite + Mock LLM
```

---

## 八、测试与质量保障

- **单元测试** — 384 passed / 5 skipped（pytest 8.0+）
- **代码规范** — ruff 0.8+（line-length 100，target Python 3.11）
- **端到端验收** — `make e2e-mock`（5 秒） / `make e2e-full-test`（8 秒）
- **Schema 校验** — 所有跨层数据走 Pydantic v2 强类型校验
- **Stage Readiness Contract** — 由 `tests/` 中的专项测试保证服务层契约一致
- **版本对齐校验** — `scripts/version_check.py` 验证 `pyproject.toml` ↔ `core/version.py` 一致

---

## 九、版本与里程碑

| 版本 | 日期 | 里程碑 |
|------|------|--------|
| v0.1 | 2026-05-01 | 项目初始化，确定四阶段分析流程；Pydantic 数据模型设计 |
| v0.5 | 2026-05-20 | FastAPI + LangGraph 状态机；PostgreSQL + Redis；JWT + RBAC；Mock LLM |
| v0.7.0 | 2026-05 末 | 阶段门禁引擎插件化；LLM 追踪；Stage Readiness Contract 引入 |
| v0.8.0 alpha | 2026-06 初 | Eval 数据集 / 实验 / 回归门禁；红队用例与覆盖门禁；追踪回填门禁 |
| **v1.0** | **2026-06-10** | **完整四阶段工作流 + 风险自适应门禁 + 人机监督 + Eval + RedTeam + 报告 + 审计；Docker Compose 调通；Streamlit Review Workbench 上线** |

---

## 十、目录结构总览

```
.
├── api/                    # FastAPI 应用入口与路由
│   └── routers/            #   chat / session / stage / oversight / evidence / safety …
├── auth/                   # JWT 认证 + RBAC 权限 + 多租户隔离
├── core/                   # 核心业务服务
│   ├── gates/              #   门禁引擎 + 插件化规则
│   ├── llm/                #   LLM 适配层（DeepSeek + Mock）
│   ├── migrations/         #   上下文 JSON 向后兼容迁移
│   └── traces/             #   LLM 调用追踪
├── stages/                 # Stage 1–4 执行器 + 领域提示词配置
├── graph/                  # LangGraph 状态机 + Interrupt 实验路径
├── tools/                  # 搜索、安全工具 + 风险分类体系
│   └── taxonomies/         #   NIST / OWASP / Microsoft / 高校 / 医疗 / Internal
├── storage/                # 存储层（PostgreSQL / SQLite / 内存）
│   └── backends/           #   存储后端实现
├── frontend/               # Streamlit 前端
│   └── components/         #   领域 UI 组件
├── scenarios/              # 可插拔 Demo 场景机制
│   └── manifests/          #   场景定义文件
├── docs/                   # 项目文档（架构、API、安全、Lite 模式等）
├── examples/               # 示例输入与报告
├── scripts/                # 工具脚本（版本校验、TLS 证书、Secret 生成）
├── monitoring/             # Prometheus + Grafana 配置
├── nginx/                  # Nginx 反向代理
├── secrets.example/        # Docker secrets 模板
├── alembic/                # 数据库迁移（V001–V003）
├── tests/                  # 单元测试与契约测试
├── docker-compose.yml      # 生产部署（PostgreSQL + Redis + LLM）
├── docker-compose.lite.yml # 轻量演示（SQLite + Mock）
└── Dockerfile
```

---

## 十一、致谢与许可

本项目为本科毕业设计项目，旨在探索 AI 系统风险预评估的工程化路径。项目借鉴了软件工程中的预验尸（Pre-mortem）方法论，并参考了 NIST AI RMF、OWASP LLM Top 10 2025、Microsoft Agent Failure Modes 等公开标准与最佳实践。

> 如果你正在评估一个 AI 项目的风险，不要等到上线后再去救火——**从立项阶段就开始预验尸**。
