# Wave D — 合规映射 2026-07-17 复核落账 具体实施部署方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地父计划（`.upgrade/plans/2026-07-17-formal-project-uplift.md`）Wave D（Task 13–14）：把 2026-07-17 联网复核结论落账进合规文档与 taxonomy 模块——新增 ISO/IEC 42005:2025 对标说明、roadmap §10.7 复核增补、三个 taxonomy docstring 盖二次复核戳——并按仓库纪律完成 STATE.md / MANIFEST / 父计划勾选的收尾。

**Architecture:** 纯文档/注释 Wave，零行为变更。三个任务严格串行（共享 git index，禁止并行提交）：D1 改两个 Markdown（`docs/compliance/iso42001-mapping.md` 追加第 6 节 + `docs/plan/improvement-roadmap.md` 插入 §10.7）；D2 改三个 taxonomy 模块 docstring（仅注释）；D3 主控收尾（STATE.md / MANIFEST.md / 父计划 checkbox / 本文件入库 + 终验）。每任务一个 commit。

**Tech Stack:** 无新增依赖。验证工具：`make doc-check`（Markdown 链接/make target/仓库路径一致性）、`make lint`（ruff）、`uv run pytest -k "taxonomy or owasp or tc260 or nist"`（87 项）、`make test`（全量，终验一次）。

**硬性纪律（继承父计划 Wave D 开头声明，逐字适用）：** 本 Wave 只落账父计划"联网调研关键结论"中列明且附来源的事实。任何来源标注为"二手/未能核实"的条目，写入文档时必须保留 [存疑] 或"待人工核对"标注。**禁止把二手转述写成确定性条款引用。禁止在本文件给定的文案之外自行补充任何外部标准事实。**

---

## 探索基线（2026-07-17，三个并行调研 subagent + 主控直读交叉核实）

| # | 事实 | 位置 / 数值 |
|---|---|---|
| 1 | `docs/compliance/iso42001-mapping.md` 共 108 行，CRLF 行尾，末行为 `- 未覆盖条款转为待办时记录到 \`.upgrade/STATE.md\` Blockers`（无尾部空行）；章节编号 `## 1.`–`## 5.`（`## 5. 维护说明` 在 :104）→ 新节应编号 `## 6.` | 已逐字核对 |
| 2 | 该文件表格分隔行风格为 `|------|------|------|`（非 `|---|`）；头部元数据用 `> 对标：/ > 建立日期：/ > 状态：` blockquote 三行 | :3-5、:83-84 |
| 3 | 该文件 :86 与 :100 已含 T3.6/v1.3.0 表述（Wave C 收尾 commit `86ecf06` 更新），本 Wave 不再动这两行 | 已核对 |
| 4 | `docs/plan/improvement-roadmap.md` 共 371 行，CRLF；第 10 节最后小节为 `### 10.6 其他核实结论`（:363-367）→ 下一编号 10.7；**:369 起是文档级 `---` + 尾注 blockquote（:371），必须保持在文件最后** → §10.7 插入点在 :367 之后、:369 的 `---` 之前 | 已逐字核对 |
| 5 | roadmap 第 10 节格式惯例：日期 ISO `YYYY-MM-DD`、强调用 `**...**`、同目录链接 `[phase-2-risk-taxonomy.md](phase-2-risk-taxonomy.md)`、代码用单反引号 | :336-367 |
| 6 | `owasp_agentic_2026.py` docstring :1-39；`核对日期：2026-07-14（通过 WebFetch 抓取 genai.owasp.org 及两个交叉来源核对）。` 在 :9，其后 :10 为空行 → 二次复核段作为新段落插在 :9 之后；文件含 [存疑] 标注（:31/:33/:52） | 已逐字核对 |
| 7 | `tc260_agent_deployment.py` docstring :1-17；**全文件无任何 [存疑] 标注、无"核对日期"行**——不确定性记录方式是 :13-16 的 `[信源说明]` 段；docstring 末行（:16）`具体措辞以官方 PDF 为准。详见摘要存档文件"信源说明"章节。`（引号为中文弯引号，锚点从 Read 输出复制）→ 二次复核段插在 :16 之后、:17 闭合 `"""` 之前 | 已逐字核对 |
| 8 | `nist_ai_600_1.py` docstring :1-20；`核对日期：2026-07-14。...` 在 :6-8，`Web 核对结论（2026-07-14，...）` 清单在 :13-19（末行 :19 为 `  - MS-2.11-001 ... [存疑，待人工核对]`）→ 二次复核段插在 :19 之后、:20 闭合 `"""` 之前；docstring 与映射表共 8 处 [存疑] 标注 | 已逐字核对 |
| 9 | 三个 taxonomy .py 文件均为 CRLF。**用 Edit 工具按 Read 输出的文本锚点编辑（先 Read 再 Edit），不要用 sed/echo 追加**（避免混入 LF、避免弯引号复制错） | file 命令核验 |
| 10 | `tests/` 全目录 grep `__doc__`/`docstring` 零命中——没有任何测试断言这三个模块的 docstring 内容；docstring-only 编辑零测试风险 | 已核对 |
| 11 | `uv run pytest tests/ -k "taxonomy or owasp or tc260 or nist" --collect-only -q` 实测收集 **87 项**（651 中 deselect 564），无收集错误 | 2026-07-17 实测 |
| 12 | `make doc-check` = `python scripts/doc_consistency_check.py`，只扫 README.md/CLAUDE.md/docs/**/*.md 三类规则（相对链接可解析 / `make <target>` 存在 / 反引号仓库路径存在），跳过围栏代码块，**不扫 .py docstring** → D2 无需跑 doc-check | 已读脚本 |
| 13 | 本文件写入的所有反引号仓库路径（`tools/taxonomies/*.py` 三个文件）与相对链接（`../compliance/iso42001-mapping.md` 自 docs/plan/ 解析）均已核验存在/可解析，doc-check 预期 0 违规 | 已核对 |
| 14 | 工作树干净、分支 `main`、HEAD=`86ecf06`（Wave C 收尾）；Wave A–C 已完成；全量测试基线 650 passed, 1 skipped；`make typecheck` = Success | git status / STATE.md |
| 15 | `.upgrade/MANIFEST.md` File Inventory 表末尾三行是 wave-a/b/c 实施计划登记行（格式 `| 路径 | active | permanent | 描述 |`）→ 本文件按同格式追加登记 | 已逐字核对 |
| 16 | `.upgrade/STATE.md` :5（Current Phase）与 :9（Current Task）各有一句"下一步 Wave D"表述需翻转；Last Completed 首条在 :13（Wave C 条目）之前插入本 Wave 条目 | 已逐字核对 |
| 17 | 父计划 Task 13 的 4 个 checkbox 在 :1142/:1144/:1162/:1176，Task 14 的 2 个在 :1193/:1216（均 `- [x] **Step N...`） | 已核对 |

## 对父计划的三处记录性偏差（决策留档）

1. **D-1：ISO 附录章节编号与表格风格。** 父计划 Task 13 Step 2 给出的标题是 `## 附：ISO/IEC 42005:2025（AI 系统影响评估）对标说明`，但目标文件全部章节用 `## N.` 编号（基线 #1），且父计划 Step 1 自己要求"模仿其现有格式追加，不要破坏原文风格"。本方案改为 `## 6. 附：ISO/IEC 42005:2025（AI 系统影响评估）对标说明`，表格分隔行从 `|---|` 改为该文件惯例 `|------|`（基线 #2）。内容文字逐字不变。
2. **D-2：TC260 "[存疑] 标注维持"措辞失实，改为 "[信源说明] 限定维持"。** 父计划两处（Task 13 的 §10.7 TC260 条目、Task 14 的 tc260 docstring 追加文案）写"`tools/taxonomies/tc260_agent_deployment.py` 的 [存疑] 标注维持"，但该文件**实际不存在任何 [存疑] 标注**（基线 #7）——其不确定性以 `[信源说明]` 段记录。照抄会让文档自我描述失实。本方案两处均改写为"[信源说明] 限定维持"并注明该文件的记录方式，复核事实本身（约 2026-07-06 正式发布、二手来源、待官网原文核对）逐字保留。
3. **D-3：§10.7 插入位置在文档尾注之前。** 父计划说"第 10 节末尾追加小节"，但文件末尾 :369-371 是文档级 `---` 分隔线 + 尾注 blockquote（"本文档不是一次性交付物……"），必须保持在最后（基线 #4）。本方案把 §10.7 插在 10.6 内容之后、`---` 之前，而非文件真末尾。

## 任务依赖图（严格串行）

```
D1（ISO/IEC 42005 对标 + roadmap §10.7，父计划 Task 13）
 └→ D2（三个 taxonomy docstring 复核戳，父计划 Task 14）
     └→ D3（收尾：STATE.md + MANIFEST + 父计划勾选 + 本文件入库 + 终验）
```

**部署方式（用户已授权 Subagent-Driven）：** 并行探索已在制定本计划时完成（3 个并行调研 subagent）。执行阶段 D1/D2 虽改动文件互不相交，但共享 git index 且各含一次 commit，**必须串行派发**——推荐每任务一个全新 subagent（携带该任务全文），任务间主控 review + 核对 commit；D3 为工作区收尾，由主控直接执行。

**全局纪律（每个任务适用）：**
- 仅新增文档/注释内容，**不改任何代码行为**；不动 taxonomy 的映射字典、不动 iso42001-mapping.md 既有各节。
- 写入内容以本文件代码块为唯一事实来源，不得增补、不得"顺手修正"其他段落。
- 禁止 `git add .`，逐文件显式 staging；提交前 `git status --short` 核对。
- 工作目录：仓库根（Git Bash 路径 `/d/BackendDevelopment/Project/Projest_Test-4/ai-workflow-premortem/ai-workflow-premortem/ai-workflow-premortem`），命令均在仓库根执行。
- 所有目标文件为 CRLF：先 Read 再 Edit，锚点文本从 Read 输出逐字复制（尤其 tc260 的中文弯引号），不用 shell 重定向写文件。

---

## Task D1: ISO/IEC 42005:2025 对标 + roadmap §10.7（父计划 Task 13）

**Files:**
- Modify: `docs/compliance/iso42001-mapping.md`（末尾追加 `## 6.` 节）
- Modify: `docs/plan/improvement-roadmap.md`（:367 与 :369 之间插入 `### 10.7`）

- [x] **Step 1: Read 两个目标文件**

Read `docs/compliance/iso42001-mapping.md` 全文（108 行）与 `docs/plan/improvement-roadmap.md` 的 330–371 行。确认基线 #1/#4 仍成立（末行文本、10.6 位置、尾注位置）。若行号有漂移，以锚点文本为准重新定位，勿盲改。

- [x] **Step 2: 在 `iso42001-mapping.md` 末尾追加第 6 节**

用 Edit：`old_string` 为现末行：

```
- 未覆盖条款转为待办时记录到 `.upgrade/STATE.md` Blockers
```

`new_string` 为该行 + 空行 + 下面整块（逐字）：

```markdown
## 6. 附：ISO/IEC 42005:2025（AI 系统影响评估）对标说明

> 复核日期 2026-07-17。ISO/IEC 42005:2025 于 2025-05 正式发布（第 1 版，SC 42/WG 1，指南性标准、非认证标准），
> 是与本平台"预验尸=事前影响评估"定位最直接对标的国际标准。来源：https://www.iso.org/standard/42005

| 42005 核心要求 | 本平台对应能力 | 状态 |
|------|------|------|
| 在生命周期哪个阶段执行影响评估 | 立项阶段四阶段引导式分析（Stage 1–4） | ✅ 覆盖 |
| 评估范围界定、责任分配、阈值设定 | 风险自适应门禁（LOW/MEDIUM/HIGH/CRITICAL 分档阈值），门禁规则 manifest 声明 owner | ✅ 覆盖 |
| 文档化 / 审批 / 复审要求 | ReportArtifact 报告导出 + PendingHumanAction 审批 + 审计事件记录 | ✅ 覆盖 |
| 融入组织 AI 风险管理（对接 ISO/IEC 23894）与管理体系（支撑 42001 的 6.1.4 / 8.4） | 本文件的 42001 条款映射 + 治理视图（/governance/*） | ⚠️ 部分：23894 尚无显式映射 |

注：本表为初版对齐说明，逐条款精细映射待获取标准全文后补充（42005 为付费标准，本表基于官方摘要与二手概述编写，条款号未逐字核对）。
```

- [x] **Step 3: 在 `improvement-roadmap.md` 插入 §10.7（10.6 之后、文档尾注 `---` 之前）**

用 Edit：`old_string` 为（10.6 末行 + 空行 + 尾注分隔线，三行连续）：

```
- 代码库中不存在 `MaterialParser` 类（第 3.3 节的指代性描述）：用户材料实为 `ProjectContext.user_materials` 纯文本字段，经 `core/evidence_service.py` 包装为 EvidenceSource——数据分级设计已按此事实展开。

---
```

`new_string` 为该末行 + 空行 + 下面整块 + 空行 + `---`（即 §10.7 夹在中间，尾注结构不动）：

```markdown
### 10.7 2026-07-17 复核增补

- **ISO/IEC 42005:2025 已正式发布**（2025-05，AI 系统影响评估指南）——与本平台定位直接对标，已在 [docs/compliance/iso42001-mapping.md](../compliance/iso42001-mapping.md) 附录建立初版对齐说明。ISO/IEC 42006:2025（认证机构要求）同年发布；ISO/IEC 42007 仍为 DIS 草案。
- **EU AI Act × Digital Omnibus 进展**：欧洲议会 2026-06-16 通过、理事会 2026-06-29 批准均已确认；**官方公报编号截至复核日未刊出**（EUR-Lex 仅有提案 CELEX:52025PC0836），10.1 节时间线维持不变，正式法规号出现后回填。修正细化：Art.50(2) 水印义务的 4 个月宽限期仅适用于 2026-08-02 前已投放市场的存量系统。
- **TC260《智能体部署使用安全指引》**：确认约 2026-07-06 正式发布（五阶段结构不变），但精确发布日与逐条条款仍基于二手来源（MLex 等），`tools/taxonomies/tc260_agent_deployment.py` 的 [信源说明] 限定维持（该文件以信源说明段而非逐条 [存疑] 标注记录不确定性），待可访问 tc260.org.cn 原文后核对清除。
- **《未成年人 AI 应用安全指南》**：确认为国标制定项目（计划号 20260326-T-469），征求意见截止 2026-08-16 未变——**2026-08 下旬为下一个强制复核点**。
- **NIST AI 600-1 四个动作项编号**：二次联网复核仍未获官方原文（MS-2.10-002 连存在性都未证实），`tools/taxonomies/nist_ai_600_1.py` 的 [存疑] 标注全部维持；解决路径只有人工直连 NIST.AI.600-1.pdf 逐字核对。
- **OWASP ASI01–ASI10**：名称经多源二次核实与 `tools/taxonomies/owasp_agentic_2026.py` 现表一致，无需改动；OWASP LLM Top 10 仍为 2025 (v2.0)，2026 改版已启动未定稿。
- **新增国内已生效法规锚点**（待纳入合规映射的候选）：《智能体规范应用与创新发展实施意见》（网信办/发改委/工信部，2026-05-08 发布、07-15 施行，敏感领域备案+检测、低风险合规自测）；《人工智能拟人化互动服务管理暂行办法》（五部门，2026-04-10 公布、07-15 施行，五类情形触发安全评估）。前者的分级治理思路与本平台风险自适应门禁直接同构。
```

- [x] **Step 4: 校验**

Run: `make doc-check`
Expected: `0` 违规（新增链接 `../compliance/iso42001-mapping.md` 与三个 `tools/taxonomies/*.py` 反引号路径均可解析，基线 #13 已预核）。

Run: `make lint`
Expected: clean（未动 .py，应与基线一致）。

- [x] **Step 5: 提交**

```bash
git status --short   # 预期仅两个 modified：docs/compliance/iso42001-mapping.md、docs/plan/improvement-roadmap.md（外加本计划文件 untracked，D3 处理）
git add docs/compliance/iso42001-mapping.md docs/plan/improvement-roadmap.md
git commit -m "docs: record 2026-07-17 external standards re-verification, add ISO/IEC 42005 alignment"
```

---

## Task D2: 三个 taxonomy 模块 docstring 盖二次复核戳（父计划 Task 14）

**Files:**
- Modify: `tools/taxonomies/owasp_agentic_2026.py`（仅 docstring）
- Modify: `tools/taxonomies/tc260_agent_deployment.py`（仅 docstring）
- Modify: `tools/taxonomies/nist_ai_600_1.py`（仅 docstring）

**约束：只动模块 docstring，映射字典（`ASI_RISK_REFS` / `TC260_*` / `NIST_*`）与行内注释一律不动。**

- [x] **Step 1: Read 三个文件的 docstring 区**（owasp :1-40、tc260 :1-18、nist :1-21），确认基线 #6/#7/#8 锚点仍在。

- [x] **Step 2: `owasp_agentic_2026.py` — 在核对日期行后插入新段落**

用 Edit：`old_string`：

```
核对日期：2026-07-14（通过 WebFetch 抓取 genai.owasp.org 及两个交叉来源核对）。
```

`new_string`（原行 + 空行 + 两行新段落）：

```
核对日期：2026-07-14（通过 WebFetch 抓取 genai.owasp.org 及两个交叉来源核对）。

二次复核：2026-07-17（WebSearch 多源交叉，ASI01–ASI10 名称与本表一致，无需改动；
官方 PDF 逐字定名仍待人工核对 ASI03/04/08 措辞变体）。
```

- [x] **Step 3: `tc260_agent_deployment.py` — 在 [信源说明] 段之后、闭合 `"""` 之前插入新段落**

用 Edit：`old_string` 为 docstring 末行（**弯引号从 Read 输出逐字复制**，此处以 Read 结果为准）：

```
具体措辞以官方 PDF 为准。详见摘要存档文件"信源说明"章节。
```

`new_string`（原行 + 空行 + 三行新段落，按 D-2 偏差措辞）：

```
具体措辞以官方 PDF 为准。详见摘要存档文件"信源说明"章节。

二次复核：2026-07-17——确认正式发布（约 2026-07-06，MLex 等二手来源；tc260.org.cn 官网原文未能抓取），
五阶段结构（评估/准备/部署/使用/停用）不变；上方 [信源说明] 的限定维持不变
（子条款措辞仍以官方 PDF 为准），待官网原文可访问后逐条核对。
```

> **执行修订（2026-07-17 质量评审）：** 上述草案中"tc260.org.cn 官网原文未能抓取"是无限定断言，与上方 [信源说明]（第 1-5 章此前已获官方 PDF）自相矛盾。最终落库文本改为四行时间限定版："本次复核未能重新抓取 tc260.org.cn 原文，第 1-5 章此前已获官方 PDF、章节级条款号已确认，见上方 [信源说明]），五阶段结构…不变；[信源说明] 的限定维持不变（五阶段子条款措辞仍以官方 PDF 为准），待官网原文可访问后逐条核对。"以 commit `7c5702d` 实际内容为准。

- [x] **Step 4: `nist_ai_600_1.py` — 在 Web 核对结论清单末行之后、闭合 `"""` 之前插入新段落**

用 Edit：`old_string`（注意行首两个空格的缩进，逐字复制）：

```
  - MS-2.11-001 子类别 MS-2.11 存在，-001 后缀 [存疑，待人工核对]
```

`new_string`（原行 + 空行 + 两行新段落，段落顶格）：

```
  - MS-2.11-001 子类别 MS-2.11 存在，-001 后缀 [存疑，待人工核对]

二次复核：2026-07-17——联网仍未获官方原文；MS-2.10-002 连存在性都未证实，
全部 [存疑] 标注维持。唯一解决路径：人工直连 nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf 第 3 节逐字核对。
```

- [x] **Step 5: 验证（相关测试 + lint）**

Run: `uv run pytest tests/ -k "taxonomy or owasp or tc260 or nist" -v`
Expected: 87 项收集、全绿 0 fail（基线 #11；无测试断言 docstring，基线 #10——任何失败都意味着改到了 docstring 之外，回退重做）。

Run: `make lint`
Expected: clean（新增文本无反斜杠转义序列，不触发 SyntaxWarning；ruff format 不重排 docstring 内容行）。

- [x] **Step 6: 提交**

```bash
git status --short   # 预期仅三个 modified 的 tools/taxonomies/*.py
git add tools/taxonomies/owasp_agentic_2026.py tools/taxonomies/tc260_agent_deployment.py tools/taxonomies/nist_ai_600_1.py
git commit -m "docs: stamp 2026-07-17 re-verification notes into taxonomy module docstrings"
```

---

## Task D3: Wave 收尾——STATE.md / MANIFEST / 父计划勾选 / 本文件入库 / 终验（主控执行）

**Files:**
- Modify: `.upgrade/STATE.md`
- Modify: `.upgrade/MANIFEST.md`
- Modify: `.upgrade/plans/2026-07-17-formal-project-uplift.md`（勾选 Task 13/14 的 6 个 checkbox）
- Add: `.upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md`（本文件）

- [x] **Step 1: 更新 `.upgrade/STATE.md` Current Phase（:5）**

用 Edit：`old_string`（行 5 尾部子串）：

```
——Wave A–C 已完成（Wave C：T3.6 LLM Judge，Task 9–12，实施方案 `.upgrade/plans/2026-07-17-wave-c-llm-judge-implementation.md`）；下一步 Wave D（合规映射复核落账，Task 13–14），Wave E 待执行。
```

`new_string`：

```
——Wave A–D 已完成（Wave D：合规映射 2026-07-17 复核落账，Task 13–14，实施方案 `.upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md`）；下一步 Wave E（公开前检查与 CI 收尾，Task 15–18），Task 19 待仓库公开后执行。
```

- [x] **Step 2: 更新 `.upgrade/STATE.md` Current Task（:9）**

用 Edit：`old_string`：

```
**Wave A（门面与治理文件，Task 0–6）、Wave B（mypy 渐进式类型检查，Task 7–8）与 Wave C（T3.6 LLM Judge，Task 9–12）已完成**，下一步 Wave D（Task 13–14）。
```

`new_string`：

```
**Wave A（门面与治理文件，Task 0–6）、Wave B（mypy 渐进式类型检查，Task 7–8）、Wave C（T3.6 LLM Judge，Task 9–12）与 Wave D（合规映射复核落账，Task 13–14）已完成**，下一步 Wave E（Task 15–18）。
```

- [x] **Step 3: `.upgrade/STATE.md` Last Completed 顶部插入本 Wave 条目**

在 `## Last Completed` 下第一个条目（`- **Wave C T3.6 LLM Judge (2026-07-17)**...`）之前插入一行（`<D1>`/`<D2>` 用 `git log --oneline -3` 实际短哈希回填）：

```markdown
- **Wave D 合规映射复核落账 (2026-07-17)**：ISO/IEC 42005:2025（AI 系统影响评估，2025-05 发布）对标说明落入 docs/compliance/iso42001-mapping.md 第 6 节（初版对齐表，付费标准全文未核对处如实标注）；docs/plan/improvement-roadmap.md 新增 §10.7 复核增补（EU AI Act Omnibus 公报编号待回填 / TC260 正式发布确认但二手来源 / NIST AI 600-1 四动作项 [存疑] 维持 / OWASP ASI 无需改动 / 两个国内已生效法规锚点候选）；三个 taxonomy 模块 docstring 盖 2026-07-17 二次复核戳（仅注释零行为变更，87 项相关测试全绿）。对父计划三处记录性偏差（§6 编号 / TC260 [信源说明] 措辞 / §10.7 插入位）见实施方案。commits: <D1>/<D2>。实施计划：`.upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md`。
```

- [x] **Step 4: `.upgrade/MANIFEST.md` File Inventory 表末尾（wave-c 行之后）追加登记行**

```markdown
| `.upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md` | active | permanent | Wave D 合规映射复核落账实施计划（D1–D3，含 17 条探索基线与三处对父计划的记录性偏差决策：ISO 附录编号 §6 / TC260 [信源说明] 措辞修正 / §10.7 插入尾注前） |
```

- [x] **Step 5: 勾选父计划 Task 13/14 的 6 个 checkbox**

在 `.upgrade/plans/2026-07-17-formal-project-uplift.md` 中把以下 6 行的 `- [ ]` 改为 `- [x]`（逐行 Edit，行文本唯一）：

- `- [x] **Step 1: 读取 \`docs/compliance/iso42001-mapping.md\` 全文，确认其章节结构与落款格式**...`（:1142）
- `- [x] **Step 2: 在该文件末尾追加一节**`（:1144）
- `- [x] **Step 3: 在 \`docs/plan/improvement-roadmap.md\` 第 10 节末尾追加小节**...`（:1162）
- `- [x] **Step 4: 校验 + 提交**`（:1176，Task 13 内）
- `- [x] **Step 1: 三个文件的模块 docstring 中"核对日期"行附近各追加一行**...`（:1193）
- `- [x] **Step 2: 确认相关测试不受影响并提交**`（:1216）

注意 :1176 的 `**Step 4: 校验 + 提交**` 与后文 Task 17 Step 3 `**Step 3: 校验 + 提交**` 文字不同不会撞车，但 Edit 时仍建议携带前后行做唯一锚定。

- [x] **Step 6: 勾选本文件 D1/D2 各 Step 的 checkbox**（执行到此时 D1/D2 已完成，把上文对应 `- [ ]` 翻为 `- [x]`；D3 各步随做随勾）。

- [x] **Step 7: 终验（Wave D 全量回归）**

```bash
make lint && make doc-check && make typecheck && make test
```

Expected: lint clean；doc-check 0 违规；typecheck `Success: no issues found`；全量 650 passed, 1 skipped（与 Wave C 基线一致——本 Wave 零行为变更，测试数不增不减）。任何失败先修复再继续。

- [x] **Step 8: 提交收尾 commit**

```bash
git status --short   # 预期：STATE.md / MANIFEST.md / 父计划 / 本文件 四项
git add .upgrade/STATE.md .upgrade/MANIFEST.md .upgrade/plans/2026-07-17-formal-project-uplift.md .upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md
git commit -m "docs: close out Wave D compliance refresh in upgrade workspace records"
```

---

## Self-Review 核对记录（制定时完成）

1. **父计划覆盖**：Task 13 Step 1→D1 Step 1、Step 2→D1 Step 2、Step 3→D1 Step 3、Step 4→D1 Step 4-5；Task 14 Step 1→D2 Step 2-4、Step 2→D2 Step 5-6；父计划全局约束（STATE.md 更新 / 显式 staging / lint / doc-check）→ D3 与各任务收尾步。无遗漏。
2. **占位符扫描**：全文无 TBD/TODO/"适当处理"；仅 D3 Step 3 的 `<D1>/<D2>` 为执行时回填的 commit 哈希，已注明回填方式。
3. **一致性**：所有写入文案与父计划"联网调研关键结论" #5–#10 逐条对应；三处偏差（D-1/D-2/D-3）均有基线事实支撑并留档；锚点文本与探索基线逐字一致。
