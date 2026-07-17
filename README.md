# AI Workflow Premortem — AI 工作流预验尸与人机监督平台

[![CI](https://github.com/gome09/ai-workflow-premortem-pure/actions/workflows/ci.yml/badge.svg)](https://github.com/gome09/ai-workflow-premortem-pure/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/gome09/ai-workflow-premortem-pure/badge)](https://scorecard.dev/viewer/?uri=github.com/gome09/ai-workflow-premortem-pure)

[English](README.en.md) | 简体中文

> 在 AI 系统上线之前，系统性地回答一个问题：**它会在哪里失败？**

2026 年上半年，AI agent 删除生产数据库、越权转移资金等事故屡见报端——共同根因不是模型能力不足，而是**可预见的失败模式在部署前从未被系统性测试过**。本项目将软件工程的预验尸（Pre-mortem）方法论应用于 AI 项目立项阶段：四阶段引导式分析（失败模式识别 → 人机协同工作流设计 → 压力测试 → 触发策略），配合风险自适应门禁（LOW/MEDIUM/HIGH/CRITICAL）与强制人工审核，让高风险 AI 项目在完成充分评估之前无法推进。

**版本：** v1.3.0 · **协议：** Apache-2.0 · 源于本科毕业设计，现作为长期维护的开源项目演进

---

## 项目背景

随着 AI 系统在教育、医疗、金融等行业的快速落地，在项目立项阶段系统性识别 AI 风险成为工程实践中的关键挑战。现有 AI 应用构建工具（如 Dify、Flowise、Langflow）专注于 AI 应用的编排与部署，但缺乏对 AI 系统本身进行结构化风险预评估的机制——团队往往在系统上线后才发现失败模式，此时修复成本极高。

本项目借鉴软件工程中的**预验尸（Pre-mortem）**方法论，将其应用于 AI 项目立项阶段，构建了一套**对话式、结构化、带人机监督的 AI 风险分析平台**。

### 核心问题

> 如何在 AI 系统部署之前，系统性地发现它可能在哪里失败？

### 解决方案

通过四个阶段的引导式分析，结合大语言模型的推理能力与人机监督机制，帮助团队在立项阶段完成：

| 阶段 | 内容 | 技术手段 |
|------|------|----------|
| Stage 1 | 失败模式识别 | 实时网络搜索（Tavily）+ LLM 深度推理（DeepSeek V4 Pro thinking） |
| Stage 2 | 人机协同工作流设计 | 明确哪些决策需要人工审核，设计监督节点 |
| Stage 3 | Zero-Shot 压力测试生成 | 自动生成 EvalCase，评估模型在边界场景下的行为 |
| Stage 4 | 触发策略与部署建议 | 给出部署时机、触发方式和监控策略 |

### 生态定位

| 相邻项目 | 定位 | 与本项目的关系 |
|---|---|---|
| [deepeval](https://github.com/confident-ai/deepeval) / [inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | LLM 评估框架（运行时/回归） | 互补：本项目的 EvalCase 是"事前生成的假设检验"，可导出到评估框架持续回归 |
| [guardrails-ai](https://github.com/guardrails-ai/guardrails) / [NeMo-Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | 运行时护栏 | 互补：预验尸预测出的失败模式，可落地为运行时护栏的具体校验器 |
| 对话式 AI 顾问团类产品 | 事前风险头脑风暴 | 差异：本项目工作流状态转换是**确定性代码控制**的，LLM 只生成分析内容不决定流程；门禁判定、人工审核、审计记录均为一等公民数据 |

### 核心创新：风险自适应阶段门禁

根据项目风险等级（LOW / MEDIUM / HIGH / CRITICAL），动态调整每个阶段的通过条件：

- **LOW**（个人/学习类）：通过基础安全检查即可推进
- **MEDIUM**（团队协作）：需 Eval 覆盖高风险节点
- **HIGH**（金融/法律/儿童）：需红队测试 + 回归评估 + 追踪记录
- **CRITICAL**（医疗/药物/诊断）：需全部门禁 + 专家评审，强制阻断

高风险项目的 Stage 3 安全阻断**不是产品缺陷，是设计意图**——系统拒绝让高风险 AI 项目在未完成充分评估的情况下推进。

---

## 核心功能

| 功能模块 | 说明 |
|----------|------|
| 四阶段工作流引擎 | Stage 1–4 确定性状态机，每步推进一个阶段 |
| 人机监督闭环 | PendingHumanAction：approve / edit / reject / verify_evidence / escalate 五种处理方式 |
| 风险自适应门禁 | Stage Gate 根据风险等级动态调整通过条件 |
| 证据核验 | EvidenceSource 采集、核验、门禁检查 |
| 安全发现 | SafetyFinding + Prompt Injection Scanner + 多标准风险分类 |
| Eval 评估体系 | EvalCase 覆盖率门禁 + EvalRun 评分 + 人工评审 + 回归对比 |
| Red Team | 对抗测试用例生成、管理与转化 |
| 报告导出 | JSON / Markdown ReportArtifact，含 readiness 与 governance 摘要 |
| 审计追踪 | 完整审计事件记录 + Streamlit Audit Workbench 可视化 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| API | FastAPI（Python 3.11+） |
| 前端 | Streamlit Review Workbench |
| 工作流引擎 | LangGraph |
| LLM | DeepSeek V4 Pro / V4 Flash（兼容 OpenAI Chat Completions 接口） |
| 数据库 | PostgreSQL（Alembic 迁移管理） |
| 缓存 | Redis |
| 容器化 | Docker Compose |
| 认证 | JWT Bearer + RBAC |
| 可观测性 | Prometheus + Grafana |

---

## 快速开始

### 离线演示模式（无需 API Key）

无需 PostgreSQL / Redis / API Key，也不依赖外网：

```bash
cp .env.example .env
# 编辑 .env，设置以下值：
#   LLM_MODE=mock
#   STORAGE_BACKEND=sqlite
#   DEFAULT_SCENARIO_ID=generic_rag_demo

uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
```

可选前端：

```bash
uv run streamlit run frontend/app.py --server.port 8501
```

### Docker 部署（可选）

> Docker 部署为可选模式，答辩现场推荐使用上方的离线演示模式。

#### Docker Lite（SQLite + Mock，无需 PostgreSQL / Redis）

```bash
# 自动将 .env.demo 复制为 .env（如尚未存在）
make lite-up
```

轻量模式使用 `.env.demo` 配置，无需 API Key，适合快速演示。

#### Docker Full（PostgreSQL + Redis + 真实 LLM）

```bash
# 生成 .env（从 .env.example）与 secrets/（从 secrets.example/），并签发 TLS 证书
make setup
# 编辑 secrets/ 中的 API Key
make prod-up
curl -k https://localhost/api/health/live
```

> `secrets/` 目录不进入版本控制，由 `make setup` 从 `secrets.example/` 模板生成，请在其中填入真实 API Key。

---

## 答辩演示模式

> 推荐使用 **离线 Mock + SQLite** 模式进行答辩演示，零外部依赖，确定性输出。

### 启动方式

```bash
# 一键启动后端 API（自动使用 .env.demo 配置）
make demo-api

# 另一终端，启动前端
make demo-ui
```

打开浏览器访问 `http://localhost:8501`，在左侧选择内置场景（如 `generic_rag_demo`），点击「新建会话」即可演示完整四阶段流程。

### 特点

- **无需 API Key**：使用 Mock LLM，返回确定性 fixture JSON
- **无需数据库**：SQLite 本地文件，无需 PostgreSQL / Redis
- **无需 Docker**：直接 `uv run` 启动
- **内置 4 个场景**：通用 RAG、高校课程问答、高校心理健康、学生选课管理
- **完整功能覆盖**：四阶段工作流、人机监督、证据核验、Eval、Red Team、报告导出

### 零依赖单文件 Demo（浏览器直接打开）

仓库根目录提供两份自包含的单文件 HTML Demo，无需启动后端/前端，双击用浏览器打开即可交互演示，数据取自真实项目实跑快照（`LLM_MODE=mock` / `STORAGE_BACKEND=sqlite` / `WORKFLOW_EXECUTION_MODE=single_step`）：

| 文件 | 说明 |
|------|------|
| `ai_workflow_premortem_demo.html` | 离线可交互 Demo，覆盖四阶段工作流全流程（通用 RAG / 高校心理健康等场景快照） |
| `trae_ai_risk_premortem_submission.html` | TRAE AI 创造力大赛提交版单页展示（内置 Mock Engine） |

### 验收测试

```bash
# Mock 场景验收（快速，约 5 秒）
make e2e-mock

# 全量测试（约 8 秒）
make e2e-full-test
```

---

## 测试

```bash
uv run pytest tests/ -q
```

测试使用内存存储和 monkeypatched LLM，无需外部依赖。

---

## 目录结构

```text
.
├── api/                    # FastAPI 路由
│   └── routers/            #   路由模块
├── auth/                   # JWT 认证 + RBAC
├── core/                   # 核心业务服务
│   ├── gates/              #   门禁引擎
│   ├── llm/                #   LLM 适配层
│   │   └── adapters/       #     LLM 适配器（含 mock_fixtures）
│   ├── migrations/         #   ProjectContext schema 迁移（区别于 alembic/ 的数据库表结构迁移）
│   └── traces/             #   LLM 调用追踪
├── stages/                 # 四阶段执行逻辑
│   └── domain_profiles/    #   领域提示词配置
├── graph/                  # LangGraph 状态机
├── tools/                  # 搜索、安全工具 + 风险分类
│   └── taxonomies/         #   风险分类体系
├── storage/                # 存储层（PostgreSQL / SQLite）
│   └── backends/           #   存储后端实现
├── frontend/               # Streamlit 前端
│   └── components/         #   UI 组件
├── scenarios/              # 可插拔 Demo 场景机制
│   └── manifests/          #   场景定义文件
├── docs/                   # 项目文档
├── examples/               # 示例输入文件
├── scripts/                # 工具脚本
├── monitoring/             # Prometheus + Grafana 配置
├── nginx/                  # Nginx 反向代理配置
├── secrets.example/        # Docker secrets 模板（复制为 secrets/ 并填入真实值）
├── data/                   # SQLite 数据文件（运行时自动生成，非仓库自带）
├── alembic/                # 数据库迁移
├── tests/                  # 测试
├── docker-compose.yml      # Docker 生产部署配置
├── docker-compose.lite.yml # Docker 轻量演示配置
└── Dockerfile
```
