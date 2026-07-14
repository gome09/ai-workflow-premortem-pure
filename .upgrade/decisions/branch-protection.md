# 分支保护策略决策

> 日期：2026-07-14
> 关联：phase-4-design.md T4.2 / spec §8

## 决策

对 main 分支开启保护，配置如下：

| 规则 | 设置 | 原因 |
|---|---|---|
| Require a pull request before merging | ✅ 开启 | 强制 PR 流程，即使个人项目也走 PR + 自我 review |
| Required reviewers | 0（个人项目无第二人） | Scorecard Code-Review 项对此部分给分（require PR 本身即得分） |
| Require status checks to pass | ✅ 开启 | lint-and-unit-tests + docker-lite-integration 必须通过 |
| Require branches to be up to date before merging | ✅ 开启 | 防止合并过时代码 |
| Allow direct pushes to main | ❌ 拒绝 | 防止绕过 PR 流程 |
| Allow force pushes | ❌ 拒绝 | 保护历史 |
| Allow deletions | ❌ 拒绝 | 保护历史 |

## 操作步骤（维护者手动执行）

分支保护是 GitHub 后台配置，无法通过代码入库实现，需维护者手动操作：

1. GitHub 仓库 → Settings → Branches → Add branch protection rule
2. Branch name pattern: `main`
3. 勾选 "Require a pull request before merging"
4. 勾选 "Require status checks to pass before merging"
   - 在 "Search for status checks" 中选择：`lint-and-unit-tests`、`docker-lite-integration`
5. 勾选 "Require branches to be up to date before merging"
6. 不勾选 "Allow force pushes"
7. 不勾选 "Allow deletions"
8. 点击 "Create" 保存

## 预期 Scorecard 影响

- Branch-Protection: 0 → 8+（开启 required status checks + require PR）
- Code-Review: 0 → 3-5（require PR before merge，虽无第二 reviewer）

## 备注

本决策在 GitHub 后台手动执行后，需在 `.upgrade/reports/` 的下一次 Scorecard 扫描报告中确认得分变化。当前仓库为 public（gome09/ai-workflow-premortem-pure），分支保护对公开仓库免费可用。
