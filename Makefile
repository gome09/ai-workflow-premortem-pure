# Makefile（本地开发快捷命令）

.PHONY: install dev-db dev-api dev-frontend dev docker-up docker-down lint test

# 安装依赖
install:
	uv sync

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

# 运行测试
test:
	uv run pytest tests/ -v
