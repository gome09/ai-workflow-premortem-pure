# 前后端连接、架构解耦与业务闭环专项审查及实施方案

审查对象：工作区项目 ai-workflow-premortem-pure；代码位置以项目根目录为基准。审查基线提交：290846eaee368d2118483c8f8a9e8708ad136337；审查日期：2026-11-13。本文只提出改造与验收方案；审查期间未修改业务代码或业务数据。

## 1. 审查概览

### 1.1 执行过程与边界

按任务要求，协调者依次安排 GPT-6.1 Terra Max 完成第一阶段代码审查，GPT-6.1 Sol Max 独立核验并补充，GPT-6.1 Terra Max 复核分歧并制定实施方案。第二阶段获得了第一阶段完整原始结果，直接检查对应代码和已有测试；第三阶段获得完整核验结果并重新读取关键修改位置。第一阶段原始结论见第 3 节，Sol 逐项结论及等级分歧见第 4 节，最终清单见第 5 节。

本轮只做代码、配置、已有测试的只读检查及 Sol 的内存替身组合验证。未启动应用或真实 API，未连接或修改真实业务库，未执行 pytest、端到端测试或会写业务数据的测试，未安装依赖、修改运行环境或部署。起始和最终项目 git status --short 均为空，git diff --check 无输出；这不等于业务测试通过。项目目录内 .venv/bin/python 不存在，未据此运行项目解释器测试。

**确认问题共 14 项：P0 1 项、P1 8 项、P2 5 项、P3 0 项。** FE-T14 是有明确条件的潜在风险；FE-T15 证据不足，均不计入确认数量。优先级使用本次任务附件定义。

### 1.2 技术栈、边界与运行环境

- Python 3.11+；前端为 Streamlit，后端为 FastAPI、Pydantic；工作流使用 LangGraph 和项目的确定性状态/门禁逻辑；数据层支持 SQLite 与进程内缓存，或 PostgreSQL 与 Redis。主要依赖见 pyproject.toml:15-75。
- 前端 frontend/app.py 装配认证及两个 st.navigation 页面；frontend/models 包含配置、认证、HTTP 客户端、状态和阶段结果适配，controllers 负责编排，views/components 负责展示。前端请求由 Streamlit 服务端的 requests 发出。
- 后端 api/main.py 注册中间件、全局异常处理和 api/routers；auth 包提供 JWT、角色和服务令牌；core/session_service.py:36-60 为兼容入口，委派 core/services 下的 workflow、governance、evidence、evaluation 和 audit 域服务；core、graph、stages 与 storage 分别承担规则/执行/阶段/持久化职责。
- 本地 frontend/models/config.py:6-16 默认 API_BASE 为 http://127.0.0.1:8000；完整容器 frontend 经 docker-compose.yml:103-115 使用 http://api:8000。Nginx 的 nginx/conf.d/app.conf:21-37 将 /api/ 转发 API、其余路径和 WebSocket 转发 Streamlit；api/main.py:295-301 从配置读取 CORS。因为请求是 Streamlit 服务端发起，不按浏览器 SPA 假定内部 API_BASE 错误。
- .env.demo 使用 mock、SQLite、memory checkpoint 和演示认证；.env.example 面向真实模型、PostgreSQL，具体环境应以部署配置为准。Dockerfile.frontend:18-31 构建只含前端源码及前端依赖的独立镜像。uv.lock:3618-3619 锁定 Streamlit 1.57.0。
- access/refresh JWT 经过后端角色和租户上下文验证；机器发布门禁使用单独服务令牌。可移动部署、生产代理连通、跨进程竞态、真实模型/目标和 PostgreSQL/Redis 场景本轮没有运行验证。

核心链为：用户操作 → Streamlit view/controller → models 状态与 HTTP → FastAPI 路由/认证 → session_service 域服务 → 工作流/门禁与存储 → 响应 → 前端状态和反馈。证据、人工动作、风险处置、实验、报告和审批之间既有数据依赖，也有独立门禁。

## 2. 前后端连接与业务流程分析

| 用户操作与前端 | 实际 HTTP 与后端入口 | 核心处理、响应及闭环结论 |
|---|---|---|
| 注册、登录与刷新：frontend/controllers/auth_controller.py、frontend/models/auth.py | POST /auth/register JSON；POST /auth/login 表单；POST /auth/refresh JSON；auth/router.py:75-92 | auth/service.py:92-116 刷新时重读用户角色；JWT 失效恢复有 FE-T08 |
| 创建、列出、重命名、删除会话：session_controller.py、sidebar.py | POST/GET /sessions/，GET/DELETE /sessions/{id}，PATCH /sessions/{id}/name；api/routers/session.py:40-57,82-111,129-147,258-273 | 服务写存储并失效对应前端缓存；列表分页和切换失败见 FE-T02、T03 |
| 对话与材料：workbench.py → session_controller.py | POST /chat/{id}；POST /sessions/{id}/materials；api/routers/chat.py:22-60、session.py:308-325 | core/services/session_workflow.py:283-351,370-413 驱动执行并持久化；请求失败时对话展示见 FE-T10 |
| 阶段及人工动作：gate_panel.py、governance_panels.py → api_client.py | GET /sessions/{id}/stage-readiness、/stage-resolution、/actions；POST /actions/{action_id}/resolve | api/routers/stage.py:37-47、oversight.py:76-115；动作结果可为 403/409/422；读取失败假空态见 FE-T09 |
| 证据核验：单条面板 → governance_controller.py → api_client.py | POST /sessions/{id}/evidence/{evidence_id}/verify；api/routers/evidence.py:44-60 | EvidenceService 先改单证据再协调关联动作并存储；作用范围与审计身份见 FE-T01、T11 |
| 评测用例、数据集、实验 | /eval-cases、/eval-datasets、/eval-experiments 及实验 /run、/status；api/routers/eval.py、eval_datasets.py、eval_experiments.py | EvaluationService 管理运行和存储；后台 target_http 可返回 202 并查询 status；恢复、轮询、校准见 FE-T04–T06，模式显示见 FE-S01 |
| 风险处置、目标部署与上线决定 | /risk-treatments、/target-deployment、/approval-status、/approvals/release；api/routers/risk_treatments.py、session.py:328-349、approvals.py | 后端使用当前身份和评估结果执行权限、独立复核及前置条件；前端显示阻断与结果，不能仅依赖前端禁用按钮 |
| 报告生成与查看 | POST/GET /sessions/{id}/reports，GET /reports/{report_id}，GET /export；api/routers/reports.py、session.py:379-393 | 报告快照与上线批准分离；列表排序截取问题见 FE-T07 |
| 机器发布门禁 | GET /release-gate/{id}，service token；api/routers/release_gate.py:57-95 | core/release_gate_service.py:115-192 要求批准有效且 readiness 通过；计算故障 fail-closed。不是普通 Streamlit JWT 入口 |

接口载荷的现状：消息使用 user_input/user_materials；单证据使用 evidence_id 路径和 note；人工动作使用 decision/note/payload_after；实验运行使用 dry_run_only、background、idempotency_key，可接受 timeout_seconds；校准使用 human_label/human_comment/disagreement_reason，reviewer_id 由后端 JWT 决定。域操作返回 StageOperationEnvelope，前端 frontend/models/stage_envelope.py 消费门禁字段。文件上传在前端读取 txt/md 文本后作为 materials JSON 提交，而不是向后端发 multipart。

## 3. Terra 原始审查结果

本节保留第一阶段原始编号、初始级别、代码依据、触发条件、影响边界及初始方向；这些不是最终裁决。第 4 节记录 Sol 对 FE-T01、T09、T13 的修正与分歧。

### FE-T01：单条证据核验会将同一人工动作中的其他证据一并标记为已核验

模块/类别：证据、人工监督、阶段与发布门禁；业务正确性、可信边界。状态及初始优先级：[已确认] P0。

前端及接口：frontend/views/panels/governance_panels.py:235-243 为每条证据显示单独的“核验证据”；frontend/controllers/governance_controller.py:135-139、frontend/models/api_client.py:418-424 提交 POST /sessions/{sid}/evidence/{evidence_id}/verify。

后端证据：api/routers/evidence.py:44-60 → core/services/evidence.py:43-56。core/governance/action_factory.py:165-185 将同一 high/critical 失败模式的多个未核验证据放入一个 unverified_sources 动作。core/governance/action_resolution.py:478-494 只要传入 ID 命中其中任意一项，即解决整个动作；core/governance/action_effects.py:88-114 随之把该动作中全部证据设为 verified=True。

触发与影响：一个高风险失败模式引用 E1、E2 且二者未核验时，用户仅点击 E1 的核验按钮，E2 也会被写为已核验。core/gates/rules/stage1_evidence_gap.py:100-101 和 core/approval_service.py:163-175 的对应证据阻断取决于 verified，故 E2 的对应证据阻断可能被错误解除。其他动作、测试、审批等门禁仍独立生效。

初步方向：单条核验只修改指定 ID；聚合动作在相关证据分别满足条件后再关闭。显式保留人工处理整个动作时的业务语义，不强制引入逐证据新模型；补充两证据核验及门禁回归。

### FE-T02：会话列表只请求第一页，本地“显示更多”和搜索无法触及旧会话

模块/类别：会话管理；分页契约、业务闭环。状态及初始优先级：[已确认] P1。

前端 frontend/models/api_client.py:274-276 固定 GET /sessions/，不传 limit、offset；frontend/views/sidebar.py:176-207,246-249 仅对已经收到的列表搜索和扩展显示数量。后端 api/routers/session.py:82-98 默认 limit=20、offset=0，最大 100；storage/backends/sqlite_store.py:1801 按更新时间倒序分页。

租户会话超过 20 个时，第 21 个及更早会话未到达前端，不能通过该界面搜索或选择；“显示更多”无法加载它们。初步方向：让 UI 真正请求后续页面，并明确搜索覆盖范围；全库搜索需相应服务端筛选或明确加载全部页面，缓存键需纳入分页/筛选条件。

### FE-T03：切换会话读取失败后，新会话 ID 与旧会话画面混在一起

模块/类别：会话工作台；失败恢复、状态一致性。状态及初始优先级：[已确认] P1。

frontend/controllers/session_controller.py:70-92 先设置新 session_id/current_state，之后 GET 新上下文；只有 ctx 非空才替换 messages、pending_flags/actions。frontend/views/workbench.py:19-36,113-119 根据当前消息渲染聊天并使用当前 ID 发送；再次点击同一会话会被 controller:71-72 提前返回。api/routers/session.py:101-111 按新 ID 返回会话或 404，api/routers/chat.py:22-36 按路径 ID 执行。

在 A 会话工作时切到 B，B 的 GET 因网络、权限、被删除等失败，页面仍显示 A 的消息，但当前 ID 已是 B；若 B 状态允许输入，用户可能在误以为仍是 A 的上下文中输入并向 B 发送。旧消息不会自动写入 B。初步方向：先成功读取再原子切换；失败保留 A 或清空并明确 B 未加载、禁用写入且可重试；同 ID 重试及手动刷新应重新拉取消息和状态。

### FE-T04：后台实验中断后缺少可用恢复入口，失败重试的幂等键也不匹配

模块/类别：评测实验；异步恢复、前后端契约。状态及初始优先级：[已确认] P1。

frontend/views/panels/eval_panels.py:250-284 仅为 created、failed 展示运行按钮，未覆盖 interrupted/cancelled；frontend/controllers/eval_controller.py:96-105 对每次真实运行生成含当前秒数的新键。api/routers/eval_experiments.py:85-128 接收键并提供状态；core/services/evaluation.py:513-551,649-674 返回 run_request_key/resumable，拒绝与已保存键不同的重试；core/eval_experiment_service.py:175-186,200-203 保持该契约。已有 tests/test_eval_batch_resilience.py:166-207 展示同键恢复预期。

真实批次超时为 failed 后再次勾选真实运行，通常生成不同键而被拒绝；worker 中断为 interrupted 时界面无恢复按钮。状态可能提示“再次运行会跳过已完成用例”，但实际 UI 无法可靠完成。失败后若改为不勾选真实执行，UI 发送空键和 dry_run_only=True；core/eval_experiment_service.py:227-243,257-278 可能跳过已保存真实结果，对剩余项按 dry-run 执行，形成混合批次。上线证据仍由后端真实执行校验阻断。

初步方向：重入时读取并复用服务端持久化键、展示可恢复状态及恢复入口；约束同一批次执行模式，避免把恢复和新实验混为一谈。

### FE-T05：实验 202 之后同步长轮询，状态读取失败或重新进入时缺乏可靠反馈

模块/类别：评测实验；异步交互与异常反馈。状态及初始优先级：[已确认] P1。

frontend/controllers/eval_controller.py:108-128 接受后最多循环 900 次、每次睡眠两秒；frontend/models/api_client.py:639-641 把 status GET 失败变为空字典，无法区分运行中与读取失败；api_get 单次超时 30 秒。最终无论 failed/interrupted/cancelled 均调用 st.success，随后立即 rerun，状态信息没有作为可重入状态保存。后端 api/routers/eval_experiments.py:106-107,114-128 返回 202 与 status；core/services/evaluation.py:492-551 在 status 查询时协调陈旧心跳并返回进度、错误码、可恢复性。

目标慢或状态服务反复超时时，该页面脚本长时间占用；仅按睡眠计算约 30 分钟，含网络等待可更久。退出、刷新或重进时，面板没有对 running 主动接回 status/陈旧心跳协调的入口；失败也被写作笼统成功。初步方向：分离提交与状态展示，重入时恢复查询；分别处理进行中、完成、失败、中断、状态不可用和等待超限，合理限频和重试。

### FE-T06：校准面板只显示最后 20 条目标运行，较大必测批次无法全部人工校准

模块/类别：真实目标评测、上线批准；数量截断。状态及初始优先级：[已确认] P1。

frontend/views/panels/eval_panels.py:112-125,142-161 过滤 target_http 后仅渲染 target_runs[-20:]，没有分页或按运行 ID 检索；frontend/models/api_client.py:461-469,742-759 已有列表和校准 API。api/routers/eval.py:189-208 为指定 run 接受校准并取 JWT user_id 作为 reviewer；core/release_evidence.py:97-132,240-267 要求相关必测运行有有效人工 passed 校准；core/approval_service.py:306-335 将其纳入批准条件。

同一真实批次超过 20 个必测运行，或更新的目标运行把当前批次必测项挤出最后 20 条时，用户无法从现有面板校准隐藏项，可能导致上线批准一直被正确阻断；API 本身仍可直接校准。初步方向：按实验/批次筛选并分页或检索全部相关运行，可定位 readiness 指出的阻断 run；保留后端逐项校准门禁。

### FE-T07：超过 20 份报告后，报告选择器反而隐藏最新快照

模块/类别：报告；排序、数量截断。状态及初始优先级：[已确认] P1。

frontend/views/panels/report_workspace.py:50-68 创建后读取列表，选择器使用 reversed(artifacts[-20:])。core/services/session_workflow.py:519-529 优先读取报告表；storage/backends/sqlite_store.py:1893-1899 和 storage/backends/postgres.py:1468-1475 均按 generated_at DESC 返回。

超过 20 份报告时，切片取得倒序结果的最旧 20 项，最新快照不在选择器内；用户无法通过报告工作台选中刚创建的最新快照，直接报告 API 不受此截断。初步方向：明确列表顺序后选择最新项并提供翻页或检索，同时覆盖投影失败时上下文回退路径。

### FE-T08：刷新凭证失效后旧 access token 持续阻止登录页出现

模块/类别：认证；401 恢复。状态及初始优先级：[已确认] P1。

frontend/models/auth.py:42-56 任意刷新请求异常仅返回 False，不清理旧令牌；frontend/models/api_client.py:68-75,100-105 等在 401 时尝试刷新；frontend/controllers/auth_controller.py:11-15,71-77 只检查 access token 是否存在，存在即跳过登录。frontend 中未找到退出登录入口。auth/jwt.py:50-65 对失效 token 返回 401；auth/service.py:92-116 对无效刷新令牌或已不存在用户拒绝，并从存储读取当前角色。

access 与 refresh 均失效、用户已移除等情况下，页面持续带旧 access 请求并收到 401，普通 rerun 不回到登录表单；需重新建立浏览器会话等外部操作恢复。初步方向：区分刷新明确拒绝与暂时网络错误；确定认证失效时清理认证及用户/租户缓存并引导登录，瞬时故障保留重试状态；刷新成功同步 UI 角色。

### FE-T09：人工监督和门禁读取失败会显示“没有待处理事项”

模块/类别：人工监督；错误与空状态区分。状态及初始优先级：[已确认] P1。

frontend/models/api_client.py:319-333 将 actions/readiness 失败转换为 []/{}；frontend/models/session_state.py:133-145 用其覆盖既有状态；frontend/views/panels/governance_panels.py:24-30、frontend/views/live_oversight.py:21-46 据空值显示无待处理事项；frontend/views/panels/gate_panel.py:35-62,171-172 在空阻断列表下也显示没有阻断项。api/routers/oversight.py:15-33 与 api/routers/stage.py:37-47 分别返回真实动作和门禁；服务器推进仍执行门禁。

刷新时读取因网络、401/403、404、5xx 失败，用户可能看到误导性绿灯或零事项。确认的是 UI 误示，不表示后端允许绕过门禁。初步方向：保留失败、未知和成功空集合的区别；失败时提示不可用，必要时保留带过期标识的上次结果。

### FE-T10：聊天失败仍保留未确认的用户消息，失败提示可能随 rerun 消失

模块/类别：聊天；失败反馈与状态恢复。状态及初始优先级：[已确认] P2。

frontend/controllers/session_controller.py:148-176 在请求前把用户消息加入本地 messages，失败不标记或撤回；frontend/views/workbench.py:107-119 在快捷操作或聊天提交后无条件 st.rerun；frontend/models/api_client.py:68-97 返回 None 并当次显示错误。api/routers/chat.py:22-36 执行消息；core/services/session_workflow.py:294-350 在具体执行路径中保存，例如 401/403 在业务调用前拒绝，超时可能结果未知。

明确拒绝时界面仍留一条看似已发送消息；网络超时不能判断后端是否最终提交，重复发送可能造成重复操作。不能对所有超时或 502 一概断言后端未保存。初步方向：区分已确认、明确失败和结果未知；保留可重试草稿或失败标识，重试前按业务能力核对服务端状态；反馈跨 rerun 保留。

### FE-T11：证据核验没有贯通 JWT 用户身份

模块/类别：证据、人工监督、审计；跨端身份契约。状态及初始优先级：[已确认] P2。

frontend/views/panels/governance_panels.py:235-243 发起核验；frontend/views/panels/closure_panel.py:59-64 展示 verified_by。api/routers/evidence.py:44-60 获得 ctx 但只传 tenant_id；core/session_service.py:229-232、core/services/evidence.py:43-55 无 actor 参数；core/evidence_service.py:142-163 默认 verified_by=user 且审计 actor=user。由人工动作核验时 core/governance/action_effects.py:97-113 也写 user；core/governance/action_resolution.py:489-494 未向关联动作传 actor。

同租户多人核验后，证据显示和直接核验审计不能准确区分真实核验人。初步方向：由可信 JWT 贯通 actor 至证据及关联动作，兼容历史 user 数据；不要接受前端自填 reviewer 身份。

### FE-T12：红队生成失败被转换成零条成功并立即 rerun

模块/类别：红队；异常传播。状态及初始优先级：[已确认] P2。

frontend/models/api_client.py:567-569 经 stage_operation_items 转换；frontend/models/stage_envelope.py:51-61 把 None 与合法空列表均变为 []。frontend/controllers/eval_controller.py:131-135 无条件显示生成 len(created) 条并刷新/rerun。api/routers/redteam.py:47-59 对业务失败返回 HTTP 400；请求层将其转为 None。

生成请求失败时控制器仍走“生成 0 条”成功分支，rerun 可能清除错误提示，用户无法据结果判断是否真正成功。初步方向：保留失败与成功空列表的区别，只有成功才刷新并显示数量；由合适层级持续提示错误。

### FE-T13：公共 HTTP 层丢失可行动的错误语义，且各方法反馈不一致

模块/类别：请求客户端、异常体系；错误契约。状态及初始优先级：[已确认] P2。

frontend/models/api_client.py:68-199 各 verb 分别实现超时、401、HTTP 错误处理；GET 对全部 404 静默；PATCH 统一显示“重命名失败”；POST/PUT 仅把 detail 放在技术详情，未读取 error_code/retryable。api/main.py:237-253 的 409 要求重新加载；:261-285 对工作流阻断提供恢复入口、对模型失败提供 error_code/retryable；api/routers/oversight.py:104-115 对动作冲突和校验错误有不同状态。

例如并发修改后的 409 仅显示一般失败并把 reload 指引藏在详情；模型不可重试错误与可重试错误都被笼统提示重试；资源 404 与合法空集合常在读包装处混淆。部分重复提示来自请求层与页面共同报错。初步方向：在现有客户端内收敛公共认证、网络及响应解析，向页面保留状态码、固定错误码、业务详情和可重试性；页面负责冲突、恢复与业务提示。不建议仅因重复 try/except 重写全部后端异常体系。PATCH 文案是否构成问题由第 4 节纠正。

### FE-T14：同步运行全部真实评测用例可能超过前端超时，重试可能重复外部调用

模块/类别：评测用例；超时与外部副作用。状态及初始优先级：[潜在风险] P1。

frontend/views/panels/eval_panels.py:32-58,293-303 允许选择 target_http，每目标超时可达 120 秒并可运行全部；frontend/models/api_client.py:68-78,472-482 对整个 POST 设置 120 秒。api/routers/eval.py:84-99 → core/services/evaluation.py:181-200 → core/eval_runner.py:399-423 串行逐项运行，服务在整个列表返回后保存；此路径不同于逐项保存的后台实验。

多个目标调用累计较长时前端可能超时，而后端可能仍执行或最终保存；用户重试可能再次调用已执行外部目标。是否发生取决于目标耗时和网络，未运行验证。初步方向：根据验证结果让可能较长的真实批量复用可恢复实验能力，或明确同步批量边界与可查询结果；评估外部副作用后定义重试/幂等，不无条件自动重试。

### FE-T15：跨会话复用表单 widget key 是否保留旧输入，需要运行核验

模块/类别：风险处置与目标部署；会话状态隔离。状态及初始优先级：[需核验] P2，未计入已确认。

frontend/views/panels/closure_panel.py:85-120 以列表下标生成 closure_owner_{index}、closure_plan_{index} 等 key；:151-175 对目标部署使用固定 key，未显式包含 session ID。frontend/controllers/session_controller.py:70-92 切会话未清理这些 widget key。api/routers/risk_treatments.py:46-67、api/routers/session.py:328-345 按当前会话 ID 处理。

待验证项目实际 Streamlit 版本下切换 A/B 且控件连续渲染时，默认值变化与 widget identity 是否重置旧值，以及风险项重排后的行为。若旧输入保留，保存可能把 A 的输入用于 B 的处置或目标声明。初步方向：确认后按会话及稳定业务 ID 隔离/清理必要 widget state；不预设所有 widget 均串值。

## 4. Sol 独立核验结果及分歧处理

### 4.1 逐项核验

| 编号 | Sol 结论及直接核查依据 |
|---|---|
| FE-T01 | [部分成立] 缺陷成立；建议 P1。factory:165-185 聚合来源，resolution:469-495 任一命中，effects:88-114 批量置 verified；需当前版本、待处理、校验通过及保存成功。不得说所有单条核验都扩大，也不得说整个发布门禁必然通过。 |
| FE-T02 | [确认成立] P1。客户端无分页参数、侧栏只处理本地列表；后端默认 20。超过 20 时第 21 个未到前端；直接 ID API 不受影响。 |
| FE-T03 | [确认成立] P1。切换前先写新 ID，失败保留旧消息；补充 GET 成功也不从 ctx 更新 current_state，旧列表缓存可造成新消息配旧状态。 |
| FE-T04 | [确认成立] P1。前端 interrupted/cancelled 无按钮且重试通常换键；后端 status 提供已保存键并拒绝不匹配。真实半批后改 dry-run 可形成混合，发布证据仍逐项验真。 |
| FE-T05 | [确认成立] P1。900 次同步轮询、GET 失败为空字典，终态统一 success；重入仅列表读取，running 不主动查询 status，陈旧状态可能不协调。占用的是该脚本执行，非证明整个服务阻塞。 |
| FE-T06 | [确认成立] P1。eval_runs 投影默认 created_at ASC，target_runs[-20:] 是最新 20，隐藏较早需校准的运行；与报告排序相反。 |
| FE-T07 | [确认成立] P1。正常投影 generated_at DESC、前端取尾 20，最新报告被排除；回退到上下文可能采用不同顺序，修复需统一契约。 |
| FE-T08 | [确认成立] P1。终态刷新失败保留旧 token，ensure_auth 按 token 存在短路；临时网络错误与终态拒绝必须区分。刷新成功后的角色会在 rerun 重解，不是永久旧角色或越权。 |
| FE-T09 | [部分成立] P1。失败确实可造成“无动作/无阻断”误示；gate_panel 默认 can_continue=False，不应声称所有请求失败均显示“当前阶段可推进”，更不应声称后端放行。 |
| FE-T10 | [确认成立] P2。请求前插入本地消息，失败后仍是普通消息；明确拒绝与超时结果未知须区分。 |
| FE-T11 | [确认成立] P2。单证据核验及关联动作未贯通 JWT 身份；普通动作和校准路径已有 reviewer 元数据，不能泛称所有复核均无身份。 |
| FE-T12 | [确认成立] P2。stage_operation_items 将 None 与空列表都变为 []，生成控制器无条件成功提示并 rerun。 |
| FE-T13 | [部分成立] P2。GET 404、状态和 retryable 等恢复语义存在缺口；POST detail 并非完全丢失而是在技术详情。PATCH 当前唯一用于重命名，因此删除其文案不合理的论据；重复捕获本身不证明需重写后端。 |
| FE-T14 | [部分成立] 作为条件性 [潜在风险]，候选 P1。客户端可能先超时，服务端可能继续，重试可能再次外调；未实测慢目标、断连与落库，不计已发生重复。requests 单值 timeout 不应概括为所有情形的端到端总时限。 |
| FE-T15 | [证据不足] 候选 P2。静态 key 事实成立，但 A→B 经 rerun 的实际 widget 状态需在锁定的 Streamlit 1.57.0 中实测，不计确认。 |
| FE-S01 | [新增问题] 候选 P2。llm_node 实验 UI 只提交 dry_run_only=True，后端实际转 dry_run，但实验行显示配置模式；真实 llm_node UI 能力是否应开放需产品确认。 |

### 4.2 新增问题 FE-S01

**最终收窄为 [确认成立] P2：配置模式与实际执行来源展示不清。** frontend/views/panels/eval_panels.py:220-224,250-283 可选 llm_node，但仅 target_http 显示真实运行勾选；frontend/controllers/eval_controller.py:96-105 将 dry_run_only 传给 POST /sessions/{id}/eval-experiments/{id}/run；api/routers/eval_experiments.py:85-104 传至 core/eval_experiment_service.py:227-232，后者把 llm_node 的 dry-run 请求变成 dry_run。core/eval_runner.py:250-269 的 dry_run 和 llm_node 分支不同；实验行显示 experiment.run_mode，可能让人误读。单个用例区能显示最近运行的 execution_kind，故不称整个 UI 从不展示来源。是否提供真实 llm_node 实验入口、是否触发真实模型费用属于待产品决定；默认不增加实际调用。

### 4.3 分歧裁决与验证事实

- **FE-T01 等级**：Terra 原判 P0，Sol 倾向 P1，理由是需要有权限操作者和多来源动作；Terra 重新检查后保持 P0，协调者接受。理由是指定单证据操作超出对象范围，持久化其他未人工核验来源的正式核验状态与核验审计，并直接移除该高风险来源的证据阻断，损害平台核心可信复核，符合附件“重大业务错误”。不以其他门禁存在自动降级，也不声称整体审批一定通过。条件详见第 3 节及第 6.1 节。
- **FE-T09、T13**：采纳 Sol 对展示范围和 PATCH 论据的收窄。FE-T03 吸收成功 GET 仍用旧 current_state 的补充，不另计数。
- **FE-T14、T15、S01**：前两项不当作已确认问题；S01 只确认展示不清，是否开放真实 llm_node 保持待决。
- Sol 使用 python -B 和 stdin 提取现有函数 AST，以内存模型/审计/传输替身组合验证：T01 单 E1 导致 E1/E2 均核验且相应证据阻断消失；T03 失败切换保留 A 消息/B ID、成功 GET 仍用列表旧状态；T04 两次模拟时间得到不同请求键；T05 900 次空状态轮询后成功提示；T12 None 转零条；T06/T07 在核实排序下验证切片。该验证没有导入应用/store/config、没有真实 HTTP 或存储，不是 pytest、数据库集成或端到端通过证明。
- 代码检查了 tests/test_frontend_session_list.py:12-22、tests/test_frontend_release_wiring.py:16-49、tests/test_eval_batch_resilience.py:166-207、tests/test_business_closure_evidence.py:66-76,109-138、tests/test_frontend_ui_smoke.py:113-138；session_list 和 release_wiring 主要是源码入口/标记断言；eval_batch_resilience 覆盖后端同键恢复；business_closure_evidence 覆盖单证据门禁；ui_smoke 覆盖离线渲染。这些不能替代本方案的多证据、多页、重入与失败 UI 验收。以上测试本轮没有运行。

## 5. 最终确认的问题清单

| 优先级 | 编号 | 最终问题 | 可确认的影响 |
|---|---|---|---|
| P0 | FE-T01 | 单条证据核验错误扩展到聚合动作的其他来源 | 错误核验状态和审计可持久化，对应高风险证据阻断消失 |
| P1 | FE-T02 | 会话列表仅取前 20 条 | 较早会话在现有 UI 不可搜索或选择 |
| P1 | FE-T03 | 切换会话失败或列表状态过期 | 显示内容与实际会话 ID/状态可能不一致 |
| P1 | FE-T04 | 实验恢复入口、幂等键和执行模式不一致 | 中断批次无法可靠恢复，部分场景可混合真实与模拟运行 |
| P1 | FE-T05 | 实验长轮询缺少可靠重入与终态反馈 | 页面长时间等待，失败或未知可能被显示成成功 |
| P1 | FE-T06 | 校准界面固定只展示最后 20 个目标运行 | 必测运行可能无法经 UI 校准，上线条件无法满足 |
| P1 | FE-T07 | 报告倒序列表错误截取尾部 | 超过 20 份时新快照无法在界面选择 |
| P1 | FE-T08 | 终态认证失败不清旧凭证 | 当前 UI 持续 401 而不回到登录 |
| P1 | FE-T09 | 人工监督/门禁读取失败转为空集合 | 界面可能误示无待处理事项或无阻断 |
| P2 | FE-T10 | 聊天失败保留未确认消息 | 明确失败或结果未知时用户难判断消息状态 |
| P2 | FE-T11 | 证据核验丢失真实用户身份 | 多人核验无法准确归属 |
| P2 | FE-T12 | 红队生成错误变为零条成功 | 失败可能被误认为已成功执行 |
| P2 | FE-T13 | 请求层丢失页面恢复需要的错误语义 | 409、502、404 等难以采取恰当恢复操作 |
| P2 | FE-S01 | 实验配置模式与实际执行来源展示不清 | llm_node 实验实际 dry-run 时实验行可能误导 |

FE-T14 为潜在风险，FE-T15 为证据不足；两项及是否开放真实 llm_node 实验入口均见第 11 节。原始列表的 FE-T13 PATCH 文案论据已由第 4 节移除。

## 6. 具体改进方案

本节是开发实施方案，并非本轮已做代码变更。每项的既有证据见第 3–4 节；以下给出触发、文件、迁移、兼容与可执行验收。无需改动的维度在 6.15 表中显式列出。

### 6.1 FE-T01｜P0｜单条核验与聚合动作作用范围

**根因/触发**：同一高风险失败模式的 E1/E2 被打包为一个当前、待处理的核验动作；单条核验 E1 经“任一命中”收口后又执行整组副作用，E2 也变为已核验。仅在有 editor/admin 权限、动作当前且校验与保存成功时成立。

**具体步骤**：

1. 在 core/services/evidence.py:43-67、core/evidence_service.py:142-165 保证单证据 API 只核验路径中的 evidence_id。修改 core/governance/action_resolution.py:456-496：按动作 payload 中的来源 ID 读取当前证据状态，仅当该动作全部应核验来源均已分别满足时才进入动作收口；未全部满足保留 pending。共享证据对应多个动作时逐动作检查。
2. 调整 core/governance/action_resolution.py:100-138 与 core/governance/action_effects.py:80-115：为“因单条证据已全部完成而自动收口”的内部路径明确跳过批量核验副作用，但仍走原有版本、状态、策略和审计约束；不得重复写入已核验证据、覆盖其 verified_by、verified_at 或 note。优先复用现有动作状态机的小范围参数/分支，而非新建动作框架。
3. 显式处理整个人工动作仍可具有整组核验语义。frontend/views/panels/governance_panels.py:40-75 应在该动作按钮旁清楚列出受影响来源及“核验所列全部证据”的范围，让操作者先看到对象；单条证据按钮仍只表示单条。保持 dismiss 不能解除尚未核验证据的门禁。
4. 保持 API 路径、单条请求体及返回 envelope 兼容；不改变高风险门禁对 verified 的要求。与 FE-T11 一起贯通身份；修复不能为单条自动收口引入新一轮批量核验。

**历史数据**：本轮未查真实库，无法估计受影响数量或识别全部记录。实施时先用已保留的事件、目标 ID、action_id、时间及当前动作/证据状态，在授权隔离副本上只读生成候选；审计有脱敏，候选不是事实证明。由业务负责人逐条复核并记录依据后，才按单独批准的受控流程追加更正事件、修正被确认的状态并重新计算受影响的当前门禁与审批；保留历史审计和批准记录。不得无证据批量重置所有 verified、审批或填写虚构核验人。更正后的 readiness 不满足时应验证现有 effective_approval_status 自动失效机制；不假设所有历史批准必然失效。

**依赖/副作用**：最优先；FE-T11 的身份贯通应与此协同发布。显式整组核验 UI 的操作说明变化需兼容老动作。**验收**：隔离数据中构造 E1/E2 同动作，核验 E1 后 E1=true、E2=false、动作仍 pending、E2 证据阻断仍在；核验 E2 后动作关闭，E1 身份/时间不变；多动作共享来源、无关联动作、过期动作、重复提交、显式整组核验及 dismiss 均符合各自契约。通过实际 API 和持久化回读验证，不只断言函数调用。

### 6.2 FE-T02｜P1｜会话列表真分页

**根因/触发**：后端默认只返回 20 条，前端把它当全集；第 21 条无法通过现有 UI 到达。

**修改位置与步骤**：在 frontend/models/api_client.py:274-276 为 list_sessions 增加 limit/offset 参数，并把两者放入缓存键；沿用 GET /sessions/?limit=20&offset=N 返回现有 list，不新增总数包装。frontend/views/sidebar.py:172-207,246-249 保存已加载页和下一 offset，点击“显示更多”发实际下一页请求并按 session_id 去重；上一页数量少于 20 表示已到末页，恰好整页可在下一次请求空页后结束。因为后端按更新时间倒序而会话可能在翻页间变化，明确“刷新从第一页重新加载”并清除旧页，不能把去重当成保证快照分页。

搜索**只针对已加载会话**，UI 明确写“搜索已加载会话”，即使当前页无匹配也保留有后续页时的加载入口；不要显示全租户搜索或总数。若将来必须全库搜索，再单独设计服务端筛选。创建/删除/重命名使对应页缓存失效。API 与响应字段不变，旧调用保留默认首 20 条。**验收**：隔离 API 返回 45 条时通过加载依次可选择第 21、41、45 条；搜索范围提示正确、无匹配仍可加载、末页无重复，空页、请求失败、排序变化后刷新和权限范围均正确。

### 6.3 FE-T03｜P1｜原子切换与完整刷新

**根因/触发**：先改 ID 与列表状态再 GET；失败仍保留旧消息，成功也未从新 ctx 取 current_state。

**修改位置与步骤**：frontend/controllers/session_controller.py:70-92 先请求目标 GET /sessions/{id}，只在成功时一起提交 session_id、ctx.current_state、selected_scenario_id、messages、flags、actions 和清空旧阶段派生状态；readiness/interrupts 可独立加载，失败标记未知而非复用 A。若 GET 失败，保持 A 的 ID、消息与操作目标一致并展示失败；或使用明确的加载中禁写状态，但不可留下 B ID 配 A 内容。移除“同 ID 永远提前返回”或为失败/显式刷新保留重试。frontend/controllers/session_controller.py:110-116 复用完整 GET 及状态投影，刷新消息和 current_state；frontend/models/session_state.py 中相关逻辑按现有职责复用。

契约不变，GET/404 和暂时网络失败需明确提示；已成功的 ctx 是状态来源，不再信任 10 秒列表缓存的状态。与 FE-T08 一同清理换身份时所有旧租户状态。**验收**：A→B GET 失败后 ID、消息、输入目标保持 A 且 B 可重试；B GET 成功而列表为旧状态时显示 ctx 中新状态；同 ID 刷新能看到服务端新消息/状态；只读辅助请求失败不产生假空态或混用上一个会话。

### 6.4 FE-T04｜P1｜实验恢复键与执行模式一致

**根因/触发**：重新点击以当前时间生成新 key，后端要求同一次运行沿用已保存 key；UI 隐藏 interrupted。空键恢复还可能把已开始真实目标批次的剩余项切成 dry-run。

**修改位置与步骤**：

1. frontend/controllers/eval_controller.py:96-105 和 frontend/views/panels/eval_panels.py:249-284：首次提交为当前 session/experiment 创建一次随机请求键，在用户点击前或提交时保存于会话状态；以后重入或响应不确定时先 GET status，优先使用服务端 run_request_key 与 resumable，failed/interrupted/cancelled 只有 resumable 才显示“恢复”；running 正常时只展示状态，只有 status 明确 can_resume_stale=true 时才另外显示“恢复心跳陈旧的运行”。该按钮由用户显式触发，不由轮询自动触发，并提交原键、原执行模式、resume_stale=true 与当前 expected_attempt。若是新比较或需要改变模式，创建新实验。
2. core/models.py 的 EvalExperiment 增加可选、默认空的“本次实际运行模式”字段，例如 execution_mode；它记录实际 dry_run 或 target_http 等执行选择，不等同 experiment.run_mode 或具体 provider 的执行来源。修改 core/services/evaluation.py:630-706、core/eval_experiment_service.py:166-203,225-243 和 core/eval_execution.py:38-61，使用现有存储版本比较完成一次短事务原子预留：从存储按租户加载最新上下文，核对实验状态、请求键和实际模式；把键、模式、running、启动时间/心跳和递增一次的 execution_attempt 一起保存。只有该版本保存成功的请求可入队；版本冲突后重读状态，同键同模式已运行可返回已接受/正在运行并引导查询，不再入队，异键或模式冲突返回 409。不可只依靠进程内 _futures 去重。
3. worker 接收预留的 session_id、experiment_id、key、mode 和 attempt，重新校验仍为该预留后消费：重构 run_experiment 的启动分支，允许它进入已预留的 running，不被旧 already-running 检查拒绝，也不第二次增加 attempt 或覆盖首次启动时间。同步旧调用仍遵循原启动契约。若提交线程池前抛错，仅在存储仍为同一 key/attempt 且状态 running 时，使用版本比较标记 interrupted 并记录错误；若提交结果未知，先查询状态，不把可能已经开始的任务盲目标记失败或重复入队。预留成功但进程在入队前崩溃的窗口通过状态和陈旧协调识别，允许按原键/模式受控恢复。
4. 心跳陈旧的 running 通过现有 POST /sessions/{id}/eval-experiments/{experiment_id}/run 显式恢复：在 api/schemas.py:217-221 的 RunEvalExperimentRequest 新增可选 resume_stale=false、expected_attempt=None；frontend/controllers/eval_controller.py 调用 frontend/models/api_client.py:617-636，仅显式陈旧恢复时把这两个字段连同原 idempotency_key、原 dry_run_only 模式加入请求体；api/routers/eval_experiments.py:85-111 将两个字段转发给 core/session_service.py 的兼容入口及 core/services/evaluation.py，GET status 经 api/routers/eval_experiments.py:114-128 返回新增状态字段。普通请求默认行为不变，旧客户端无需发送新字段。用户点击对应恢复按钮时，core/services/evaluation.py:630-706 按租户从存储读取最新状态，在同一乐观锁 CAS 事务中核对仍为 running、服务端心跳确已过期、expected_attempt 与当前 execution_attempt 完全相同、原请求键及实际模式一致；仅符合时记录旧 attempt 已中断的审计，立即预留 running 的新 attempt（递增一次并更新时间/心跳）并提交保存。只有 CAS 成功者入队；心跳刚更新、attempt 已变化或重复并发请求返回 409 并提示刷新 status，不覆盖新状态。旧空键或旧模式不明不能借此绕过第 6 步的兼容规则。

   worker 每次外部调用及结果保存前核对当前 key/mode/attempt，发现已被替代立即停止后续执行。core/services/evaluation.py:593-614 的旧 worker StaleContextError 修复分支也必须在按租户重读后核对 key/attempt；若已属新 attempt，只记录旧任务结束，不能将新任务改为 interrupted 或覆盖新心跳。预留与保存均用现有存储版本检查，避免旧上下文覆写。现有 _reconcile_stale_experiment 的在飞表仅属于当前进程，而 Dockerfile:36 默认两个 worker，另一进程的空表不能证明旧任务已死，故多 worker 的 GET 只提示心跳陈旧并提供上述显式恢复入口，不自动判死或重启；单 worker 可沿用本地在飞判断。按钮说明已发出的目标调用可能仍在执行并可能重复；只有已知不可重复且有严重副作用的目标，应先核实旧执行/目标状态再点击。已发出的请求无法通过 attempt 检查撤回，网络分区及发出后未落库仍属至少一次窗口，CAS 不保证外部 exactly-once。
5. GET status 在现有返回中向后兼容地增添可选 execution_mode、heartbeat_stale 和 can_resume_stale；沿用 execution_attempt、run_request_key、resumable 等原字段。can_resume_stale 只表示服务器观察到 running 且心跳过期、键/模式与 attempt 具备恢复依据，最终是否能预留由 POST 中的重新检查和 CAS 决定，不证明旧调用已停止。原 202 契约保留；同键正常运行时以已接受状态查询替代原本的泛化冲突，属于需覆盖旧客户端的行为调整。该字段属于现有上下文/实验 payload JSON，勿修改创建时 run_config 而使 run_config_hash 与配置不一致。实际实施前验证两个存储后端的 payload、上下文兼容和迁移策略，只有需要时才安排相应版本迁移；不预设新增数据库列。
6. 旧实验缺字段时，从已有 run 的实际 run_mode 及可用启动审计记录判断：来源一致且证据充分才能恢复；混合、无运行结果且来源无法证明等情况显示“模式未知”，不自动假定真实或模拟，可提示新建实验。旧空键调用需兼容已有公开契约，但不能借空键绕过已知模式一致性；状态冲突用明确 409/业务信息告知，不因文案字符串猜测是否可恢复。

**兼容/依赖**：新增 status 字段是可选增量；修复会阻止以前被错误允许的跨模式恢复，这是有意的行为变化。保持已完成/失败用例不重跑和同键幂等，外部调用已发出但结果未保存的窗口仍是至少一次语义。与 FE-T05、FE-S01 一起设计展示。**验收**：模拟真实批次执行部分后超时，刷新/重进取原键恢复并跳过已保存项；不同键/不同模式不能混跑；中断可从 UI 恢复；旧字段缺失时按证据处理；排队响应丢失后查询可定位状态；正常 running 无恢复按钮，running 且 can_resume_stale=true 才允许用户携原键/模式/expected_attempt 显式恢复。恢复前心跳更新或 attempt 变化、两个并发旧 attempt 恢复分别只能有一个 CAS 成功，其余收到 409 并刷新；旧 worker 的 StaleContextError 或延迟保存不能覆盖新 attempt/心跳；成功者一次预留一次入队，已落库项不重跑。在预留有效、worker 正常存活、未发生陈旧误判或崩溃时，两个真实并发首次提交也只有 CAS 胜出者入队；崩溃/断连窗口不以此声称外部调用恰好一次。

### 6.5 FE-T05｜P1｜提交和轮询分离

**根因/触发**：202 后当前 controller 同步循环，状态读取失败被视为空字典；所有终态及等待耗尽落入同一 success。

**修改位置与步骤**：frontend/controllers/eval_controller.py:96-128 只在明确点击时 POST 一次；frontend/models/api_client.py:639-641 保留 status 读取失败信息；frontend/views/panels/eval_panels.py 在重新进入某 session/experiment、或列表显示 running 时 GET 改进后的 status，按 session_id+experiment_id 保存显示状态：只有确认全部署仅一个 API 进程、无其他副本且本地无在飞任务时才可协调陈旧心跳；多进程或多副本所有者不明时 status 返回 heartbeat_stale 与 can_resume_stale，不根据当前进程空表自动判死；若 can_resume_stale=true，界面显示第 6.4 节的显式恢复按钮，并把当前 execution_attempt、原键和模式提交到现有 run API。可在该面板使用 Streamlit 1.57 的 st.fragment(run_every=...) 或等价轻量周期重渲染；该版本接口仅按 func/run_every 使用，不使用新版本的 parallel/key 参数。只有运行中建立轮询，终态触发常规页面重渲染后停止。轮询**只能 GET**，不能自动 POST 或自动恢复。

展示 accepted/running、completed、failed、interrupted/cancelled、心跳陈旧待核实、unknown/状态读取失败、等待超限及完成/失败数量；completed 仅表示批次执行结束，仍须显示 failed_cases，不能等同所有用例通过。请求返回前后检查当前 session/experiment 和视图代次，切换后旧响应不得覆盖新页面；页面关闭/离开停止展示轮询，重新进入可恢复 GET。保留后端 202、status、逐项保存和已有超时机制，不另建任务队列。

**验收**：Mock 202→running→completed、failed、interrupted、超时/404/401/5xx；未知与失败均无 success；重进 running 重新查询，正常 running 不可恢复，stale running 的可恢复状态显示显式按钮并在点击后发送 expected_attempt，CAS 冲突提示刷新；切会话或实验后旧响应不覆盖新状态；每次 GET 不触发 POST；真正完成后列表、运行数与人工动作刷新。官方参考：[Streamlit 1.57 fragment](https://docs.streamlit.io/1.57.0/develop/api-reference/execution-flow/st.fragment)。

### 6.6 FE-T06｜P1｜使同一批次的所有必测运行可校准

**根因/触发**：frontend/views/panels/eval_panels.py:112-125 仅显示按创建时间升序列表的最后 20 条；必测批次超过 20 或被新运行挤出时，隐藏项不可达。

**修改位置与步骤**：在该面板按 experiment_id/运行 ID 筛选，优先提供当前 readiness 对应必测 run 的定位入口，并对已加载列表分页/“显示更多”；前端现有 GET /eval-runs 已取完整列表，按需本地分页足以修复，不必新增数据库分页或响应包装。frontend/models/api_client.py:461-469 维持失败与空列表的区分；校准继续 POST /eval-runs/{run_id}/calibrate，后端保持 JWT reviewer 和真实执行校验。若 readiness 暂不能标定完整候选批次，允许按实验和 run ID 找到所有结果，明确当前筛选范围。

**兼容/依赖**：不改变排序契约、判定标准或已校准数据；与 FE-T09/T13 的错误语义一致。**验收**：单个真实批次 25 个必测运行均可逐页找到和校准；较新历史运行出现后仍能按批次找到旧必测项；失败目标仍不可校准为 passed，所有必要人工校准完成后 readiness 随后端规则变化。

### 6.7 FE-T07｜P1｜统一报告排序后展示最新页

**根因/触发**：正常报告投影按 generated_at DESC，前端取尾部 20；回退上下文列表可能是追加顺序，不能对两条路径用同一假设切片。

**修改位置与步骤**：core/services/session_workflow.py:519-529 在正常投影与 ctx 回退返回前约定 generated_at 降序，时间相同时以 report_id 作稳定次序；验证 SQLite/PostgreSQL 及空/异常日期的模型兼容。frontend/views/panels/report_workspace.py:53-68 消费该契约，从首 20 项显示最新页并可逐页查看更早快照；创建成功后失效报告列表缓存并显示新项。后端仍返回原 list 和原字段，快照 GET/导出内容不变；明确这是报告顺序，不能照搬 eval_runs 的升序假设。

**验收**：正常 SQLite、PostgreSQL 投影和模拟回退分别放入 25 份快照，最新与最旧均可到达；新增第 26 份后最新页可选中；同时间戳排序稳定；详情内容、不可变快照及审批分离不变。

### 6.8 FE-T08｜P1｜终态认证失效后安全重新登录

**根因/触发**：refresh 失败一律 False，旧 access token 仍令 ensure_auth 短路；用户已移除或刷新令牌过期会反复 401。

**修改位置与步骤**：frontend/models/auth.py:42-56 将刷新成功、明确的认证拒绝（例如 refresh HTTP 401 或无 refresh 凭证）与网络超时/连接失败/5xx 分类；frontend/models/api_client.py 各方法共用一次刷新逻辑，认证明确终态时触发 frontend/controllers/auth_controller.py 登录流并显示原因。清理 access_token、refresh_token、user_role、所有用户/租户相关 API 缓存、session_id、消息、flags/actions、readiness、报告/实验轮询及相关用户数据；可复用并扩展 frontend/models/session_state.py:36-50，确保新登录其他用户/租户不会继承前一身份的状态。瞬时故障保留凭证并显示可重试，不错误清会话；刷新成功立即同步角色。演示自动登录维持现有环境边界，避免终态失败造成自动登录循环。

**兼容/依赖**：不更改 JWT 或刷新 API，保留服务端重读角色；公共认证错误路径由 FE-T13 统一，状态清理与 FE-T03 配套。**验收**：过期 refresh 401 后下一界面可登录且旧数据不显示；用户 A 后登录 B 无 A 的 session/cache/轮询；refresh 超时或 5xx 不清凭证并可恢复；刷新成功使用服务端新角色；原请求最多在刷新成功后重试一次。

### 6.9 FE-T09｜P1｜人工监督未知状态不能显示为空

**根因/触发**：GET 失败转为 []/{} 并覆盖状态；视图把空与未知视为同一种“无待处理”结果。

**修改位置与步骤**：frontend/models/api_client.py:319-345、frontend/models/session_state.py:119-145 使用 FE-T13 的结构化失败语义；成功空列表才表示零动作，失败标 unknown，或保留带过期时间/明确“上次数据”的旧结果且不把它称为实时结论。frontend/views/panels/governance_panels.py:24-30、frontend/views/live_oversight.py:21-46、frontend/views/panels/gate_panel.py:35-62,171-172 明确显示加载失败/重试；既不能显示“没有待处理事项”，也不据未知状态启用推进。保留后端实际授权、门禁及批准 readiness 的 fail-closed 逻辑。

**兼容/依赖**：只调整受影响读包装及视图，其他返回列表成功形状不变；与 FE-T03 和 FE-T13 配套。**验收**：分别使 actions、readiness、两者、advancement GET 失败和返回合法空值；失败显示未知而非无阻断，成功空才可显示零；后端真实阻断仍拒绝推进；从网络恢复后重试显示新值。不要要求所有故障均出现同一标题。

### 6.10 FE-T10｜P2｜消息的成功、失败与未知

**根因/触发**：先本地 append 用户消息，API 失败仍普通渲染并无条件 rerun；明确拒绝和网络结果未知被混用。

**修改位置与步骤**：frontend/controllers/session_controller.py:148-178、frontend/views/workbench.py:107-119 维护消息的 pending、confirmed、failed、unknown 标识；明确的 401/403/409 等拒绝保留可编辑草稿和原因，成功后以响应更新状态；网络超时或连接中断标为 unknown，并说明服务端可能仍在处理，保留输入供人工核对。状态与错误提示跨 rerun 保存。允许稍后刷新服务端历史并让用户显式决定如何继续；**一次 GET 尚未看到消息不能证明后端已经停止或未提交**。不能通过匹配相同文本去重，因重复“确认”等可能是合法请求；unknown 写操作不自动重发。如未来需要安全自动重试，另行设计并实现服务端请求幂等契约，本方案不假定已有此能力。

**兼容/依赖**：原 chat API 和后端工作流状态保持不变；使用 FE-T13 保留明确错误/未知的差异。**验收**：模拟 403 显示 failed 草稿、不当作已发送；模拟服务器已提交但响应超时与尚在处理两种情况均显示 unknown、不自动 POST；刷新后可展示后端历史但单次未出现仍不标记安全重试；成功请求消息与后端一致。

### 6.11 FE-T11｜P2｜以 JWT 贯通证据核验人

**根因/触发**：证据路由只传 tenant_id；单证据及动作副作用均默认 user。多人核验无法区分真实人。

**修改位置与步骤**：api/routers/evidence.py:44-60 将 ctx.user_id/ctx.role 作为服务端内部参数传给 core/session_service.py:229-232、core/services/evidence.py:43-55、core/evidence_service.py:142-163 及 core/governance/action_resolution.py:456-495；core/governance/action_effects.py:97-113 显式接收可信 actor 并写 EvidenceSource.verified_by、审计 metadata 的 reviewer_id/reviewer_role。core/models.py:286-299 的 AuditEvent.actor 是 system/user/ai 枚举，继续写 actor=user，**不得把 UUID 直接写入 actor**；身份放 verified_by 和现有 metadata。使用 core/data_protection.py 的现有脱敏，不在事件里新增自由文本原文。FE-T01 的自动收口不得覆盖已核验来源的身份和时间。

**兼容/依赖**：请求体不增加 reviewer_id；普通动作和评测校准保留现有 JWT 来源；历史 verified_by=user 保持原样、展示为历史未知而不伪造身份。**验收**：两个已认证成员分别核验证据，API 与审计可区分两者，actor 仍 user；伪造请求体身份不能覆盖 JWT；间接动作、多来源与旧 user 记录可正常读取，证据脱敏规则不回退。

### 6.12 FE-T12｜P2｜红队失败与成功零条分离

**根因/触发**：stage_operation_items 同时把失败和成功空列表变成 []，生成控制器始终 success。

**修改位置与步骤**：frontend/models/stage_envelope.py:51-61 与 frontend/models/api_client.py:567-569 保留失败语义；frontend/controllers/eval_controller.py:131-135 仅在请求成功时显示创建数、失效相应缓存并刷新动作。合法零项为“成功生成 0 条”，400/403/409/5xx、连接失败为明确失败，提示跨 rerun 保留；frontend/views/panels/eval_panels.py:62-82 复用 FE-T13 反馈，无二次报错。

**兼容/依赖**：后端路由和现有 envelope 不变；有其他 stage_operation_items 调用时逐个检查成功空列表语义，避免破坏它们。**验收**：分别模拟 HTTP 400、网络失败、合法空结果与 3 条结果，只有后两者显示成功数量，失败不显示零条成功且可见一次错误。

### 6.13 FE-T13｜P2｜按需统一客户端错误传播

**根因/触发**：多个 verb 重复实现 401/网络处理并把结构化失败压为 None，业务页面无法区分资源不存在、并发冲突及模型不可重试错误。

**修改位置与步骤**：在 frontend/models/api_client.py 现有模块内增加有实际职责的私有 _request，或等价小范围共享实现：保持每个 verb 的超时和 202/204/JSON 行为；公共处理一次刷新和网络/解析错误；成功返回原 payload，失败一律抛出轻量 ApiError，至少保留 HTTP status、detail（字符串、字典及 FastAPI 422 list 均原样可处理）、error_code、retryable 和必要的 recovery_endpoint。不得暴露 token 或 provider 原文。终态认证走 FE-T08；通用网络错误有统一可见提示；409 stale/blocked、403、404、422、502 等按调用场景由页面决定业务处理。请求层与页面不要对同一错误重复提示，跨 rerun 需要保留一次性反馈。

在同一变更批次按调用链迁移所有受影响域包装及其控制器/页面：成功形状保持兼容，失败向控制器/页面边界抛出并只在该边界捕获一次；不得保留将同一失败又转为 None、[] 或 {} 的竞争路径。对本来允许 404 的可选读取由明确的调用方捕获并决定。保留 api/main.py:237-293 已有全局异常处理和各路由必要的局部业务映射；仅在确有具体错误码错误时修补该位置，不强行把所有 ValueError 改一种异常，不重包成功响应或另造 DTO/BFF。

**兼容/依赖**：先铺好最小错误传播，再迁 FE-T08–T12/T05 使用它；迁移期需逐调用点测试，防止已有 None 检查失效。**验收**：401 刷新成功/失败、403、404、409 stale 与 blocked、422 detail 列表、502 retryable true/false、连接/超时和 202/204 均保留语义；每个失败只呈现一次可行动反馈；无敏感数据泄露。

### 6.14 FE-S01｜P2｜显示配置模式与实际执行来源

**根因/触发**：实验的 run_mode 是所选配置，llm_node 在当前 UI 提交 dry_run_only=True 时实际运行 dry_run；列表只显配置模式。

**修改位置与步骤**：frontend/views/panels/eval_panels.py:180-183,220-224,249-284 在运行前明确当前会执行模拟；实验行将“配置模式”和从该实验关联 EvalRun.run_mode/execution_kind 汇总得到的“实际执行来源”分别展示。未执行显示“尚未执行”，混合/历史缺字段显示“混合或未知”，不能把其他实验相同 eval_id 的最新 run 当成本实验来源。复用已加载 eval_runs，必要时以 experiment_id 过滤；不需要新增接口。移除或更新与实际能力不符的笼统“运行时校验延后”文字。

**兼容/依赖**：默认保持 dry-run，不增加收费模型请求；与 FE-T04 的模式一致性协同。是否提供显式真实 llm_node 实验入口由产品决定。**验收**：llm_node 配置的模拟实验显示“配置 llm_node、实际 dry_run_simulation”，未运行不显示已执行；混合或缺失来源不虚报；原 target_http 真实执行和单用例执行保持现有行为。

### 6.15 逐项契约、职责和依赖对照

| 问题 | 接口契约调整 | 职责/公共逻辑或异常 | 保留及兼容要点 | 推荐依赖 |
|---|---|---|---|---|
| T01 | 路径/请求/响应不变，修正单 ID 作用范围 | evidence 与动作副作用协调；局部复用状态机 | 显式整组动作、门禁及历史审计保留 | 与 T11 同步 |
| T02 | 不变；实际使用已有 limit/offset | 前端分页及参数化缓存 | list 返回、旧首屏调用兼容 | 无 |
| T03 | 不变 | 前端原子状态更新及失败反馈 | 后端 GET/聊天职责不变 | T08/T09/T13 协同 |
| T04 | run 请求增可选 resume_stale/expected_attempt，status 增可选 execution_mode/heartbeat_stale/can_resume_stale；旧字段不删 | 域服务 CAS 校验同批模式/键与 expected_attempt，前端显式恢复 | 普通请求默认不变；旧记录可读，未知模式不猜；run_config_hash 不乱变 | T05、S01 协同 |
| T05 | 保留 202/status | 前端状态轮询与重入；无新队列 | 只 GET 轮询、可终止、原后台能力保留 | T04/T13 |
| T06 | 不变 | 前端按批次筛选及本地分页 | 后端逐项人工校准与门禁不变 | T09/T13 |
| T07 | 明确报告列表降序，形状不变 | 报告服务统一正常/回退排序 | 详情与导出不变；排序变化告知其他消费者 | 无 |
| T08 | 不变 | 公共认证终态和临时失败分流、清理状态 | 后端角色刷新和演示边界保留 | T13、T03 |
| T09 | 不变 | 保留读失败、页面显示未知 | 不改变服务端门禁 | T13 |
| T10 | 不变；不假设幂等 | 页面消息状态及一次性反馈 | timeout 未知、不自动重发 | T13 |
| T11 | 外部请求不变，内部传 actor | JWT 到 evidence/审计元数据 | AuditEvent.actor 枚举、旧 user 和脱敏保留 | T01 |
| T12 | 后端不变；前端内部失败语义改变 | 域包装保留失败、页面提示 | 合法零项仍成功 | T13 |
| T13 | 后端既有错误形状保留 | 现有客户端小范围共享传输/错误 | 保留 422 多形态、202/204 和已有全局处理 | 可与 T08/T09 并行打底 |
| S01 | 不变 | 实验视图区分配置与执行来源 | 继续默认模拟，不自动调用收费模型 | T04 |

## 7. 前后端模块化与解耦设计

### 7.1 职责与依赖方向

保留现有 models ← controllers ← views ← app 的前端装配方向：models 负责传输、认证、缓存及数据/失败语义，controllers 负责用户动作、状态转移及重试选择，views 负责可见的状态、表单和一次性反馈。Streamlit 的 session_state 是前端交互状态，不得成为授权、证据核验或门禁的可信依据。

后端保持 api/routers → core/session_service.py 兼容入口 → core/services 域服务 → core/graph/storage 的现有路径；权限和租户边界保留在后端，证据状态、动作协调、风险处置和发布 readiness 在对应域层确定。core/services/access.py:41-91 的共享存储与缓存访问和兼容 facade 暂保留，不要求新建 Repository、DTO、Adapter、Facade 或 BFF。

| 当前位置 | 已确认的具体职责问题 | 调整后职责与迁移方法 |
|---|---|---|
| frontend/models/api_client.py | HTTP 动词重复刷新/错误转换，页面拿不到必要语义 | 保留业务域 API 包装；仅把有实际重复的传输、认证和错误解析内聚到本文件私有 _request/轻量错误结构；按 FE-T13 逐调用点迁移 |
| frontend/controllers/session_controller.py 与 models/session_state.py | 切换时 ID、消息及服务端状态分步写入 | controller 编排成功后提交，models 中已有状态恢复/清空逻辑供复用；不让 view 直接协调跨会话写入 |
| frontend/controllers/eval_controller.py 与 views/panels/eval_panels.py | 一次点击既提交又长时间轮询；重入状态没有明确所有者 | controller 负责单次提交/恢复选择；面板内聚状态读取及展示，可用一个实际承担轮询职责的函数/fragment。只有实现时复杂度证明必要才抽一个实验状态模块；不按行数拆小文件 |
| core/services/evidence.py、core/governance/action_resolution.py、action_effects.py | 单证据核验通过动作收口意外触发整组副作用，身份未贯通 | evidence 服务负责指定 ID，动作状态机负责条件收口，effects 只在明确整组人工动作时施加对应效果；由可信 ctx 传身份，不产生跨模块反向依赖 |
| core/services/evaluation.py、core/eval_experiment_service.py | 恢复请求键/实际执行模式与 UI 不一致 | 域服务负责已保存键及模式一致性，前端负责重入展示；保留逐项保存、状态端点和现有后台执行器 |
| core/services/session_workflow.py 与 report_workspace.py | 投影与回退报告列表顺序未统一，UI 使用错误切片 | 服务统一报告降序契约，视图只处理分页选择；保持快照/导出/审批分离 |

本次未发现仅由文件行数本身构成必须拆分的证据。frontend/models/api_client.py 的域包装为调用点提供真实语义，不因体积机械切成大量转发文件；core/session_service.py 是兼容入口，不因存在转发就删除。阶段结果 envelope 有真实的状态同步职责，也不因形式去除。若实现后确有某段新的轮询或请求逻辑独立变化，再一次性迁移至一个内聚模块，并保证旧导入路径兼容和调用方向单向；禁止只为缩短行数拆出大量单函数文件。

### 7.2 防止回归

- 针对跨端接口新增行为型契约测试：方法、路径、请求字段、成功与失败结构，以及授权身份来自 JWT。不要仅断言源码中出现字符串。
- 用离线 AppTest 覆盖 UI 状态而非只测页面可渲染；保留后端领域测试验证服务端规则。
- 评测运行与报告排序分别在接口/测试中明确，禁止通过切片方向推测。前端缓存键包含实际查询参数、身份切换时失效。
- 公共错误只在一个层级产生通用反馈，页面处理自己的业务恢复；新功能优先使用已有认证、门禁、缓存和状态转换能力。

## 8. 全局异常与前端错误处理设计

**结论：需要收敛前端错误传播，不需要推翻现有后端异常体系。** api/main.py:237-293 已对 StaleContextError、TenantIsolationError、WorkflowBlockedError、LLMCallError 提供有语义的全局处理；路由对业务异常的局部映射也有价值。应保留这些处理，只对有证据的映射缺陷做局部调整，不机械地将每个业务方法加 try/catch，也不让同一错误在多层重复记录、包装和提示。

前端在现有 api_client 内采用唯一默认路径：_request 成功返回原 payload，失败抛出轻量 ApiError，包含 status、detail、error_code、retryable、recovery_endpoint 和网络/超时类型。域包装不把错误吞成空值，控制器/页面边界单点捕获和反馈；认证终态集中清理。它是内部错误传播方式，不是新外部 DTO 或统一成功响应。detail 保持字符串、字典或 FastAPI 的验证错误列表；只显示适合用户与当前权限的信息，不记录 token、提示词或 provider 原始异常。业务包装保留当前成功数据形状，逐一迁移失败分支，避免 None 与成功空列表混淆。

| 事件 | 现有后端/传输含义 | 建议责任与用户反馈 |
|---|---|---|
| 401 access | 尝试 refresh；refresh 明确 401/无凭证为认证终态 | 公共层清身份及租户状态并回登录；刷新网络/5xx 是临时不可用，不清凭证 |
| 403 | 权限不足或业务权限限制 | 保留状态和安全 detail；页面说明当前动作不可用，不伪装为登录过期或成功 |
| 404 | 资源不存在，跨租户也可隐藏为不存在 | 显示目标不可用或由明确允许缺省的页面处理；不得全局静默成空列表 |
| 409 stale/blocked/并发 | 需重新加载、恢复或解决冲突；具体 detail 可能不同 | 页面读取 detail/恢复信息并提供对应动作；不得统一自动重试有副作用的写入 |
| 422 | 字段/业务校验失败，detail 可为列表或对象 | 页面定位可读字段错误，保留原结构用于测试；不把列表当字符串字段假设 |
| 502 LLM | api/main.py 返回固定 error_code 和 retryable，非 provider 原文 | 页面根据 retryable 提示，但不因此自动重试结果未知的写操作 |
| 网络超时/连接故障 | 请求可能尚未送达、正在处理或响应丢失 | 区分读失败与写入结果未知；保留消息草稿及状态，不能仅凭一次 GET 推断可以安全重试 |
| 202、204、合法空列表 | 接受后台任务、无内容成功、成功但无数据 | 分别正常解析，不显示通用错误；202 只能说明已接受，不能等同完成 |

通用错误与业务页面只显示一次，必要时以 session_state 的一次性反馈跨 rerun 显示；状态轮询暂时失败时显示 unknown，不反复刷屏或产生成功提示。日志按现有安全策略记录必要的错误类型、状态和关联 ID，不新增敏感自由文本。风险处置、动作和审批的现有 403/409/422 语义应保留；没有证据时不统一更改所有 404/400。

## 9. 分阶段实施计划

实施批次与问题风险等级不同，以下顺序按依赖排列。

| 批次 | 模块与任务 | 前置条件和风险 | 完成标准 |
|---|---|---|---|
| 1 | FE-T01、FE-T11：单证据边界、聚合动作收口、可信身份及审计 | 同时改 evidence/动作副作用，注意已核验来源不覆盖；历史数据只做受控识别方案 | E1/E2、共享动作、身份、门禁和历史兼容的隔离测试全通过 |
| 2 | FE-T13 最小错误传播；FE-T08、T03、T09、T10、T12 消费错误语义 | 同步迁调用方避免 None/异常语义不兼容；切换身份清缓存 | 401/403/404/409/422/502、跨会话及失败反馈行为测试通过 |
| 3 | FE-T04、T05、S01：实验键/模式、202 状态、重入及来源展示 | 评估旧 JSON 实验、并发/崩溃窗口和未确认模式；禁止自动真实调用 | 中断恢复、原键、模式一致、切换隔离和模拟来源验收通过 |
| 4 | FE-T02、T06、T07：会话真分页、校准可达性、报告顺序 | 明确列表范围，验证 PostgreSQL/SQLite 和回退排序不同 | 45 会话、25 运行、25 报告的访问及缓存验收通过 |
| 5 | 按第 11 节验证 T14、T15；收尾契约与回归 | 使用隔离目标和锁定 Streamlit；不因候选风险先改行为 | 获得实际证据后决定是否追加改造；汇总可复现测试与未覆盖环境 |

批次 2 的公共错误实现可以先做最小基础，与批次 1 并行开发；合并发布顺序须保证 P0 修复优先，且每一批次可独立回滚。第 4 批次不等待第 3 批次的所有增强，但 FE-T06 使用的失败状态应与批次 2 的约定一致。历史证据更正是独立的受控业务操作，不随代码发布自动运行。

## 10. 测试与验收方案

以下均为**未来实施后的验收计划，本轮没有执行**。涉及写入时只使用临时 SQLite、临时目录、隔离的 PostgreSQL/Redis 测试服务和可控虚拟目标；绝不连接真实业务数据。使用项目已有隔离环境和已安装依赖，例如可在依赖就绪时采用 uv run --no-sync pytest；不通过验收命令自动安装依赖。

### 10.1 接口契约与核心闭环

| 对应问题 | 测试方法及可核对结果 |
|---|---|
| T01/T11 | 后端领域测试 + API 集成：同动作 E1/E2，仅核验 E1 后重新读取 E2=false、E2 阻断存在、动作 pending；随后 E2 核验后动作关闭、E1 身份时间不变。覆盖两个动作共享来源、无关联、过期版本、显式整组处理、dismiss、重复提交、授权与 reviewer 取 JWT、审计枚举及旧 user。 |
| T02 | 带 45 条假数据的前端/后端契约：观察实际 limit/offset 顺序和缓存键；第 21/41/45 项可访问，搜索只宣称已加载范围，筛选无匹配仍可继续加载。 |
| T03/T08 | Streamlit AppTest/控制器替身加 API：A→B 读取失败不切 ID/消息；成功以 ctx.current_state 为准；同 ID 重试与刷新生效；终态 refresh 后 A 所有租户状态清除，B 登录看不到 A；refresh 5xx/超时不清。 |
| T04/T05 | 隔离 target_http 实验 API 与前端：模拟 202 后 running→completed/failed/interrupted、worker 重启、请求/响应丢失、同键重试、异键冲突及模式变化；重入能 GET 原状态，GET 不自动 POST，已保存项不重跑，旧模式未知不猜。验证 202 丢失、预留成功到入队之间崩溃、入队明确失败时同 key/attempt 条件修复、worker 消费 running 预留时不二次增 attempt、旧 worker 尝试保存时的版本冲突，以及旧客户端兼容。双 worker 正常存活且预留未陈旧时，同时提交同键/异键仅一个成功预留并入队；另测不同进程查询陈旧心跳时不得以本地空表断言全局任务已死；running stale 的显式 POST 携原键、模式和 expected_attempt，心跳在提交前更新、attempt 被替代、双请求竞态分别验证 409/仅一者 CAS 成功；旧 worker 的错误处理和迟到保存均不能改变新 attempt/心跳。已在途目标请求模拟仍可重复，不宣称跨网络分区的外部调用恰好一次。 |
| T06 | 25 个必测运行，按 batch/run 找到每个并逐一校准；JWT reviewer、实际输出及 comment 仍必需；不可把模拟/目标失败改判成有效放行证据。 |
| T07 | 正常 SQLite/PostgreSQL 投影与强制 ctx 回退均建立 25 份以上报告；按生成时间倒序分页，可选新旧快照；重名时间戳结果稳定，报告生成不等同上线批准。 |
| T09/T12/T13 | 分别返回成功空集合、401、403、404、409（stale/blocked）、422 list/dict、502 retryable true/false、网络断连；检查数据与错误都不被混淆、不重复提示、无敏感文本。红队 0 条成功与失败明确不同。 |
| T10 | 验证明确拒绝、已提交但响应超时和仍在处理三种模拟；unknown 不自动重发、不依相同文本去重，单次 GET 未出现不被视为确定失败。 |
| S01 | llm_node 模拟实验显示配置及实际来源；未运行与混合历史不伪称已真实执行，整个用例不发真实模型调用。 |

### 10.2 回归与验收证据

- 优先扩充 tests/test_business_closure_evidence.py、tests/test_eval_batch_resilience.py、tests/test_frontend_session_list.py、tests/test_frontend_ui_smoke.py 和 tests/test_frontend_release_wiring.py 中相应行为测试；如需要新测试文件，以明确职责命名并使用隔离 fixtures。既有仅扫描源码的测试不能替代功能断言。
- 运行对应单元/领域测试，再运行使用 FastAPI 测试客户端和临时存储的接口测试、离线 Streamlit AppTest；涉及并发保存、投影和实验持久化时覆盖 SQLite 与隔离 PostgreSQL/Redis。跨服务真实目标测试仅对受控模拟服务执行，显式记录跳过的环境依赖。
- 验证原有登录/邀请、创建/切换/删除会话、材料追加、阶段推进与恢复、人工动作、风险处置、校准、报告与独立审批、service-token 发布门禁、缓存失效和多租户授权。确认未修改的能力未出现行为回归。
- 分别记录测试命令、隔离配置、结果、耗时和 skip；任何未具备 PostgreSQL/Redis、目标服务或真实模型环境的测试都标为未运行/跳过，不记为通过。上线前对部署的 API 地址、代理、状态轮询和认证边界做实际环境复核。

## 11. 待核验问题与剩余风险

### 11.1 FE-T14：同步全量真实评测的超时窗口

在隔离服务中配置可控延迟和调用计数，使多个 target_http 用例累计超过客户端读等待；分别模拟客户端断开、后端继续和取消、响应丢失、存储完成或失败。记录目标请求数、后端最终结果、是否存在外部副作用。只有获得结果后决定是否引导长真实批量改用现有实验、限制同步批量、增加可查询状态或明确幂等；不因为潜在风险预设每次超时都会重复，不自动重试，也不无限延长超时。

### 11.2 FE-T15：Streamlit widget 跨会话/重排

用 uv.lock 锁定的 Streamlit 1.57.0 和真实 AppTest 分别构造 A→B 不同默认值、相同默认值、已编辑未保存输入、风险项重排，观察 rerun 前后控件、当前 session_id 与最终 POST 的 source_id/body。验证是否在当前具体路径保持控件身份及值，再决定是否将 key 包含 session_id 和稳定 source_type/source_id 或明确清理。不能仅用手写替身模拟 Streamlit 而宣称复现。官方参考：[Streamlit widget 行为](https://docs.streamlit.io/develop/concepts/architecture/widget-behavior)。

### 11.3 真实 llm_node 实验的产品边界

当前只确认实验行对配置模式与实际模拟来源的展示不清。产品需决定是否要在实验界面提供真实 llm_node 执行、如何向用户说明真实模型调用及成本；无此决定保持现有默认模拟。单用例 llm_node 能力和发布证据规则已有各自边界，不能据此推断所有实验应自动真实执行。

### 11.4 环境及历史数据

本轮没有真实数据库、运行服务、实际 provider 或浏览器会话证据。FE-T01 历史影响数量、已批准会话是否受影响、审计信息是否足够识别每项，必须在授权环境依照第 6.1 节只读识别和逐项复核；本文件不推断数量或自动更改数据。PostgreSQL/Redis 多进程、网络断连、升级旧实验字段及服务端已发出但未落库的至少一次窗口仍需隔离验证。现有陈旧判断的在飞表是进程内状态，其他 worker 的空表不能证明执行已经停止；改造后的 status 仅提示 stale 并由用户通过现有 run 接口显式恢复，重新校验心跳和 expected_attempt。多 worker 故障与恢复必须单独验证，原子预留只约束有效预留期间的入队竞争，不保证跨故障外部 exactly-once；已知不可重复且有严重副作用的目标应先核实旧执行状态。

## 12. 最终结论

最优先修正 FE-T01：单条核验不能替其他证据生成已核验状态和审计，且必须保持高风险证据门禁与明确的整组人工操作语义。其后处理跨会话状态、认证失效、人工监督假空态，以及可恢复实验的键、模式、轮询和实际来源；再补齐真实分页、校准和报告访问。

必须保留前后端相互独立的部署、服务端角色/租户与门禁、真实目标和人工复核要求、报告与审批分离、机器 service-token 发布门禁和已有后端全局异常处理。前端只需对实际重复的传输和失败反馈做小范围收敛，现有域包装、MVC 和兼容 facade 继续承担其职责；不因行数或格式重建框架。

预期收益是让核验对象、显示数据、实际执行及用户反馈重新一致，使中断和身份失效可恢复，并为每项修改提供可验证的回归标准。额外维护成本主要是少量状态分类、实验实际模式的兼容处理和相应行为测试；FE-T14、T15 及真实 llm_node 入口在获得证据或产品决定前不列为确定改造。
