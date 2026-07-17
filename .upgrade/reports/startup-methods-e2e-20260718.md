# 四种启动方式全流程测试报告（2026-07-18）

> 测试执行：Claude Code 会话（Windows 11 / Docker Desktop 28.3.2 / uv 0.11.12 / Python 3.12 venv）
> 结论：**四种启动方式全部 PASS**；发现并修复 6 处缺陷（3 阻塞类 + 3 前后端语义一致性类），全量回归 650 passed, 1 skipped。

---

## 1. 测试范围与方法

对仓库支持的四种启动方式逐一冷启动，验证前后端链路：

- **API 冒烟**：auth（注册/登录）→ 建会话 → chat 推进 → stage-readiness / gate-report → 导出报告
- **UI 驱动**：Playwright（chromium headless）驱动 Streamlit 前端真实点击——新建会话、处理人工动作（批准/核验证据/批准红队用例）、阶段推进，截图核对渲染
- **后台监控**：uvicorn / docker logs 挂后台任务实时检查 4xx/5xx、WARNING、Traceback
- **镜像卫生**：Docker 构建使用 `--no-cache`，测试前清理旧 SQLite 数据库与项目容器/卷，避免旧产物污染

## 2. 各方式测试结果

### 方式1：离线演示模式（uv + mock LLM + SQLite）— ✅ PASS

| 验证项 | 结果 |
|---|---|
| `uvicorn api.main:app`（.env.demo 配置） | ✅ /health/live 200，version=1.3.0；/health/ready postgres=ok, redis=skipped (sqlite mode) |
| Streamlit :8501 | ✅ 200，欢迎页/侧栏正常渲染 |
| **API 四阶段全流程** | ✅ init → s1_running → s1_review →（resolve 4 动作）→ s2 →（1 动作）→ s3 →（1 动作）→ s4 →（2 动作）→ **complete**；四阶段 gate-report 全部 overall=passed（13 规则）|
| 终态数据 | ✅ stage_1..4_output 齐全；evidence=2, safety=3, eval_cases=2, traces=38, audits=30, actions=8（全 resolved）|
| 报告导出 | ✅ JSON 53 keys；Markdown 11,549 字符；快照 RPT-dfa739a9 创建成功 |
| **UI 驱动全流程** | ✅ 16 轮浏览器交互（批准继续 ×5 / 核验证据 ×2 / 批准红队用例 ×1 / chat 推进 ×8），侧栏进度 100% · 已完成，四阶段圆点全绿 |
| 后端日志 | ✅ 0 条 5xx，无未捕获异常 |

### 方式2：Docker Lite（SQLite + Mock，2 容器）— ✅ PASS

| 验证项 | 结果 |
|---|---|
| 镜像构建 | ✅ `docker compose -f docker-compose.lite.yml build --no-cache` 全新构建 |
| 容器健康 | ✅ api + frontend 均 Up；/health/ready ready |
| API 冒烟 | ✅ 登录 200 → 建会话 → chat 推进至 s1_running → readiness lifecycle=running |
| 前端（浏览器） | ✅ 会话列表正常加载（含跨启动方式共享的 data/workflow.db 历史会话）|
| 清理 | ✅ `compose down` 无残留容器 |

### 方式3：本地混合开发模式（容器 DB 临时端口 + 本机应用）— ✅ PASS

按要求使用**临时端口**避开本机 Windows 原生 PostgreSQL 的 5432 冲突：

| 验证项 | 结果 |
|---|---|
| postgres:16-alpine @ **15432**、redis:7-alpine @ **16379**（独立容器） | ✅ pg_isready / PONG |
| .env 覆写（STORAGE_BACKEND=postgres + 临时端口 + 密码） | ✅ |
| 后端启动 | ✅ /health/ready postgres=ok, **redis=ok** |
| alembic 自动迁移 | ✅ 启动时建齐 21 张表（sessions/human_actions/evidence_sources/eval_*/redteam_cases/llm_traces/audit_events…） |
| 数据落库验证 | ✅ 建会话 + chat 后 `SELECT count(*) FROM sessions` = 1；redis dbsize=3 |
| 前端（浏览器） | ✅ 会话列表来自 postgres（仅 1 条，与 sqlite 历史隔离） |
| 清理 | ✅ 临时容器已删除；.env 还原 demo 配置 |

### 方式4：生产模式（7 服务栈 + TLS + 监控）— ✅ PASS（修复 2 缺陷后）

secrets 按要求自行创建：`cp -r secrets.example secrets && ./scripts/gen_secrets.sh`（jwt/postgres/redis/grafana 随机化并同步 .env；LLM_MODE 改 mock 以离线验证）。

| 验证项 | 结果 |
|---|---|
| prod-preflight 等价检查 | ✅ 六 secrets 文件 + nginx/certs 齐备，无 CHANGE_ME 占位 |
| 7 容器（postgres/redis/api/frontend/nginx/prometheus/grafana） | ✅ 全部 Up，api/postgres/redis healthy |
| HTTP→HTTPS 重定向 | ✅ 301 → https://localhost/ |
| nginx 路由 | ✅ `/api/` → 后端（/api/health/live 200, version=1.3.0）；`/` → Streamlit（浏览器渲染正常，无连接错误）|
| HTTPS 全链路冒烟 | ✅ 注册/登录 200 → 建会话 → chat s1_running → readiness 200 → gate-report 200 |
| 监控栈 | ✅ Prometheus target `api` = up；Grafana /api/health database=ok v10.4.0 |
| 空库冷启动复测（down -v 后重启） | ✅ 双 worker 迁移无竞态（修复后），App started ×2 |
| 清理 | ✅ compose down；.env 还原 |

## 3. 发现并修复的缺陷

### 阻塞类

| # | 位置 | 现象 | 根因 | 修复 |
|---|---|---|---|---|
| 1 | `frontend/app.py` `ensure_auth` | 前端所有请求 401，页面全站报错 | demo 账号已存在时仍先调 `/auth/register`，触发 5/hour 限流得 429，原逻辑仅处理 409 | 改为**先登录、失败再注册**；429 也回退登录 |
| 2 | `scripts/gen_secrets.sh` | 生产栈 redis 认证失败（invalid username-password pair），/health/ready degraded | Windows Git Bash 下 openssl 输出 CRLF，secret 文件含 `\r`：redis `--requirepass $(cat …)` 吃掉 `\r` 而 .env 同步值保留，两边密码不一致 | 生成时 `tr -d '\r\n'`；存量 secrets 已清理 |
| 3 | `storage/backends/postgres.py` `initialize` | 空库冷启动 `UVICORN_WORKERS=2` 时 worker 崩溃：`UniqueViolation: pg_type_typname_nsp_index (alembic_version)` | 多 worker 并发执行 `alembic upgrade head`，竞态创建 alembic_version 表 | 用 `pg_advisory_lock` 串行化迁移；down -v 后冷启动复测通过 |

### 前后端语义一致性类

| # | 位置 | 现象 | 修复 |
|---|---|---|---|
| 4 | `frontend/app.py` 主区路由 | `nav_page` 全代码无赋值点 → **治理总览页永远不可达**，`/governance/*` 三端点前端从不调用 | 侧栏新增「会话工作台 / 治理总览」radio 导航；`governance_overview.py` 同时补齐 `reports_exported` 指标、`state_distribution` 柱图、gate-trends 周明细（evaluations/passed/top_blocking_rules） |
| 5 | `api/main.py` `/health` | 前端侧栏读 `interrupt_adapter_status` 但后端从未返回 → 恒显"中断适配器：未知" | 后端补齐该字段（single_step→`disabled`/"未启用"，langgraph_interrupt→`healthy`/"正常"） |
| 6 | `frontend/app.py` 评测/审计面板 | 后端已返回但前端丢弃的字段 | 补展示：EvalCase `pass_criteria`、EvalRun `judge_reason`/`violated_criteria`、实验 `human_disagreement_rate`（人工校准分歧率）、审计事件 `before/after_snapshot`（并排 diff 视图） |

## 4. 回归验证

| 检查 | 结果 |
|---|---|
| `uv run pytest tests/ -q` | ✅ 650 passed, 1 skipped |
| `ruff check` + `ruff format --check`（改动文件） | ✅ clean |
| 浏览器复测（修复后） | ✅ 中断适配器显示"未启用"；治理总览页可达且四指标/双分布/趋势/积压全渲染；评测面板"通过标准"可见；审计历史含快照入口 |

## 5. 遗留观察项（未修，非阻塞）

1. **死代码**：`frontend/components/` 下 8 个英文版 panel（gate_panel / trace_panel / action_queue / audit_timeline / evidence_panel / safety_panel / eval_panel / eval_experiment_panel / gate_diagnosis）与 `frontend/api_client.py`、`frontend/state.py` 定义后从未被 app.py 调用——真实 UI 全部内联在 app.py。建议后续删除或接线，避免双实现漂移。
2. **后端能力无前端入口**：`/traces`、`/eval-judgments`、`/human-calibrations`、`/eval-runs/{id}/calibrate`、`/eval-experiments/{id}/comparison`(GET)、`/actions/{id}` 单查、`/evidence/{id}` 单查。数据可经报告 JSON 导出获得，非功能缺失，但 LLMTrace / EvalJudgment / HumanCalibration 三类一等公民记录在 UI 完全不可见。
3. 审计历史仅显示最近 30 条；报告面板各列表截断前 5 条（完整数据可下载 JSON，信息不丢失）。

## 6. 测试环境备注

- 本机 5432 被 Windows 原生 postgres.exe 服务占用——方式3 必须临时端口（15432/16379）或改映射；方式4 不受影响（prod compose 不映射 DB 端口到宿主机）。
- `make` 未安装：所有 Makefile target 以等价命令手动执行，行为与 target 定义一致。
- Playwright 为本次测试临时安装（pip install playwright + chromium headless shell），非项目依赖。
