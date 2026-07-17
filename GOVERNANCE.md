# 项目治理

## 现行模式：单一维护者（BDFL）

本项目当前由单一维护者 [@gome09](https://github.com/gome09) 维护，持有仓库全部管理权限与技术方向最终决定权。

## 决策方式

- 常规改动：直接以 PR + CI 全绿合入 main（受分支保护约束）。
- 重大决策（架构、合规映射口径、破坏性变更）：决策记录写入 `.upgrade/decisions/` 或 `docs/plan/`，理由留档可追溯。
- 外部贡献：按 [CONTRIBUTING.md](CONTRIBUTING.md) 提交 Issue/PR，维护者承诺 7 个自然日内响应。

## 如何成为维护者

持续提交高质量 PR（3 个以上被合入）并表达长期维护意愿后，可在 Issue 中申请 maintainer 权限，由现任维护者评估授予 triage/write 权限。

## 项目连续性

若项目获得稳定外部用户，维护者将把仓库迁移至 GitHub Organization 并至少增加一名备份管理员，避免单点风险。
