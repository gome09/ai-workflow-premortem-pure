# 阶段 2 实施计划：AI 风险分类体系补强

> 上游路线图：[improvement-roadmap.md](improvement-roadmap.md) 第 6 节「阶段 2」。
> 配套设计规格：[../spec/risk-taxonomy-engine.md](../spec/risk-taxonomy-engine.md)（本计划的所有技术决策依据在 spec 中，此处只列任务与验收）。
> 现状基线核实日期：2026-07-13。
> 状态：未启动。前置依赖：无硬依赖（可与阶段 1 并行）；建议在阶段 0 完成后启动以便新增代码走安全化的 CI。

---

## 1. 目标

把"贴标签式"风险分类升级为可回答"具体依据哪一条标准条款"的分类体系；补齐 OWASP LLM Top 10 2025 缺口；接入 2026 年新出现的两个直接适用标准（OWASP Agentic Top 10、TC260 智能体部署使用安全指引）。

## 2. 现状基线（已核实，详见 spec 第 1 节）

- OWASP LLM 2025 覆盖 6/10（`tools/taxonomies/owasp_llm_2025.py`），缺 LLM05/07/08/10。
- `nist_ai_rmf.py` 仅映射到 GOVERN/MAP/MEASURE/MANAGE 四个大类标签。
- 判定逻辑集中在 `tools/safety_classifier.py`（正则）与 `tools/prompt_injection_scanner.py`（7 条正则，返回 bool）。
- `SafetyFinding.risk_type` 为 7 值 Literal（`core/models.py:417-425`）。
- 领域扩展标签（medical/university）生产链路未接入，仅测试可达。
- 限流基础设施存在（`api/limiter.py`）但与风险分类脱节。

## 3. 任务分解

### T2.1 OWASP LLM05/07/10 三项补齐

- **内容**：按 spec 第 3 节落地——扩展 `risk_type` 枚举 3 个值；`prompt_injection_scanner.py` 拆分出 `LEAKAGE_PATTERNS`（LLM07）；`safety_classifier.py` 新增 `UNSAFE_OUTPUT_PATTERNS` 输出侧规则组（LLM05）；会话级 LLM 调用/token 计数 + 阈值告警 finding（LLM10）。
- **涉及文件**：`core/models.py`、`tools/prompt_injection_scanner.py`、`tools/safety_classifier.py`、`tools/risk_taxonomy.py`、`tools/taxonomies/`（四张标签表补 key）、`core/context_manager.py`、`core/execution_service.py`、`core/migrations/`（ProjectContext 新增计数字段）。
- **验收**：每个新 risk_type 有正例+反例测试；`make e2e-mock` 全绿；LLM08 缓办决策已写入 `owasp_llm_2025.py` 文件头注释。
- 工作量：L

### T2.2 NIST-AI-600-1 动作项引用

- **内容**：新增 `tools/taxonomies/nist_ai_600_1.py`（6-8 个高频动作项，每条含条款号+中文摘要），`mapper.py` 聚合接入。设计见 spec 第 4 节。
- **前置**：从 NIST 官网下载 NIST-AI-600-1 原文并核对动作项编号（AI RMF 1.0 修订中，文件头注明核对日期）。
- **验收**：任一 finding 的 `taxonomy_refs` 包含具体动作项编号；标签表完整性测试通过。
- 工作量：M

### T2.3 OWASP Agentic Top 10 2026（ASI）接入【新增，路线图未覆盖】

- **内容**：新增 `tools/taxonomies/owasp_agentic_2026.py`，把 11 个内部 attack_type 与 7+3 个 risk_type 映射到 ASI01-ASI10。映射初稿见 spec 第 5 节。
- **前置**：通读 genai.owasp.org 的 ASI 正式条目定义，逐条复核初稿映射，不确定的条目宁缺毋滥。
- **验收**：映射表入库、有完整性测试；红队用例（`apply_taxonomy_to_redteam_case`）能带出 ASI 标签。
- 工作量：M

### T2.4 TC260《智能体部署使用安全指引》映射

- **内容**：该指引已于 2026-07 正式发布（路线图 8.2 节"真实性待确认"前提已解除）。第一步获取官方全文并存档条款摘要至 `.upgrade/reports/`；第二步新增 `tools/taxonomies/tc260_agent_deployment.py`（五阶段↔四阶段工作流映射 + 安全要求→控制项标签）。设计见 spec 第 6 节。
- **验收**：条款摘要存档；映射表入库；"停用阶段无对应能力"作为已知产品缺口记录进映射文件注释与本文件第 5 节。
- 工作量：M

### T2.5 领域扩展标签接入生产链路

- **内容**：`apply_taxonomy_to_safety_finding` 增加 domain 参数，medical/university 场景的 finding 叠加领域标签。设计见 spec 第 7 节。
- **验收**：以 `university_ai` mock 场景跑一轮全流程，产出的 finding 带 `UNIV_*` 标签；现有 `tests/test_domain_profile_*.py` 不回退。
- 工作量：S

### T2.6 标准动态跟踪（持续任务，无终点）

- 《网络安全技术 人工智能技术涉及未成年人应用安全指南》征求意见截止 **2026-08-16**，定稿后核对 `university_mental_health` 场景的未成年人数据处理逻辑。
- TC260 分行业指导性技术文件（金融/广电/卫生健康/政务，2026-07 起密集征集参编）定稿后评估是否新增对应 `stages/domain_profiles/`。
- NIST AI RMF 修订版、AI Agent Interoperability Profile（NIST 预告 2026 Q4）发布后更新 T2.2 条款号。
- **验收**：每次跟踪检查在 `.upgrade/logs/` 留一条记录（哪怕结论是"无变化"）。

## 4. 推进顺序与依赖

```
T2.1（独立，最大工作量，先启动）
T2.2 / T2.3 / T2.4（互相独立，可并行；各自有"先读原文"的前置步骤）
T2.5（依赖 T2.1 完成后再动 mapper.py，避免合并冲突）
T2.6（贯穿整个阶段，与其他任务并行）
```

## 5. 风险与注意事项

- `risk_type` 枚举扩展会触及 `core/models.py` 的 Literal 与所有消费方（gates 规则、oversight 动作创建、前端展示），T2.1 需全链路回归（`make e2e-full-test`）。
- 新增正则规则的误报率需用 mock 场景语料实测：LLM05 的输出侧规则最容易误伤"演示性代码块"，severity 定为 medium + 人工复核而非直接阻断，就是为此留的缓冲。
- ASI/TC260 映射是"解释性标签"而非"判定规则"，不改变门禁行为——不要在本阶段顺手往门禁里加新的 blocking 规则（那属于阶段 3 的规则治理议题）。
- 已知产品缺口（本阶段记录、不解决）：TC260 五阶段中的"停用"阶段（模型/系统退役时的数据清理与交接）在本项目工作流中无对应环节。

## 6. 阶段验收清单

- [ ] OWASP LLM Top 10 2025 覆盖从 6/10 提升到 9/10（LLM08 有记录的缓办决策）
- [ ] 任一风险分类结果能回答"对应 NIST AI RMF 哪个具体动作项"（不只是字母大类）
- [ ] OWASP ASI 2026 映射表入库并有完整性测试
- [ ] TC260 智能体指引条款摘要存档 + 映射表入库
- [ ] 领域扩展标签在生产链路可达
- [ ] `make test` / `make e2e-full-test` 全绿
