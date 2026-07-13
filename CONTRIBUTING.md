# 贡献指南

感谢你考虑为 AI 工作流预验尸平台贡献代码！本指南帮助你快速参与。

## 开发环境搭建

见 [docs/local_setup.md](docs/local_setup.md)。最快方式（离线 Mock + SQLite，零外部依赖）：

```bash
cp .env.demo .env
uv sync --all-extras --frozen
uv run uvicorn api.main:app --reload --port 8000
```

## 提交前检查

每次提交前请本地运行以下三步，CI 会执行相同检查：

```bash
make lint            # ruff check + ruff format --check
make test            # uv run pytest tests/ -v
make version-check   # pyproject.toml 与 core/version.py 版本一致性
```

> `make e2e-mock` 可跑离线场景验收（注册、Mock LLM、流程），约 5 秒。

## 分支与提交约定

- 从 `main` 拉分支，命名：`feat/<topic>` / `fix/<topic>` / `docs/<topic>` / `chore/<topic>`。
- Commit message 遵循 Conventional Commits（与现有历史一致）：
  - `feat:` 新功能 / `fix:` 缺陷修复 / `docs:` 文档 / `chore:` 杂项 / `refactor:` 重构
  - 示例：`fix: 联通红队测试覆盖门控与人工动作状态`
- 一个 PR 聚焦一件事；大改动拆分为多个小 PR。

## 测试约定

- 测试位于 `tests/`，使用内存存储 + monkeypatched LLM，**不依赖** PostgreSQL / Redis / 外部 API Key。
- 新增功能须附带测试；bug 修复须附回归测试。
- `pytest` 配置见 `pyproject.toml`（`asyncio_mode = "auto"`）。

## PR 流程

1. 确保本地三步检查全绿。
2. PR 描述说明：动机、改动点、测试方式。
3. 等待 CI（lint + 单测 + docker-lite 集成冒烟）通过后合并。
4. 个人项目无强制第二人 review，但鼓励自我 review 后再合。
