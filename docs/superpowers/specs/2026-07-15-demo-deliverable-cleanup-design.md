# Demo 可交付化整理 — 设计文档

**日期：** 2026-07-15
**状态：** 已批准
**背景：** 离线模式四阶段 E2E 测试已 PASS（会话走完 Stage 1–4 至 `complete`，16 类面板端点全部连通）。现需整理项目使其成为可交付/可展示的 demo。

## 交付目标

**git 仓库 + zip 双轨交付**：本次初始化 git 仓库并完成干净的首次提交；zip 交付后续用 `git archive` 随时导出，不单独写打包脚本。

## A. 根目录清理

| 文件 | 处置 | 理由 |
|------|------|------|
| `..env` | 删除 | 与 `.env.demo` 逐字节相同（`diff` 已确认），误建冗余 |
| `show.md` | 移至 `docs/showcase.md` | 项目展示文档，归入 docs 体系并加入 `docs/README.md` 索引 |
| `trae_ai_risk_premortem_submission.html` | 移至 `docs/archive/` | 比赛提交页面，历史产物归档 |
| `DEMO_README.md` | 独有内容并入 `README.md` 后移至 `docs/archive/` | 独有信息：登录账号（demo@example.com / demo-password-123）、API docs 地址（`/docs`）、注意事项（端口占用/Python 版本/JWT_SECRET 提醒）。合并后归档，避免双 README 漂移 |

根目录最终保留：README / CHANGELOG / CLAUDE.md / AGENTS.md / CONTRIBUTING / SECURITY / LICENSE / Makefile / pyproject.toml / uv.lock / Dockerfile / docker-compose*.yml / alembic.ini / 三个 bat 脚本 / .env 系列（.env.demo / .env.example；.env 被 gitignore）/ .gitignore / .dockerignore。

## B. 脚本增强（Windows bat 三件套）

### B1. `start-demo.bat` 健壮化

- 前置检查：
  - `uv` 是否可用 → 否则提示先运行 `install-demo.bat` 并退出
  - `.venv` 是否存在 → 否则提示先运行 `install-demo.bat` 并退出
  - 8000 / 8501 端口是否被占用（`netstat -ano | findstr`）→ 占用则明确报错退出（提示可运行 `stop-demo.bat`），不静默失败
- `.env` 不存在时从 `.env.demo` 创建（保留现有行为）
- 启动后端后**轮询 `http://127.0.0.1:8000/health` 直到就绪**（curl，2 秒间隔，最长 60 秒），替代固定 `timeout /t 5`；超时则报错并提示查看后端窗口
- 后端就绪后启动前端，并自动打开浏览器 `http://localhost:8501`
- 保留双 `cmd /k` 窗口模式（后端/前端各一窗口，便于现场看日志）

### B2. `stop-demo.bat` 新增

- 按 8000 / 8501 端口用 `netstat -ano` 查 LISTENING 状态的 PID，`taskkill /PID <pid> /F` 终止
- 每个端口输出「已停止」或「未在运行」，幂等可重复执行

### B3. `verify-demo.bat` 新增

- 检查 `http://127.0.0.1:8000/health` → 未启动则提示先运行 `start-demo.bat` 并退出
- 运行 `uv run python scripts/live_e2e_four_stage.py`
- 按退出码明确输出 PASS / FAIL 与产物位置（`artifacts/live_e2e_four_stage/`）

### B4. Makefile 增加 `e2e-live` target

```make
e2e-live:
	uv run python scripts/live_e2e_four_stage.py
```

（供 bash 用户使用，与 verify-demo.bat 等价；需同步更新 `.PHONY`。）

### B5. 修复 `scripts/live_e2e_four_stage.py` Stage 3 统计

第 743 行统计 key 列表 `["eval_cases", "stress_tests", "test_cases"]` 补上 `test_results`，消除误导性的 "Stage 3 eval cases: 0"（实际 `stage_3_output.test_results` 有 5 项）。

## C. 文档同步

- `README.md`：
  - 快速开始新增「Windows 一键启动」小节：install-demo.bat / start-demo.bat / stop-demo.bat / verify-demo.bat 用法
  - 补登录信息（demo@example.com / demo-password-123）与 API 文档地址（http://127.0.0.1:8000/docs）
  - 合并 DEMO_README.md 的注意事项要点
- `docs/README.md`：索引补 `showcase.md` 与 archive 新条目
- `docs/startup.md`：补 Windows bat 一键启动方式
- 跑 `make doc-check` 确保无坏链（DEMO_README/show.md 被引用处需同步修正）

## D. git 初始化（干净首提）

1. `git init`
2. 复核 `.gitignore`（现有规则已覆盖 artifacts/、*.db、.venv/、.upgrade/logs 等，`.env` 已排除、`.env.demo`/`.env.example` 白名单保留）
3. **分组显式 staging**（遵守 CLAUDE.md 禁用 `git add .`）：源码包（api/ auth/ core/ stages/ graph/ storage/ tools/ scenarios/ frontend/ alembic/）→ 配置与脚本（Makefile、pyproject、bat、docker、scripts/）→ 文档（README、docs/ 等）→ 测试（tests/）→ 其余标准文件
4. 单个初始提交
5. zip 导出方式（不写脚本，记入 README 或按需执行）：`git archive -o demo.zip HEAD`

## E. 验证闭环

顺序执行，全绿后才提交：

1. `make lint`（ruff check + format --check）
2. `make e2e-full-test`（全量 pytest，Mock + SQLite）
3. `verify-demo.bat` 实测：用新 start-demo.bat 真实启动 → 四阶段 live E2E PASS → stop-demo.bat 停止
4. `make doc-check`（文档-代码一致性）

## 不做的事（YAGNI）

- 不写单独打包脚本（`git archive` 已覆盖）
- 不改业务/生产代码（唯一代码改动是 E2E 脚本统计 key 一处）
- 不动 Docker / 生产部署配置
- 不做 CI 变更

## 风险与回滚

- 所有文件移动在 git 首提交之前完成，移动本身无历史可破坏；bat 脚本改动可随时对照本文档回退。
- E2E 与 pytest 全量验证保证整理未破坏任何功能路径。
