# 决策记录：OpenSSF Scorecard 基线

> 日期：2026-07-13
> 关联任务：Phase 0 T0.7

## 决策 1：本地 CLI + GitHub Actions 双路径扫描

**背景**：本地 scorecard CLI 因 GitHub API 速率限制无法远程扫描，且无 GitHub PAT 可用。

**决策**：采用双路径——
1. 本地 `--local=.` 扫描获取可本地评估的 10 项检查
2. GitHub Actions workflow 使用 `GITHUB_TOKEN` 执行全量 18 项远程扫描

**理由**：本地扫描虽受限于 `.venv/` 误判，但提供即时基线；远端扫描提供权威全量结果。

**代价**：远端 artifact 需认证下载，当前会话无法获取精确分数，采用推断预期值。

## 决策 2：Pinned-Dependencies 保持 `>=` 声明

**背景**：Scorecard Pinned-Dependencies 检查因 `pyproject.toml` 使用 `>=` 下限而给 0 分。

**决策**：保持现状，不改为 hash pin。

**理由**：
- `uv.lock` 保证可复现性，等效于 hash pin 的实际效果
- hash pin 与 uv 工作流冲突（`uv add` / `uv upgrade` 会重写 hash）
- 远端 Scorecard 可识别 lock 文件给予部分分数

## 决策 3：Scorecard 工作流保留 push 触发

**背景**：原设计为 `workflow_dispatch` 仅手动触发，但无 `gh` CLI 或 PAT 无法远程触发。

**决策**：保留 `push` + `workflow_dispatch` 双触发。

**理由**：Phase 0 基线需至少一次自动运行；后续可移除 `push` 触发以减少 CI 消耗。

**后续**：Phase 1 稳定后改为 `workflow_dispatch` + `schedule: cron` 周扫描。
