# 阶段 4 实施计划：开源社区打磨（持续性工作）

> 上游路线图：[improvement-roadmap.md](improvement-roadmap.md) 第 6 节「阶段 4」。
> 配套设计规格：[../spec/supply-chain-security.md](../spec/supply-chain-security.md) 第 6-8 节。
> 状态：未启动。前置依赖：阶段 0 的 Scorecard 基线（T0.7）是本阶段所有量化目标的对照起点。本阶段与阶段 1-3 并行推进，没有终点。

---

## 1. 目标

Scorecard 分数相对阶段 0 基线持续爬升、文档与代码不再靠事后人工对账、仓库达到"外部贡献者可以放心参与"的工程健康度。

## 2. 现状基线

- Scorecard 预估：18 项中明确达标约 4-5 项（详表见 [../spec/supply-chain-security.md](../spec/supply-chain-security.md) 第 6 节），量化基线待阶段 0 实测。
- 已知文档腐烂样本：`docs/spec/stage3-risk-adaptive-gate.md` 中存在指向 `../archive/verification-reports/` 的悬空引用（`.upgrade/MANIFEST.md` 已记录为既有问题）；`.upgrade/decisions/RELEASE_CLEANUP.md` 记录过一整轮文档-代码不一致修复。
- CONTRIBUTING.md 将由阶段 0 产出初版，本阶段负责随项目演进维护。

## 3. 任务分解

### T4.1 文档-代码一致性检查 CI 化

- **内容**：`scripts/doc_consistency_check.py` + `make doc-check` + CI 步骤（链接存在性/make target 存在性/仓库路径存在性三类规则）。设计见 [../spec/supply-chain-security.md](../spec/supply-chain-security.md) 第 7 节。
- **第一批修复对象**：stage3 文档的悬空 archive 引用（修链或补档，二选一并记录决策）。
- **验收**：CI 真实拦截过至少一次坏链（可用故意引入的测试 PR 验证）；存量坏链清零后转为强制（非 `continue-on-error`）。
- 工作量：M

### T4.2 分支保护与评审流程

- **内容**：GitHub 后台开启 main 分支保护（required status checks：lint + 单测 job；require PR before merge）。个人项目无第二评审人，采用"PR + 自我 review"模式。设计见 supply-chain spec 第 8 节。
- **验收**：直接 push main 被拒绝；Scorecard Branch-Protection 项得分提升。
- 工作量：S

### T4.3 Scorecard 持续爬升机制

- **内容**：每完成一个阶段重跑 `scorecard` CLI 存档对照（`.upgrade/reports/`）；可选接入 Scorecard GitHub Action 周期扫描（其需要的 workflow 权限按最小化单独声明）。
- **验收**：至少两次跨阶段的分数记录且趋势向上。
- 工作量：S（机制性任务）

### T4.4 锦上添花项（视精力，明确不承诺）

- Signed Releases（`gh release create` + 校验和起步，Sigstore 仅在有真实分发需求时）。
- CII/OpenSSF Best Practices Badge 申请。
- 发布为可安装包（Packaging）——仅当出现"其他团队想复用"的真实需求。
- **决策原则**：这三项在没有外部用户信号前不投入；Star/Fork 等虚荣指标不追逐（路线图 5.2 节结论保持）。

### T4.5 社区响应约定

- **内容**：issue/PR 模板（`.github/ISSUE_TEMPLATE/`、`PULL_REQUEST_TEMPLATE.md`）+ 在 CONTRIBUTING.md 声明响应节奏（个人业余维护，尽力 7 天内响应）。
- **验收**：模板存在；承诺与实际维护能力相符（不过度承诺）。
- 工作量：S

## 4. 推进顺序

```
T4.1（价值最高，优先）→ 其余任务无序，随时间碎片推进
T4.3 在每个其他阶段收尾时触发一次
```

## 5. 风险与注意事项

- 本阶段最大的风险是"过度工程"：所有任务都应服务于"工程健康度可验证"，而不是堆徽章。T4.4 的不承诺清单就是防线。
- doc-check 规则过严会把文档写作变成负担——启发式规则宁松勿严，误报率高于约 5% 就收窄规则。

## 6. 阶段验收清单（滚动）

- [ ] doc-check 进 CI 且转为强制
- [ ] stage3 文档悬空引用清除
- [ ] main 分支保护开启
- [ ] Scorecard 分数相比阶段 0 基线有实质提升且有至少两次记录
- [ ] issue/PR 模板与响应约定就位
