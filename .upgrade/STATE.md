# Upgrade State

## Current Phase

Phase 0–4 代码侧已完成；formal-project-uplift Wave A–E（Task 0–18）已完成并收尾为 v1.3.0。剩余项均为远端治理或外部复核：Task 19 CodeQL 转正、main 分支保护、发布设置及标准原文复核。

## Current Task

**计划已完成（Task 19 除外，待公开后）**：`.upgrade/plans/2026-07-17-formal-project-uplift.md`（正式个人项目升级：门面治理文件 / mypy 渐进式类型检查 / T3.6 LLM Judge 落地 / 合规映射 2026-07-17 复核落账 / 公开前检查，目标版本 v1.3.0，Task 0–19）。**Wave A–E（Task 0–18）全部完成**。此前遗留：GitHub 后台开启 main 分支保护（步骤见 `.upgrade/decisions/branch-protection.md`，已并入新计划 Task 15 公开后动作清单）。

## Last Completed

- **文档—代码深度复核与失效脚本清理 (2026-07-27)** — 4 个子代理只读审查规格、运行文档、文档清单与安全合规，主代理按代码/配置/测试复核并定点修正：默认执行器与 SQLite 路径、供应链 workflow 当前态、治理 Gauge 占位边界、Stage 3 safety finding 条件、Context 迁移删除条件、本地真实模式 secrets 初始化、PII 掩码覆盖范围、心理健康示例数据分级、显式同意缺口及双重密钥存储。删除 3 个无调用且在当前认证 API 上不可运行/硬编码旧 alpha 假设的归档脚本，保留一次性 tenant 迁移参考。未删除或合并职责独立的 spec、PIA、plan 历史基线。验证：`python scripts/doc_consistency_check.py` 扫描 51 份 Markdown、0 违规；version 1.3.0 一致；全量测试 623 passed / 8 skipped；`git diff --check` 通过。当前 Windows 环境没有 `make`，故直接运行 Makefile 对应底层命令。
- **Git / Docker ignore 边界加固 (2026-07-25)** — 审查确认 Git 当前及历史均未跟踪真实 `.env`、`secrets/`、TLS 私钥、SQLite 数据、coverage 或缓存；发现 `.dockerignore` 未排除真实 `secrets/` 且 Dockerfile 使用 `COPY . .`，存在密钥进入 build context/镜像层的高风险。已补齐 `.gitignore` 的 agent local settings、通用私钥/keystore、环境管理、扩展测试缓存与数据库规则；`.dockerignore` 现排除所有 `.env*`、`secrets/`、证书/私钥、agent 配置、测试/文档/CI/升级记录、部署配置、缓存与运行时数据，同时保留运行时需要的 `examples/`。验证：无 tracked-ignore 冲突、context 模拟 `included_risky=NONE`、Full/Lite compose config 通过；实际 build 因本机 Docker daemon 未运行未完成。决策：`.upgrade/decisions/ignore-boundary-hardening-20260725.md`。
- **代理指导文件同步 (2026-07-25)** — 基于当前业务代码、`.upgrade/STATE.md` / `MANIFEST.md` 和项目验证链，更新根目录 `AGENTS.md` 与 `CLAUDE.md`：AGENTS 成为仓库级代理权威入口，CLAUDE 作为补充并显式服从 AGENTS；同步 v1.3.0、Alembic V005、ProjectContext 0.9.0、623 passed/8 skipped 基线、Phase 计划历史定位、doc-check/typecheck/docker-full CI 状态，以及字段加密默认未启用/留存无自动清理器等真实边界。保留 project-upgrade 受控块原文。决策：`.upgrade/decisions/agent-guidance-sync-20260725.md`。
- **文档与业务代码一致性整理 (2026-07-25)** — 子代理独立审查 + 主代理代码实证复核。修正迁移链、CI 状态、当前测试基线、归档版本措辞、安全/PIA/留存能力边界、备份与应急可执行性、分支保护状态等事实漂移；10 份 Phase 0–4 计划/设计文档统一标为历史基线；README 合并重复启动说明。`doc_consistency_check.py` 扫描范围由 35 份扩展到 51 份当前项目 Markdown（排除升级历史/archive/运行时产物/缓存）。删除未跟踪且无引用的旧 v1.2.2 运行时导出 `artifacts/live_e2e_four_stage/session_export.md`。当前验证：623 passed/8 skipped、doc-check 51 文件 0 违规、version 1.3.0 一致。决策记录：`.upgrade/decisions/doc-code-reconciliation-20260725.md`。
- **本地 CI 复现 + 远端 GitHub CI 全绿 (2026-07-18)** — 按计划 `.upgrade/plans/2026-07-18-local-then-remote-ci-execution.md` 两阶段执行：Phase A 本机完整复现 ci.yml 三 job（lint/typecheck/doc-check/version-check/pip-audit/test-cov 650 passed 1 skipped 覆盖率 69%/docker lite 冒烟/docker full 7 容器 TLS 断言）全绿，每个长耗时步骤附独立后台监控窗口 + 硬超时预算，日志留存 `.upgrade/logs/ci-{local,remote}-20260718-*`；Phase B 安装 gh CLI 2.96.0 后分诊基线失败 run 29621280076：①doc-check 平台差异（Windows 忽略路径尾点号使 `tests/...` 省略号占位在本地 `exists()` 误判通过、Linux 报 9 处违规）→ `scripts/doc_consistency_check.py` 规则 3 跳过 `..` 结尾占位路径；②docker-full api/grafana 容器读不到 600 权限 secrets（runner 属主 vs 容器内非 root 用户）→ ci.yml 生成后 `chmod 644 secrets/*`（仅限 CI 一次性随机值）。修复 commit 5b4003f 推送后 run 29647651072 三 job 全 success——**docker-full-integration 观察期首次转绿**。附带发现本机 `pytest-of-embar` 临时目录 ACL 损坏致 68 errors（TMP 重定向绕过，需用户重启后清理）。完整报告：`.upgrade/reports/ci-run-20260718.md`。
- **文档-代码一致性核查与修复 (2026-07-18)** — 6 个并行子代理全维度核查（根目录门面 / 架构与 API / 安全合规 / 门禁与分类体系 / 启动部署 / 版本与索引），结论：无高危不一致。修复 3 中危 + 5 低危：①`risk-taxonomy-engine.md` §1 改标"历史快照"并逐条括注缺口已在 v1.1.0 补齐（LLM05/07/10、NIST 600-1 动作项、ASI、TC260），§5 补落地复核补注（unbounded_consumption→ASI07 错误映射已按宁缺毋滥删除，与 `owasp_agentic_2026.py` 文件头决策对齐）；②`startup.md`/`local_setup.md` 修正 grafana_password 同步描述（`gen_secrets.sh` 仅同步 jwt/postgres/redis 三项进 .env，grafana 走 `GF_SECURITY_ADMIN_PASSWORD__FILE` secrets 挂载）；③过时版本自指清理：`architecture.md` "(v1.0.0)" 标题改为"自 v1.0.0 确立，v1.3.0 复核仍有效"、`security-model.md`/`data-classification-and-privacy.md` 的 "v1.0.3 落地" 改为"自 v1.0.3 起落地并沿用至今"；④`api-reference.md` 补录 `PATCH /sessions/{id}/data-classification` 与 `DELETE /sessions/{id}` 两端点（此前计入总数 84 但未列明细）；⑤`architecture.md` 动作解析链路图补编排层注记（SessionService 为 orchestrator，三模块非在 oversight_service 内部串联）；⑥`data-classification-and-privacy.md` §5 `ai_generated_notice` 位置描述改为与实现一致（字典尾部 disclaimer 前，非头部）；⑦`acceptance_report.md` 3 处失效 `file:///...pure-main` 绝对 URI 改仓库相对链接。验证：doc-check 35 文件 0 违规 / version-check OK (1.3.0)。改动纯文档，未触生产代码。
- **四种启动方式全流程 E2E 测试 + 6 缺陷修复 (2026-07-18)** — 四种启动方式全部冷启动实测 PASS（方式1 离线演示：API+UI 双路径走满四阶段至 complete、四阶段 gate-report 全 passed；方式2 Docker Lite：`--no-cache` 全新构建避免旧镜像污染；方式3 混合开发：临时端口 15432/16379 避开本机原生 postgres 5432 冲突，alembic 自动建 21 表 + 数据落库验证；方式4 生产栈：自建 secrets 后 7 容器全 healthy，nginx TLS 全链路 + Prometheus/Grafana 验证）。测试方法：API 冒烟 + Playwright 浏览器驱动真实 UI 交互 + 后台日志监控。修复 6 缺陷：①前端 ensure_auth 注册限流 429 致全站 401（改先登录后注册）；②`gen_secrets.sh` Windows CRLF 污染 secrets 致 redis 认证失败（`tr -d '\r\n'`）；③postgres 多 worker 并发 alembic 竞态 UniqueViolation（pg_advisory_lock 串行化）；④`nav_page` 无赋值点致治理总览页不可达（侧栏新增页面导航 radio + 总览页补 4 指标/双分布/周明细）；⑤`/health` 缺 `interrupt_adapter_status` 字段致前端恒显"未知"（后端补齐）；⑥前端补展示后端已返回字段（eval pass_criteria / judge_reason / violated_criteria、实验人工校准分歧率、审计 before/after 快照）。回归：650 passed, 1 skipped + ruff clean + 浏览器复测全过。完整报告：`.upgrade/reports/startup-methods-e2e-20260718.md`。遗留观察项（死代码 panels / 无 UI 入口端点）见报告第 5 节。
- **生产启动链路加固 (2026-07-18)** — 启动审计遗留项 7–9 落地（三项方案经用户逐项确认）：①`scripts/gen_secrets.sh` 接入 `make setup`（随机生成 4 个可生成密钥 + 同步 `.env` 占位行——实测确认 pydantic-settings 源优先级 env>.env>/run/secrets，`.env` 残留 CHANGE_ME 会遮蔽 Docker secrets，故 setup 必须两处同步；API key 占位行注释化）；②`prod-preflight` target（secrets 六文件+证书存在性硬阻断提示 make setup，示例占位值仅警告），本地三场景实测通过（缺证书报错 exit 1 / 齐全 exit 0 / 占位值警告不阻断）；③ci.yml 新增 `docker-full-integration` job（每次 push，观察期 continue-on-error，mock LLM + 随机 secrets + 自签 TLS，经 nginx HTTPS 验证 live/ready/health + 前端 + 7 容器 running 断言）。gen_secrets/gen_certs 补 git 执行位（100755）。文档同步：README / startup.md / local_setup.md Docker Full 段 + CHANGELOG 维护记录。
- **启动方式审计与偏差修复 (2026-07-17)** — 2 个并行子代理审计（启动机制实盘 / 启动文档核对），确认五种启动方式（demo / dev-db 本地全量 / Docker Lite / Docker Full / 单文件 HTML Demo）均真实可用、Docker 双档支持完整。修复 6 处偏差：①`docs/startup.md` 测试数 642→650（v1.3.0）+ Last updated 2026-06-08→07-17 + Docker 生产步骤删冗余 `cp .env.example .env`（make setup 已自带）；②`docs/local_setup.md` 测试数 376/6 过时快照改为 650/1 + Last updated 更新；③README 中文版离线演示章节从"cp .env.example 手改 3 变量"统一为 `make demo-api/demo-ui`（与 README.en.md / CLAUDE.md 对齐）；④Makefile `.PHONY` 删除幽灵 `dev`（无规则实体）、补 install-dev/migrate 系列；⑤`demo-frontend` 改为 `demo-ui` 别名（此前不刷新 .env，残留生产配置时前端会读错 API_BASE）。~~遗留工程决策项（gen_secrets.sh 孤儿脚本 / 生产栈 CI 零覆盖 / prod-up 无 fail-fast 前置检查）~~ 已于 2026-07-18 全部落地（见上条）。doc-check 0 违规。
- **文档同步收尾 (2026-07-17)** — 3 个并行子代理审计（.upgrade 登记完整性 / 项目级 md 与验收报告时效性 / STATE 交叉引用与 staged 变更一致性）后修复全部发现：①`docs/acceptance_report.md` 更新至 v1.3.0（保留 2026-07-14 v1.2.1 四阶段 E2E 实测快照，新增"v1.3.0 回归验证"段：650 passed/1 skipped + e2e-mock 63 passed 均 2026-07-17 实测、版本三方一致、报告架构版本 1.2.1→1.3.0）；②Mode 3 搬迁遗留 stale 引用修正 6 处（phase-0-design ×2 / phase-2-design ×3 / phase-4-design ×2 指向已归档 scorecard-baseline 与已移位 standard-tracking 的旧路径，CHANGELOG:73 加移位注记）；③`standard-tracking-2026-07-14.md` 头部位置自述修正（仍称"位于 logs/ gitignored"→ 现位于 reports/ 受控）；④MANIFEST benchmarking 目录描述修正（tags 快照实际仅 deepeval+inspect_ai 两家，非四家全有）；⑤`docs/README.md` 索引补录 5 份 phase-N-design.md + archive/verification-reports 存档段。doc-check 6 处违规 → 0。
- **Mode 3 工作区清理 (2026-07-17)** — 3 个并行子代理审查 `.upgrade/` 全部 46 个文件（reports/decisions 时效性 / plans/research 留存价值 / 交叉引用一致性）。执行：①删除 `tmp/` 6 个 mypy raw 输出（88K，可由 `uv run mypy` 再生）+ 冗余截断副本 `research/benchmarking-20260716/readme_deepeval.md`（为 full 版前缀截断）；②归档 `reports/release_manifest_v1.0.md` + `reports/scorecard-baseline-20260713.md` → `archive/`（git mv，趋势报告链接同步改指 archive）；③ `logs/standard-tracking-2026-07-14.md` → `reports/` 纳入版本控制（曾丢失重建过，Required Context File 不应居 gitignored 目录）；④ Wave E 实施计划 20 个已执行步骤 checkbox 补翻勾（Task 19 的 3 个保持不勾）；⑤ MANIFEST 规则段 `stages/`→`plans/` 措辞对齐 + line 89 过时悬空引用备注修正。一致性检查结论：STATE 引用无悬空、Inventory 准确、git 追踪无遗漏、无以现在时态陈述旧版本处。trace：`.upgrade/traces/20260717-224754-mode3.trace`。
- **Mode 4 项目扫描归档 (2026-07-17)** — 3 个并行子代理全仓扫描（根目录候选内容审查 / 全仓引用安全检查 / 非源码目录模式扫描）。结论：仓库整体干净，git status 起始 clean，.gitignore 覆盖无遗漏。经确认归档 2 项：`show.md`（v1.0 毕设展示文档，被 README v1.3.0 取代且全仓无引用，git mv → `.upgrade/archive/`）、`artifacts_live_e2e.log`（一次性 E2E 日志 → `.upgrade/logs/`，gitignored）。`artifacts/` 因 3 个脚本硬编码路径依赖评 high 风险保留原地；两份 HTML（demo/submission）为 README 正式登记资产保留。trace：`.upgrade/traces/20260717-223539-mode4.trace`。
- **Wave E 公开前检查与 CI/发布收尾 (2026-07-17)**：公开前全历史敏感信息扫描通过（仅 DEMO_PASSWORD 演示凭据 + secrets.example 占位符两类良性命中，报告含公开后 10 步人工动作清单）；CI 覆盖率产出（pytest-cov + make test-cov + GitHub job summary，不接 codecov）；doc-check 转强制、mypy 维持 non-blocking（从未在远端跑过，转正条件未满足——评估结论见报告第 4 节）；docs/plan/ecosystem-positioning.md 生态定位文档（赛道三层地图 / SynthBoard.ai 差异化 / 门面对标结论，数字与 2026-07-16 JSON 快照逐字段一致）；v1.3.0 收尾（version 三件套 + README :14 + CHANGELOG + tag v1.3.0 打在收尾 commit）。对父计划六处记录性偏差（预扫描良性清单 / doc-check 转正范围 / commit message / README 版本行 / STATE 段落名 / tag 位置）见实施方案。commits: 63f4c31/955c0ef/622edc7/d23aa6a+本 commit。实施计划：`.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md`。
- **Wave D 合规映射复核落账 (2026-07-17)**：ISO/IEC 42005:2025（AI 系统影响评估，2025-05 发布）对标说明落入 docs/compliance/iso42001-mapping.md 第 6 节（初版对齐表，付费标准全文未核对处如实标注）；docs/plan/improvement-roadmap.md 新增 §10.7 复核增补（EU AI Act Omnibus 公报编号待回填 / TC260 正式发布确认但二手来源 / NIST AI 600-1 四动作项 [存疑] 维持 / OWASP ASI 无需改动 / 两个国内已生效法规锚点候选）；三个 taxonomy 模块 docstring 盖 2026-07-17 二次复核戳（仅注释零行为变更，87 项相关测试全绿；tc260 戳按质量评审意见做时间限定修正，避免与 [信源说明] 自相矛盾）。对父计划三处记录性偏差（§6 编号 / TC260 [信源说明] 措辞 / §10.7 插入位）见实施方案。commits: efef623/7c5702d。实施计划：`.upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md`。
- **Wave C T3.6 LLM Judge (2026-07-17)**：EVAL_LLM_JUDGE / EVAL_LLM_JUDGE_AUTOFINAL 两 flag（默认 off）+ EvalRun.llm_judge_suggestion 字段；core/eval_llm_judge.py 建议生成器（防注入模板、失败静默降级）+ judge 专用 mock fixture；eval_runner 风险分层 autofinal 门控（HIGH/CRITICAL 永不采纳、manual run 不生成建议——对父计划的记录性偏差见实施方案）；spec §5 翻转 Implemented (v1.3.0)。测试 tests/test_llm_judge_v130.py 8 条，全量回归 650 passed, 1 skipped。commits: 46fb178 / de76b04 / 6e5a372 + 文档收尾 commit。实施计划：`.upgrade/plans/2026-07-17-wave-c-llm-judge-implementation.md`。
- **Wave B mypy 渐进式类型检查 (2026-07-17)** — mypy 引入与全量清零：宽松档基线 108→0（inspect_ai 模式，files 限 7 核心包，排除 tests/frontend/scripts/examples/alembic），core.gates/graph 近 strict 13→0，`uv run mypy` = `Success: no issues found in 153 source files`。新增 `make typecheck` target + CI `Type check (non-blocking)` 接入 ci.yml（观察期，转正评估归 Wave E Task 16）。防漂移版本钉子：mypy>=1.14,<3、langgraph>=1.1,<2。修复含一处真实 bug（create_redteam_dataset/create_dataset_from_failed_traces 的不存在 note= 关键字，latent TypeError）+ SourceType 单一定义化。分片提交 B1–B6（873e256/57aec07/6a1fe93/cbc1193/d8ba8b4/0f64dd8 + 本收尾）。实施计划：`.upgrade/plans/2026-07-17-wave-b-mypy-implementation.md`；基线报告：`.upgrade/reports/mypy-baseline-20260717.md`。
- **Wave A 门面与治理文件 (2026-07-17)** — 对标调研快照归档至 `.upgrade/research/benchmarking-20260716/`；包名统一 `ai-workflow-premortem` + hatchling 可安装化（`uv pip install -e .` 验证通过）；SECURITY.md 报告渠道定稿（仅 GitHub 私密报告）；新增 CODE_OF_CONDUCT.md（Contributor Covenant 2.1）/ GOVERNANCE.md（BDFL）/ .github/CODEOWNERS / issue config.yml；README 门面改造（徽章 + origin story + 生态定位）+ README.en.md。实施计划：`.upgrade/plans/2026-07-17-wave-a-implementation.md`。
- **文档同步 + `.upgrade` 整理 (2026-07-16)** — 记录此前未纳入版本控制的单文件 Demo `ai_workflow_premortem_demo.html`（165KB 自包含离线可交互 Demo，真实四阶段实跑快照，`LLM_MODE=mock`/`STORAGE_BACKEND=sqlite`/`WORKFLOW_EXECUTION_MODE=single_step`），README「答辩演示模式」新增「零依赖单文件 Demo」小节登记两份 HTML；CHANGELOG 追加 2026-07-16 维护记录；`.upgrade/MANIFEST.md` File Inventory 补齐遗漏条目 `decisions/doc-alignment-and-frontend-polish.md`（此前已提交但未登记）。最小审查：version 1.2.1 一致 / ruff clean / doc-check 通过
- **GitHub CI 离线全流程验证 (2026-07-15)** — 远端 `.github/workflows/ci.yml` 实测两个 job 全绿：`lint-and-unit-tests`（ruff + doc-check[non-blocking] + pip-audit[non-blocking] + `.env.demo` mock+SQLite 全量 pytest）与 `docker-lite-integration`（`docker-compose.lite.yml` 构建 + API `/health/live`+`/health` + 前端 8501 smoke test）。全程离线无真实 LLM（`LLM_MODE=mock`）/无外部 DB（`STORAGE_BACKEND=sqlite`）。CI run #13 conclusion=success。附带修复：`tests/test_taxonomy_owasp_agentic_2026.py` 两处 docstring `\d` 改 raw string 消除 SyntaxWarning。本地验证：ruff clean / 615 passed,8 skipped / version 1.2.1
- **文档对齐 + 前端中文化收尾 (2026-07-14)** — 基于四维审计（路线图达成度 / 前端中文展示 / 文档-代码对齐 / 启动方式）做收尾对齐：①四份 spec 的 `Status:` 从 "Designed, not implemented" 翻转为 "Implemented"，CLAUDE.md 文档维护段同步；②phase-0~3 验收清单 + roadmap §6 诚实勾选（未完成项保留并注明）；③api-reference 补治理 API + 路由数 79→84，security-model 补 3 个新风险类型/字段加密/PII 掩码/数据分级，docs/README 补 iso42001 索引，startup 测试数 388→642；④doc-check 脚本新增"跳过围栏代码块"，存量违规 25→0；⑤前端 labels 新增 RISK_TYPE/EXEC_MODE/ADAPTER_STATUS 映射，修复侧边栏健康状态、欢迎页首屏、待处理动作/安全发现的英文泄漏。决策见 `.upgrade/decisions/doc-alignment-and-frontend-polish.md`。验证：ruff clean / doc-check 0 / version 1.2.1 / e2e-mock 63 passed / 全量 642 passed,1 skipped / 后端 app 加载 OK
- **E2E 全流程复测 (2026-07-14)** — v1.2.1 本地离线全流程 E2E 复测 PASS：四阶段全部 advanced=True、hard_blockers=0、16 个 panel 端点全部 200、前端 Streamlit 渲染正常 + JWT 自动登录、后端日志无错误。会话 `91e799e4-15d1-4af3-baa9-79a8be890eb5`，耗时 18s。`.gitignore` 补 `artifacts/`；`docs/acceptance_report.md` 同步更新至 v1.2.1；`.upgrade/MANIFEST.md` File Inventory 补齐 7 个遗漏条目
- **Phase 4 (2026-07-14, v1.2.1)** — T4.1 doc-check CI 化 + T4.5 社区模板 + T4.2 分支保护文档 + T4.3 Scorecard 趋势报告；T4.4 不承诺
- **Phase 3 Wave 6 (2026-07-14)** — 收尾：version bump 1.1.0→1.2.0、CHANGELOG v1.2.0、STATE.md 更新、git tag v1.2.0
- **Phase 3 Wave 4 (2026-07-14, commit 0bca456)** — T3.5 Prometheus 业务指标 + Grafana 治理面板（6 个 premortem_* 指标 + governance-overview.json）+ T3.7 ISO/IEC 42001 条款映射表（25 条款映射 + 4 缺口 + spec 两处修正）
- **Phase 3 Wave 3 (2026-07-14, commit 16c3439)** — T3.3 expert_review 规则落地（补 stage3 历史欠账）+ GATE_RULES_DISABLED 治理；T3.4 治理 API 三端点 + Streamlit 治理页
- **Phase 3 Wave 2 (2026-07-14, commit b534929)** — T3.2 rule_version 携带 + gate_evaluation_records 表（alembic V005）+ 存储层聚合方法
- **Phase 3 Wave 1 (2026-07-14, commit fbcfdfe)** — T3.1 门禁规则元数据清单 manifest（13 条规则 version/owner/rationale/changelog）
- **Phase 3 Design Plan (2026-07-14)** — 详细设计方案 `docs/plan/phase-3-design.md`
- **Phase 2 全部完成 (2026-07-14, v1.1.0)** — T2.1–T2.6 AI 风险分类体系补强，5 Waves
- **Phase 1 全部完成 (2026-07-14, v1.0.3)** — T1.1–T1.9 安全与合规硬缺口修复

## Required Context Files

- `.upgrade/MANIFEST.md`
- `docs/plan/phase-1-design.md` — Phase 1 详细设计方案
- `docs/plan/phase-2-design.md` — Phase 2 详细设计方案
- `docs/plan/phase-3-design.md` — Phase 3 详细设计方案
- `docs/plan/phase-4-design.md` — Phase 4 详细设计方案
- `docs/plan/phase-1-security-compliance.md` — Phase 1 实施计划
- `docs/plan/phase-2-risk-taxonomy.md` — Phase 2 实施计划
- `docs/plan/phase-3-governance-platform.md` — Phase 3 实施计划
- `docs/plan/phase-4-community.md` — Phase 4 实施计划
- `docs/plan/improvement-roadmap.md` — roadmap
- `docs/spec/governance-platform.md` — 治理平台设计规格
- `docs/spec/supply-chain-security.md` — 供应链与 CI 安全设计规格
- `docs/compliance/iso42001-mapping.md` — ISO/IEC 42001 条款映射表
- `.upgrade/reports/standard-tracking-2026-07-14.md` — 标准动态跟踪记录

## Blockers

- **旧 Docker 镜像敏感文件复核**：本次已修复 build context，但 Docker Desktop daemon 当前未运行，无法检查修复前构建的本地/远端镜像是否含 `/app/secrets`。daemon 恢复后需重建并检查；如旧镜像曾被推送或分享，应轮换相关密钥。步骤见 `.upgrade/decisions/ignore-boundary-hardening-20260725.md`。
- **Phase 4 T4.2 分支保护**：决策记录已入库（`.upgrade/decisions/branch-protection.md`），但实际开启需维护者登录 GitHub 后台手动操作（Settings → Branches → main → Enable protection）。操作后预期 Scorecard Branch-Protection 0→8+、Code-Review 0→3-5。
- **Phase 4 T4.1 doc-check 转强制**：已完成。当前 `.github/workflows/ci.yml` 的 doc-check 步骤没有 `continue-on-error`，文档一致性失败会阻断 CI。
- Phase 3 T3.6 (LLM Judge)：~~gated on user confirming real demand~~ 已解除——用户确认需求后于 2026-07-17 作为 Wave C 落地（v1.3.0，flag 默认关）。真实 LLM 一致率数据待生产启用后经 human_calibrations 累计。
- NIST AI 600-1 中 4 项动作项编号标 [存疑]（MS-2.10-002 / MS-2.5-005 / MS-2.5-003 / GV-1.3-002），待 NIST 发布修订版后核对。
- TC260《智能体部署使用安全指引》条款文字基于二手摘要，待补全文核对。
- ISO 42001 映射未覆盖缺口（更新后 3 项）：系统停用/退役阶段、跨租户集团视图、第三方供应链风险集成。原第 4 项"LLM Judge 校准闭环"已随 T3.6 落地（v1.3.0）转为"机制就位、真实一致率数据待生产启用后累计"。

## Active Stage Report

Phase 4 开源社区打磨代码侧全部完成。核心成果：

### 文档-代码一致性 CI（T4.1）
| 能力 | 实现 | 状态 |
|---|---|---|
| 检查脚本 | `scripts/doc_consistency_check.py`（三类规则：链接/make target/仓库路径） | ✅ |
| Makefile target | `make doc-check` | ✅ |
| CI 接入 | ci.yml lint job 追加 doc-check 阻断步骤 | ✅ |
| 存量坏链修复 | stage3 悬空引用补档 `docs/archive/verification-reports/` | ✅ |

### 社区响应约定（T4.5）
| 能力 | 实现 | 状态 |
|---|---|---|
| Issue 模板 | `.github/ISSUE_TEMPLATE/bug_report.md` + `feature_request.md` | ✅ |
| PR 模板 | `.github/PULL_REQUEST_TEMPLATE.md` | ✅ |
| 响应节奏 | CONTRIBUTING.md 追加"社区响应约定"（7 天响应承诺） | ✅ |

### 分支保护（T4.2）
| 能力 | 实现 | 状态 |
|---|---|---|
| 决策记录 | `.upgrade/decisions/branch-protection.md` | ✅ |
| 文档声明 | CONTRIBUTING.md 追加"分支保护"段落 | ✅ |
| 实际开启 | GitHub 后台手动操作 | ⏳ 待维护者操作 |

### Scorecard 持续爬升（T4.3）
| 能力 | 实现 | 状态 |
|---|---|---|
| 扫描机制 | `.github/workflows/scorecard.yml`（weekly cron + manual） | ✅ |
| 基线报告 | `.upgrade/archive/scorecard-baseline-20260713.md`（2026-07-17 Mode 3 归档） | ✅ |
| 趋势报告 | `.upgrade/reports/scorecard-trend-20260714.md` | ✅ |

### 历史测试验证（2026-07-14）
- 全量测试：650 passed, 1 skipped
- e2e-mock：63 passed
- lint + format：clean
- doc-check：0 处违规（当时扫描范围）

当前基线见 `Last Completed` 最新条目与 `docs/acceptance_report.md`，不从本历史小节推断当前测试数量。

## Validation Commands

- `git status --short`
- `uv run python scripts/version_check.py`
- `uv run ruff check . && uv run ruff format --check .`
- `Copy-Item -Force .env.demo .env; uv run pytest tests/ -q`
- `python scripts/doc_consistency_check.py`
- `git tag --list` (expect `v1.3.0`；历史 tag v1.0.x–v1.2.0 在仓库整理时未保留，见 CHANGELOG 追溯说明)

## Next Action

1. **维护者手动操作（公开序列）**：按 `.upgrade/reports/pre-publication-checklist-20260717.md` 文末清单执行——push（含 tags）→ 转 Public → 分支保护 → Private vulnerability reporting → Dependabot → CodeQL 转正（Task 19）→ Scorecard dispatch → 徽章核验 → GitHub Release v1.3.0
2. **观察期评估**：mypy 与 `docker-full-integration` 均继续 non-blocking；待远端稳定数轮并单独评估后再决定是否移除 `continue-on-error`
3. **2026-08 下旬强制复核点**：《未成年人 AI 应用安全指南》征求意见截止（2026-08-16）后核对定稿内容（roadmap §10.7）

## Last Updated

- Date: 2026-07-27
- By: Codex（4 个子代理只读审查 + 主代理代码实证复核）
- Summary: 完成全仓 Markdown 与业务代码/配置/测试的深度对账，收窄 PII、治理指标与远端治理能力声明，修复运行、迁移、架构和供应链事实漂移；删除 3 个已失效且无调用的归档脚本，保留有独立职责的当前文档与历史基线。

### 上一轮（2026-07-20 上午）

- Date: 2026-07-20
- By: claude-code (全面整理扫描 Mode 5+4+3)
- Summary: 三路并行只读扫描（Mode 5 健康检查 / Mode 4 项目根扫描 / Mode 3 工作区审计）结论：根目录无杂散文件（两个 HTML 为已入库交付物，coverage/缓存/data 均被 .gitignore 正确覆盖，.env 未被 git 追踪）；工作区无硬错误。经用户确认执行两项整理：① 删除 `.upgrade/logs/` 全部 12 个一次性 CI 日志（~1.83MB，gitignored，分诊结论已固化于 `.upgrade/reports/ci-run-20260718.md`）；② MANIFEST.md 修补规则悬空（FINAL_REPORT.md / reviews/ 标注"尚未产出"，补 research/ 非标准目录结构说明，登记 artifacts_live_e2e.log 已删）。plans/ 整批归档与 scorecard-trend 刷新继续 defer 至仓库公开 + Task 19 闭环后。

### 上一轮（2026-07-18）

- Date: 2026-07-18
- By: claude-code (本地 CI 复现 + 远端 GitHub CI 全绿验证)
- Summary: 本地按 ci.yml 复现 lint/testcov/lite/full 全部通过；远端首个 run 29621280076 失败后经 5b4003f 修复 doc-check 与 secrets 权限，最终 run（29647651072 / 收尾推送后 29647756391）三 job（lint-and-unit-tests / docker-lite-integration / docker-full-integration）全 success。完整报告 `.upgrade/reports/ci-run-20260718.md`。仓库仍处于"待维护者点公开按钮"状态。
