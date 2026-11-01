# Makefile（本地开发快捷命令）

.PHONY: install install-dev clean dev-db dev-api dev-frontend docker-up docker-down lint typecheck test test-cov setup setup-win prod-preflight prod-up prod-down prod-logs demo-api demo-frontend demo-ui lite-up e2e-mock e2e-full-test e2e-business version-check doc-check audit security-check migrate migrate-new migrate-history

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
	uv run python -m uvicorn api.main:app --reload --port 8000

# 启动前端（需先启动 dev-api）
dev-frontend:
	uv run python -m streamlit run frontend/app.py --server.port 8501

demo-api:
	cp -f .env.demo .env
	uv run python -m uvicorn api.main:app --reload --port 8000

# demo-frontend 与 demo-ui 等价（均刷新 .env 后启动前端）
demo-frontend: demo-ui

demo-ui:
	cp -f .env.demo .env
	uv run python -m streamlit run frontend/app.py --server.port 8501

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

# 依赖漏洞审计（本地严格；CI 以 non-blocking 观察步骤运行）。
# PIP_AUDIT_IGNORES 显式登记已接受 advisory（复核日期 2026-10-31；2026-11-01 外部库
# 已增至 124 条 unique advisory / 19 个包，CI 不再阻断，本地仍会失败并要求分诊）：
# - pillow: CVE-2026-96640 / CVE-2026-96778 / GHSA-78g4-xqwv-q3g8（streamlit 依赖上限
#   pillow<13，上游放开后移除）
# - python-jose: PYSEC-2026-4298（无修复版本，迁移出 python-jose 前接受）
# - pyasn1: PYSEC-2026-3455 / 3456 / 3457 / CVE-2026-119194 / 119195 / 119196 / 119197
#   （python-jose 传递依赖，随 python-jose 迁移一并移除）
# - python-multipart: PYSEC-2026-3036 / 3037 / 3040（streamlit 传递依赖上限）
# 其余 advisory 一律阻断；忽略项必须在本注释登记并定期复核。
PIP_AUDIT_IGNORES ?= CVE-2026-96640 CVE-2026-96778 GHSA-78g4-xqwv-q3g8 PYSEC-2026-4298 PYSEC-2026-3455 PYSEC-2026-3456 PYSEC-2026-3457 CVE-2026-119194 CVE-2026-119195 CVE-2026-119196 CVE-2026-119197 PYSEC-2026-3036 PYSEC-2026-3037 PYSEC-2026-3040

audit:
	uv export --frozen --no-emit-project --format requirements-txt --no-hashes -o requirements-audit.txt
	uv run pip-audit --strict -r requirements-audit.txt $(addprefix --ignore-vuln ,$(PIP_AUDIT_IGNORES))

# 安全检查组合（lint + 依赖漏洞审计）。本地严格；CI 中 lint 阻断、audit 观察。
security-check: lint audit

# 版本元数据一致性检查（pyproject.toml 与 core/version.py 对齐）
version-check:
	uv run python scripts/version_check.py

# 文档-代码一致性检查（链接/make target/仓库路径）
doc-check:
	uv run python scripts/doc_consistency_check.py

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

# 全栈业务 E2E（创建 → 推进 → 暂停 → 恢复 → 回滚）；默认指向 nginx HTTPS
e2e-business:
	uv run python scripts/e2e_business_flow.py --base $${API_BASE:-https://localhost}

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
	@echo "Randomizing service secrets and Fernet encryption keys, then syncing .env..."
	./scripts/gen_secrets.sh
	@echo "Generating TLS certificates..."
	./scripts/gen_certs.sh
	@echo "Setup complete. For LLM_MODE=real, edit secrets/deepseek_api_key and secrets/tavily_api_key with real API keys."

setup-win:
	powershell -ExecutionPolicy Bypass -File .\scripts\gen_certs.ps1

lite-up:
	@if [ ! -f .env ]; then echo "Copying .env.demo to .env..."; cp .env.demo .env; fi
	docker compose -f docker-compose.lite.yml up --build

# prod-up 前置检查：secrets/ 八文件与 TLS 证书缺失时立即报错（避免晦涩的 compose 挂载失败）；
# 可生成密钥仍为 CHANGE_ME 示例值时仅警告（本地试跑生产栈仍可用）。
prod-preflight:
	@missing=0; \
	for f in jwt_secret postgres_password redis_password deepseek_api_key tavily_api_key grafana_password data_encryption_key checkpoint_encryption_key; do \
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
