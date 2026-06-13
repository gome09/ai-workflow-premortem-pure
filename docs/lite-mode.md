# Lite Mode — SQLite Backend

Lite mode 指当前代码支持的 `STORAGE_BACKEND=sqlite`。

---

## 快速开始

最简单的现成模板是 `.env.demo`：

```bash
cp .env.demo .env
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
```

如需真实 API Key，也可以从 `.env.example` 派生并手工加入：

```bash
STORAGE_BACKEND=sqlite
UVICORN_WORKERS=1
```

`.env.demo` 已默认包含：
- `LLM_MODE=mock`
- `STORAGE_BACKEND=sqlite`
- `DEFAULT_SCENARIO_ID=generic_rag_demo`

---

## Docker 轻量模式

仓库里存在：

```bash
cp .env.demo .env
docker compose -f docker-compose.lite.yml up --build
```

该组合默认不需要真实 API Key、外网、PostgreSQL、Redis 或 TLS 证书。

当前仓库里不存在 `.env.lite`，旧文档如有该文件名，均以 `.env.demo` 或 `.env.example` 替代。

---

## 适用边界

- 适合本地演示
- 适合论文答辩或功能展示
- 适合无 PostgreSQL / Redis 的轻量开发

不适合：
- 多进程高并发
- 生产部署
- 需要独立 Redis 缓存的一致性场景

---

## 代码对应关系

| 文件 | 用途 |
|------|------|
| `storage/backends/sqlite_store.py` | SQLite 会话存储 |
| `storage/backends/memory_cache.py` | 进程内缓存 |
| `storage/session_store.py` | 后端工厂 |
| `storage/cache.py` | 缓存工厂 |
| `docker-compose.lite.yml` | 轻量 Docker 入口 |
