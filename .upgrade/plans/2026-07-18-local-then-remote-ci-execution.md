# 本地 CI 复现 → 远端 GitHub CI 验证实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans（推荐本会话内联执行——任务间强顺序依赖 + 共享后台监控任务，不适合子代理隔离执行）。Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本机完整复现 `.github/workflows/ci.yml` 的三个 job（lint-and-unit-tests / docker-lite-integration / docker-full-integration），全绿后推送触发远端 GitHub Actions CI 并监控至完成；全程附带独立监控窗口防卡死，非严重阻塞的失败自主修复。

**Architecture:** 两阶段串行——Phase A 本地按 ci.yml 步骤顺序直跑（无 make，用 Makefile 等价命令），每个长耗时步骤用后台监控任务 + 硬超时预算包裹；Phase B 安装 gh CLI 后触发/观察远端 run，失败则拉日志→修复→提交→重推，循环上限 3 轮。

**Tech Stack:** uv / ruff / mypy / pip-audit / pytest+coverage / Docker Compose (lite + full 栈) / gh CLI / Git Bash (Windows 11)

---

## 背景与约束（执行者必读）

1. **本机无 `make`**——ci.yml 中所有 `make <target>` 必须替换为下方给出的等价直跑命令（已逐条从 Makefile 抄录，勿凭记忆改写）。
2. **本机无 `gh` CLI**——Phase B 第一步安装；若 winget 安装失败且用户无法手动装，远端监控降级为"请用户开浏览器看 Actions 页"，这属于**严重阻塞，停下询问**。
3. **Python 版本差异**：本机 3.13.0，CI 用 3.11。本地测试通过不 100% 保证远端通过（反之亦然）；远端失败时先看是否版本相关。
4. **`.env` 会被反复覆盖**：demo 测试用 `.env.demo`，full 栈用 `.env.example`+sed。**计划最后必须恢复 `cp -f .env.demo .env`**（本机日常开发态）。
5. **Upgrade Workspace 规则**（CLAUDE.md）：日志进 `.upgrade/logs/`，临时产物进 `.upgrade/tmp/`，完成后更新 `.upgrade/STATE.md`；禁止 `git add .`，必须显式 staging。
6. **昨日（2026-07-18）四模式 E2E 已在本机全过**：secrets/、nginx/certs/ 应已存在且非占位值；docker 镜像层有缓存。若发现缺失按步骤内命令重建即可。
7. **并发注意**：full 栈与 lite 栈不可同时运行（端口 8000/8501 冲突）；先 lite 后 full，每段结束 `down -v`。

## 自主修复策略（用户授权：非严重阻塞自行修复）

| 类别 | 处置 |
|---|---|
| lint / format 违规 | 自主修复（`ruff check --fix` + `ruff format`，人工复核 diff 后提交） |
| mypy 新增错误 | 自主修复（基线为 0，出现即回归） |
| doc-check / version-check 违规 | 自主修复 |
| 测试失败（代码/测试 bug） | 自主修复；**若修复需改动生产代码逻辑（非测试/文档/配置），修完后在最终报告中显式列出** |
| docker 健康检查超时（瞬时/资源） | 重试 1 次；仍失败则查日志修复 |
| pip-audit 漏洞告警 | **只记录不修**（CI 中本就 non-blocking；依赖升级风险大于收益，落账到报告） |
| **严重阻塞（停下询问用户）** | GitHub 账号/权限/认证失败；gh 无法安装且无替代；推送被分支保护拒绝；GitHub 服务故障；需要付费/账号级操作；同一失败修复 3 轮仍不过 |

## 监控窗口机制（用户要求：防卡死无效耗时）

**双层防护：**

1. **硬超时**：每个前台长命令用 `timeout <秒> <命令>` 包裹（Git Bash 自带 coreutils timeout）。超时即命令失败，进入修复流程而非无限等待。
2. **独立监控窗口**：每个 docker 阶段与远端 CI 阶段，先用 Bash 工具 `run_in_background: true` 启动一个监控循环任务（写日志到 `.upgrade/logs/`），主流程用 `TaskOutput(block=false)` 每 30–60 秒轮询一次监控日志与主任务状态。**预算耗尽时：`TaskStop` 杀掉主任务 → `docker compose down -v` 清理 → 判定为失败进入修复流程。**

**耗时预算表**（超预算=卡死判定，立即中止）：

| 步骤 | 预算 | 参考依据 |
|---|---|---|
| lint | 2 min | 秒级 |
| typecheck | 5 min | 153 文件已编译缓存 |
| doc-check + version-check | 1 min | 秒级 |
| pip-audit | 5 min | 走网络 |
| test-cov（650 测试+覆盖率） | 10 min | 无覆盖率时 ~8s |
| docker lite（build+up+冒烟） | 15 min | 有层缓存 |
| docker full（7 容器+TLS） | 25 min | 昨日实测可过 |
| 远端 CI 单轮全程 | 35 min | 三 job 并行 |

---

## Phase A：本地 CI 复现

### Task 1: 预检与监控基建

**Files:**
- Create: `.upgrade/logs/`（若无）与本次日志前缀 `ci-local-20260718-*`
- 不改任何代码

- [ ] **Step 1.1: 确认工作区干净、工具在位**

```bash
cd "D:\BackendDevelopment\Project\Projest_Test-4\ai-workflow-premortem\ai-workflow-premortem\ai-workflow-premortem"
git status --short          # 预期：空（或仅本计划文件未提交）
docker info --format '{{.ServerVersion}}'   # 预期：28.x，无报错
timeout 5 echo timeout-ok   # 预期：输出 timeout-ok（确认 timeout 可用）
ls secrets/ nginx/certs/ 2>&1   # 预期：六个 secret 文件 + server.crt/key
```

任一预期不符：docker 未启动→提示用户启动 Docker Desktop（严重阻塞）；secrets/certs 缺失→Task 7 的 Step 7.2 会重建，此处仅记录。

- [ ] **Step 1.2: 端口占用预检**

```bash
netstat -ano | grep -E 'LISTENING' | grep -E ':(80|443|8000|8501) ' || echo "ports free"
```

预期：`ports free`。若被占用：找到占用进程，属于本项目残留容器则 `docker compose down`/`docker compose -f docker-compose.lite.yml down` 清理（自主处置）；属于无关第三方进程则**停下询问用户**（不杀用户进程）。

- [ ] **Step 1.3: 记录基线**

```bash
git log --oneline -1 > .upgrade/logs/ci-local-20260718-baseline.log
git status --short >> .upgrade/logs/ci-local-20260718-baseline.log
```

### Task 2: Lint（对应 ci.yml `make lint`）

- [ ] **Step 2.1: 运行**

```bash
timeout 120 uv run ruff check . && timeout 120 uv run ruff format --check .
```

预期：`All checks passed!` + 无 format diff，退出码 0。

- [ ] **Step 2.2（仅失败时）: 自主修复**

```bash
uv run ruff check --fix . && uv run ruff format .
git diff --stat   # 人工复核改动合理性
```

复核通过后重跑 Step 2.1 确认全绿。修复的文件留在工作区，Phase B 前统一提交（Task 9）。

### Task 3: Typecheck（对应 `make typecheck`，CI 中 non-blocking，本地按基线 0 处理）

- [ ] **Step 3.1: 运行**

```bash
timeout 300 uv run mypy
```

预期：`Success: no issues found in 153 source files`（文件数可能随代码增长略有出入，关键是 no issues）。

- [ ] **Step 3.2（仅失败时）: 自主修复**

逐条修复报错（基线为 0，任何 error 都是回归）。修复原则：优先修类型注解而非加 `# type: ignore`；确需 ignore 必须带错误码（如 `# type: ignore[arg-type]`）并在最终报告说明。重跑 Step 3.1 确认。

### Task 4: 文档与版本一致性（对应 `make doc-check` + `make version-check`）

- [ ] **Step 4.1: 运行**

```bash
timeout 60 uv run python scripts/doc_consistency_check.py && timeout 60 uv run python scripts/version_check.py
```

预期：`OK: 文档-数据一致性检查通过`（0 违规）+ `Version metadata OK: 1.3.0`。

- [ ] **Step 4.2（仅失败时）: 自主修复**

按脚本输出逐条修复（文档链接/路径/版本引用）。重跑确认。

### Task 5: 依赖漏洞审计（对应 `uv run pip-audit --strict`，CI 中 non-blocking）

- [ ] **Step 5.1: 运行并落账（无论结果均不阻塞后续）**

```bash
timeout 300 uv run pip-audit --strict > .upgrade/logs/ci-local-20260718-pip-audit.log 2>&1; echo "exit=$?"
```

预期：exit=0（无漏洞）或 exit≠0（有告警）。**有告警时只记录到日志与最终报告，不修复不阻塞**（与 CI 策略一致）。超时（网络问题）同样记录后继续。

### Task 6: 单元测试 + 覆盖率（对应 `make test-cov`，mock + SQLite）

- [ ] **Step 6.1: 准备环境文件**

```bash
cp -f .env.demo .env
```

- [ ] **Step 6.2: 后台运行测试 + 启动监控**

主任务（Bash `run_in_background: true`）：

```bash
timeout 600 uv run pytest tests/ --cov --cov-report=term --cov-report=xml -q > .upgrade/logs/ci-local-20260718-testcov.log 2>&1; echo "exit=$?" >> .upgrade/logs/ci-local-20260718-testcov.log
```

监控方式：每 30–60 秒 `TaskOutput(block=false)` 轮询 + 查看日志尾部（`tail -5 .upgrade/logs/ci-local-20260718-testcov.log`）确认测试数在推进。10 分钟预算耗尽仍未结束 → `TaskStop` + 判定卡死 → 查日志定位挂起测试。

- [ ] **Step 6.3: 核验结果**

```bash
tail -15 .upgrade/logs/ci-local-20260718-testcov.log
```

预期：`650 passed, 1 skipped`（数字与 STATE.md 基线一致；新增测试导致数字增大可接受，failed/error 必须为 0）+ `exit=0` + 生成 `coverage.xml`。

- [ ] **Step 6.4（仅失败时）: 自主修复**

对每个失败测试：读失败输出 → 定位根因（测试 bug vs 代码回归）→ 修复 → 单跑该测试确认 → 最后全量重跑 Step 6.2。若需改生产代码，在最终报告列出。同一失败修 3 轮不过 → 停下询问。

### Task 7: Docker Lite 集成（对应 ci.yml `docker-lite-integration` job）

- [ ] **Step 7.1: 准备与启动（后台）+ 监控窗口**

```bash
cp -f .env.demo .env
mkdir -p data
```

监控窗口（Bash `run_in_background: true`，先于主任务启动）：

```bash
LOG=.upgrade/logs/ci-local-20260718-lite-monitor.log
END=$((SECONDS+900)); while [ $SECONDS -lt $END ]; do echo "=== $(date +%T) ==="; docker compose -f docker-compose.lite.yml ps --format '{{.Service}} {{.Status}}' 2>/dev/null; sleep 20; done > "$LOG" 2>&1
```

主任务（Bash `run_in_background: true`）：

```bash
docker compose -f docker-compose.lite.yml up --build -d > .upgrade/logs/ci-local-20260718-lite-build.log 2>&1; echo "exit=$?" >> .upgrade/logs/ci-local-20260718-lite-build.log
```

轮询监控日志：容器状态应在数分钟内进入 `running/healthy`。15 分钟预算耗尽 → `TaskStop` 两任务 + `docker compose -f docker-compose.lite.yml down -v` + 查 build 日志定位。

- [ ] **Step 7.2: 冒烟测试（与 ci.yml 逐条一致）**

```bash
timeout 90 bash -c 'until curl -sf http://localhost:8000/health/live; do sleep 2; done'
curl -sf http://localhost:8000/health/live && curl -sf http://localhost:8000/health
timeout 90 bash -c 'until curl -sf -o /dev/null http://localhost:8501; do sleep 2; done' && echo FRONTEND-OK
```

预期：health 返回 JSON、输出 `FRONTEND-OK`。失败→`docker compose -f docker-compose.lite.yml logs --tail=100 > .upgrade/logs/ci-local-20260718-lite-fail.log` 后修复重试（重试 1 次策略）。

- [ ] **Step 7.3: 清理**

```bash
docker compose -f docker-compose.lite.yml down -v
```

同时 `TaskStop` 监控窗口任务（若仍在跑）。

### Task 8: Docker Full 生产栈集成（对应 ci.yml `docker-full-integration` job）

- [ ] **Step 8.1: 准备 env/secrets/证书（幂等）**

```bash
cp -f .env.example .env
sed -i 's/^LLM_MODE=real/LLM_MODE=mock/' .env
./scripts/gen_secrets.sh    # 幂等：已有非占位值则 [keep]
./scripts/gen_certs.sh      # 已有证书则跳过或重签，输出为准
```

预期：脚本正常退出；secrets/ 六文件齐全非 CHANGE_ME（API key 两个占位允许，mock 模式不用）。

- [ ] **Step 8.2: 启动（后台）+ 监控窗口**

监控窗口（`run_in_background: true`）：

```bash
LOG=.upgrade/logs/ci-local-20260718-full-monitor.log
END=$((SECONDS+1500)); while [ $SECONDS -lt $END ]; do echo "=== $(date +%T) ==="; docker compose -f docker-compose.yml ps --format '{{.Service}} {{.Status}}' 2>/dev/null; sleep 20; done > "$LOG" 2>&1
```

主任务（`run_in_background: true`）：

```bash
docker compose -f docker-compose.yml up --build -d > .upgrade/logs/ci-local-20260718-full-build.log 2>&1; echo "exit=$?" >> .upgrade/logs/ci-local-20260718-full-build.log
```

25 分钟预算，轮询与超时处置同 Task 7。

- [ ] **Step 8.3: 冒烟 + 7 容器断言（与 ci.yml 逐条一致）**

```bash
timeout 240 bash -c 'until curl -ksf https://localhost/api/health/live; do sleep 3; done'
curl -ksf https://localhost/api/health/live && curl -ksf https://localhost/api/health/ready && curl -ksf https://localhost/api/health
timeout 120 bash -c 'until curl -ksf -o /dev/null https://localhost/; do sleep 3; done' && echo FRONTEND-OK
running=$(docker compose -f docker-compose.yml ps --status running --format '{{.Service}}' | sort)
expected=$(printf 'api\nfrontend\ngrafana\nnginx\npostgres\nprometheus\nredis\n')
[ "$running" = "$expected" ] && echo "7-CONTAINERS-OK" || { echo "MISMATCH:"; echo "$running"; }
```

预期：三个 health 全 200、`FRONTEND-OK`、`7-CONTAINERS-OK`。失败→`docker compose -f docker-compose.yml logs --tail=200 > .upgrade/logs/ci-local-20260718-full-fail.log` 后修复重试。

- [ ] **Step 8.4: 清理 + 恢复开发态 .env**

```bash
docker compose -f docker-compose.yml down -v
cp -f .env.demo .env
```

`TaskStop` 监控窗口。**Phase A 完成判据：Task 2/3/4/6/7/8 全绿（Task 5 仅落账）。**

---

## Phase B：远端 GitHub CI

### Task 9: 提交本地修复（若 Phase A 产生了修复）

- [ ] **Step 9.1: 检查工作区**

```bash
git status --short
```

若为空（Phase A 零修复）：跳过本 Task。若有改动：

- [ ] **Step 9.2: 显式 staging + 提交（禁止 git add .）**

```bash
git add <逐个列出被修复的文件>
git commit -m "fix: resolve issues found during local CI replication

<逐条列出修了什么>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

注意：本计划文件本身（`.upgrade/plans/2026-07-18-local-then-remote-ci-execution.md`）也在此一并提交。

### Task 10: 安装并认证 gh CLI

- [ ] **Step 10.1: 安装**

```bash
winget install --id GitHub.cli -e --source winget --accept-package-agreements --accept-source-agreements
```

预期：安装成功。新 PATH 在当前 shell 可能未生效，用全路径兜底：

```bash
GH="/c/Program Files/GitHub CLI/gh.exe"; "$GH" --version
```

winget 失败 → 试 `scoop install gh` / 提示用户手动装（若均不可行 = 严重阻塞，询问用户）。

- [ ] **Step 10.2: 认证**

```bash
"$GH" auth status
```

未认证 → 提示用户在会话内运行 `! gh auth login`（交互式，选 SSH + 浏览器登录），完成后重查 `auth status`。预期：`Logged in to github.com as gome09`。**认证必须用户亲自完成，属用户账号操作。**

### Task 11: 触发远端 CI + 启动监控窗口

- [ ] **Step 11.1: 查存量 run（此前 push 已触发过）**

```bash
"$GH" run list --repo gome09/ai-workflow-premortem-pure --limit 5
```

记录最近 run 的结论作基线参考（成功/失败/进行中）。

- [ ] **Step 11.2: 触发新 run**

若 Task 9 有新提交：

```bash
git push origin main    # push 自动触发 ci.yml
```

若 Task 9 无提交（HEAD 已在远端）：

```bash
"$GH" workflow run ci --repo gome09/ai-workflow-premortem-pure --ref main
sleep 10
```

- [ ] **Step 11.3: 锁定 run-id 并启动监控窗口**

```bash
RUN_ID=$("$GH" run list --repo gome09/ai-workflow-premortem-pure --workflow=ci --limit 1 --json databaseId --jq '.[0].databaseId')
echo "RUN_ID=$RUN_ID"
```

监控窗口（Bash `run_in_background: true`）：

```bash
GH="/c/Program Files/GitHub CLI/gh.exe"
LOG=.upgrade/logs/ci-remote-20260718-monitor.log
END=$((SECONDS+2100)); while [ $SECONDS -lt $END ]; do
  echo "=== $(date +%T) ==="
  "$GH" run view $RUN_ID --repo gome09/ai-workflow-premortem-pure --json status,conclusion,jobs --jq '{status,conclusion,jobs:[.jobs[]|{name,status,conclusion}]}'
  status=$("$GH" run view $RUN_ID --repo gome09/ai-workflow-premortem-pure --json status --jq .status)
  [ "$status" = "completed" ] && break
  sleep 45
done > "$LOG" 2>&1; echo "MONITOR-DONE" >> "$LOG"
```

主流程每 60 秒 `TaskOutput(block=false)` 轮询该日志。**35 分钟预算耗尽仍 in_progress → 视作远端卡死：`"$GH" run cancel $RUN_ID` 后进入 Step 12 排查（对照 concurrency 组是否被新 push 顶掉——`cancel-in-progress: true` 会把旧 run 标记 cancelled，属正常，跟进最新 run 即可）。**

### Task 12: 结果分诊与修复循环（上限 3 轮）

- [ ] **Step 12.1: 读取结论**

```bash
"$GH" run view $RUN_ID --repo gome09/ai-workflow-premortem-pure
```

三种情况：
- **success** → 进入 Task 13。
- **failure** → Step 12.2。
- **cancelled**（被并发组顶掉）→ 回 Step 11.3 锁定最新 run。

- [ ] **Step 12.2（失败时）: 拉取失败日志**

```bash
"$GH" run view $RUN_ID --repo gome09/ai-workflow-premortem-pure --log-failed > .upgrade/logs/ci-remote-20260718-run${RUN_ID}-failed.log 2>&1
tail -80 .upgrade/logs/ci-remote-20260718-run${RUN_ID}-failed.log
```

注意：`docker-full-integration` 是 `continue-on-error: true`（观察期 non-blocking），它失败**不算 run 失败**；若仅它红，落账报告即可，不阻塞验收。

- [ ] **Step 12.3（失败时）: 分诊与修复**

| 失败特征 | 处置 |
|---|---|
| 本地未复现、疑似 3.11 vs 3.13 差异 | 读日志定位具体 API 差异，修复代码使其双版本兼容 |
| `uv sync --frozen` 锁文件不一致 | `uv lock` 重新锁定后提交 uv.lock |
| runner 环境瞬时故障（网络超时/镜像拉取失败） | 直接 `"$GH" run rerun $RUN_ID --failed` 重试一次 |
| actions 权限/secrets 缺失 | **严重阻塞，询问用户** |
| 其余代码/测试/文档问题 | 同 Phase A 修复策略，本地先复现验证再推 |

修复后：显式 `git add <files>` → commit → `git push origin main` → 回 Step 11.3 跟踪新 run。**第 3 轮仍失败 → 停下，附三轮日志询问用户。**

### Task 13: 收尾落账

- [ ] **Step 13.1: 写执行报告**

创建 `.upgrade/reports/ci-run-20260718.md`，内容必须包含：Phase A 各步骤结果表（含耗时）、pip-audit 告警清单（若有）、Phase A/B 各自的修复清单（区分测试/文档/生产代码改动）、远端 run 链接与三 job 结论、docker-full non-blocking 状态说明、遗留观察项。

- [ ] **Step 13.2: 更新 STATE.md**

在 `.upgrade/STATE.md` 的 `## Last Completed` 顶部插入本次条目（格式仿照现有条目：日期 + 一段式摘要 + 报告路径引用）。

- [ ] **Step 13.3: 提交收尾产物**

```bash
git add .upgrade/reports/ci-run-20260718.md .upgrade/STATE.md .upgrade/plans/2026-07-18-local-then-remote-ci-execution.md
git commit -m "chore: record local+remote CI verification run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin main
```

注意：此 push 会再触发一轮远端 CI（纯 .upgrade/ 改动，预期必绿）；用监控窗口同法确认后即完成。

- [ ] **Step 13.4: 最终状态核验**

```bash
git status --short          # 预期：空
git log --oneline -3
"$GH" run list --repo gome09/ai-workflow-premortem-pure --limit 3   # 预期：最新 run success
cat .env | head -3          # 预期：demo 配置（确认已恢复开发态）
```

---

## 验收清单

- [ ] Phase A：lint / typecheck / doc-check / version-check / test-cov / docker-lite / docker-full 全部通过（pip-audit 已落账）
- [ ] 每个长耗时步骤均有监控窗口日志留存于 `.upgrade/logs/`
- [ ] 无任何步骤超预算后仍在傻等（超时即中止进修复流程）
- [ ] Phase B：远端 ci.yml 最新 run conclusion=success（docker-full 若红已按 non-blocking 落账）
- [ ] 所有修复（若有）已提交并显式列在报告中；生产代码改动单独标出
- [ ] `.upgrade/reports/ci-run-20260718.md` + STATE.md 更新完毕并推送
- [ ] `.env` 已恢复为 demo 开发态；无残留运行中的容器与后台任务

## 自查记录（writing-plans Self-Review）

1. **需求覆盖**：本地 CI 步骤（Task 1–8，逐条对应 ci.yml 三 job）✅；远端 CI 步骤（Task 10–12）✅；自主修复授权与边界（修复策略表 + 各 Task 失败分支）✅；监控窗口防卡死（预算表 + 每个长步骤的后台监控任务 + TaskStop 处置）✅；计划落位 `.upgrade/plans/` ✅。
2. **占位符扫描**：无 TBD/TODO；所有命令为实际可执行内容；Task 9/13 的 commit 文件列表依运行时结果填充属必要的运行时变量，非占位符。
3. **一致性**：日志文件名统一 `ci-{local|remote}-20260718-*` 前缀；`$GH` 全路径变量在 Task 10 定义、11/12/13 复用；预算表数值与各 Step 的 timeout/END 秒数一致（120/300/60/300/600/900/1500/2100）。
