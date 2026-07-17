# Makefile（本地开发快捷命令）

.PHONY: install install-dev clean dev-db dev-api dev-frontend docker-up docker-down lint typecheck test test-cov setup setup-win prod-preflight prod-up prod-down prod-logs demo-api demo-frontend demo-ui lite-up e2e-mock e2e-full-test version-check doc-check audit security-check migrate migrate-new migrate-history

# 安装依赖
install:
	uv sync

# 清理缓存、临时数据库和编译产物
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	rm -f data/*.db data/*.db-shm data/*.db-wal
	@echo "Clean complete."

# 启动本地数据库（仅 postgres + redis）

install-dev:
	uv sync --all-extras --frozen

dev-db:
	docker compose up postgres redis -d

# 启动 API（需先启动 dev-db）
dev-api:
	uvicorn api.main:app --reload --port 8000

# 启动前端（需先启动 dev-api）
dev-frontend:
	streamlit run frontend/app.py --server.port 8501

demo-api:
	cp -f .env.demo .env
	uvicorn api.main:app --reload --port 8000

# demo-frontend 与 demo-ui 等价（均刷新 .env 后启动前端）
demo-frontend: demo-ui

demo-ui:
	cp -f .env.demo .env
	streamlit run frontend/app.py --server.port 8501

# 完整 Docker 启动
docker-up:
	docker compose up --build -d

# 停止并清理
docker-down:
	docker compose down

# 代码检查
lint:
	uv run ruff check .
	uv run ruff format --check .

# mypy 类型检查（全局宽松 + core.gates/graph 收紧，配置见 pyproject.toml）
typecheck:
	uv run mypy

# 依赖漏洞审计（非阻断）
audit:
	uv run pip-audit --strict

# SAST + 漏洞审计组合
security-check: lint audit

# 版本元数据一致性检查（pyproject.toml 与 core/version.py 对齐）
version-check:
	python scripts/version_check.py

# 文档-代码一致性检查（链接/make target/仓库路径）
doc-check:
	python scripts/doc_consistency_check.py

# 运行测试
test:
	uv run pytest tests/ -v

# 带覆盖率的测试（CI 用；本地看行覆盖明细可加 --cov-report=html）
test-cov:
	uv run pytest tests/ --cov --cov-report=term --cov-report=xml -q

# ── 答辩验收 ────────────────────────────────────────────────────────────────

# Mock + SQLite 离线验收测试（场景注册、Mock LLM、场景流程）
e2e-mock:
	cp -f .env.demo .env
	uv run pytest tests/test_scenarios_registry.py tests/test_scenario_session_flow.py tests/test_mock_llm_mode.py -v

# 全量测试（Mock + SQLite，无需外部依赖）
e2e-full-test:
	cp -f .env.demo .env
	uv run pytest tests/ -q

# ── Database migrations ──────────────────────────────────────────────────────

migrate:
	docker compose exec api python -m alembic upgrade head

migrate-new:
	docker compose exec api python -m alembic revision --autogenerate -m "$(msg)"

migrate-history:
	docker compose exec api python -m alembic history

# ── Production startup ───────────────────────────────────────────────────────

setup:
	@if [ ! -f .env ]; then echo "Copying .env.example to .env..."; cp .env.example .env; fi
	@if [ ! -d secrets ]; then echo "Copying secrets.example/ to secrets/..."; cp -r secrets.example secrets; fi
	@echo "Randomizing generatable secrets (jwt/postgres/redis/grafana) and syncing .env..."
	./scripts/gen_secrets.sh
	@echo "Generating TLS certificates..."
	./scripts/gen_certs.sh
	@echo "Setup complete. For LLM_MODE=real, edit secrets/deepseek_api_key and secrets/tavily_api_key with real API keys."

setup-win:
	powershell -ExecutionPolicy Bypass -File .\scripts\gen_certs.ps1

lite-up:
	@if [ ! -f .env ]; then echo "Copying .env.demo to .env..."; cp .env.demo .env; fi
	docker compose -f docker-compose.lite.yml up --build

# prod-up 前置检查：secrets/ 六文件与 TLS 证书缺失时立即报错（避免晦涩的 compose 挂载失败）；
# 可生成密钥仍为 CHANGE_ME 示例值时仅警告（本地试跑生产栈仍可用）。
prod-preflight:
	@missing=0; \
	for f in jwt_secret postgres_password redis_password deepseek_api_key tavily_api_key grafana_password; do \
		if [ ! -f "secrets/$$f" ]; then echo "ERROR: secrets/$$f missing"; missing=1; fi; \
	done; \
	if [ ! -f nginx/certs/server.crt ] || [ ! -f nginx/certs/server.key ]; then \
		echo "ERROR: nginx/certs/server.crt|key missing"; missing=1; fi; \
	if [ "$$missing" = "1" ]; then \
		echo ""; echo "Run 'make setup' first to provision secrets/ and TLS certs."; exit 1; fi
	@for f in jwt_secret postgres_password redis_password grafana_password; do \
		if grep -q '^CHANGE_ME' "secrets/$$f" 2>/dev/null; then \
			echo "WARNING: secrets/$$f still holds the example placeholder — run ./scripts/gen_secrets.sh"; fi; \
	done

prod-up: prod-preflight
	@if [ ! -f .env ]; then echo "Copying .env.example to .env..."; cp .env.example .env; fi
	docker compose -f docker-compose.yml up --build -d

prod-down:
	docker compose -f docker-compose.yml down

prod-logs:
	docker compose -f docker-compose.yml logs -f --tail=100
