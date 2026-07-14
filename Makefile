# Makefile（本地开发快捷命令）

.PHONY: install clean dev-db dev-api dev-frontend dev docker-up docker-down lint test setup setup-win prod-up prod-down prod-logs demo-api demo-frontend demo-ui lite-up e2e-mock e2e-full-test version-check doc-check audit security-check

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

demo-frontend:
	streamlit run frontend/app.py --server.port 8501

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
	@echo "Generating TLS certificates..."
	./scripts/gen_certs.sh
	@echo "Setup complete. Edit secrets/deepseek_api_key and secrets/tavily_api_key with real API keys."

setup-win:
	powershell -ExecutionPolicy Bypass -File .\scripts\gen_certs.ps1

lite-up:
	@if [ ! -f .env ]; then echo "Copying .env.demo to .env..."; cp .env.demo .env; fi
	docker compose -f docker-compose.lite.yml up --build

prod-up:
	@if [ ! -f .env ]; then echo "Copying .env.example to .env..."; cp .env.example .env; fi
	docker compose -f docker-compose.yml up --build -d

prod-down:
	docker compose -f docker-compose.yml down

prod-logs:
	docker compose -f docker-compose.yml logs -f --tail=100
