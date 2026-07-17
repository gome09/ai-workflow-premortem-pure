# 公开前检查报告（2026-07-17）

> 父计划：`.upgrade/plans/2026-07-17-formal-project-uplift.md` Task 15；实施方案：`.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md` E1。
> 结论先行：**三项检查全部通过（含 2 类已知良性命中，判定留档如下），可以公开**。公开动作与后台配置由维护者按文末清单人工执行。

## 1. 全历史敏感信息扫描 — ✅ 通过（仅已知良性项）

- 密钥模式扫描（api_key/secret/password/token 赋值 + 排除模板类关键词）：命中 `DEMO_PASSWORD = "demo-password-123"` 共 5 行——`scripts/live_e2e_four_stage.py` 本地 e2e 演示凭据，源码行尾带 `noqa: S105 # demo credential for local e2e, not a real secret`，非真实密钥，无需处置。
- 高熵前缀扫描（sk- / ghp_ / AKIA）：命中 `CHANGE_ME_sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 共 2 行——`secrets.example/deepseek_api_key` 模板占位符，无需处置。
- 上述之外命中：**0**。无真实密钥，无需吊销，无需历史重写。

```bash
$ git log --all -p | grep -inE "(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}" | grep -ivE "(example|placeholder|your[_-]|template|fixture|mock|test|<.*>|\{\{)" | head -50
59311:+DEMO_PASSWORD = "demo-password-123"  # noqa: S105  # demo credential for local e2e, not a real secret
97097:-DEMO_PASSWORD = "demo-password-123"
97098:+DEMO_PASSWORD = "demo-password-123"  # noqa: S105  # demo credential for local e2e, not a real secret
106504:+DEMO_PASSWORD = "demo-password-123"
113430:+DEMO_PASSWORD = "demo-password-123"

$ git log --all -p | grep -inE "(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})" | head -20
60144:+CHANGE_ME_sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
144462:+CHANGE_ME_sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## 2. 工作区与敏感文件检查 — ✅ 通过

- `secrets/`、`data/`、`.env` 均被 .gitignore 覆盖（:44 / :77 / :12）；`docs/internal/`、`secrets/` 目录不存在。
- `git ls-files` 无 `docs/internal`、`secrets/`、根 `.env` 被跟踪。
- 已审查接受的例外：`.env.demo` / `.env.example` 有意跟踪（`.gitignore` `!` 豁免），内含值全部为 mock/演示占位（JWT_SECRET 带"仅用于本地演示"注释）；`secrets.example/` 为模板目录，6 个文件均为 CHANGE_ME 占位。

```bash
$ git status --short
?? .upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md

$ git check-ignore -v secrets/ data/ .env
.gitignore:44:secrets/	secrets/
.gitignore:77:	data/
.gitignore:12:.env	.env

$ ls docs/internal/ 2>/dev/null && echo "WARNING: docs/internal exists (gitignored, confirm not committed)" || echo OK
OK

$ git ls-files | grep -E "^docs/internal|^secrets/|\.env$" && echo "LEAK: tracked sensitive file" || echo OK
OK
```

## 3. 提交邮箱核查 — ⚠️ 提示项（不阻塞公开）

- 全历史唯一提交邮箱：`3567039961@qq.com`（author = committer）。
- 维护者决策项：如不愿公开个人邮箱，可开启 GitHub email privacy（Settings → Emails → Keep my email addresses private）并将本地 `git config user.email` 改为 noreply 地址——只影响未来提交；历史邮箱无法追改（除非重写历史，默认不做）。

```bash
$ git log --format="%ae %ce" | sort -u
3567039961@qq.com 3567039961@qq.com
```

## 4. CI 门槛转正评估结论（父计划 Task 16 标题承诺，Wave E 落账）

| 步骤 | 现状 | 结论 | 依据 |
|---|---|---|---|
| doc-check | non-blocking（ci.yml `continue-on-error`） | **本 Wave 转强制**（E2 落地） | 存量违规已清零；远端 CI run #13（2026-07-15）已观察一轮 |
| mypy typecheck | non-blocking | **暂不转强制** | 该步骤从未在远端 CI 运行（Wave B 后 26+ commits 未 push）；待公开后首轮远端 CI 全绿再移除 continue-on-error |
| pip-audit | non-blocking | 维持（本 Wave 不动） | 依赖漏洞告警需人工评估升级路径，转强制会被上游 CVE 披露节奏绑架 |

## 公开后维护者人工动作清单（按序）

0. **先 push**：`git push origin main --tags`（本地领先 origin/main 30+ commits，含 v1.3.0 tag；公开前后均可，公开时远端必须已是 v1.3.0 状态）。
1. Settings → General → 转 Public。
2. Settings → Branches → 按 `.upgrade/decisions/branch-protection.md` 开启 main 分支保护（Scorecard Branch-Protection 项依赖此步）。
3. Settings → Security → 启用 Private vulnerability reporting（SECURITY.md 与 issue config.yml 均指向此渠道）。
4. Settings → Security → 启用 Dependency graph / Dependabot alerts（公开仓库免费）。
5. `.github/workflows/codeql.yml`：把触发器从"仅手动+cron"改为加上 push/PR（文件内注释已预告此步；执行内容见实施方案附录 E5 / 父计划 Task 19）。
6. 手动 dispatch 一次 `scorecard.yml`，拿公开后首个真实分数，记入 `.upgrade/reports/`。
7. 核对 README 徽章全部渲染正常（CI/Scorecard 徽章需公开+首跑后才生效）。
8. 创建 GitHub Release v1.3.0（tag 已在本地打好；Release notes 直接复用 CHANGELOG v1.3.0 段），同时解决"0 release"的作品集短板。
9. 远端首轮 CI 全绿后：移除 ci.yml mypy 步骤的 `continue-on-error: true` 转强制（见上表）。
10. （可选）GitHub → About 栏填 description + topics：`ai-governance, premortem, risk-assessment, human-oversight, langgraph, llm-evaluation`。
