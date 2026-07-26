# Git / Docker Ignore 边界加固（2026-07-25）

## 审查结论

- Git 当前未跟踪真实 `.env`、`secrets/`、TLS 私钥、SQLite 数据库、覆盖率或缓存文件。
- `.gitignore` 已覆盖主要运行时产物，但缺少 Claude 本地设置、通用私钥/keystore、`.envrc`、扩展测试缓存与 `sqlite3` 等防御性规则。
- `.dockerignore` 存在高风险缺口：根目录真实 `secrets/` 未排除，而 Dockerfile 使用 `COPY . .`。本地 secrets 和 TLS 材料可能进入 build context，并被复制进镜像层。
- `.dockerignore` 还显式重新包含 `.env.example`，并允许测试、文档、CI、代理配置、部署配置和覆盖率 XML 等无关文件进入镜像。

## 决策

- Git 保留 `.env.example` 与 `.env.demo` 两个无真实密钥的模板，忽略其他 `.env*`、本地 agent 设置、私钥/keystore、缓存、测试报告和数据库变体。
- Docker build context 排除所有 `.env*`、`secrets/`、证书/私钥、`.streamlit/`、本地 agent 配置、测试/文档/CI/升级记录、部署配置、缓存和运行时数据。
- 保留 `examples/` 在镜像 context 中，因为 `scenarios/registry.py` 会在运行时读取场景 Markdown 输入样例。
- 保留 `api/`、`auth/`、`core/`、`frontend/`、`graph/`、`scenarios/`、`stages/`、`storage/`、`tools/`、`alembic/`、`alembic.ini`、`pyproject.toml` 与 `uv.lock`，满足 API、Streamlit 和迁移运行需求。

## 验证标准

- `git check-ignore` 必须命中 `.env`、`secrets/*`、TLS private key、数据库、coverage、agent local settings。
- `git ls-files -ci --exclude-standard` 必须为空，避免新增规则误伤已跟踪文件。
- Docker context 规则必须排除真实 `secrets/` 和所有 `.env*`。
- `git diff --check`、doc-check 与 version-check 通过。

## 验证结果

- `git ls-files -ci --exclude-standard`：空；新增规则未忽略任何已跟踪文件。
- tracked risk path 扫描：只命中预期公开模板 `.env.example` / `.env.demo`；未命中真实 secrets、证书、数据库、coverage 或缓存。
- `git log --all -- .env secrets nginx/certs data`：无路径记录，未发现这些真实运行时路径进入历史提交。
- Dockerignore 规则模拟：201 个文件进入 context、19674 个本地/缓存文件被排除；真实 `.env*`、`secrets/`、`secrets.example/`、TLS、data、agent settings、`.upgrade/`、tests/docs/scripts 均排除，`included_risky=NONE`；API、前端、Alembic、场景 manifests 与 `examples/` 保留。
- `docker compose config --quiet` 与 Lite compose config：通过。
- 实际 `docker build` 已尝试，但本机 Docker Desktop daemon 未运行，无法完成镜像层内文件复核；静态 context 断言已通过，待 daemon 可用时可补跑 `docker build`。

## 遗留风险与后续动作

在本次修复前、且本地 `secrets/` 已存在时构建的旧镜像，理论上可能包含 `/app/secrets/`，因为旧规则未排除该目录且 Dockerfile 执行 `COPY . .`。Docker daemon 恢复后应：

1. 重新构建镜像并验证 `/app/secrets`、`/app/.env*`、`/app/nginx/certs` 均不存在。
2. 删除或停止分发修复前构建的应用镜像。
3. 如果旧镜像曾被推送、导出或提供给他人，轮换其中可能包含的 API key、JWT、数据库、Redis 与 Grafana 密钥。
