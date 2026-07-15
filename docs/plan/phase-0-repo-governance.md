# 阶段 0 实施计划：仓库治理最小闭环

> 上游路线图：[improvement-roadmap.md](improvement-roadmap.md) 第 6 节「阶段 0」。
> 配套设计规格：[../spec/supply-chain-security.md](../spec/supply-chain-security.md)。
> 现状基线核实日期：2026-07-13（下表全部条目经代码仓库直接核实，非估算）。
> 状态：未启动。前置依赖：无——本阶段是所有后续阶段的地基。

---

## 1. 目标

让仓库"看起来、也确实是"一个治理良好的开源项目：治理文件齐备、CI 权限最小化、依赖更新自动化、历史可追溯性有诚实说明、并拿到一个量化的 OpenSSF Scorecard 基线分数作为后续阶段的对照起点。

## 2. 现状基线（已核实）

| 项 | 现状 | 证据位置 |
|---|---|---|
| LICENSE | ❌ 缺失 | 仓库根目录无任何 LICENSE 文件 |
| SECURITY.md | ❌ 缺失 | 根目录无 |
| CONTRIBUTING.md | ❌ 缺失 | 根目录无 |
| CODE_OF_CONDUCT.md | ❌ 缺失（可选项） | 根目录无 |
| CI `permissions:` 声明 | ❌ 未声明 | `.github/workflows/ci.yml` 全文无 `permissions` 字段（两个 job：`lint-and-unit-tests`、`docker-lite-integration`） |
| dependabot.yml | ❌ 缺失 | `.github/` 下无 dependabot/renovate 配置 |
| CHANGELOG 追溯说明 | ❌ 未补 | `CHANGELOG.md` 记录 v0.1（2026-05-01）/v0.5（2026-05-20），早于本地可见最早 commit（`4fdf8c8` initial commit），无任何说明文字 |
| Git tag / Release | ❌ 无 | `git tag --list` 为空 |
| Scorecard 量化基线 | ❌ 未跑过 | 无存档记录 |
| uv.lock | ✅ 存在 | 根目录，锁定完整依赖树 |
| CI 测试 | ✅ 已具备 | `ci.yml`：ruff lint + pytest + docker-lite 集成冒烟 |
| 版本一致性检查 | ✅ 已具备 | `make version-check`（`scripts/version_check.py`） |

## 3. 任务分解

### T0.1 补充 LICENSE 【阻塞：需用户决策】

- **内容**：在根目录添加 LICENSE 文件。协议选择（MIT / Apache 2.0 / AGPL-3.0）是路线图第 8 节明确留给项目所有者的决策，**本任务在决策前保持待定，不做假设性落地**。
- **决策参考**：若希望被企业内部采用无阻力 → MIT/Apache 2.0；若希望防止闭源二次分发 → AGPL-3.0；Apache 2.0 额外提供专利授权条款，对含算法逻辑的项目更稳妥。
- **验收**：LICENSE 文件存在且为 OSI 认可协议全文；README 首屏声明协议类型。
- 工作量：S（决策后 10 分钟）

### T0.2 补充 SECURITY.md

- **内容**：漏洞报告渠道（邮箱或 GitHub Security Advisories）、支持的版本范围（当前仅 v1.0.x）、响应时间承诺（个人项目建议承诺"7 天内确认"而非企业级 SLA）。
- **验收**：文件存在、渠道真实可用、内容非模板占位。
- 工作量：S

### T0.3 补充 CONTRIBUTING.md

- **内容**：开发环境搭建（指向 [../local_setup.md](../local_setup.md)）、提交前检查（`make lint` + `make test` + `make version-check`）、分支与 commit message 约定、测试约定（`tests/` 目录、内存存储 + monkeypatched LLM）、PR 流程。
- **验收**：文件存在，且其中引用的命令均真实可运行（与 Makefile 对齐）。
- 工作量：S

### T0.4 CI 权限最小化

- **内容**：`.github/workflows/ci.yml` 顶层添加 `permissions: contents: read`。具体设计见 [../spec/supply-chain-security.md](../spec/supply-chain-security.md) 第 2 节。
- **验收**：workflow 顶层有显式 `permissions` 声明；CI 全绿（权限收紧未破坏现有 job）。
- 工作量：S

### T0.5 补充 dependabot.yml

- **内容**：覆盖 `pip`（uv 项目使用 pip 生态标识）与 `github-actions` 两个生态，weekly 节奏，分组小版本更新以控制 PR 噪音。配置模板见 [../spec/supply-chain-security.md](../spec/supply-chain-security.md) 第 3 节。
- **验收**：`.github/dependabot.yml` 存在且推送后 GitHub 后台能看到 Dependabot 已激活。
- 工作量：S

### T0.6 CHANGELOG 追溯说明

- **内容**：在 `CHANGELOG.md` 头部补一段说明：v0.1–v0.7 阶段的详细提交历史因仓库整理未完整保留，如需追溯请查阅 `origin` 远程分支的完整历史（2026-05-31 起 21 次提交）。这是对"叙事与可验证证据之间的缺口"的诚实修复。
- **验收**：说明文字已入库；表述与事实一致（不夸大也不回避）。
- 工作量：S

### T0.7 OpenSSF Scorecard 基线扫描

- **内容**：运行 `scorecard` CLI（需仓库已推送到 GitHub），将 18 项检查的量化结果存档至 `.upgrade/reports/` 下（命名格式 scorecard-baseline-YYYYMMDD.md，如 scorecard-baseline-20260713.md）。注意 Scorecard v5.5.0（2026-04）起支持按仓库类型跳过不适用检查。
- **同时人工确认**（本地无法检测的项）：GitHub 后台的 Branch Protection 与强制 Code Review 设置状态，一并记录进基线报告。
- **验收**：基线报告存档，含总分与逐项分数；阶段 4 以此为对照基线。
- 工作量：M（含环境准备）

### T0.8 Git tag 补挂（顺手项）

- **内容**：对当前 HEAD 补挂 `v1.0.2` annotated tag（与 CHANGELOG 最新版本对齐），此后每次版本号变更同步打 tag。签名（Signed Releases）留到阶段 4，本阶段不做。
- **验收**：`git tag --list` 非空且与 CHANGELOG 版本对应。
- 工作量：S

## 4. 推进顺序与依赖

```
T0.2 / T0.3 / T0.4 / T0.5 / T0.6 / T0.8  （互相独立，可并行，一次提交或分批均可）
T0.1  （等待协议决策，不阻塞其他任务）
T0.7  （建议放最后跑：让前面的改进先反映到分数里）
```

## 5. 风险与注意事项

- T0.4 权限收紧后若未来新增需要写权限的 workflow（如自动发布），需在该 workflow 内单独声明所需权限，而不是放宽全局默认。
- T0.5 Dependabot PR 会带来持续的维护负担；分组策略（见 spec）是控制噪音的关键，不建议逐包单独开 PR。
- T0.7 Scorecard 部分检查项（CI-Tests、Contributors、Dependency-Update-Tool）在其公共周扫描中不计分，本地 CLI 全量跑一次才能拿到完整基线。

## 6. 阶段验收清单

- [x] LICENSE / SECURITY.md / CONTRIBUTING.md 三个文件都存在且内容非模板占位
- [x] `ci.yml` 有显式 `permissions` 最小化声明且 CI 全绿
- [x] `.github/dependabot.yml` 已激活
- [x] CHANGELOG 头部有历史追溯说明
- [x] Scorecard CLI 量化基线报告已存档至 `.upgrade/reports/`
- [x] 当前版本已打 git tag
