# 企业 AI 项目部署前风险预评估 Demo

> AI 工作流预验尸与人机监督平台 · 本科毕业设计项目

## 快速启动

### 方式一：一键启动（推荐）

```
1. 解压 demo.zip 到任意目录
2. 双击运行 install-demo.bat（首次运行，安装依赖）
3. 双击运行 start-demo.bat（启动前后端服务）
4. 在浏览器中打开 http://localhost:8501
```

### 方式二：手动启动

```powershell
# 安装依赖
uv sync

# 启动后端（终端1）
uv run uvicorn api.main:app --port 8000

# 启动前端（终端2）
uv run streamlit run frontend/app.py --server.port 8501
```

## 访问信息

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:8501 |
| 后端 API | http://127.0.0.1:8000 |
| API 文档 | http://127.0.0.1:8000/docs |

## 登录信息

- **用户名**: `demo@example.com`
- **密码**: `demo-password-123`

## 核心功能

### 四阶段风险分析工作流

| 阶段 | 内容 | 说明 |
|------|------|------|
| Stage 1 | 失败模式识别 | 使用 LLM 分析项目可能的失败场景 |
| Stage 2 | 人机协同工作流设计 | 设计监督节点，明确人工审核点 |
| Stage 3 | Zero-Shot 压力测试 | 自动生成边界场景测试用例 |
| Stage 4 | 触发策略与部署建议 | 给出部署时机和监控策略 |

### 风险自适应门禁

根据项目风险等级动态调整通过条件：

- **LOW**（个人/学习）：基础安全检查
- **MEDIUM**（团队协作）：Eval 覆盖高风险节点
- **HIGH**（金融/法律/儿童）：红队测试 + 回归评估
- **CRITICAL**（医疗/药物）：全部门禁 + 专家评审

### 内置场景

1. **通用 RAG 演示** (`generic_rag_demo`)
2. **大学生选课系统** (`student_course_selection`)
3. **高校课程问答** (`university_course_qa`)
4. **校园心理健康 AI** (`university_mental_health`)

## 运行模式

### 演示模式（默认）

```
LLM_MODE=mock
```

无需真实 API Key，使用内置 Mock 数据，适合离线演示、论文答辩、功能展示。

### 真实模式

如需使用真实 DeepSeek 和 Tavily，编辑 `.env`：

```
LLM_MODE=real
DEEPSEEK_API_KEY=你的API密钥
TAVILY_API_KEY=你的API密钥
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | FastAPI + Python 3.11 |
| 前端 | Streamlit |
| 状态机 | LangGraph |
| 数据库 | SQLite（演示）/ PostgreSQL（生产） |
| LLM | DeepSeek V4 Pro/Flash |
| 搜索 | Tavily |
| 认证 | JWT + RBAC |

## 文件结构

```
demo/
├── api/              # FastAPI 后端 API
├── auth/             # 认证模块（JWT + RBAC）
├── core/             # 核心业务逻辑
│   ├── gates/        # 阶段门禁规则引擎
│   ├── llm/          # LLM 适配器（Mock/真实）
│   └── ...
├── frontend/         # Streamlit 前端
├── stages/           # 四阶段业务逻辑
├── storage/          # 存储层（SQLite/PostgreSQL）
├── scenarios/        # 场景定义
├── tests/            # 测试用例
├── examples/         # 示例输入
├── docs/             # 文档
├── install-demo.bat  # 依赖安装脚本
├── start-demo.bat    # 一键启动脚本
├── .env.demo         # 演示模式配置
└── pyproject.toml    # 依赖配置
```

## 端口说明

| 端口 | 服务 |
|------|------|
| 8000 | FastAPI 后端 |
| 8501 | Streamlit 前端 |

## 注意事项

1. **首次运行**：必须先执行 `install-demo.bat` 安装依赖
2. **Python 版本**：需要 Python 3.11+
3. **端口占用**：确保 8000 和 8501 端口未被占用
4. **演示模式**：默认使用 Mock 数据，无需联网
5. **安全提醒**：演示模式使用默认密钥，生产环境请修改 `.env` 中的 `JWT_SECRET`

## 许可证

Apache-2.0 License
