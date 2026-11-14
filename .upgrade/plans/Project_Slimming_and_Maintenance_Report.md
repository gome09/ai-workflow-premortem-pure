# 项目瘦身与整理实施报告

审查基线为 `main` 的 `af16495a7251ce41dd93244e4e23d253a8cc741f`，工作区项目为 `ai-workflow-premortem-pure/`。审查日期为 2026-11-13（America/Los_Angeles）。报告中的代码行号均对应此提交。三阶段使用 GPT-6.1 Terra Max、GPT-6.1 Sol Max、GPT-6.1 Terra Max，依次取证、复核、制定方案。源码、配置、依赖锁和 Git 状态均未改动。

## 1. 项目现状概览

这是一个 Python 3.11+ 单仓库应用。uv 管理依赖与锁定，Hatchling 提供项目安装与打包，FastAPI/Uvicorn 提供 HTTP 服务，Streamlit 提供界面，Pydantic 提供模型与设置。LangChain Core 消息和 OpenAI 兼容适配用于模型调用，LangGraph 支撑可选的持久化中断模式。生产使用 PostgreSQL、Redis、nginx、Prometheus、Grafana，离线模式使用 SQLite、内存缓存和 Mock LLM。`pyproject.toml` 无 `project.scripts` 或 uv workspace 声明，跟踪文件无 npm 工作区配置。根 HTML 演示可独立打开，Streamlit 组件 HTML 由 `frontend/components/session_item.py:10` 按固定目录装载。

| 路径 | 职责与引用入口 |
| --- | --- |
| `api/`、`auth/` | `api.main:app` 注册 18 个路由组，负责会话、认证、阶段、治理、评估、报告及发布等协议适配。JWT、工作区成员查询和服务令牌位于 `auth/`。见 `api/main.py:146,355`、`auth/jwt.py:55,84`。 |
| `core/`、`graph/`、`stages/`、`tools/` | 业务服务管理会话、评估、门禁、报告、留存及人机监督。`execute_one_turn` 用配置选择单步或 LangGraph 中断。阶段执行器消费上下文、模型消息和工具。见 `core/execution_service.py:182`、`graph/runner.py:28`、`graph/nodes.py:35`。 |
| `storage/`、`alembic/`、`core/migrations/` | 会话存储工厂动态选择 SQLite/PG，缓存选择内存/Redis。Alembic V001–V014 处理数据库结构，`core/migrations` 处理历史 `ProjectContext` 数据。见 `storage/session_store.py:19`、`storage/cache.py:118`、`core/migrations/__init__.py:10`。 |
| `frontend/`、`.streamlit/` | `frontend/app.py` 装配认证和两个页面。模型、控制器、视图与组件通过 HTTP 访问 API。工作目录可按 Streamlit 规则读取本地主题，独立镜像已有隔离契约。见 `frontend/app.py:4`、`frontend/models/api_client.py:7`、`tests/test_frontend_image_isolation.py:46`。 |
| `scenarios/`、`examples/`、领域和 Mock 模块 | JSON glob 注册四个内置场景，逐项读取 Markdown，并按清单中的字符串加载 profile 和 fixture。见 `scenarios/registry.py:12,25,61,75`。 |
| `tests/`、`.github/`、`Makefile` | 本地 pytest、Ruff、mypy、pip-audit、版本和文档检查。GitHub CI 有离线覆盖率、Lite 集成、PG/Redis 与迁移、Full HTTPS 集成四条路径，另外有 CodeQL、Scorecard 与 Dependabot。见 `Makefile:53,81,89`、`.github/workflows/ci.yml:16,68,107,216`。 |
| `Dockerfile*`、`docker-compose*.yml`、`nginx/`、`monitoring/` | 分开构建 API/Streamlit 镜像。默认 Compose 含开发 override，显式 Full 配置启动七项服务，Lite 面向演示。nginx 路由、TLS 和监控配置由 Compose 挂载。见 `Dockerfile:13,26,36`、`Dockerfile.frontend:20,31,41`、`docker-compose.yml:65,103,124`。 |
| `scripts/`、`secrets.example/`、`docs/`、`.upgrade/`、根 HTML | Make/CI 生成证书和测试密钥，运维脚本处理历史数据。样例密钥文件由 `make setup` 引用，文档和升级资料承担用户说明、决策和历史验收的职责。Docker 忽略规则已排除多数非运行资产。 |

**主业务调用链。** Streamlit 页面 → controller → requests HTTP 客户端 → `api/routers/chat.py:22` → `core/session_service.py:100` → `core/services/session_workflow.py:286` → `core/execution_service.py:182` → 单步或中断运行器 → 阶段执行器 → 存储、缓存和事件。阶段推进经过 `core/stage_readiness_service.py:768` 和 `core/gates/engine.py:114`，门禁规则在 `core/gates/rules/__init__.py` 显式注册。治理摘要、报告导出、上线审批有不同消费路径，删除前需分别保持契约。

**复杂度主要来自三个有实际入口的边界。** 离线和生产采用不同运行依赖，旧库与旧会话走不同迁移机制，单步与中断承担不同恢复语义。可降低的复杂度主要是重复的前端依赖声明及后端镜像装载、已失效的私有辅助逻辑、版本/文档事实分叉、重复 CI 扫描和未被生产运行使用的复制范围。保留安全与数据边界的回归测试。

**依赖基线。** 25 个主依赖、6 个 dev extra、5 个前端组依赖，锁文件 157 个条目（含项目根包）。当前项目与报告 schema 版本是 `1.11.0`，锁根元数据是 `1.9.0`。三个组的直接依赖名、extras 及锁定版本对现有约束的满足情况一致。`git diff 153e3a2..af16495 -- pyproject.toml uv.lock` 在两文件内只显示项目版本改动。当前能确定版本元数据错位，尚未确认它导致安装或镜像运行失败。[uv 锁文件检查](https://docs.astral.sh/uv/concepts/projects/sync/) · [uv 的 Docker 安装说明](https://docs.astral.sh/uv/guides/integration/docker/)

## 2. Terra 原始审查结果

| 分类 | 第一阶段候选及主要依据 |
| --- | --- |
| 已确认可安全整理 | **C01** Ruff 仍豁免不存在的 `frontend/api_client.py`。**C02** README、文档索引和验收快照把历史版本或测试结果写作当前。**C03** 脚本文档与完整栈 CI 的证书和密钥初始化步骤不一致。 |
| 高概率可整理，需验证 | **V01** 锁根包 `1.9.0` 与应用 `1.11.0` 不一致。**V02** 五个旧门禁收集器只见定义。**V03** Stage 3 摘要和规则重复计算，但两路仍在用。**V04** `core/llm/retry.py` 无仓内引用。**V05** 两个前端包装函数只见定义。**V06** 项目声明 Passlib，认证代码直接用 bcrypt。**V07** 未发现 `langchain`、`langchain_community` 直接导入。**V08** `langchain_core`、`prometheus_client`、`requests` 存在传递安装依赖。**V09** API 镜像安装前端包且复制前端源码。**V10** Lite API 的三个 bind mount 缺少清晰的当前用途。**V11** 普通 wheel 与场景资源的边界未验证。**V12** 四个公开符号的仓外消费者未知。 |
| 有维护成本，暂保留 | **H01** 会话、存储和中断兼容门面仍有注入或兼容用途。**H02** 手工及一次性脚本仍属于运维和旧库迁移路径。**H03** `.upgrade/` 是治理和留档。**H04** 两个根 HTML 提供不同离线或留档体验，已排除出运行镜像。**H05** 双后端和双执行模式在各自场景正常接线。 |
| 不应删除或调整 | **P01** 两条迁移链。**P02** 动态场景、示例、profile 和 Mock 资源。**P03** 门禁规则、覆盖策略和防回归测试。**P04** 认证、租户、加密和发布门禁。**P05** 网关及监控部署资产。**P06** 已接入 pytest/CI 的回归测试与夹具。 |

附录 A 保留 Terra 每项的位置、引用、风险、收益、验证方法及环境实测记录。

## 3. Sol 独立交叉核验

| 核验结论 | 逐项处置 |
| --- | --- |
| 确认成立 | C01、C03；V01 根元数据漂移；V02 五个函数无仓内调用；V05 两个前端包装只见定义；V06 Passlib、V07 LangChain 及 Community 的静态删除候选；V09 API 镜像存在前端依赖和源码。H01–H05、P01–P06 确认保留。确认仓内证据的 V 项仍须按各自发布、外部使用及运行条件验收。 |
| 部分成立，需修正 | C02 还包括同日历史数据冲突和迁移头过时。V03 两条路径有意或实际承担不同配置与记录行为。V04 活跃 provider 的重试链走 `core/context_manager.py`。V08 requests 还有手动 CLI 用途，PyYAML 是测试直接依赖。V10 挂载维护用途、收益各异。V11 根场景文件之外还要考虑 Alembic/配置。 |
| 否决的动作 | V03 以引擎结果直接替代摘要。V09 以合并前后端镜像削弱隔离。V10 把三个 bind mount 视作一组直接删除。V11 将普通 wheel 发布和目录迁移纳入当前瘦身批次。没有否决 Terra 一整项候选的情况。 |
| 证据不足 | V12 的四个公开符号继续保留；V02、V04–V07、V09–V11 涉及的外部消费者或运行验证仍需逐项完成；H01–H04 的外部兼容、运维和留档范围未获证实。 |
| 新发现 | **N01** 现行启动文档引用 V013、验收页历史数字冲突。**N02** 默认开发 Compose 将整个仓库挂进 UI，独立镜像边界测试没覆盖该合并配置。**N03** Scorecard 对同一仓库扫描两次。**N04** 覆盖报告用同一谓词构造两份相同列表。**N05** readiness 可能重复评估并记多条门禁记录，真实次数待测。 |

| 分歧 | Terra 的依据 | Sol 核验与最终取舍 |
| --- | --- | --- |
| C02 / N01 | 应用 `1.11.0`，入口与旧验收把 `1.8.0` 写成当前。 | `docs/acceptance_report.md:12,66` 对同一日期给出 1256/1253，`AGENTS.md:15` 支持 1256 作为历史记录。`docs/startup.md:76` 所称迁移头落后一版。保留历史版本、时间、范围，去重复冲突数字并修正当前启动说明。 |
| V01 | 版本文件与锁根不一致，CI 使用冻结同步。 | 双方复核三组依赖元数据。Sol 在临时独立项目验证了 `--frozen`、`--check` 的差异，并发现普通 `uv run` 可以先刷新锁。将提交版本的轻量检查置于会重锁的命令之前，重锁独立验收。 |
| V02 / V03 | 五个收集器无调用，第六个仍被摘要读取。 | 经 AST 和局部动态对照确认边界。禁用 Stage 3 规则后摘要仍保留来源 ID，`report_export_allowed` 仍为 false。直接替换会改变行为，并混入引擎记录副作用。仅把五个旧函数列为删除候选，保留第六个契约。 |
| V04 | 旧模块无引用，结构化请求转发 `max_retries`。 | `core/llm/adapters/openai_compatible.py:9` 是未实现的结构化适配入口，实际 `ChatOpenAI` 重试配置经 `core/context_manager.py:50,69`。删除候选只限独立旧模块，保留运行重试和相关测试。 |
| V06–V08 | 三个未使用依赖及三个直接导入边界。 | 在锁图中，Community 的移除收益大于独立 LangChain。用各自提交验证，并显式声明已直接使用的模块，含前端、CLI 和测试。历史认证和域扩展仍需验收。 |
| V09–V11 | API 装载 UI、Lite 挂载疑似冗余、普通 wheel 资源边界待证。 | API 镜像前端复制的跟踪源码上界 234,410 字节。Lite scripts 依靠 bind mount 而非 `COPY` 入容器，单独核查手工使用。普通 wheel 还可能缺根 Alembic 配置与迁移脚本。先保住现有本地与生产入口，再选择最窄改动。 |
| V12 | 名字检索只见定义，可能有仓外引用。 | `RUNTIME_VALIDATION` 在历史维护文档中有记录，`required_node_ids_for_tier` 明言兼容别名。收益低，消费者未知，保留。 |

附录 B 提供逐项独立核验和五个新发现的完整证据。

## 4. 最终项目瘦身清单

每一行以当前基线为起点。P0 优先处理确定的问题，V01 的修复仍以成功重锁和受控验收为前提。P1–P3 的具体实施和回滚步骤见附录 C。

| 优先级 / 项目 | 当前用途、问题与证据 | 推荐动作、影响、风险与收益 | 验证 |
| --- | --- | --- | --- |
| P0 · C01 `pyproject.toml:114` | Ruff 例外仍指向已删除的客户端路径。当前文件在 `frontend/models/`。 | **删除**旧条目及注释。只影响 lint 配置，风险极低，减少误导。 | `make lint`。 |
| P0 · C02、N01 `README.md:14,145`、`docs/acceptance_report.md:12,66`、`docs/startup.md:76` | 当前代码是 1.11.0，历史文档把旧版本写成当前，同日记录出现 1256 与 1253，启动文档将 V013 写作 head。 | **简化**事实来源，标明历史，去掉冲突的重复数字，启动说明更新至实际 V014。只改文字，风险低。 | `make doc-check`、版本检查、核对日期及 Alembic 链。 |
| P0 · C03 `scripts/README.md:37` | 将证书和密钥初始化描述为仅本地，Full CI 实际调用两个 Bash 脚本。 | **简化**说明并保留脚本，分别写清 CI、本地和 Windows 入口。风险极低。 | 对照 `.github/workflows/ci.yml:227` 并做文档检查。 |
| P0 · V01 `uv.lock:20`、`scripts/version_check.py:28` | 根包版本滞后，现行版本检查漏读锁。 | **简化**版本验证。将静态锁根检查放在 CI 同步前，工具重锁单独提交。仅元数据问题已确认，锁求解仍 **[需核验]**。 | `uv lock --check`、冻结安装、对照第三方锁条目与哈希，普通 `uv run` 之前执行版本检查。 |
| P1 · V02 `core/stage_readiness_service.py:174,192,465,554,588` | 5 个旧私有收集器只见定义，现有门禁由注册规则执行。 | **[需核验]** 后 **删除**五个定义，保留共享 helper 与第六个 Stage 3 收集器。风险主要为仓外调用，预期少维护 229 行。 | 核对外部与动态调用，比较前后门禁结果、异常、审计和记录，跑门禁及阶段回归。 |
| P1 · V06、V07、V08 `pyproject.toml:20,40,63` | Passlib、LangChain、Community 无直接调用。Core、Prometheus client、requests 等有直接消费者。 | **[需核验]** 后分别 **删除**三项多余声明，按运行和测试角色 **简化**依赖声明。社区包的静态闭包收益较大，风险为扩展或历史环境的隐式依赖。 | 每项冻结安装、比较锁图、认证与历史 bcrypt 样本、Mock 工作流及 provider 本地替身。 |
| P1 · V09 `Dockerfile:15,26`、`Dockerfile.frontend:21,31` | API 安装 UI 包并复制 `frontend/`，已有独立 UI 镜像。 | **[需核验]** 后从 API 安装路径 **移动**三项 UI 根依赖并独立 **简化** COPY 清单。保留本地开发、AppTest、CLI 入口和生产资产。 | 同平台测双镜像依赖与层大小，验证本地、Lite、Full 和生产迁移路径。 |
| P2 · V04、V05 `core/llm/retry.py:6`、`frontend/labels.py:313`、`frontend/models/api_client.py:295` | 旧重试模块及两个 UI 函数没有仓内调用。活跃重试由 `core/context_manager.py:69` 配置。 | **[需核验]** 后分别 **删除**。收益小，审查仓外 Python 和 Streamlit 扩展的成本应与收益相称。 | 重试/解析测试、API 错误及 UI 认证恢复，核对所有委托和缓存行为。 |
| P2 · V10、N02 `docker-compose.lite.yml:16`、`docker-compose.override.yml:13` | Lite 的 API 额外挂载 UI、config、scripts。默认开发 UI 挂整树，可能带入宿主配置。 | **[需核验]** 后分别 **简化**挂载。优先核验 Lite API 的 frontend；scripts 和 config 已有或可能有手工用户。缩小开发挂载面，避免移除 CLI、主题、热重载。 | 对照默认、Lite、Full 的有效 Compose 配置和实际挂载，在隔离数据下验证。 |
| P2 · N05 `core/stage_readiness_service.py:862,923,994` | readiness 可重评门禁，持久化记录参与趋势统计。 | **[需核验]**，先测记录数量与趋势定义。写入优化可能改变审计与严格失败语义，先保留。 | 隔离 SQLite/PG 记录写入次数、时序、失败和趋势差异。 |
| P3 · V03、N04 `core/stage_readiness_service.py:632,994`、`core/coverage/policy.py:193` | Stage 3 摘要与门禁均计算缺口，摘要状态仍参与导出契约。覆盖报告中两个字段共用谓词。 | **保留**双入口及两个输出字段。后续若有实际维护收益，再 **合并**纯计算。直接换用门禁引擎会改变禁用规则时的报表状态。 | 核对 ID、顺序、配置禁用、错误处理、持久化和报告契约。 |
| P3 · V11、V12 | `pyproject.toml:81` 的 wheel 包选择与生产运行资源不同，若干公开符号和兼容别名无已知当前仓内读取。 | **保留**现有支持与兼容边界。[需核验] 普通 wheel 需求及仓外消费者。没有实际需要时避免结构迁移。 | 仅在支持独立分发时验证普通 wheel、场景与 PG 迁移，公共符号核对旧消费者。 |
| P3 · N03 `.github/workflows/scorecard.yml:22` | 一次 JSON 扫描、一次可读扫描，上传产物只用 JSON。 | **[需核验]** 后可 **合并**为一次扫描加可读摘要。保留产物、失败语义、权限与留存期，收益限 CI。 | 对照可读内容、JSON 内容、job 退出和实测耗时。 |

## 5. 文件删除清单

| 状态 | 文件或内容 | 判定与约束 |
| --- | --- | --- |
| 可安全删除 | **暂无整文件。** 可删 `pyproject.toml:114–115` 的失效 Ruff 例外，以及验收报告重复且冲突的页脚数字。 | 是配置或文字条目清理。历史报告正文和原始成绩保留。 |
| 删除前需验证 | `core/llm/retry.py`；`core/stage_readiness_service.py` 内 5 个函数；`frontend/labels.py` 和 `frontend/models/api_client.py` 各 1 个函数。 | 整文件候选只有 retry 模块，保留实际 provider 重试。其余只删精确符号。需排除仓外、反射和测试替身使用，并跑受影响的回归。 |
| 删除前需验证 | 从 API 镜像复制清单排除的 `frontend/`；Lite API 的 `frontend`、`config`、`scripts` 挂载。 | 优化构建或开发入口，仓库文件不在删除范围。`scripts` 勿与其他挂载同时撤掉。 |
| 明确保留 | `alembic/`、`core/migrations/`、动态场景及示例、全部有效回归与 fixture、14 条规则和 Stage 3 摘要、兼容门面、认证/权限/加密、手工回填脚本、独立前端镜像及配置、`secrets.example/`、监控与 nginx、两个根 HTML、`.upgrade/`。 | 运行、运维、历史或测试用途已查实，对外兼容和留档仍有未确认事项。前端组件 HTML 依约定加载，本地 `.streamlit/config.toml` 由框架自动发现。 |

## 6. 依赖整理清单

| 处置 | 包或分组 | 原因、影响与验证 |
| --- | --- | --- |
| 可删除候选，需验证 | `passlib[bcrypt]` 1.7.4、`langchain` 1.2.18、`langchain-community` 0.4.1。 | bcrypt 直接实现验密，核心模型使用 LangChain Core 和 OpenAI provider。先独立删除 Passlib，随后优先验证 Community，LangChain 最后单独处理。逐项确认历史密码、扩展、安装及锁图。 |
| 可替换 | 暂无替换建议。 | JWT 等既有库有实用调用。替换须先确认公告或兼容性问题适用于实际用法，再评估令牌和旧数据兼容。本轮未执行完整依赖漏洞审计。 |
| 建议升级 | 暂无升级项目。 | V01 是项目锁元数据对齐，目标保持已锁第三方版本。`langgraph-checkpoint-postgres==3.0.5` 和 V006 schema 及测试绑定，任何升级需单案核对 upstream migrations、持久化回归和回滚。 |
| 分组或补全声明 | 继续用前端组的 Streamlit、Altair、Pandas、requests、dotenv。按实际入口补齐 `langchain-core`、`prometheus-client`、用于 CLI 的 requests、测试直接用的 PyYAML。 | 审查后端镜像、前端镜像、完整开发与手工 CLI 四个消费路径。测试的 PyYAML 属开发依赖。requests 还给 `scripts/live_e2e_four_stage.py:46` 使用，须保持用户执行路径可用。 |
| 建议保留 | LangGraph、LangChain Core/OpenAI、Tavily、FastAPI/Uvicorn、Pydantic、PG/Redis、bcrypt、JWT/cryptography、multipart、slowapi、Alembic、Prometheus、自有 HTTP 依赖与现用开发工具。 | 调用链、搜索、认证表单、生产存储和可观测性有实际引用。附录 A/B 给出依赖证据，附录 C 给出逐项验证。 |

依赖组和冻结同步行为以 [uv 官方同步说明](https://docs.astral.sh/uv/concepts/projects/sync/) 为依据，包约束以本仓库 `pyproject.toml` 与 `uv.lock` 为准。[LangChain Core 1.3.3](https://pypi.org/project/langchain-core/1.3.3/) · [Checkpoint PostgreSQL 3.0.5](https://pypi.org/project/langgraph-checkpoint-postgres/3.0.5/)

## 7. 代码与结构整理方案

- **先删证据充分的旧配置，再对照门禁删精确函数。** 五个旧收集器可在查清仓外用途后独立删除。Stage 3 现在的摘要逻辑继续与可配置的门禁、写入记录路径分开。保留所有当前有效规则、共用 helper 和回归测试。
- **维持可理解的模块边界。** 保留前端 MVC、后端协议/应用/存储职责和双迁移机制。暂不移目录、不引入共享框架。不合并有不同租户、事务、恢复或发布契约的实现。
- **沿现有镜像边界优化。** 先测后端真实依赖，逐组清理并让镜像 COPY 仅包含所需源码与资源。单独审查 Lite 和默认 override。前端镜像、主题、数据挂载、迁移、nginx、监控和运行预检均依各自入口验收。保留当前前端镜像隔离规则。[Docker build context](https://docs.docker.com/build/concepts/context/) · [Compose 合并](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/) · [Streamlit 配置位置](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)
- **收敛现行文档与脚本说明。** `README.md` 指向运行、测试和部署说明的权威位置。历史快照使用日期、版本、运行环境和当时测试结果。README 只需简述入口，运维脚本直接连接到真实场景，不另建万能配置或打包入口。
- **CI 先查锁，再安装。** 继续保留 Lite、PG/Redis 和 Full 的区别。只有当前两次 Scorecard 扫描的输出可从同一结果等价生成时，才收敛扫描。不用缓存或删记录换取未测明的收益。[Scorecard 输出说明](https://github.com/ossf/scorecard#formatting-results)

## 8. 成本改善预期

| 指标 | 基线或条件估算 | 验证口径 |
| --- | --- | --- |
| 工作树规模 | 607 个跟踪文件、5,562,697 字节、445 个 Python 文件、80,932 个 Python 物理行（含测试与注释）、169 个 `tests/test_*.py`。 | 同一提交基线上按 Git 跟踪路径和实际字节统计。物理行数仅用于估算审查范围。 |
| V02 源码 | 五个旧函数合计 229 个物理行。单独落地时，预期删除 5 个定义，文件数不变。 | 用独立提交的 AST/文本 diff 复核，只移除明确的定义和随之确认失效的 import。 |
| 主依赖及 API 锁图 | Linux/Python 3.11 锁图 121 个包，3.12 为 120 个。固定当前版本模拟单删 Passlib 少 1，单删 LangChain 少 1，单删 Community 少 15，拆出 Streamlit/Altair/Pandas 三个 UI 根少 22。六个根一起移出 API 闭包时分别估算为 80/79，少 41 个。 | Sol 现有锁图按 Linux/Python 标记与 extras 静态计算，不含本项目根包。重锁、平台、共享依赖与组选择会改变实际结果，不能据此推算镜像大小或安装速度。 |
| 镜像源码 | API 镜像可能排除的 `frontend/` 跟踪源码合计 234,410 字节。`.upgrade` 的 645,537 字节及根 HTML 的 238,579 字节已排除出镜像上下文。 | 前端值为跟踪源码上界，实际层大小受忽略规则、压缩、构建缓存影响。发布口径使用同基镜和平台的实际镜像、层及依赖列表。 |
| CI 与读取成本 | Scorecard 当前为两次命令调用，若可从 JSON 生成同等可用摘要，可减少一次扫描调用。readiness 重评触发的记录次数仍待实测。 | 对比相同 commit/runner 的冷、暖运行至少各三次，报告中位数与单项耗时。门禁先量 SQL 写入数、记录数和趋势差异，保留异常与审计语义。 |
| 安装体积、镜像大小、构建/启动/测试时间 | 本轮无可用的完整运行基线，不填改善数字。仓库没有独立的 npm 前端构建或可比的 JS Bundle 产物。 | 未来使用同 uv/Python/Docker、同平台与缓存策略记录安装耗时、依赖目录大小、镜像大小、健康响应时间及 CI job 总时长，结合功能验收判断收益。 |

## 9. 实施顺序与回滚点

| 批次 | 工作与依赖 | 阶段通过条件与回滚 |
| --- | --- | --- |
| A · 配置和文档 | C01、C02、C03、N01；无需等待依赖拆分。 | `make lint`、文档与版本检查通过，独立回退小范围文字和配置。 |
| B · 锁定基线 | V01；取得完整包源或缓存后重锁，添加安装前验证，与 A 可并行。 | 根元数据正确，无未解释的第三方 diff，冻结安装与基线可复现。锁文件和版本检查单独成组回退。 |
| C · 门禁死代码 | V02；依赖 B 提供的可跑基线和仓外确认，与 D 低耦合。 | 门禁结果、日志/记录、报告契约保持。恢复五个函数，确保不会影响真实规则和写入。 |
| D · 依赖和容器 | 先确认 V08 的各消费边界，再独立验证 V06 与 V07，最后分别测 V09 的依赖和源码复制改动。 | 目标包仅从对应环境消失，现有安装和上线流程都合法。单项回退声明与锁，或恢复上一个镜像与 Compose 配对。 |
| E · 挂载与小候选 | V04、V05、V10、N02；依赖各自外部消费者和容器使用信息。N05 可先单独测量。 | 删除前核实具体调用，挂载逐项回退。任何门禁观测变更先定义趋势口径并提供 SQLite/PG 对照。 |
| F · 后置 | V03、V11、V12、N03、N04。产品需求或测量结果明确后才立项。 | 保持各项公开语义。改动有行为差异或实际收益不足时，保留现状。 |

以上均为后续实施方案。每批保留独立的代码、锁和构建证据，任何回滚尽量聚焦当前提交。与 schema 无关的优化采用代码/镜像回退，数据库演练限隔离实例。

## 10. 测试与验收标准

| 验收面 | 执行要求与通过标准 |
| --- | --- |
| 安装和锁 | 在干净工作区、获准的完整缓存/源使用项目支持的 Python，至少跑 CI/镜像使用的 3.11。先用原生 Python 运行扩展后的版本检查，然后 `uv lock --check`、`uv sync --all-extras --frozen`。锁根与当前项目一致，完整依赖组均可安装，非目标第三方版本、来源、标记、extras 和哈希保持原有结果，例外须单列。 |
| 静态和文档 | `make lint`、`make typecheck`、`make doc-check`、`make version-check` 和 diff 检查。复查全部删除路径和符号的静态引用、动态加载、CLI Help、生产挂载、历史链接。README/启动/运维说明与真实运行入口一致。 |
| 本地离线 | 干净隔离副本注入 `sqlite`、`memory`、`mock`、`single_step`，显式使用测试数据路径，跑既有回归与覆盖率。记录真实通过、失败、跳过，缺基础依赖导致的跳过不能充当通过。分别通过本地 API `/health/live`、`/health/ready`、本地 Streamlit 页面、四个内置场景、四阶段推进、暂停/恢复/回滚和报告生成/导出检查。 |
| 业务契约 | 正常流程中核对会话切换与租户隔离、授权与登录/刷新、证据核验、风险处置、报告唯一性与发布批准。保留 `ApiError`、空结果和读取失败、聊天投递 `failed`/`unknown` 区分。Stage 3 的 `rule_id`、`source_id`、导出状态、评估记录以及严格失败处理做变更前后对照。 |
| 生产构建与部署 | 对 API/前端分别从冷缓存执行依赖构建，审查安装包清单和文件清单。分别跑默认开发 Compose、显式 Lite 和显式 Full 的 `config` 与启动。验证 nginx HTTPS、Streamlit、PG/Redis readiness、Prometheus/Grafana，前端无后端密钥、预期资产可见，删除依赖不会进入目标镜像。Full CI 的 Mock 是集成验收，真正生产 `APP_ENV=production` 的配置和 readiness 仍单独验收。 |
| 迁移与恢复 | 在可销毁隔离 PG 备份或数据副本上验证新库到 head、V008 到 V014、回退后再升级、备份恢复、旧记录可读。保留加密字段、持久化 checkpoint、中断恢复、租约、幂等和并发契约。三份上下文夹具升级至 `0.10.0` 并保留既有历史样本。 |
| CI/CD 和回滚 | 有权限的维护环境验证 lint+unit、Lite、production-safety、Full integration、CodeQL 等现行检查。观察型检查保留其阻断级别。记录 job、提交和镜像标识。发布前保留上一份已验收镜像及锁文件，代码和依赖变更按小提交回滚；配置分离回滚时使用原镜像/Compose 对，不回退数据库 schema 来处理与 schema 无关的瘦身回归。 |

只有确认确需独立 wheel 发布时，才附加 `uv build --wheel`、解包和非 editable 安装验收。检查配置、静态资源、场景输入、Alembic 与存储启动，仓库 editable 和 Docker 各自按实际入口验收。

## 11. 集中的 [需核验] 清单

| 编号 | 尚需取得的证据 | 证据不足时的处置 |
| --- | --- | --- |
| V01 | 完整锁定包源或缓存、Python 3.11、实际工具重锁、三组同步和基线回归。 | 优先记录问题和前置检查，避免兼带依赖升级。 |
| V02、V04、V05、V12 | 仓外插件、调用脚本、旧 wheel/分发消费者、动态属性或测试补丁。 | 五个旧收集器及两个 UI 函数继续列候选。独立 retry 模块和公开兼容符号暂保留，等使用范围明确。 |
| V03、N04、N05 | 完整门禁/摘要/报告测试、配置禁用、真实记录写入和趋势口径，可能的字段别名消费者。 | 保持两个入口和两个公开 payload 字段。记录次数的调整另案。 |
| V06、V07、V08 | 重新锁定、传递依赖消失、历史密码样本、真实已用 provider 配置、命令行脚本及第三方/外部领域扩展。 | 将候选分别验证。缺少明确证据的包保持声明；不推荐无目的升级。 |
| V09、V10、N02 | 真实镜像体积及安装闭包、默认 Compose 生效配置、开发热重载、维护者挂载习惯、scripts 和 config 是否有仓外用法。 | 分别保留待证的挂载。镜像依赖与 COPY 改动独立发版，保留可回滚镜像。 |
| V11 | 普通 wheel 是否为部署契约，真实 wheel 内资源、独立安装与迁移。 | 维持 editable/Docker 支持边界，暂停包结构搬移。 |
| H01–H04、N03 | 兼容 API 消费者、历史脚本/升级保留决策、外链或离线演示、Scorecard 可读输出的使用方。 | 保留对应文件、入口及审计产物。 |
| 环境与远端状态 | 当前提交真实 Docker/PG/Redis、全量 pytest、完整构建、远端 CI/CD 与分支保护；供应链公告对当前版本、配置和实际用法的适用性。 | 标为未验证，历史通过结果不计入本次验收。 |

## 附录　执行证据和复现范围

| 检查 | 本轮观察 | 结论范围 |
| --- | --- | --- |
| 仓库盘点与语法 | 607 个 Git 跟踪文件，5,562,697 字节，445 个 Python 文件，169 个 `tests/test_*.py`。主审解析 445 个 Python、12 个 YAML、2 个 TOML 与锁文件。Terra 在隔离副本完成 `compileall`。 | 统计基于提交和工作树，语法检查不启动应用。 |
| 版本与文档 | `python -B scripts/version_check.py` 输出 `1.11.0`，`python -B scripts/doc_consistency_check.py` 扫描 37 份 Markdown，0 处规则违规。 | 版本脚本未读 `uv.lock`，文档脚本主要检查链接、Make 目标和文件路径。 |
| uv 锁图 | `uv tree --frozen --offline --depth 2` 可读，根包显示 `1.9.0`。各组直接依赖约束及 extras 静态一致。 | `--frozen` 不检查锁新鲜度。Python 3.12.14、uv 0.13.6；仓库的 CI/镜像主要用 Python 3.11。 |
| 冻结安装、锁检查、wheel | `uv sync --all-extras --frozen --offline` 缓存不足。不同副本先缺 `pandas`、`python-dateutil` 或 `narwhals`；`uv lock --check --offline` 缺 checkpoint-postgres 缓存；`uv build --wheel --offline` 缺 Hatchling。 | 尚无完整安装或构建证据；未发现符合环境网络策略的包索引。 |
| 局部防御性动态检查 | Sol 在隔离副本中直接调用 24 个无需 fixture 的现有测试函数，均完成断言。四个内置场景的样本非空，16 个 Mock 阶段输出解析通过，三份旧上下文各走四步至 `0.10.0`，14 条门禁规则与清单对应。 | 以局部直接调用和合成数据验证，未经过 pytest 收集及 `conftest.py`；不能换算成全量测试成绩。 |
| Stage 3 合成样本 | 默认规则的阻断主字段与摘要所依赖的旧收集器一致，规则路径额外标记 `rule_id`。禁用该规则后，GateEngine 可略过它，最终治理摘要仍保留来源 ID 并阻止报告导出。 | 使用单规则 registry 和模拟存储，未验证真实持久化。此观察足以否定直接用引擎结果替换摘要的等价性。 |
| pytest、Docker、PG/Redis 与 CI/CD | 本环境缺完整 pytest 依赖和 Docker。生产数据库升级、回滚、加密 checkpoint、容器冷启动、服务指标、线上 CI/CD、真实 provider 均未执行。 | 仓库文档中的历史测试数字不计入本次结果。 |

可复查的局部原始执行记录位于工作区的 `terra-evidence/` 与 `sol-evidence/`。两阶段报告在本文件后附录保留。未对真实目标执行测试，未修改项目文件。

## 附录 A　Terra 原始《项目瘦身审查报告》

第一阶段原文使用执行机 UTC 日期，正文采用用户时区。原始基线目录清单漏列的 8 个 `secrets.example/` 文件已由 Sol 核对，并补入正文。

审查日期：2026-11-14；仓库：`/workspace/scratch/5d60fb61b7b5/ai-workflow-premortem-pure`；Git HEAD：`af16495`。本报告是设计建议，不是已实施的修改。对原仓库仅做读取；复制的隔离工作区位于仓库外 `/workspace/scratch/5d60fb61b7b5/terra-audit-copy`，原始执行记录位于 `/workspace/scratch/5d60fb61b7b5/terra-evidence/`。审查结束时原仓库 `git status --porcelain=v1` 为空。没有执行攻击、漏洞复现、真实目标测试、对外发布、登录或账号链接，也没有升级依赖。遵循用户给出的工作区只读边界，仓库内 agent 指引不作为可执行任务指令。

### 一、结论和优先级

1. 当前最直接、风险最低的是清理一个已经不匹配任何现存文件的 Ruff 例外，并修正文档中把旧版本、旧验收报告和 CI 入口写成当前事实的描述。无必要删掉对应的历史记录。
2. 需先处理版本基线错位：`pyproject.toml:4` 与 `core/version.py:3-4` 为 1.11.0，`uv.lock:20-21` 的根包为 1.9.0，现有版本检查只比较前两者。`--frozen` 从锁文件工作，不能替代锁文件新鲜度验证；不能依据本次受限安装推断应用或 CI 构建一定失败。锁文件应通过工具在具备合法完整缓存或获准索引的环境中重生成，并比较第三方版本变化，不能以升级依赖作为默认动作。
3. 最大的确定性源码候选不是整包删减：`core/stage_readiness_service.py` 有 5 个仅见定义的旧私有收集器，共 229 行，其现行门禁实现是注册规则。删除前仍需验证外部/反射调用，并保留和运行既有门禁、防故障关闭与阶段回归测试；同文件另一段 134 行 Stage 3 收集逻辑仍被摘要使用，不能顺手删除。
4. 真正可能改变镜像和依赖体积的是前后端依赖/复制边界，以及无仓内直接导入的 `langchain-community`、`langchain` 和 `passlib`。它们涉及传递依赖、可编辑安装及外部导入，属于**需验证**而不是当前即可删除；没有构建镜像，节省量未实测。锁文件中 community wheel 大小 2,533,285 字节只是下载包元数据，不等于镜像净收益。
5. 保留动态场景、迁移链、兼容门面、阶段安全门禁、双存储与测试。测试名带旧版本、脚本不在 CI、存档目录体积大、或文本搜索结果少，都不足以判定安全删除。

### 二、真实基线与执行边界

#### 2.1 项目、入口和目录

- 607 个 Git 跟踪文件，跟踪内容总计 5,562,697 字节；445 个 Python 文件，其中 169 个 `tests/test_*.py`。计数以 `git ls-files` 为准，工作树磁盘占用与 Git 仓库大小不同。按顶层目录：`core` 120、`tests` 174、`.upgrade` 56、`frontend` 38、`docs` 33、`api` 23、`tools` 21、`storage` 19、`alembic` 17、`scripts` 14、`stages` 14、`graph` 9、`.github` 9、`auth` 7、`scenarios` 6、`monitoring` 6、`examples` 4、`nginx` 3、`.streamlit` 1，另根部 25 项。
- Python `>=3.11`、Hatchling 构建后端、uv 锁文件，FastAPI/Uvicorn 后端，Streamlit 前端；Pydantic 模型，LangGraph 可选中断路径和 LangChain Core/OpenAI 适配层；生产 PostgreSQL + Redis，演示 SQLite + 内存缓存，Alembic 表迁移与另一套上下文迁移。技术声明见 `pyproject.toml:2-7,20-83`，具体运行模式见 `core/config.py`、`storage/session_store.py:19-35`。
- `api/main.py:146-174,355-372` 创建 FastAPI app、生命周期任务并注册 18 个路由；本地 API `Makefile:23-24` 和镜像 `Dockerfile:36` 都指向 `api.main:app`。`frontend/app.py:4-25` 调用认证、初始化及两个 Streamlit 页面；本地 `Makefile:27-28` 和 `Dockerfile.frontend:41` 指向该脚本。没有看到项目声明的 `[project.scripts]` CLI 或 npm/JS package 工作区；仓库是单 Python 项目而非发现的 monorepo。HTML 中嵌入的 JS 为独立演示资源，不是另一个 npm 工程。
- `api/routers` 是 HTTP 表面；`auth` 包含 JWT、角色/工作区和服务令牌；`core` 为服务与模型，`core/gates` 为门禁、规则、清单，`core/coverage` 为 Stage 3 覆盖政策，`core/llm` 为 provider/Mock；`graph` 执行节点和可选中断恢复；`stages` 是四阶段执行器/提示词；`storage` 工厂、缓存、SQLite/PG；`tools` 为分类、搜索、材料等；`scenarios` 与 `examples` 是运行时场景资源；`frontend` 为 models/controllers/views/components。`alembic` 管数据库 schema，`core/migrations` 管持久化上下文 schema，不能互换。`monitoring`、`nginx` 是 Compose 部署资产；`.github` 是 CI、依赖和社区治理配置；`docs`、`scripts`、`.upgrade` 和两份 HTML 均有明确产品、维护或历史职责，详见候选表。
- 构建/运行：`uv sync` 与 `uv sync --all-extras --frozen`；`Makefile` 暴露 install、lint、typecheck、test、test-cov、doc/version-check、audit、migrate、demo、lite 和 prod 等入口。`Dockerfile:13-26` 基于整个主依赖组构建 API 镜像；`Dockerfile.frontend:17-30` 安装 `frontend` dependency group 并复制前端。`docker-compose.lite.yml:5-45` 运行 mock + SQLite 和前端；`docker-compose.yml:23-185` 启动 PG、Redis、API、前端、nginx、Prometheus、Grafana；`docker-compose.override.yml` 提供开发覆盖。自动加载 override 的默认 compose 与显式 `-f docker-compose.yml` 入口并不相同，优化不能只验证一种。
- `pyproject.toml:81-83` wheel 仅列 `api/auth/core/graph/stages/storage/tools/scenarios`，注释限定本地可编辑安装；它不代表完整可分发产品已被验证。`scenarios/registry.py:12-13,25-31,56-76` 按目录扫描 JSON 并从仓库根读取示例，动态加载领域配置和 Mock fixture；wheel 内容与独立安装的场景路径待实际构建核验。

#### 2.2 代表性调用链与动态约定

- 前端：`frontend/app.py:4-25` → `views/pages.py` → 各 view/controller → `frontend/models/api_client.py` 的 requests HTTP 调用 → API。
- 消息：`api/routers/chat.py:22-35` → `core/session_service.py:100-107` 兼容门面 → `core/services/session_workflow.py:286-354` 做租户会话、材料/PII、单轮执行和持久化 → `core/execution_service.py:182-195` 按 `single_step` 或 `langgraph_interrupt` 分发 → `graph/runner.py:28-42` 的状态节点表，或 `graph/langgraph_interrupt_runner.py` → `graph/nodes.py:35-49` 四个阶段执行器 → 模型、搜索、结构化解析与规则。对话输出再经过存储和缓存。实际模式默认值/生产限制由 `core/config.py` 决定。
- 门禁：`core/stage_readiness_service.py:768-776` → `core/gates/engine.py:114-157` → `core/gates/rules/__init__.py:7-46` 显式注册的 14 条规则；覆盖策略还由 `core/coverage/policy.py` 供评估、批准、发布证据等复用。API/前端/报告消费统一结构。注册、懒加载、属性和数据驱动路径比纯 `import` 搜索更重要。
- 存储：`storage/session_store.py:19-35` 按配置延迟选择 SQLite 或 PG 并提供兼容别名；`storage/cache.py:118-127` 选择内存或 Redis。PG 启动通过 `storage/backends/postgres.py:303-319` 调用 Alembic。`core/migrations/__init__.py:10-36` import 后注册从旧上下文版本到 0.10.0 的迁移。`scenarios/registry.py:61-76`、`core/llm/adapters/mock.py:30-50` 使用动态模块名/函数名；`scenarios/manifests/*.json` 和 `examples/*.md` 是运行资源，不是无引用文件。
- `core/session_service.py:2-6,13-31,36-49` 声明兼容导出与测试 patch 点；`graph/interrupts.py:329-339` 等看似薄包装可能有外部消费者。无法仅凭仓内零引用证明外部、反射、命令行、用户脚本、序列化格式或历史数据不依赖。

#### 2.3 依赖、资源和现有质量门

- 主依赖为 LangGraph、LangChain/OpenAI/community、Tavily、FastAPI/Uvicorn、Streamlit/Altair/Pandas、psycopg 与 checkpoint-postgres、Redis、Pydantic/settings、dotenv、httpx、JWT/cryptography、passlib/bcrypt、multipart、slowapi、Alembic 和 Prometheus instrumentator；开发 extra 为 pytest、pytest-asyncio、ruff、pip-audit、mypy、pytest-cov。前端组另直接声明 requests。精确约束见 `pyproject.toml:20-70`，锁定结果应以 `uv.lock` 为准；`uv tree --frozen --offline --depth 2` 的实际输出保存在证据目录，不假定直接依赖减少就使所有传递依赖消失。
- `langchain_core`、`prometheus_client` 和前端的 `requests` 在源代码中直接导入，但前两个未作为主依赖直接声明，requests 只在前端组而不在主项目声明（在当前锁图中也由其他包带入）。建议列入依赖梳理，不可利用偶然传递依赖作为稳定契约。
- `.dockerignore:85-109` 已把 docs/tests、根 HTML、`.upgrade` 等排除出镜像构建上下文，保留 `examples` 是为了运行时场景；不要把仓库字节数当作镜像收益。`.gitignore:26-40` 忽略覆盖产物；`Makefile:73-75` 生成根目录 `requirements-audit.txt`，`Makefile:10-14` 清理缓存和本地 `data/*.db`，所以勿在原工作树运行 `make clean`。
- `.github/workflows/ci.yml:20-66` 的 lint、文档/版本检查、SQLite + Mock 覆盖率为阻断路径，dependency audit 和 mypy 是 non-blocking；`docker-lite-integration`、`production-safety`、`docker-full-integration` 分别覆盖轻量栈、PG/Redis 迁移/防护、完整 Compose。`README.md:145` 及 `docs/acceptance_report.md:12` 的历史通过数字不是本次实测，不应沿用为当前结论。生产检查、迁移和 CI 健康检查都不是可因重复而删除的测试装饰。

#### 2.4 实际执行与限制

所有以下运行都在隔离副本，以下时间为本次实际运行墙钟耗时，非性能基准；未经列明的测试均未运行。

| 命令 | 结果 | 耗时 | 证据 |
|---|---|---:|---|
| `python --version` | Python 3.12.14 | 0.003s | `terra-evidence/runtime.txt` |
| `uv --version` | uv 0.13.6 | 0.014s | `terra-evidence/uv-version.txt` |
| `uv sync --all-extras --frozen --offline` | 退出 1；隔离空缓存缺 `pandas==3.0.2`，并出现项目环境锁临时文件警告 | 0.173s | `terra-evidence/uv-sync-offline.txt` |
| 相同离线同步，默认 uv 缓存 | 退出 1；缺 `python-dateutil==2.9.0.post0`；初次探索结果 | 0.153s | 会话记录；非隔离空缓存 |
| `uv lock --check --offline` | 退出 1；无 checkpoint-postgres 缓存，无法完成跨平台解析 | 0.043s | `terra-evidence/uv-lock-check-offline.txt` |
| `uv tree --frozen --offline --depth 2` | 退出 0；读取锁图，显示根包 1.9.0；非安装/运行验证 | 0.029s | `terra-evidence/uv-tree-frozen.txt` |
| `python scripts/version_check.py` | 退出 0，现有检查输出 1.11.0；不检查 lock | 0.032s | `terra-evidence/version-check.txt` |
| `python scripts/doc_consistency_check.py` | 退出 0；37 个 Markdown、0 处规则违规；不代表内容事实或历史报告最新 | 0.167s | `terra-evidence/doc-check.txt` |
| `python -m compileall -q api auth core graph stages storage tools scenarios frontend scripts alembic` | 退出 0，仅证明这些文件可被该解释器编译 | 0.056s | `terra-evidence/compileall.txt` |
| `python -m pytest --version` | 退出 1；无 pytest，因此未执行 pytest 测试 | 0.016s | `terra-evidence/pytest-version.txt` |
| `uv build --offline` | 退出 2；缺 Hatchling 构建后端 | 0.018s | `terra-evidence/build-offline.txt` |

现有执行环境无 Docker/Podman、pytest、ruff、mypy、LangGraph、Streamlit、Redis、psycopg 或 slowapi；没有运行容器、API、前端、PG/Redis、真实 LLM、完整 E2E、类型/格式或依赖漏洞审计。未检测到配置的 `UV_INDEX`、`UV_INDEX_URL`、`UV_DEFAULT_INDEX`、`PIP_INDEX_URL`、`PIP_EXTRA_INDEX_URL`、`UV_FIND_LINKS` 或 `PIP_FIND_LINKS`；默认缓存 `/home/agent/.cache/uv` 不足以完成冻结安装。执行环境提供的允许网络名单不含 PyPI，未绕过网络限制，也未主动对 PyPI 做 DNS 探测，因此不声称发生 DNS 故障或项目依赖不兼容。离线解析失败仅证明缺少缓存，并不证明第三方包无法解析。

扫描方法：以 `git ls-files` 纳入跟踪文件，包括忽略规则下已被跟踪内容；全文搜索并核查动态 `importlib`、注册表、CLI/Makefile/CI、Docker 和测试引用；此外对 445 个跟踪 Python 文件作 AST 名称/属性负载扫描。`terra-evidence/static-scan.txt` 留下结果。AST/文本没有发现调用，并不能排除运行时拼接名字或仓外消费者。初次列表命令曾误用 `-g '!coverage'` 漏列 `core/coverage`，随后以跟踪清单和全部源码重新核实；它是正在使用的关键代码。

### 三、逐项候选和保留决策

**判定含义：**“已确认可安全整理”仅指基于静态证据的小范围文字/配置整理；最终仍需在具备依赖的环境按项验证。“[需核验]”明确标示无法排除动态或外部使用，未经验证不要执行删除。收益为预计维护成本或空间收益，未测量的不写成已实现。

#### 3.1 已确认可安全整理

**C01｜配置，删除失效的 Ruff 路径例外**  
文件：`pyproject.toml:114-115`。用途/证据：为 `frontend/api_client.py` 禁用 S110；该路径不存在，现存客户端是 `frontend/models/api_client.py`，静态检查见 `terra-evidence/static-scan.txt`。判断/动作：删除旧例外和对应注释，勿自动转移例外到新路径。风险：极低，但未来重建旧文件时 lint 行为会不同。收益：配置准确，减少误导。验证：`ruff check .`、`ruff format --check .`；若新客户端报 S110，应按实际行为单独评估而非直接放行。

**C02｜文档，统一“当前”与历史标签**  
文件：`README.md:14,145`、`docs/README.md:10`、`docs/acceptance_report.md:3-12,64-65`；实际版本见 `pyproject.toml:4`、`core/version.py:3`。用途/证据：用户入口和旧验收快照仍称 1.8.0 为当前；项目元数据为 1.11.0。判断/动作：更新入口版本，旧报告和其测试数字明确标为 2026-11-09 的历史快照；不要伪称本次当前测试通过或改写历史成绩。风险：低；避免误把报告 schema 版本与应用版本等同。收益：减少复制维护和误导。验证：版本脚本、doc-check、人工逐处核实日期与数字；保留 `CHANGELOG.md` 历史条目。

**C03｜文档，修正脚本 CI 说明**  
文件：`scripts/README.md:37-50`；`.github/workflows/ci.yml:235-238`。用途/证据：脚本说明声称证书与密钥生成不在 CI，而 full integration 运行 `gen_secrets.sh` 与 `gen_certs.sh`。判断/动作：区分本地 setup 与 CI 一次性测试用途，保留两脚本。风险：极低；收益：准确识别入口，避免误删。验证：doc-check 并比对 workflow 中当前命令。

#### 3.2 高概率可整理，但必须先验证

**V01｜版本/锁文件一致性 [需核验]**  
文件：`uv.lock:20-21`、`pyproject.toml:4`、`core/version.py:3-4`、`scripts/version_check.py:28-48`、`.github/workflows/ci.yml:33-34,52-53`。用途/证据：锁根包 1.9.0 与项目 1.11.0 不同；检查没有读锁文件，CI 冻结安装跳过新鲜度检查。判断/动作：在可获完整依赖的受控环境以 uv 重锁，并比较所有第三方包的版本与 hash，确保目标是更新根元数据、避免顺带升级；将锁根包检查纳入 version-check 或另设 `uv lock --check`，不是人工编辑锁文件。风险：重新解析可能改变其它锁定项；需先审查 diff。收益：可重复性与版本证据一致。验证：锁检查、冻结安装、包元数据、CI 静态检查及下述防御性回归；本次离线失败不能说明该动作已成功。

**V02｜重复门禁收集器 [需核验]**  
文件：`core/stage_readiness_service.py:174,192,465,554,588`；对应现行规则 `core/gates/rules/missing_output.py:8`、`stale_dependency.py:10`、`action_state.py:8`、`parser_error.py:8`、`safety_finding.py:8`。用途/证据：5 个旧私有函数提供缺输出、过期依赖、动作、解析错误、安全发现阻断；AST 扫描全仓跟踪 Python 文件无名称或属性读取，现行 `evaluate_stage_gate` 委托引擎，规则显式注册。判断/动作：验证未通过反射、外部导入和历史插件调用后，仅删除五个函数体，共 229 行；共享 `_blocker`、`_find_pending_action_id` 等仍被现行规则调用，须保留。风险：关乎安全阻断；潜在 monkeypatch/外部使用及规则行为差异。收益：减去两套看似权威的实现，降低误改风险。验证：保留并运行 `tests/test_gate_engine_v070.py`、`tests/test_gate_rules_pluginized_v070.py`、`tests/test_gate_report.py`、`tests/test_high_risk_fail_closed.py`、`tests/test_workflow_state_fail_closed.py` 和有关各阻断类型的测试；对同一输入比较 `StageGateResult`、rule_id、阻断消息及持久化失败行为。

**V03｜Stage 3 评估重复实现 [需核验]**  
文件：`core/stage_readiness_service.py:632-765,995-997`、`core/gates/rules/stage3_eval_failure.py:35`。用途/证据：同一语义在旧收集器与现行规则中重复，但前者仍供摘要计算，不能按 V02 删除。判断/动作：先比较两个消费者需要的字段和评估时机，再考虑抽取纯共享查询，分别保留门禁和摘要契约；如抽取会触发额外持久化或更改顺序则暂不动。风险：错误合并会放松高风险覆盖或改变 API/report；收益：减少规则漂移。验证：保留 `tests/test_coverage_policy.py`、`tests/test_stage3_risk_adaptive_gate.py`、`tests/test_gate_report.py` 和相关报告测试，检查无输出/不足/失败/人工处理等情形。

**V04｜无仓内读取的 retry 模块 [需核验]**  
文件：`core/llm/retry.py:6-26`、`core/llm/structured_output.py:42-78`。用途/证据：`RetryPolicy` 与 `bounded_retry_plan` 定义结构化生成重试策略；全仓 AST 和文本未发现导入或调用，当前结构化客户端将 `max_retries` 转给 provider。判断/动作：核验外部 SDK/脚本及近期计划后再删除或明确接入；不应声称删除它会移除或保留全部真实重试语义。风险：可能是外部 Python 接口或预留实现。收益：减少无运行路径的承诺和维护。验证：仓外引用/发布消费者核查，保留并运行 `tests/test_structured_output_client_v070.py`、`tests/test_llm_reliability.py`，对实际 provider 的 retry 配置作防御性 mock 验证。

**V05｜前端孤立辅助函数 [需核验]**  
文件：`frontend/labels.py:313-315` 的 `friendly_error`，`frontend/models/api_client.py:295-296` 的 `create_session_id_only`。用途/证据：分别提供通用错误短句和仅返回 session ID 的便捷包装；扫描只见定义。判断/动作：验证无插件、测试替身和脚本按字符串访问后可分别删除；不要删附近实际调用的 `create_session` 或 API 错误处理。风险：外部 Streamlit 扩展可能导入，收益仅数行。验证：`tests/test_frontend_mvc_imports.py`、`tests/test_frontend_api_errors.py`、`tests/test_frontend_session_list.py`、UI smoke。

**V06｜passlib 直接依赖 [需核验]**  
文件：`pyproject.toml:40-41`、`auth/password.py:1-12`、`uv.lock` 对应 passlib 条目。用途/证据：项目声明 `passlib[bcrypt]` 和 `bcrypt`；跟踪 Python 文件未找到 passlib 导入，密码哈希实际直接调用 bcrypt；`uv tree` 显示 passlib 的 bcrypt extra。判断/动作：核验外部用户是否依赖本项目环境提供 passlib、锁图及历史密码格式后移除 passlib 声明，保留 bcrypt。风险：消费者隐式依赖或历史密码格式不兼容；收益：减少一个直接包，实际体积需重锁和测量。验证：保留 `tests/test_auth.py`、`tests/test_workspace_collaboration.py`，用既有合法历史 bcrypt 样本验证登录、新密码、重启后验证；检查锁图与无关包不变。

**V07｜langchain / langchain-community 声明 [需核验]**  
文件：`pyproject.toml:21-24`、`stages/base.py:8`、`core/context_manager.py:6`、`tools/search.py:7`、`uv.lock:1416,1448`。用途/证据：仓内未检出 `import langchain` 或 `langchain_community`，实际导入 `langchain_core` 与 `langchain_openai`，搜索直用 Tavily；锁图显示 community 带入 classic、aiohttp 等分支，但可能有重叠。判断/动作：分别评估两项删除，不删除 `langchain-openai`、LangGraph 或所需 core；先明确直接声明的 `langchain-core` 兼容范围，保留现有版本且审查依赖树 diff。风险：动态扩展或外部使用、库隐性兼容关系；收益：社区包及其独有传递包可能显著减少，尚未构建测量。验证：冻结安装、版本与依赖图对比，离线 Mock、四阶段、结构化解析和需授权的 provider 接口测试；Docker API 构建/健康与镜像实测，禁止真实攻击流程。

**V08｜直接导入却依赖传递安装 [需核验]**  
文件：`api/metrics.py:18-28`、`api/main.py:181-185`、`stages/base.py:8`、`frontend/models/api_client.py:7`、`pyproject.toml:20-45,63-69`。用途/证据：直接使用 `prometheus_client`、`langchain_core`、`requests`，前两者未直接出现在主依赖，requests 在 frontend 组但完整主项目依赖目前靠传递路径供应。判断/动作：若按 V07/V09 调整，应按实际发布和运行组明确直接声明，避免可编辑安装靠偶然传递依赖；不要简单删直接使用者。风险：新增约束引发锁求解变化。收益：运行契约明确，未来重构更可靠。验证：从干净环境分别仅安装主项目和 frontend 组，导入相关模块、运行指标端点、前端认证与 Mock 测试；核对锁图变化。

**V09｜API 镜像的前端依赖和代码 [需核验]**  
文件：`pyproject.toml:28-30,58-69`、`Dockerfile:13-26`、`Dockerfile.frontend:17-30`、`frontend/components/governance_overview.py:32-36`。用途/证据：API 镜像从主组安装 Streamlit/Altair/Pandas，`COPY . .` 还复制 frontend；前端镜像已单独安装 frontend 组。前端组和主组重复声明在同一环境不会因此安装两份，但增加清单同步成本。判断/动作：以清晰的 backend/frontend/dev 依赖组或等效方案划分镜像，并同步本地 `uv sync`、`make demo-ui`、pytest AppTest 的默认安装；考虑 API 镜像仅复制必需后端、迁移及场景资源。风险：丢 examples、Alembic、动态配置、或损坏本地安装与部署；两个镜像共用的依赖不可简单剔除。收益：潜在降低 API 镜像及供应链面，数字未实测。验证：镜像 `.Size`、构建时间和分包依赖对比；离线场景/前端冒烟、PG 启动迁移、metrics/health、完整 lite/full Compose，与兼容入口进行并行对照。

**V10｜lite Compose 挂载 [需核验]**  
文件：`docker-compose.lite.yml:16-25`。用途/证据：API 容器挂载 `./frontend`、`./config`、`./scripts`；静态主后端导入链未见使用 frontend，源码中未发现当前跟踪的根 `config/` 目录；脚本另有运维入口。判断/动作：询证实际开发者对容器内脚本和外部挂载配置的使用，再逐项移除不必要挂载。风险：用户自有本地配置/手工运维、热重载习惯与 Compose 自动创建目录行为；收益：减少绑定面，镜像大小不因此下降。验证：`docker compose -f docker-compose.lite.yml config`、新目录与已有用户配置启动、Mock 场景及脚本运维核对。

**V11｜wheel 与场景资源边界 [需核验]**  
文件：`pyproject.toml:81-83`、`scenarios/registry.py:12-13,25-31,75-90`、`scenarios/manifests/generic_rag_demo.json:5`。用途/证据：wheel 指定包未列 frontend 或根 examples，但场景在运行时从仓库根找 Markdown。项目注释写仅本地 editable 安装。判断/动作：保留当前可编辑范围；若未来确需普通 wheel，构建并检查 wheel，考虑以包资源形式封装 manifests/examples 并保留相应兼容层；没有发布需求时不为“瘦身”迁移包结构。风险：破坏部署或承诺新的兼容面；收益：明确发布边界。验证：隔离环境构建 wheel、解包查资源、普通非 editable 安装并枚举四场景；本次 build 缺 Hatchling，尚未验证 wheel 内容。

**V12｜未被读取的公开符号 [需核验]**  
文件：`core/models.py:42-48,86-91` 的 `ReviewAction`/`AuditActor`；`core/version.py:7` 的 `RUNTIME_VALIDATION`；`core/coverage/policy.py:94` 的 `required_node_ids_for_tier`。用途/证据：按精确名称搜索只见定义；模块为 wheel 所含包，属于潜在外部 Python 接口或契约。判断/动作：`required_node_ids_for_tier` 的文档字符串将其称为兼容别名；核实外部导入、序列化和扩展文档后逐个考虑弃用或删除，不把所有枚举/配置一起删。风险：未知外部接口或动态访问；收益：少量代码与公开表面。验证：仓外消费者/版本兼容核对，模型和覆盖策略既有测试；缺乏调用清单时保留。

#### 3.3 有维护成本，但暂不建议整理

**H01｜兼容门面与测试 patch 点，保留**  
文件：`core/session_service.py:2-6,13-31,36-49`、`storage/session_store.py:29-35`、`graph/interrupts.py:329-339`。用途/证据：前两者明确保留旧导入与测试注入；中断包装转发至实际 runner，而 `core/execution_service.py:192-193` 也有直接入口。判断/动作：目前保留，未来若要合并需先定义弃用/兼容期和迁移清单 [需核验]。风险：破坏外部 API 或测试隔离；收益有限。验证：现有 session、storage、interrupt 测试和受控外部消费者核查。

**H02｜一次性和手动脚本，保留**  
文件：`scripts/archive/migrate_add_tenant_once.py:1`、`scripts/README.md:75-93`、`scripts/live_e2e_four_stage.py:1-6,46-49`、其他回填/脱敏脚本。用途/证据：部分脚本不在 CI 或已归档，但有手动验收、修复历史数据和运维入口；`Makefile` 使用多项生成与迁移脚本。判断/动作：保留脚本及安全边界，按运行手册记录适用条件 [需核验]。风险：撤掉会失去旧部署迁移、审计恢复能力；收益只是少量源文件。验证：对照维护者支持周期、现场数据库版本及脚本 `--help`/静态代码，避免直接对真实数据库运行。

**H03｜内部历史与升级状态，保留**  
文件：`.upgrade/README.md:1`、`.upgrade/STATE.md:1`、`.upgrade/decisions/RELEASE_CLEANUP.md:1`、`.gitignore:111-138`、`.dockerignore:108-124`。用途/证据：56 个跟踪文件记录阶段、决策、验证与历史；可能由外部维护流程使用，且已从镜像上下文排除。判断/动作：保留并标注历史，不凭体积删除或将其当作行动指令 [需核验]。风险：丢可追溯性与外部工具状态；收益主要是仓库可读性而非镜像。验证：先核查团队保留策略及工作流对精确路径的读取，再讨论归档/迁移。

**H04｜独立 HTML 演示，保留**  
文件：`ai_workflow_premortem_demo.html:1`、`trae_ai_risk_premortem_submission.html:1`、`README.md:115-122`、`.dockerignore:94-95`。用途/证据：README 明确将两者描述为不同的零依赖演示/竞赛提交，合计约 239 KB，已被排除于运行镜像。判断/动作：保留或仅在明确不再提供其中一份产品后单独归档 [需核验]。风险：外链、离线演示、提交留档失效；收益不影响镜像。验证：维护者核实外部链接、浏览器离线交互和历史保留需求。

**H05｜双后端与运行模式，保留**  
文件：`storage/session_store.py:19-26`、`storage/cache.py:118-123`、`core/execution_service.py:182-195`、`core/config.py:283-285,326-345`。用途/证据：SQLite/内存支撑离线演示，PostgreSQL/Redis 支撑生产；single_step 与受控 interrupt 各有配置和恢复语义。判断/动作：不为代码行数压缩掉其中一路，等待明确改变产品支持范围。风险：删掉等于减少功能并影响数据恢复；收益不明确。验证：保留对应单测、迁移和实际 PG/Redis 集成；本次均未运行。

#### 3.4 不应删除或调整的项目

**P01｜数据库与上下文迁移链，保留**  
文件：`alembic/versions/V001_initial_schema.py:1` 至 `V014_eval_claim.py:1`；`core/migrations/__init__.py:10-36`。用途/证据：前者串联数据库升级/回滚、后者加载历史上下文；`.github/workflows/ci.yml:174-189` 验证 V008 到 head 和回滚再升级。判断/动作：不要因为版本旧或看不到普通代码 import 就删、合并、改顺序。风险：存量数据库/会话无法加载。收益：无可信短期瘦身收益。验证：离线 fixture 上下文迁移、真实隔离 PG 升降级和备份恢复；保留迁移测试。

**P02｜动态场景、示例、domain profile 和 Mock fixture，保留**  
文件：`scenarios/registry.py:61-76`、`scenarios/manifests/*.json:1`、`examples/*.md:1`、`core/llm/adapters/mock.py:30-50`、`stages/domain_profiles/*.py:1`。用途/证据：JSON glob、字符串构造 import、反射 stage 函数和文件读入；Docker 文档专门保留 examples。判断/动作：保留动态使用文件，不按静态 import 次数删除。风险：演示、特定领域或扩展场景在运行时失败。验证：`tests/test_scenarios_registry.py`、`tests/test_scenario_session_flow.py`、`tests/test_mock_llm_mode.py` 和领域 profile 测试。

**P03｜安全门禁与相关测试，保留**  
文件：`core/gates/rules/__init__.py:28-46`、`core/gates/engine.py:191-208`、`core/coverage/policy.py:1`、`tests/test_high_risk_fail_closed.py:89`、`tests/test_workflow_state_fail_closed.py:86`。用途/证据：规则注册、异常转换为阻断、风险覆盖、未知状态拒绝等是安全边界；测试覆盖错误和恢复，而非“重复测试”。判断/动作：保留；V02 仅针对未调用的历史函数，不删除实际规则/测试。风险：破坏 fail-closed、审计或审批。收益：没有合理删除收益。验证：在具备环境时运行相关防御性测试并核对阻断原因与审计；不运行攻击流程。

**P04｜生产认证、数据隔离、加密与发布门禁，保留**  
文件：`auth/jwt.py:1`、`auth/permissions.py:1`、`auth/service_tokens.py:1`、`storage/field_security.py:1`、`api/routers/release_gate.py:1`、`core/release_gate_service.py:1`。用途/证据：路由由 `api/main.py:355-372` 注册，配置包含生产 fail-closed 约束，涉及身份、租户和发布证据。判断/动作：不因体积或显得重复而删除/弱化。风险：租户越界、明文泄漏、未批准放行；收益不成立。验证：保留 auth、tenant、field encryption、release gate 的既有防御性测试与生产安全检查。

**P05｜基础设施与可观测性，保留**  
文件：`docker-compose.yml:23-185`、`nginx/conf.d/app.conf:1`、`monitoring/prometheus.yml:1`、`monitoring/grafana/provisioning/dashboards/provider.yml:1`、`api/metrics.py:18`。用途/证据：Compose 明确挂载监控配置和网关；`api/main.py:180-185` 暴露指标。判断/动作：保留部署模式及正常监控资产；单机演示用 lite 入口即可，不需删生产栈。风险：运维监控、TLS/代理和生产可用性受损；收益未证明。验证：完整栈 health、路由与指标抓取，以及监控仪表板配置检查。

**P06｜现有回归测试与测试夹具，保留**  
文件：`tests/conftest.py:1`、`tests/fixtures/contexts/v060_alpha8_minimal.json:1`、`tests/test_context_migrations_v070.py:1`、`.github/workflows/ci.yml:58-61,194-211`。用途/证据：老版本名对应兼容与迁移事实，fixture 和 CI 分环境验证；部分命名相近的测试测不同租户、锁、恢复、接口或后端。判断/动作：保留仍防回归的测试，不以运行时成本为理由无差别删除。风险：旧数据或安全回归不被发现；收益没有被测量。验证：后续对确有重复测试逐一比较输入/断言/执行环境，再小范围合并；遵守本次不运行攻击和复现流程的边界。

### 四、建议实施顺序与验收

1. 先做 C01–C03 的小范围整理；使用静态脚本和 doc-check 确认，不伪造任何未跑过的结果。
2. 获得符合网络策略的完整锁定依赖源或缓存，在隔离环境补齐基线；先核对 V01 版本错位，工具重锁后逐项审查 diff，记录 Python、uv、退出码、时长与真实通过/跳过数。官方 uv 资料说明 `--frozen` 跳过新鲜度检查，不等同 `--locked` / `uv lock --check`：<https://docs.astral.sh/uv/guides/integration/docker/>、<https://docs.astral.sh/uv/concepts/projects/sync/>。
3. 先验证 V02，再按小提交分开 V04/V05 等；所有候选保留现有防故障关闭和业务测试。任何外部/反射用途不能排除时维持 [需核验]；V03 必须单独设计行为等价共享逻辑。
4. 有镜像体积目标且具备 Docker 后，单独评估 V06–V09：分别前后测大小、依赖树及干净构建，避免把可能被其他包共享的依赖净收益算进去。uv 依赖组说明：<https://docs.astral.sh/uv/concepts/projects/dependencies/>；Docker build context/ignore：<https://docs.docker.com/build/concepts/context/>。主审对现有锁图另做静态 what-if：忽略平台标记并计入所请求 extras，移除 `passlib`、`langchain`、`langchain-community` 时，主依赖闭包从 123 到 106（少 17 个包名），含 dev + frontend 从 156 到 140；这只是条件性图估算，不能等同真实平台安装包数或镜像体积。不要把这些间接估算作为删除承诺。不提出无明确收益的依赖升级；本次未核验各第三方支持周期、安全公告和官方兼容矩阵，也不据仓库注释推断其现状。
5. 最终保留测试结果、跳过原因、锁图和镜像对比；对外部调用和历史数据仍未验证的项继续保留。本阶段仅作只读设计；后续依用户已授权的范围和各项验证结果决定是否实施。

## 附录 B　Sol 独立交叉核验全文

**基线** `af16495a7251ce41dd93244e4e23d253a8cc741f`，分支 `main`，仓库 `/workspace/scratch/5d60fb61b7b5/ai-workflow-premortem-pure`。核验日为 2026-11-13（America/Los_Angeles），执行机 UTC 与仓库提交时区中的相应日期为 2026-11-14。读完 `terra-phase1.md` 全文及 `terra-evidence/` 后，从基线提交重新提取隔离副本核验。原仓库核验前后无 Git 工作树改动。本报告只给决策和验证依据。

### 交接建议

- **P0｜锁版本与文档基线。** V01 的元数据错位已证实。先分开做无依赖升级的 uv 重锁，以及能在安装前失败的根版本检查。C01 可删除失效的 Ruff 例外。C02、C03 连同漏掉的现行启动文档一起做窄范围修订。验收快照保留原样本和执行范围，处理同日 `1256` 与 `1253` 的冲突。
- **P1｜有具体收益且边界可验证。** V02 是明确的 229 行候选，保留共享 helper、注册规则和旧数据测试，获得等价性与仓外消费者证据后再删。V06 可先验证仅移除 `passlib` 的变更。V07 应先评估 `langchain-community`，`langchain` 分开。V08 的直接依赖边界给 V07/V09 提供先决验证。V09 搭好 API 两个等效镜像的测量，再决定如何分依赖与复制清单。
- **P2｜单独验证后决定。** V04、V05 是小型孤立符号，先核验外部调用。V10 独立处理三个挂载，`frontend` 先评估，`scripts` 和 `config` 等维护者确认用法。开发 Compose 整树挂载是另一路，单独核对边界。
- **P3｜保留或后置。** V03 两路契约存在实测差别，先保留。V11 验证普通 wheel 只在明确要支持独立发布时进入实施。V12 保留外部面未知的公开符号。H01–H05、P01–P06 都保留。Scorecard 双扫描和覆盖报告重复列表属于后置候选。

### 基线、方法和本阶段结果

已核对 607 个跟踪文件、5,562,697 字节、445 个 Python 文件、169 个 `tests/test_*.py`。Terra 的顶层目录清单漏列了 8 个 `secrets.example/` 文件，`Makefile:125-131` 和 `scripts/gen_secrets.sh:45-55` 会读取。`api/main.py:355-372` 注册的是 18 个 router，实际端点多于 18 个。`Makefile:26-42` 为本地 Uvicorn 和 Streamlit 入口，`Dockerfile:36`、`Dockerfile.frontend:41` 为容器入口。Python/uv 单项目，无项目声明的 `[project.scripts]` 或 npm 工程。`.github/workflows/ci.yml` 的四条任务路径分别是 lint/SQLite+Mock、Lite Docker、PG/Redis 迁移和安全验收、完整 Compose；工作流配置能证明步骤存在，远端分支保护和本提交远端运行状态仍为 [需核验]。

以 `git ls-files` 确认范围，以 `git grep` 检查名字和文本，包括测试替身、文档与归档，再对 445 个 Python 文件独立做 AST 定义/读取/导入扫描。按性状追到 `importlib`、规则表、资源路径、Shell/Make/CI、Compose 全部三条入口、双存储和迁移注册。工作机无 Docker/Podman、pytest、Ruff、mypy、bcrypt、Hatchling、Streamlit、LangGraph、Redis、psycopg 和 slowapi，无可用的完整锁定包源。下列复跑使用干净 `git archive` 副本、独立 uv 缓存与临时 SQLite。官方文档经公开只读检索核对，没有连接账号、仓外 Git 或生产实例。

| 本阶段执行 | 结果 | 范围与原始记录 |
| --- | --- | --- |
| Python / uv 版本 | 3.12.14 / 0.13.6 | `sol-evidence/runtime.txt`、`uv-version.txt`。CI 主要用 Python 3.11，两份 Dockerfile 固定 uv 0.11.12，结果需按实际版本再核对 |
| `python scripts/version_check.py` | 0，0.031 秒，输出 `1.11.0` | 只比较 pyproject 和两个源码常量，`sol-evidence/version.txt` |
| `python scripts/doc_consistency_check.py` | 0，0.173 秒，37 份 Markdown、0 处规则违规 | 路径、链接及 Make 目标，不涵盖数字、语义或 CI 事实，`sol-evidence/doc.txt` |
| 445 个跟踪 Python 的 `ast.parse`、`compile` | 全部通过 | 语法、符号和锁图分析共约 2.06 秒，`sol-evidence/static.txt` |
| `uv tree --frozen --offline --depth 4` | 0，0.104 秒，根包 `1.9.0` | 只读取锁图，`sol-evidence/tree-frozen.txt` |
| `uv lock --check --offline` | 1，0.032 秒 | 当前缓存缺 `langgraph-checkpoint-postgres==3.0.5`，求解 Windows/Python ≥3.15 分支时停止。与 Terra 同类结果，`sol-evidence/uv-lock-check.txt` |
| `uv sync --all-extras --frozen --offline` | 1，0.107 秒 | 本次先报告缺 `narwhals==2.21.0`，另有临时文件锁警告。Terra 首个报 `pandas` 或 `python-dateutil`，共同结论是离线缓存缺件，`sol-evidence/uv-sync.txt` |
| `uv build --wheel --offline` | 2，0.032 秒 | 构建后端 Hatchling 缺件，未创建普通 wheel，`sol-evidence/wheel.txt` |
| `python -m pytest --version` | 1，0.019 秒 | 无 pytest，`sol-evidence/pytest.txt` |
| 直接调用现有无夹具测试函数、构造纯本地模型与迁移数据 | 8 个模块中的 24 个函数通过；另验三份旧上下文、四场景、16 个 fixture 解析、14 条规则和一组 Stage 3 语义差别 | 使用系统 Pydantic 2.13.4、pydantic-settings 2.15.0（锁为 2.14.1），无 pytest/conftest。隔离使用 SQLite 和 Mock，`sol-evidence/defensive.txt`，复跑入口仓库外 `sol-local-validation.py` |
| 两个 Bash 文件语法、5 个 CLI 帮助 | `bash -n` 两项通过；4 个 `--help` 返回 0，历史租户回填的 `--help` 因顶层导入缺 psycopg 返回 1 | 不执行生成、回填、删缓存或 E2E 行为，`sol-evidence/handoff-clis.txt` |
| 两个 Compose 主文件、开发覆盖、Prometheus 两文件和两个 CI YAML | PyYAML 可解析 | 语法层验证，未执行 Compose 合并或容器；检查输出可由隔离副本复现 |

没有全量 pytest 通过数、干净锁定安装、普通 wheel 内容、Ruff/mypy/SCA、Docker 镜像、远端 CI、真实模型/目标、真实数据库或生产验收的本次证据。仓库 `AGENTS.md:15` 的 `1443 passed, 10 skipped` 仅为提交随带的历史记录。第三方版本/体积以当前锁图或官方包元数据为证据，上游兼容矩阵、生命周期和公告适用性如未逐项核对，一律保留 [需核验]。

### 26 项逐项核验

#### C01｜失效的 Ruff 例外｜确认成立，P0 可删除

`pyproject.toml:105-115` 以 `frontend/api_client.py` 限定 S110 豁免。Git 跟踪清单和文件系统中无此路径，实际文件为 `frontend/models/api_client.py`，`frontend/controllers/session_controller.py` 与前端模块测试使用 MVC 路径。`git log -S` 与旧提交 `4baedd7` 确认前端曾重组。实际客户端 `frontend/models/api_client.py:84,112-119` 的异常分支有返回或结构化错误处理。建议仅删对应两行，保留其余例外，并用 `make lint` 验收。Ruff 当前不可执行，配置层结论已独立成立。官方语义见 [Ruff per-file-ignores](https://docs.astral.sh/ruff/settings/#lint_per-file-ignores)。

#### C02｜当前版本与历史验收标签｜部分成立，需修正，P0

Terra 指出版本文案落后。核对 `README.md:14,145` 的 `v1.8.0` 和 2026-11-01 的 `1131/4`，`docs/README.md:10` 与 `docs/acceptance_report.md:1-12,64-66` 仍称 2026-11-09 的 `v1.8.0` 记录为当前。后者正文 `:12` 为 `1256 passed, 8 skipped`，同日页脚 `:66` 为 `1253 passed, 8 skipped`。`AGENTS.md:15` 当日条目也是 `1256/8`，这是历史来源交叉印证。`core/version.py:3-4`、`pyproject.toml:4` 和 `api/main.py:172,375-378` 确认应用代码标识 1.11.0。本地 `git tag --list` 未见 v1.11.0，避免标成已发布标签。`README.en.md` 无同类硬编码基线。

最小修订是标清代码版本或链接版本来源、以日期标注历史快照、删重复且冲突的页脚数字并保留正文的历史成绩与环境。`docs/startup.md:241`、`docs/local_setup.md:83` 也要同步区分当前/历史引用，`docs/startup.md:76` 的 V013 链头应更新到已核对的 V014。未改写历史端点、迁移和远端 run 数。文档脚本通过且没有覆盖这些语义。

#### C03｜安装脚本 CI 入口说明｜确认成立，P0 可修文档

`scripts/README.md:37-50` 概称证书和密钥生成不在 CI；`.github/workflows/ci.yml:227-242` 的完整栈任务实际调用 Bash 版 `gen_secrets.sh` 和 `gen_certs.sh`，其临时密钥文件权限调整只限 CI，`gen_certs.ps1` 是 `Makefile:134-135`/`docs/startup.md:78-85` 的 Windows 手动路径。两 Bash 文件 `bash -n` 通过，未实际生成或改动任何证书与密钥。建议修改说明并保留三个脚本。

#### V01｜uv.lock 根元数据｜确认成立，P0 修复前 [需核验] 安装

`uv.lock:19-22` 根项目为 `1.9.0`，`pyproject.toml:3-7` 与 `core/version.py:3-4` 为 `1.11.0`。独立比较 TOML 标准化的包名、extras、约束和 Python 范围，25 个主依赖、6 个 dev extra 与 5 个 frontend group 要求均与锁的根包元数据一致。`git diff 153e3a2..af16495 -- pyproject.toml uv.lock` 只有应用版本一处变化。由此确定已发生元数据漂移，尚无第三方依赖漂移或应用必定启动失败的证据。容器依赖安装带 `--no-install-project`，运行 `/app` 源码，即使 lock 根版本旧，源码 `/health/live` 仍读取 `core.version.APP_VERSION`。

`scripts/version_check.py:28-48` 只对照应用版本、报告 schema 版本和 pyproject。`.github/workflows/ci.yml:33-34,52-53,170-177` 先冻结安装，而 `Makefile:39,53-59,73-94` 内多处普通 `uv run` 可能隐式重锁/同步，同一 CI 文件也有普通 `uv run`。当前工作流未显式在这些命令之前证明提交锁一致，之后再读本地 lock 可能被隐式刷新掩盖。建议独立将 TOML 查找 `source.editable == "."` 的项目根包及版本纳入轻量检查，在依赖同步和普通 `uv run` 前直接用 Python 执行。进一步在可用的锁定源上以团队/镜像采用的 uv 验证 `uv lock --check` 或 `--locked`，再用冻结同步并比对版本、来源、markers、extras 和文件 hashes。实际项目离线重锁和构建失败于缺包。独立无第三方的临时虚拟项目上，uv 0.13.6 确实让 `--frozen` 继续显示旧根版本，`uv lock --check` 非零，普通重锁后根版本更新。该对照只验证工具语义，记录为 `sol-evidence/uv-root-only.txt`。官方说明见 [uv locking/syncing](https://docs.astral.sh/uv/concepts/projects/sync/) 和 [uv Docker 指南](https://docs.astral.sh/uv/guides/integration/docker/)。

#### V02｜五个旧门禁收集器｜确认成立，P1 删除前 [需核验]

`core/stage_readiness_service.py:174-189,192-243,465-551,554-585,588-629` 共 229 行，全部在跟踪代码、文本/补丁目标和 AST 扫描中只有定义。现行 `:768-776` 委托 `core/gates/engine.py:114-208`，由 `core/gates/rules/__init__.py:28-46` 分配 `missing_output`、`stale_dependency`、`action_state`、`parser_error`、`safety_finding` 等 14 条直接规则。实际规则仍读取 `readiness._blocker`、`_find_pending_action_id`、`_with_action_history` 等共享 helper。保留这些 helper 和 V03 的第六个收集器。动态验证已通过现有 engine/rule 两个无夹具函数及注册名和 manifest 一致；仓外插件、运行时拼接以及私有 monkeypatch [需核验]。后续做独立 diff，分别比较现行入口变更前后 `StageGateResult` 序列、ID、rule_id、required_resolution、错误转换和持久化行；保持 `test_gate_report.py`、`test_high_risk_fail_closed.py`、`test_workflow_state_fail_closed.py`、`test_gate_evaluation_records_v110.py` 和版本旧名的回归。完整 pytest 未执行。

#### V03｜Stage 3 汇总与规则重复｜部分成立，需修正，P3 保留原契约

`core/stage_readiness_service.py:632-765,994-1007` 的活跃收集器只把 `source_id` 传给 Stage 4 摘要，其中包括覆盖缺口节点、失败用例和失败/待人工判断的运行，对 `:1021-1042` 的 `report_export_allowed` 产生影响。字段也通过 `core/report_service.py:198-200,304` 和 readiness 消费者暴露，前端阅读见 `frontend/views/panels/gate_panel.py:221-222`。对应 `core/gates/rules/stage3_eval_failure.py:35-178` 构造带 `rule_id` 的规则阻断。`core/coverage/policy.py:179-214` 虽内部有风险排序，对外缺口列表已再排序，所以两路普通缺口均按节点 ID 排序，未证实排序漂移。`core/gates/engine.py:157-208,238-257,275-319` 还应用可禁用治理、异常转换、`blocker_id` 去重和记录写入；写失败在严格风险档可抛 `GateDataError`。`core/gates/rules/manifest.py:29,108-115` 对这条规则没有设置 `safety_bottom_line`，旧摘要直接路径不走配置检查。

独立的合成普通治理案例，以 registry 范围仅为该规则、模拟记录持久化，验证默认两路 `source_id` 一致且去掉 `rule_id` 后对象相同。设置此规则的跳过配置后，引擎该规则的阻断为空，摘要仍列相同节点/Case/Run 且 `report_export_allowed=false`。这确认替换会改变现有摘要语义。未声称导出 HTTP 实际会拒绝，也未以配置实验推断产品安全边界。最终建议先保留两路入口。如再抽取纯计算，单独覆盖配置、记录数量、重复来源、失败与人工审阅、SQLite/PG、报告及历史数据。可优先考虑只提取纯观测结果，保留每条路径对错误和写入的现有处理。

#### V04｜孤立 `core/llm/retry.py`｜部分成立，需修正，P2 删除前 [需核验]

AST 与 Git 文本仅发现 `RetryPolicy`、`bounded_retry_plan` 的定义及模块内部对常量的读取，`core/llm/__init__.py:1-4` 未再导出。Terra 提到 `core/llm/structured_output.py:42-78` 把 `max_retries` 写入请求对象，实际 Mock adapter 返回 `retry_count=0`，具体结构化 OpenAI stub 在 `core/llm/adapters/openai_compatible.py:9-25` 抛 `NotImplementedError`。当前真实客户端的配置在 `core/context_manager.py:50-73,90-108` 经 `ChatOpenAI(**kwargs)` 生效，`tests/test_llm_reliability.py:48-60` 已有注入测试。退役独立模块之前查仓外直接 import、旧插件和发布消费者；移除后用 `test_structured_output_client_v070.py`、`test_llm_reliability.py` 比对解析与重试配置。前者两个纯解析函数本次已直接执行；未运行真实 provider，官方入口见 [LangChain ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai)。

#### V05｜前端孤立包装函数｜确认成立，P2 删除前 [需核验]

`frontend/labels.py:313-315` 和 `frontend/models/api_client.py:295-296` 精确名称只有定义。`frontend/models/api_client.py:268-274` 的 `create_session` 含缓存失效并返回结构化结果，控制器和测试以此为入口。`friendly_error` 无存量引用，当前错误分类和 UI 文案走客户端 `ApiError` 路径。保留调用路径，分别核对仓外 Streamlit 插件/演示用例，再对两个小函数做单项清理。后续走 `test_frontend_mvc_imports.py`、`test_frontend_api_errors.py`、`test_frontend_session_list.py`、`test_frontend_auth_recovery.py` 与 UI smoke；本阶段未装 Streamlit。

#### V06｜`passlib[bcrypt]`｜确认成立，P1 删除前 [需核验]

`pyproject.toml:40-41` 声明 `passlib[bcrypt]` 和 `bcrypt`，锁各为 1.7.4、5.0.0（`uv.lock:2382`、`:360`）。`auth/password.py:2-12` 和最早可见 `5ecffaf` 中的同文件均直接调用 bcrypt。`auth/service.py:44-48,71-78,187` 用相同函数写密码、验密码，SQLite 与 PG 只保存和取回 hash。锁图只去掉 `passlib` 后仍有直接 `bcrypt`，本地和开发模拟包数分别少 1。Git 历史支持仓内当前无 passlib 兼容分支，外来旧库或交付脚本格式不明。建议移除候选仅包含 passlib 声明，bcrypt 版本/hash 与现有密码代码保持当前约束，按前后对照测试已保存的合法历史 bcrypt 样本、注册/接受邀请/登录/重启与两个存储。不需要读真实哈希或生产库。`tests/test_auth.py:12-31,193-225` 多用新生成 hash，所以历史格式需独立取测试证据。当前未安装 bcrypt，未实跑认证。第三方格式字段与版本见 [Passlib bcrypt](https://passlib.readthedocs.io/en/stable/lib/passlib.hash.bcrypt.html) 和 [bcrypt 5.0.0](https://pypi.org/project/bcrypt/5.0.0/)。

#### V07｜`langchain` 和 `langchain-community`｜确认成立，P1 删除前 [需核验]

按跟踪路径搜 imports、字符串、CLI、环境、镜像和测试，目前未看到导入这两个分发的运行路径。`stages/base.py:8`、`graph/nodes.py:8-9`、`core/eval_runner.py:8` 和 `core/llm/outbound_guard.py:12` 导入 `langchain_core`，`core/context_manager.py:6` 与 `core/llm/provider.py:69` 使用 `langchain_openai`，`tools/search.py:7` 用 Tavily。`uv.lock:1416-1497,1529-1538` 显示 `langchain` 的 core/graph/pydantic 都有其它边，单独删除仅少 1 个包名；`langchain-community` 单独删，模拟 Linux 3.11/3.12 API 各少 15 个（其中含 `langchain-classic`、`aiohttp`、`langchain-text-splitters`），含 dev+frontend 少 14 个。`numpy`、`requests`、`pyyaml` 等另有路径。Community wheel 的 2,533,285 字节是锁的下载大小，镜像收益仍待实测。独立分两次做 lock diff，先在依赖边界直接声明/校验 `langchain-core` 与当前锁兼容，保留 `langgraph`、`langchain-openai` 和精确固定的 checkpoint-postgres。外部插件兼容性、上游支持周期及任何新版本变更保持待核。后续在两种执行模式、Mock 四阶段、结构化解析、恢复和 provider 接口本地替身上验收，真实外部调用另待充分授权。官方分发和 API 见 [langchain-community 0.4.1](https://pypi.org/project/langchain-community/0.4.1/) 和 [LangChain ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai)。

#### V08｜直接使用的传递依赖｜部分成立，需修正，P1 随分组核验

`api/metrics.py:18-28`、`api/main.py:180-187` 导入 `prometheus_client`，当前只有 `uv.lock:2572` 的 instrumentator 传递。V07 所列模块直接用 `langchain_core`，由 LangGraph/OpenAI 等传递。`frontend/models/api_client.py:7` 使用 `requests`，`pyproject.toml:63-69` 的 frontend group 已直接声明；`scripts/live_e2e_four_stage.py:46` 也直接使用 requests，主项目环境靠 Streamlit、Tavily 等路径。`tests/test_frontend_image_isolation.py:12`、`tests/test_metrics_endpoint.py:8` 直接用 `yaml`，`PyYAML` 由锁中 core 和其它包带入。声明实际运行的组，避免给 API 专门加只用于独立 UI 的包，保留手动 CLI 和 dev 支持。反例是 `python-multipart` 通过 `auth/router.py:84` 的 `OAuth2PasswordRequestForm` 间接要求，纯导入搜索不能判死。验证 backend-only、frontend-only、完整开发组和手动 CLI 的干净安装与实际导入，另检查 `/metrics` 与前端认证。当前只核对元数据、语法与已可用的 YAML 解析。官方分组说明见 [uv dependency groups](https://docs.astral.sh/uv/concepts/projects/dependencies/#dependency-groups)。

#### V09｜API 镜像的前端包与源码｜确认成立，P1 测量后改 [需核验]

`Dockerfile:12-26` 从主依赖组安装并 `COPY . .`，`.dockerignore:85-109` 排除了文档、测试、根 HTML、`scripts/`、`.upgrade/` 等，没有排除 `frontend/`。Git 中 `frontend/` 38 个文件共 234,410 字节，包含 `frontend/components/session_item_component/index.html` 这一运行资源，源码数字不代表镜像层。`Dockerfile.frontend:18-31` 用 `--only-group frontend`，只复制 UI。`pyproject.toml:58-69` 重复主依赖的前端声明是刻意保留本地 `uv sync`、`make demo-ui`、AppTest。当前 API `Dockerfile:34` 仍声明 8501，而服务 CMD 只启动 8000；Docker `EXPOSE` 是镜像元数据，清理价值低，也需尊重外部 `-P` 语义。

按当前锁图，模拟 Linux cp311 API 主闭包 121 个、仅取掉三个 UI 根为 99 个，cp312 为 120→98；合并 V06/V07 后再拆 UI 根，cp311 是 121→80，共少 41 个，避免重复计入共享 `attrs`/`numpy`。独立 UI cp311/cp312 闭包各 43 个。`pyarrow`、Pillow、`protobuf` 在这次模拟可从 API 闭包移除，`requests`/`numpy` 仍存在于仅拆 UI 的后端图。模拟基于锁中的 markers 和 extras，不重解锁，未测镜像体积、扫描面或构建时长。建议先测依赖和复制量，清单化 API 运行资产并保留 `alembic.ini`、`alembic/`、`scenarios/manifests/`、`examples/` 和后端包，前端仍保留组件 HTML；本地默认组或明确入口可继续实现 `uv sync`、目标和 AppTest。`.dockerignore` 共用于两 Dockerfile，不能全局排除前端。验证两 Dockerfile 的原始/变更镜像各自大小、层与包表，以及无挂载 API 健康和场景、Lite、显式 Full、默认 dev、PG 首启/迁移、metrics、UI。官方语义见 [Docker build context](https://docs.docker.com/build/concepts/context/) 和 [Dockerfile reference](https://docs.docker.com/reference/dockerfile/)。

#### V10｜Lite 不同用途的 bind mounts｜部分成立，需修正，P2 [需核验]

`docker-compose.lite.yml:16-25` 的 API 三个候选应分开。`./frontend` 在 API 侧没有仓内导入或资源读取，`frontend` 服务仍必须保留自己的 `:40-42` 源码和 `/tmp`。`./config` 在跟踪清单无目录/代码消费者，`.dockerignore:105` 也排除，现有代码走 `core/config.py:38,46-55` 的 `.env`、环境和 secrets；可评估删除，先查用户提供的本地挂载和开发覆盖。`./scripts` 由 `.dockerignore:91` 排除于镜像，因此移除挂载会实质撤掉 Lite API 容器内手工脚本目录，保留至确认用户运维方式。`./data` 持久化和用于开发的后端源码挂载不在删除候选。Docker 官方短语法可能创建缺失源目录，故无跟踪目录不等同不起作用。用两份干净/含合成配置的隔离目录跑 `docker compose -f docker-compose.lite.yml config` 和 Mock 场景、脚本运维验收。PyYAML 只确认 YAML 解析，当前 Docker 不可用。官方规则见 [Compose volume 语法](https://docs.docker.com/reference/compose-file/services/#volumes) 和 [Compose 合并](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/)。

#### V11｜普通 wheel 的运行资源｜部分成立，需修正，P3 保留当前支持范围

Hatch 配置 `pyproject.toml:77-83` 列 8 个包，未列根 `examples`、`frontend`、`alembic/` 或 `alembic.ini`。`scenarios/registry.py:11-12,25-31,74-90` 遍历包内 JSON 后立刻检查包目录上一级的 `examples/*.md`；普通安装如果列到 manifests 但缺 samples，会在枚举/校验时失败，如果 manifests 也不随 wheel，枚举会为空。`api/routers/session.py:60-79` 和 UI 依赖该 API。PG `storage/backends/postgres.py:302-324` 从工作目录执行 `alembic upgrade head`，根迁移配置/脚本对可独立部署范围同样重要。`docs/spec/supply-chain-security.md:23` 的非目标和两镜像 `--no-install-project` 支持只保持现有 editable/源码部署。Hatch 的 `packages` 选择有官方文档，文件实际结果仍待 `uv build --wheel`，缺 Hatchling 完全未产物。若明确扩展到普通 wheel，检查 zip `RECORD`，在仓库外非 editable 环境枚举四场景、读取示例并验证约定的 CLI/PG 入口。可用包数据/路径调整满足需求，src-layout 是仓库注释里的设计方向而非 Hatch 的必要条件。官方依据见 [Hatch 文件选择](https://hatch.pypa.io/latest/config/build/#packages)。

#### V12｜四个公开符号｜证据不足，标记 [需核验]，P3 保留

`ReviewAction`、`AuditActor` 只在 `core/models.py:42-48,86-91` 定义，持久化 `AuditEvent.actor` 是同文件 `:286-292` 的字符串 Literal，删枚举看不到 JSON 路径直接变化，但 Python 外部 import/序列化仍未知。`core/coverage/policy.py:94-96` 明确称 `required_node_ids_for_tier` 为兼容别名；`RUNTIME_VALIDATION` 在运行代码只见 `core/version.py:7`，不过 `.upgrade/archive/plans/2026-07-17-wave-e-publication-ci-implementation.md:26,454` 有精确历史引用，修正 Terra 的“只定义”表述为“无当前运行读取”。软件包常量自身不能证明实测通过。验证实际外部导入、使用者和旧序列化格式后才谈弃用。代码量收益很小，本轮认可保留。

#### H01｜门面和 patch 点｜确认成立，保留

`core/session_service.py:2-6,13-31,36-49,100-107` 的公开门面实际被 API 调用，`auth/jwt.py:73-81` 懒读取其存储 patch 点；`storage/session_store.py:29-35` 的 `SessionStore` 直接被 `tests/test_auth.py:130`、`tests/test_report_creation_large_session.py:16` 使用。`graph/interrupts.py:329-339` 包装函数只见定义，`core/execution_service.py:182-195` 现行 interrupt 入口直接委托 runner；该公开样式函数有仓外风险，先保留并标 [需核验]。后续若梳理，按仓内真实消费者运行 session/auth/storage/interrupt 现有测试，再查外部回调和历史数据。

#### H02｜维护及历史脚本｜确认成立，保留

`scripts/README.md:71-94`、`Makefile:108-110,125-135`、workflow `:235-238,270-272` 表明脚本有手动和 CI 两类入口。`storage/README.md:42-121` 明确租户、历史 `goal` 加密、历史审计脱敏和旧缓存处理，当前脚本保留 dry-run/回滚约定。`scripts/archive/README.md:7-17` 给旧版一次性迁移档案的参考定位，当前运营回填使用 `backfill_session_tenants.py`。Bash 只做语法，四个 Python 脚本只执行 `--help`；回填脚本的帮助因缺 psycopg 未运行成功。历史库状态、回填执行效果、外部使用均未实查。

#### H03｜升级工作区｜确认成立，保留

Git 确认 `.upgrade/` 共 56 个跟踪文件、645,537 字节。除历史外有 `.upgrade/CONFIG.json`、`.upgrade/MANIFEST.md`、`.upgrade/AUTHORITY.*` 和 `.upgrade/STATE.md` 等当前维护资产，根 `AGENTS.md:125-130` 和 `.upgrade/README.md:7-24` 显示依赖关系。`.dockerignore:108-124` 默认排除，`.gitignore:111-138` 下也有已跟踪旧档案，不能用 ignore 规则作为删除依据。远端/维护工具未接入验证，具体历史保留政策 [需核验]。

#### H04｜根目录两个 HTML 演示｜确认成立，保留

`README.md:115-122` 明确提供两份独立离线演示，现有 HTML 有内嵌脚本和示例数据，静态检查未看到需要外部脚本或样式的载入。两个根级文件合计 238,579 字节，`.dockerignore:94-95` 已排除。`frontend/components/session_item_component/index.html` 属另一运行资源，通过组件 `frontend/components/session_item.py:10-11` 活跃使用。未打开浏览器、检查外部引用或核实比赛留档授权，均不足以删除。

#### H05｜两个存储/缓存和执行模式｜确认成立，保留

`storage/session_store.py:19-26`、`storage/cache.py:118-127` 和 `core/config.py:280-285,322-352` 证明 SQLite/Memory 支撑演示，PG/Redis 和独立 checkpoint 约束支撑生产；`core/execution_service.py:182-195` 与 `graph/checkpoint_manager.py:65-127,138-171` 明确保留两种执行模式和持久恢复。仅初始化过临时 SQLite，未读任何生产数据；PG/Redis、LangGraph 中断和重启恢复 [需核验]。保留双后端与切换/回滚测试。

#### P01｜两条迁移链｜确认成立，保留

静态追踪 `alembic/versions/*.py` 的 14 个 revision 和 `down_revision`，是连续的 V001→V014 链。`core/migrations/__init__.py:10-36` 独立注册四步历史 JSON 迁移，`core/migrations/registry.py:33-65` 在副本上运行而不修改调用者输入。三份自带 `0.6.0-alpha.8` JSON 直接迁为 `0.10.0`，各有四条历史，13 个无夹具迁移测试函数独立执行通过。`storage/backends/postgres.py:302-324` 和 CI `:173-186,208-211` 分别验证入口与设计路径，实际 PG upgrade/downgrade、备份恢复本次未运行。`storage/README.md:42-65` 资料表明旧库有基线补列和租户回填要求，不能以“已升级”推断所有实例一致。保留历史迁移并修正文档/测试注释的链头描述。

#### P02｜动态场景与 Mock 资源｜确认成立，保留

`scenarios/registry.py:25-31,61-90` 明确枚举 JSON、校验样例存在，再按字符串加载 profile 和 fixture。`core/llm/adapters/mock.py:16-50` 的四阶段函数名动态决定，`api/routers/session.py:60-79` 对 UI 暴露。独立实际跑出 4 个场景、4 份非空 Markdown 和 16 个 Mock 产生并通过真实 parser 的样例结果，另外两条现有注册测试直接通过。未跑整套会话、前端或普通 wheel。保留 `examples`、manifests、领域 profile 和内部 fixture。

#### P03｜实际门禁和安全回归｜确认成立，保留

`core/gates/rules/__init__.py:28-46` 与 `core/gates/rules/manifest.py` 的 14 个规则 ID 已直接比对一致。`core/gates/engine.py:191-208,275-319` 保留规则/数据错误的决策区别，`core/stage_readiness_service.py:819-845,923-938` 将严格落表故障变成稳定阻断，`tests/test_high_risk_fail_closed.py:232-248` 和 `tests/test_workflow_state_fail_closed.py` 固化失败语义。V02 只涉及未被调用的旧私有函数。实际故障注入全套、业务流报表与 PG 持久化未执行；继续保留现有防御性回归。

#### P04｜认证、租户、加密与发布门禁｜确认成立，保留

`auth/jwt.py:18-26,55-69,73-85` 固定算法、检查类型和租户上下文；JWT 人机身份与服务令牌分开，`api/routers/release_gate.py:57-98` 明确不缓存、错误必返回阻断，`core/release_gate_service.py:115-209` 与现有审计测试覆盖。`core/config.py:280-320` 生产配置拒绝 mock/SQLite 等降级并校验字段加密，`storage/field_security.py` 实现持久化边界。前端旧数据占位展示 `frontend/labels.py:268` 与 `tests/test_frontend_execution_source.py:105` 仍有用途。保留 `test_auth_request_role_revalidation.py`、`test_tenant_fail_closed.py`、`test_field_encryption.py`、`test_evidence_verification_identity.py` 和 `test_release_gate.py`。未执行这些完整认证/生产测试，没有当前漏洞暴露结论。

#### P05｜生产部署与可观测性｜确认成立，保留

`docker-compose.yml:65-181` 挂载 TLS、Prometheus、Grafana 配置，`nginx/conf.d/app.conf:12-31` 的 HTTPS 前端/API 路由由完整栈使用。`monitoring/prometheus.yml:5-12` 明确抓取 `api:8000/metrics`、加载告警；`api/main.py:180-187` 是运行端点，`api/metrics.py:250-279` 每次采集读共享存储。已解析监控 YAML 并确认挂载引用，未验证网关、告警或 scrape 是否真正工作。Lite 与 Full 有不同用途，生产资产保留。

#### P06｜现有测试与 fixtures｜确认成立，保留

`tests/conftest.py`、三份 JSON fixture、`tests/test_context_migrations_v070.py`、`tests/test_migration_upgrade_path.py:17-26,108-119` 与 CI `:58-61,192-211` 显示同类测试跨环境覆盖旧数据、回滚、写入与失败语义。实验只直接跑 24 个无夹具函数，其余 pytest 不会被这些数据替代。稳定基线后先查输入、断言、环境和跳过语义再考虑合并；未发现足以据此删除的测试集合。

### 主要分歧、遗漏和最后取舍

| 项 | Terra 依据 | Sol 交叉证据 | 风险差异与最终建议 |
| --- | --- | --- | --- |
| C02 / 新发现 N01 | `README.md:14,145` 和旧验收报告的版本文字落后 | `docs/acceptance_report.md:12,66` 同日成绩冲突，`AGENTS.md:15` 支持 `1256/8` 作为历史记录；`docs/startup.md:76,241` 和 `docs/local_setup.md:83` 同样未区分现行和历史；V014 链已静态核实 | 一律标为有日期的证据，删除冲突的重复数字，保留历史原始统计。修正当前启动链头。低风险、P0 |
| V01 | 源码与 lock 根版本不符，现有脚本漏查 | 三组依赖名/约束/extra 同步；隔离实测冻结树仍旧，合成根项目实测 `--check` 不通过；CI 的常规 `uv run` 可能先改工作区 lock | 错位确定，运行故障未证。检查应置于安装前。合法源上重锁，出现第三方变更先核查，P0 |
| V02/V03 | 五个私有历史收集器无调用，第六个服务摘要 | AST、动态规则注册和旧夹具确认区别。V03 的 `stage_readiness_service.py:994-1042` 保留直接结果，关闭指定规则的合成局部对照显示摘要仍阻止导出状态。引擎有写记录及严格失败路径 | V02 仓外核验和回归后删除。V03 保持纯结果/有副作用路径边界，不以引擎结果直接替换摘要。P1/P3 |
| V04 | 结构化输入转发 `max_retries` | `core/llm/adapters/openai_compatible.py:9-25` 仍占位；已生效的真实路径从 `core/context_manager.py:63-73` 传给 `ChatOpenAI` | 避免把两套语义合并到清理提交。候选仅是独立孤立模块，P2 |
| V06–V08 | 无仓内调用，删除可能减少传递依赖；列三处直接依赖 | 从 `5ecffaf` 验到直接 bcrypt；独立锁追到 Passlib -1、LangChain -1、Community -15，CLI 也直接用 requests、有两测试直接用 PyYAML | 先做可逆的小改动和冻结安装；修正角色分组，保留历史哈希和 CLI。具体外部消费者 [需核验]，P1 |
| V09/V10 | API 复制/装载前端，Lite 三项高概率冗余 | 当前 API 跟踪源码量 234,410 字节，锁模拟拆 UI 根 -22。`.dockerignore:91` 使 `scripts` 实际只靠 Lite bind 进入。`.dockerignore:105` 禁入镜像，而 Compose 短语法仍创建本地 config 目录 | 镜像、开发挂载和手工运维三项分别量化。保留脚本直到确认，独立评估 frontend/config，P1/P2 |
| V11/V12 | 普通 wheel 和外部符号风险待确认 | Hatch 选择清单也遗漏 PG 根迁移配置与源码，`RUNTIME_VALIDATION` 仍有 `.upgrade` 历史引用，`required_node_ids_for_tier` 是明确兼容别名 | 保留现有发布边界；按产品需求另测普通安装，外部未明的符号继续保留，P3 |

**N01｜新发现的问题，P0。** 启动指南将 V013 作为当前链头，验收指南的持久化链接又将 1.8.0 快照描述为当前。属于 C02 的最小联动，证据见上表。`tests/test_migration_upgrade_path.py:5` 写死旧头的注释也可用动态 head 描述修正，测试实际通过 `_head()` 读取头（`:46-47`）。

**N02｜新发现的问题，P2 [需核验]。** `docker-compose.override.yml:13-20` 的开发前端 bind 整棵 `.:/app`。这会带入构建排除的本地文件，而 `tests/test_frontend_image_isolation.py:16,31-63` 仅验证显式 Full 与 Lite 文件和镜像，未验证默认合并入口。`frontend/models/config.py` 使用 dotenv，本地主题 `.streamlit/config.toml` 也通过工作目录约定读取；`tests/test_frontend_theme.py:10,18-30` 验证根配置必须保留，独立镜像依 `tests/test_frontend_image_isolation.py:59` 排除整个根目录 `.streamlit/`。建议标明开发边界和验证有效挂载。如确定默认开发行为可兼容，只绑定前端所需源码/非敏感主题并保留热重载。未实际导入宿主 `.env`、读取任何真实值或模拟越界。官方依据见 [Docker Compose 文件合并](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/) 和 [Streamlit 配置路径](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)。

**N03｜新发现的问题，P3 [需核验]。** `.github/workflows/scorecard.yml:22-44` 对同一仓库执行两次 Scorecard，一次 JSON 并上传，一次可读输出且忽略失败。可以测量是否仅从原 JSON 生成可读摘要即可满足维护者需要，保留 JSON artifact、保留天数、权限与首轮失败语义。没有连接远端或运行扫描，CI 时间/API 用量收益未测。官方依据见 [OpenSSF Scorecard 输出格式](https://github.com/ossf/scorecard#formatting-results)。

**N04｜新发现的问题，P3。** `core/coverage/policy.py:193-202,212-214` 为 `missing_required_node_ids` 和 `min_cases_gaps` 用同一谓词生成两份同值且独立的列表。若后续整理 V03，可以复用计算并保留两个响应字段以及各自的列表对象。属于微小局部整理，未发现值得独立变更的运行收益，需保留覆盖与 API 两个字段契约。

**N05｜新发现的问题，P2 [需核验]。** 可安全地进一步测量门禁记录写入量。`core/stage_readiness_service.py:862-882,923-927,994-1007` 在一次构建 readiness 中可能先评价 Stage 3，再通过 Stage 4 规则或最终摘要重评。`core/gates/rules/stage4_final_governance.py:24-26` 重新评上游；`core/gates/engine.py:256-257,292-313` 会对非空会话走记录路径，`storage/backends/sqlite_store.py:2730-2764` 每次生成独立记录，`:2766-2782` 的趋势读取会消费行。该静态路径提示潜在写入/统计成本，当前并未在完整流程测量次数。不要在 V02/V03 顺带删除记录或以缓存改变严格失败、趋势、审计语义。用本地 SQLite/PG 和普通合成会话先测次数，再与维护者确认记录的定义和趋势口径。

**未立项的假设。** `requirements-audit.txt` 已由 `.gitignore:88` 和 `.dockerignore:101` 排除，未发现跟踪或进入镜像的问题。`python-multipart` 用于登录表单，双后端、旧迁移和监控均有运行引用。Makefile 供应链注释所列外部公告是其他时间和环境的记录，未做本次 SCA；未证实需要升级或替换其它依赖。两份 HTML 及 `.upgrade` 可解释仓库体积，但不构成运行镜像清理收益。

本阶段只确认清理候选和后续验收顺序。第三阶段可依据 P0–P3 继续整理方案。任何项目文件修改、重锁、删除、远端 CI 操作及生产验证均未发生。

## 附录 C　第二次 Terra 的分批实施方案

**裁决（2026-11-13，America/Los_Angeles）**：基于 `af16495`，优先修复确定的锁元数据漂移与少量失效配置、文档；先取得合法完整依赖源和隔离环境，再动依赖、门禁死代码与镜像。P0 的问题确定不等于重锁已被验证。整体仍是实施计划，仓库未修改，本文路径和行号以该提交为准。

**删除边界**：当前可安全删除的是 C01 的失效配置条目及历史文档中重复冲突的数字，不是整个文件；暂无可立即安全删除的整个项目文件。V02 的五个函数、V04 的整个模块、V05 的两个函数和 V06/V07 的依赖声明均须先核验。V03、V11、V12、H01–H05、P01–P06 目前保留。

**优先级**：P0＝C01–C03、N01 和 V01；P1＝V02、V06–V09；P2＝V04、V05、V10、N02、N05；P3＝V03、V11、V12、N03、N04。P0 的文档/配置可独立先做；V01 的受控重锁与检查可在单独分支前置，无法完成时不宣称锁已修复。

**基线与收益口径**：607 个 Git 跟踪文件、5,562,697 字节、445 个 Python 文件、169 个 `tests/test_*.py`；不是镜像大小或测试通过数。V02 仅在核验后减少五个函数共 229 行。`frontend/` 38 个跟踪文件共 234,410 字节，但不等同镜像层节省。

**锁图静态估算**：Linux/Python 3.11 下，单独移除 V06 的 Passlib 少 1 个包，V07 的 LangChain 少 1 个、Community 少 15 个；单独拆出 V09 的三个 UI 根少 22 个；六项合并由 121 至 80，少 41 个，不能把独立数值直接相加。依据现锁 markers/extras、未重新求解；实际安装包、镜像大小、构建时间、性能和安全收益均须实测。

**证据边界**：前两阶段做了静态分析、24 个无需 pytest fixture 的测试函数直接调用、4 场景的 16 个 Mock 样例解析、3 份历史上下文夹具迁移及局部合成对照；没有完整 pytest、锁定安装、普通 wheel、Docker、PostgreSQL/Redis 或远端 CI 通过证据。缺包的离线失败不能证明依赖冲突或产品失败。

**执行总原则**：各项在隔离工作树/副本及合成数据中按下列小批次独立提交；保留锁文件和镜像基线、命令退出码与版本、产物与通过/跳过数。只用允许的源或完整缓存，不连接外部账户、真实数据库或真实目标，不绕过网络限制，不进行攻击或漏洞复现。

**共通验收/回滚**：每批先做特定对照，再跑受影响测试、`make lint`、版本/文档检查；具备环境后再跑相应 CI 作业，未跑则明确列出。任一必要验证失败或消费者无法核清，停止该项、保留原实现；回滚该项提交及成对的锁/镜像改动，复跑同一对照。避免在原工作树运行会删除本地数据库的 `make clean` 或会覆盖 `.env` 的 demo 目标。

### 批次 A：P0 确定性文档与配置

**C01｜删除失效配置条目**：`pyproject.toml:105-115` 豁免不存在的 `frontend/api_client.py`，现用 `frontend/models/api_client.py`；删该条目及专属注释，不转移豁免。
- 风险/收益：未来重建旧路径时 lint 生效；当前减少误导。验收：`make lint` 中 Ruff 检查及格式检查；异常时只恢复该条目，不放宽新文件规则。

**C02｜修正当前/历史版本表述**：`README.md:14,145`、`docs/README.md:10`、`docs/acceptance_report.md:1-12,64-66` 混用旧快照与当前版本；当前代码为 1.11.0，不称其已有发布 tag。
- 保留 2026-11-09 正文 `1256 passed, 8 skipped` 作为历史成绩及环境，移除页脚重复冲突的 `1253/8`；README 的 2026-11-01 `1131/4` 同样标注历史，不改写原始成绩或宣称本次通过。
- 风险/收益：区分应用版本、报告 schema 和历史证据，避免误报；验收 `python scripts/doc_consistency_check.py`、`python scripts/version_check.py` 并人工核对日期、数字及链接；回滚仅还原相应文案。

**C03｜修正脚本 CI 说明**：`scripts/README.md:37-50` 与 `.github/workflows/ci.yml:227-242` 不符；说明 Bash 证书/密钥脚本既用于本地 setup 也用于 CI 临时全栈，PowerShell 仍为手动入口。
- 保留所有脚本；风险低，收益是入口准确。验收对照工作流及 `doc_consistency_check.py`；错误时还原说明，不执行证书生成。

**N01｜修正迁移链与历史链接**：`docs/startup.md:76,241`、`docs/local_setup.md:83` 仍写 V013/旧快照，静态核实链头是 V014；`tests/test_migration_upgrade_path.py:5,46-47` 可把过时注释改为动态 head 描述。
- 不改迁移链/测试逻辑，保留旧验收材料并标明日期；收益是启动指引准确。验收检查 revision 链、文档脚本与相关迁移测试；回滚相应文字。

### 批次 B：P0 可复现锁与安装前检查

**V01｜锁根版本漂移，确定但修复待环境验证**：`uv.lock:19-22` 是 1.9.0，`pyproject.toml:3-7`、`core/version.py:3-4` 是 1.11.0；`scripts/version_check.py:28-48` 未检查锁，CI 的冻结同步未验证新鲜度。
- 在可用合法源/完整缓存的隔离分支，用团队及镜像使用的 uv 版本重锁；不手工编辑锁，不默认升级第三方。审查根元数据及所有第三方版本、来源、markers、extras、文件 hashes 的 diff；无关变更先查明，无法解释则暂不合入。
- 在 Python 3.11 下以标准库解析 TOML，检查规范化项目名及 `source.editable = "."` 的唯一根包版本与项目版本；缺失、重复或不一致均失败。将检查放入 `.github/workflows/ci.yml` 中 Python 安装后、任何同步和普通 `uv run` 前；保留现有 schema 检查。
- 验收：使用合成一致/不一致/缺失/重复根条目证明检查正反例；在完整源上运行 `uv lock --check` 或等效 `--locked` 检查，再做 `uv sync --all-extras --frozen`、版本/文档检查并保存依赖 diff；同时核对 CI Python 3.11、镜像 uv 0.11.12 的实际表现。
- 风险/收益：求解可能变动无关依赖，检查过晚可能被 `uv run` 隐式更新掩盖；受控执行可让提交锁与源码一致。回滚锁及检查提交；保留已知漂移待补环境，不声称已修复。

### 批次 C：P1 门禁小范围整理

**V02｜五个旧私有收集器 [需核验]**：`core/stage_readiness_service.py:174-189,192-243,465-551,554-585,588-629` 仅见定义，现行入口 `:768-776` 委托已注册规则；范围严格限这五个函数、229 行。
- 先查外部导入、动态反射、插件及 monkeypatch；无法排除则保留。确认后独立删除五个函数，保留 `_blocker`、`_find_pending_action_id`、`_with_action_history`、14 条注册规则、V03 第六收集器和现有测试。
- 验收相同合成输入前后对照 `StageGateResult`、阻断 ID、`rule_id`、`required_resolution`、消息、错误转换及持久化行；运行 gate engine/plugin/report、high-risk fail-closed、workflow-state fail-closed、evaluation-record 等既有测试。
- 风险/收益：外部私有调用及安全失败语义可能受影响；收益是减少重复实现与 229 行维护。任一差异/调用未解释即恢复整项，不在此提交修改审计或趋势。

**V03｜Stage 3 两条路径，P3 保留**：`core/stage_readiness_service.py:632-765,994-1042` 的摘要仍直接消费收集结果，`core/gates/rules/stage3_eval_failure.py:35-178` 经引擎应用配置与记录。
- 已验证禁用该规则时，引擎该规则阻断为空，但摘要仍列缺口且 `report_export_allowed=false`；不得以引擎结果直接替换摘要，亦不推断 HTTP 导出实际拒绝。
- 若后续确需合并，仅单独抽无副作用的纯计算，保持字段、时序、禁用配置下的摘要、fail-closed 和记录行为；验收覆盖缺口、失败、人工处理、报告及 SQLite/PG。收益仅减少漂移；行为不符即回滚，当前不安排删除。

### 批次 D：P1 依赖契约与镜像，先基线后逐项变更

**V08｜先梳理直接依赖 [需核验]**：`api/metrics.py:18-28` 直接用 `prometheus_client`，`stages/base.py:8` 等直接用 `langchain_core`；`frontend/models/api_client.py:7` 与 `scripts/live_e2e_four_stage.py:46` 均用 requests，前端组已声明；部分测试直接用 PyYAML。
- 为实际使用的运行/开发组明确声明 `prometheus-client`、`langchain-core` 和必要的测试 PyYAML，保留 frontend 的 requests，并确保手工脚本入口仍能获得 requests；不要只为 UI 把 requests 强塞后端专用环境。以现锁兼容约束为起点审查重锁，`python-multipart` 为登录表单间接所需，保留。
- 验收分别从干净环境安装 backend、frontend、完整开发组和手工脚本所需环境，导入实际模块、检查 `/metrics`、前端认证、脚本 `--help`（不运行外部 E2E）；风险是约束变化影响求解，收益是减少偶然传递依赖，失败则恢复声明和锁。

**V06｜Passlib 依赖 [需核验]**：`pyproject.toml:40-41` 同时声明 `passlib[bcrypt]` 与 bcrypt；`auth/password.py:2-12` 直接用 bcrypt，当前仓内未见 Passlib 导入。
- 核查仓外部署脚本/消费者和历史密码格式后，仅删除 Passlib 声明，保留 bcrypt 及当前代码、版本/哈希；依次比较独立锁 diff 与干净安装。
- 用合成、合法的历史 bcrypt 样本测试验密，覆盖注册、邀请、登录、重启，以及 SQLite/PG；不读真实密码或数据。风险是外部隐式依赖/非 bcrypt 旧格式，收益是静态闭包少 1 包；失败恢复声明与锁。

**V07｜Community 与 LangChain 分开处理 [需核验]**：`pyproject.toml:21-24` 声明两者但仓内未见导入；`core/context_manager.py:6` 等实际用 `langchain-openai`，多个模块直接用 Core，`tools/search.py:7` 用 Tavily。
- V08 完成后先单独评估并删除 `langchain-community` 声明，再单独评估 `langchain`；逐项核查外部插件、锁 diff 和兼容性。保留并明确 Core、OpenAI、LangGraph、Tavily 与精确固定的 checkpoint-postgres，不调整现锁版本为默认目标。
- 验收干净冻结安装、两种执行模式、Mock 四阶段、解析、恢复、provider 本地替身和相关现有测试；不对真实 provider 发请求。风险是动态扩展或传递兼容变化，静态闭包分别少 15/1 包；差异未解释时回滚单项及锁。

**V09｜API 镜像依赖与源码分别优化 [需核验]**：`Dockerfile:12-26` 安装主组并复制上下文，前端镜像 `Dockerfile.frontend:18-31` 单独使用 frontend group；主组 UI 包是为本地 `uv sync`、`make demo-ui` 和 AppTest 保留。
- 首先测原始双镜像构建时间、`.Size`、层与包表；以经过验证的依赖分组/等效方案分离 API 的 Streamlit、Altair、Pandas，同时保留原本本地默认开发入口或提供明确等效迁移。单独提交 API COPY 白名单，不全局在共用 `.dockerignore` 排除 frontend。
- 保留 API 的 `alembic.ini`、`alembic/`、后端包、场景 manifests 和 `examples/`，保留前端组件 HTML；保持现有 `EXPOSE 8501` 直至评估外部 `-P` 使用。镜像源码与依赖改动分别比较，可独立回滚。
- 验收无挂载 API health、4 场景、`/metrics`、前端登录/UI、Lite、显式 Full、默认 dev、PG 首次启动/迁移及热重载；对照两个镜像大小、层和真实包表，运行相关 AppTest。风险是丢运行资源、开发入口或迁移；收益以实测为准。

### 批次 E：P2 挂载、孤立函数与观测

**V04｜孤立 retry 模块 [需核验]**：`core/llm/retry.py:6-26` 仅见定义，现行 `core/context_manager.py:63-73` 将配置传给 `ChatOpenAI`，结构化 OpenAI adapter 仍是占位实现。
- 先核对外部 import、旧插件和发布消费者；确认不用后才可单独删除整个 `retry.py`，否则保留。运行结构化输出和 LLM reliability 测试，用本地替身对比真实客户端配置；风险是外部接口，收益少量维护，失败恢复模块；不改实际重试语义。

**V05｜两个前端包装函数 [需核验]**：`frontend/labels.py:313-315` 的 `friendly_error`、`frontend/models/api_client.py:295-296` 的 `create_session_id_only` 仅见定义。
- 先查扩展/字符串访问和测试替身，再分别删除；保留 `create_session`、缓存失效和 `_perform` 请求层。风险为外部导入及 UI 回归，收益仅数行，未核清即保留。
- 运行 frontend MVC、API errors、session list、auth recovery 和 UI smoke；比较 401 刷新成功/拒绝/暂时失败、允许 404、204、4xx 结构化错误、超时/连接失败与无效 JSON，保持 session/租户缓存隔离；异常分别恢复函数。

**V10｜Lite API 的三个挂载分别评估 [需核验]**：`docker-compose.lite.yml:16-25,40-42`，API 挂载 `frontend`、`config`、`scripts`；UI 服务还有自己的 frontend 挂载。
- 先验证 API 的 frontend 是否可移除；config 先核查用户自有挂载、环境/secrets 与短语法自动建目录行为；scripts 被 `.dockerignore:91` 排除，取消挂载会撤掉容器内手工 CLI，确认实际运维前保留。保留 UI 挂载、`data` 和后端开发挂载。
- 在干净与含合成配置的隔离目录分别执行 `docker compose -f docker-compose.lite.yml config`、Mock 场景、热重载与手工脚本入口验收；风险是配置或运维失效，收益是缩小绑定面而非镜像变小。逐项恢复挂载即可回滚。

**N02｜默认开发 Compose 整树挂载 [需核验]**：`docker-compose.override.yml:13-20` 的 `.:/app` 可带入宿主文件；这与 V10 的 Lite API 挂载是不同入口，`frontend/models/config.py` 使用 dotenv，主题由 `.streamlit/config.toml` 提供。
- 先在合成文件的隔离工作区检查 `docker compose config` 的合并结果和有效可见文件，不读取真实 `.env`；如兼容，再单独收窄至前端必需源码与非敏感主题并保留热重载。
- 验收默认 dev、显式 Full、Lite、主题、前端认证和镜像隔离测试；风险是配置、主题或热重载改变，收益是缩小数据暴露边界；失败还原 override，不误删或屏蔽 CLI。

**N05｜先测门禁记录，再定义趋势 [需核验]**：`core/stage_readiness_service.py:862-882,923-927,994-1007`、`core/gates/engine.py:256-257,292-313` 存在一次 readiness 内重复评价及写记录的可能；`storage/backends/sqlite_store.py:2730-2782` 的趋势读取消费记录行。
- 在本地隔离 SQLite/PG 用普通合成会话测每次 readiness/Stage 4 的评价次数、写入数和趋势结果，覆盖写入失败与严格风险阻断；不读生产数据。与维护者先明确一次评价、审计事件和趋势分母的定义，再评估是否需要单独变更。
- 收益是取得真实成本/口径，风险是缓存或删记录改变审计、趋势和 fail-closed；V02/V03 不顺带调整。若另行修改，前后对照事件数、顺序、失败语义及 SQLite/PG，差异不符合约定则恢复原逻辑。

### 批次 F：P3 后置与明确保留

**V11｜普通 wheel [需核验]**：`pyproject.toml:77-83` 只声明 8 个包，`scenarios/registry.py:25-31,74-90` 要求示例，`storage/backends/postgres.py:302-324` 依赖根 Alembic 配置；本次缺 Hatchling，普通 wheel 内容与安装行为均未验证。
- 当前保留 editable/源码部署边界；仅在产品要求独立 wheel 时，先构建检查 `RECORD`，在仓外非 editable 环境验证四场景/示例及约定的 CLI/PG 迁移，再决定包资源和路径方案。风险是改变发布兼容面，收益是明确可分发范围；失败恢复包配置，不为瘦身强推 src-layout。

**V12｜四个公开符号，保留 [需核验]**：`core/models.py:42-48,86-91` 的 `ReviewAction`/`AuditActor`、`core/version.py:7` 的 `RUNTIME_VALIDATION`、`core/coverage/policy.py:94-96` 的兼容别名可能被外部导入或历史引用。
- 外部消费者和旧序列化未核清，不删不改；如未来弃用，先列消费方/兼容期并跑模型、覆盖和历史格式测试。收益很小，避免破坏公开契约；回滚为恢复符号及兼容导出。

**N03｜Scorecard 重复运行 [需核验]**：`.github/workflows/scorecard.yml:22-44` 一次生成 JSON、一次生成可读输出且忽略失败。仅当比较证明 JSON 可生成所需摘要时再合并，保留 artifact、留存期、权限和首轮失败语义。
- 风险是可读信息/失败语义变化，CI 时间与 API 节省未测；在合适的隔离 CI 中逐项对照，异常恢复两个步骤；当前不触发远端扫描。

**N04｜覆盖缺口列表重复计算**：`core/coverage/policy.py:193-202,212-214` 的 `missing_required_node_ids` 与 `min_cases_gaps` 同值；收益极小，不必独立立项。
- 若将来与 V03 的纯计算整理一并做，只复用计算并保留两个字段、顺序以及互不共享的列表对象；运行覆盖与 API 合约测试，差异即回滚。

**H01–H05 与 P01–P06｜明确保留**：兼容门面与 patch 点、维护/历史脚本、`.upgrade/`、两个离线演示、双存储/缓存/执行模式；两条迁移链、动态场景/示例/Mock、14 条门禁及 fail-closed 测试、认证/租户/加密、生产部署/监控、全部有效测试和历史 fixtures。
- 代表证据：`core/session_service.py:2-6,100-107`、`core/migrations/__init__.py:10-36`、`scenarios/registry.py:61-90`、`core/gates/rules/__init__.py:28-46`、`core/config.py:280-352`；`secrets.example/` 的 8 个跟踪模板也供 setup 使用。删除会损害兼容、数据恢复、边界或运维；收益无实证，保持现状与对应回归。

### 验收矩阵、工时与决策点

- **开发/HTTP**：隔离环境核对 `uv sync`、`make dev-api`、`make dev-frontend`、`make demo-ui` 的等效入口；仅使用合成 `.env`，测试认证刷新与错误分类、会话缓存和租户隔离。
- **CI/数据**：依次运行静态检查、完整 pytest/覆盖、Lite Docker、PG/Redis 迁移与生产安全、显式 Full 和默认 override；在一次性数据库验证 V008→V014→回滚→head、旧上下文夹具和备份恢复，不修改生产数据。记录失败、跳过和环境差异；远端执行须遵守现有权限及授权。
- **依赖裁决**：删除候选仅 Passlib、LangChain、Community 三个直接声明，均需上述核验；前端依赖可从 API 安装路径移动到 UI/开发入口，测试所需 PyYAML 可归入开发组。替换与升级：暂无证据支持任何立即替换或升级；保留 bcrypt、Core/OpenAI、LangGraph、Tavily、checkpoint-postgres、python-multipart 等实际依赖。
- **工时粗估，非承诺**：A 约 1–2 人时；B 约 3–6 人时，受制于合法依赖源；C 约 3–6 人时；D 约 8–20 人时；E 约 6–14 人时；F 按产品需求另估。未计排队、环境构建、外部消费者核验与生产迁移演练；镜像/运行性能只以实测前后对照计。
- **完成条件**：每批独立 diff、对照/测试记录和明确回滚点齐全；受环境或外部消费者阻挡的项维持 [需核验]，不把直接函数调用或历史报告记作全套通过。可先合入独立通过的低风险批次，其余等待各自前置条件。
