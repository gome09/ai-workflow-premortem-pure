# 风险分类体系升级设计规格

> Status: Implemented（v1.1.0 落地 T2.1–T2.6；LLM08 依赖 RAG 组件，明确缓办。落地任务见 [../plan/phase-2-risk-taxonomy.md](../plan/phase-2-risk-taxonomy.md)）
> Last updated: 2026-07-14
> 对标依据：OWASP LLM Top 10 2025 (v2.0)、OWASP Top 10 for Agentic Applications 2026 (ASI)、NIST-AI-600-1 Generative AI Profile、TC260《智能体部署使用安全指引》（2026-07 发布）

---

## 1. 现状架构（已核实）

当前存在**两条独立机制**，本规格分别升级、不合并（保持确定性架构原则）：

**(A) 安全发现打标链**——判定与标签分离：
```
stages/base.py:scan_stage_io / core/session_service.py:scan_user_materials 等
  → tools/safety_classifier.py 的 scan_* 函数（正则判定 → risk_type 字符串）
  → tools/taxonomies/mapper.py:apply_taxonomy_to_safety_finding（查表打标）
  → SafetyFinding.taxonomy_refs / control_refs（list[str]）
  → core/gates/rules/safety_finding.py（门禁消费）
```
- `tools/taxonomies/` 下所有标准文件（`internal.py` / `owasp_llm_2025.py` / `nist_ai_rmf.py` / `microsoft_agent_failure_modes.py`）均为**纯 dict 标签表**，唯一含逻辑的是 `mapper.py`。
- `SafetyFinding.risk_type` 为 7 值 Literal 枚举（`core/models.py:417-425`）。
- `medical_ai_clinical.py` / `university_ai_edu.py` 领域扩展标签**仅被测试调用**（`mapper.py:refs_for_risk_type_extended`），生产链路未接入。

**(B) 项目风险分级链**——`core/gates/risk_profile.py:classify_project_risk` 纯关键词匹配输出 LOW/MEDIUM/HIGH/CRITICAL，决定门禁 blocking 集合；文件头自带 FIXME"关键词匹配太粗糙"。

已知缺口（对照 2026-07-13 外部核实结果）：
1. OWASP LLM Top 10 2025 覆盖 6/10，缺 LLM05/07/08/10。
2. NIST 映射只到 GOVERN/MAP/MEASURE/MANAGE 四个大类字母，无具体动作项。
3. **OWASP 2026 年新发布 Agentic Applications Top 10（ASI01-ASI10）完全未覆盖**——本项目是 LangGraph Agent 工作流平台，这是最直接适用的新标准。
4. TC260《智能体部署使用安全指引》（2026-07 正式发布，评估/准备/部署/使用/停用五阶段）未映射。
5. slowapi 限流基础设施（`api/limiter.py`：注册 5/hour、登录 10/minute、阶段推进 20/hour、消息 30/hour）与风险分类体系脱节，无 Unbounded Consumption 风险类型。

## 2. 设计原则

1. **判定与标签继续分离**：新增风险的判定逻辑进 `tools/safety_classifier.py` / `tools/prompt_injection_scanner.py`，标签表继续放 `tools/taxonomies/`，`__init__.py` docstring 声明的"deterministic, dependency-free mappings"契约不变。
2. **`taxonomy_refs: list[str]` 结构不变**：新标准以新前缀字符串接入（`OWASP_ASI_2026:ASI02`、`NIST_AI_600_1:MP-2.3` 等），报告聚合（`build_taxonomy_summary`）与存储层零改动。
3. **枚举扩展保持向后兼容**：`risk_type` Literal 只增不改不删，已落库的 finding 不受影响。
4. **每条标签可回答"依据是什么"**：新增标签表的每个条目附带标准原文条款号，这是阶段 2 验收口径（"回答具体动作项而不只是字母大类"）。

## 3. OWASP LLM 2025 补齐设计（LLM05 / LLM07 / LLM10）

### 3.1 新增风险类型

`core/models.py` 的 `SafetyFinding.risk_type` Literal 扩展 3 个值：

| 新 risk_type | 对应 | 判定来源 |
|---|---|---|
| `improper_output_handling` | LLM05 | safety_classifier 新增输出侧扫描规则 |
| `system_prompt_leakage` | LLM07 | prompt_injection_scanner 拆分现有规则 |
| `unbounded_consumption` | LLM10 | 限流/用量计数接入（3.4） |

`tools/risk_taxonomy.py:RISK_DESCRIPTIONS` 同步补 3 条中文描述；`tools/taxonomies/internal.py` / `owasp_llm_2025.py` / `nist_ai_rmf.py` / `microsoft_agent_failure_modes.py` 四个标签表同步补 key（保持"每个 risk_type 在所有标签表中都有条目"的隐含约定）。

### 3.2 LLM07：System Prompt Leakage 判定拆分

现状：`tools/prompt_injection_scanner.py` 的规则 3（`system prompt`）、规则 6（`泄露.*(系统提示词|system prompt)`）能匹配泄露类输入，但统一归类为 `prompt_injection`（LLM01）。

目标形态：
- `prompt_injection_scanner.py` 从"返回 bool"升级为返回命中类别：新增 `LEAKAGE_PATTERNS`（把现有规则 3/6 移入，并补充 `repeat (your|the) (system|initial) (prompt|instructions)`、`输出你的(系统提示|初始指令)` 等泄露特征），保留 `has_prompt_injection()` 兼容签名，新增 `classify_injection(text) -> Literal["injection", "leakage", None]`。
- `tools/safety_classifier.py:scan_text` 据此产出 `system_prompt_leakage` 类型 finding（severity 默认 high——系统提示词含门禁策略描述，泄露即绕过线索）。

### 3.3 LLM05：Improper Output Handling 判定

判定点选在**输出消费边界**而非生成时：
- `scan_text` 对 AI 输出增加规则组 `UNSAFE_OUTPUT_PATTERNS`：`<script`、`javascript:` 伪协议链接、`on\w+=` 内联事件、SQL DML/DDL 语句特征、shell 命令注入特征（`; rm `、`$(`）。命中产出 `improper_output_handling`（severity=medium，供人工判断是否属演示性内容）。
- `core/report_service.py` 的 Markdown 导出对上述模式做转义处理（防止报告被下游渲染器执行），此项独立于 finding 机制，属硬化措施。

### 3.4 LLM10：Unbounded Consumption 接入

把"有基础设施但未接入分类体系"接通，分两层：
- **计数层**：`core/context_manager.py` 已控制单次调用 `max_tokens`；新增会话级累计计数——`ProjectContext` 增加 `llm_call_count` / `llm_token_estimate` 字段（由 `core/execution_service.py` 的 `execute_one_turn` 递增），阈值配置进 settings（默认：单会话 200 次调用 / 500k tokens 告警）。
- **判定层**：超阈值时产出 `unbounded_consumption` finding（severity=medium，requires_human_review=False——告警不阻断，避免误伤长会话）；同时 slowapi 429 事件在 `api/limiter.py` 的 exception handler 中记入审计日志（接入 `core/audit_service.py`），作为租户级滥用证据。

### 3.5 LLM08 明确缓办

Vector and Embedding Weaknesses 依赖 RAG/向量检索，项目当前无此组件。**决策：不预先实现**，在 `owasp_llm_2025.py` 文件头注释记录"LLM08 缓办，引入 RAG 时激活"，避免文档-代码不一致。

## 4. NIST-AI-600-1 动作项升级设计

新增 `tools/taxonomies/nist_ai_600_1.py`（不改动现有 `nist_ai_rmf.py`，大类标签继续保留）：

```python
# 结构示例：risk_type → Generative AI Profile 具体动作项
NIST_GAI_ACTION_REFS = {
    "prompt_injection":     ["NIST_AI_600_1:MS-2.7-008"],   # 红队测试 GAI 系统
    "sensitive_info":       ["NIST_AI_600_1:MS-2.10-002"],  # 隐私风险度量
    "unsupported_claim":    ["NIST_AI_600_1:MS-2.5-005"],   # Confabulation 度量
    "over_autonomy":        ["NIST_AI_600_1:GV-1.3-002"],   # 人类监督程度界定
    ...
}
NIST_GAI_ACTION_DESCRIPTIONS = { "MS-2.7-008": {"zh": "...", "source": "NIST AI 600-1 §..."}, ... }
```

- 首批覆盖 6-8 个高频动作项（对应 GAI Profile 的 12 类风险中与本项目 7+3 个 risk_type 相交的部分），每条附条款号与中文摘要。
- `mapper.py:refs_for_risk_type` 聚合顺序追加 `NIST_GAI_ACTION_REFS`。
- **注意**：NIST AI RMF 1.0 正在修订中（官网确认，尚无新版号），且 NIST 已启动 AI Agent 标准计划（2026-02）与关键基础设施 Profile（2026-04 概念稿）——`nist_ai_600_1.py` 文件头需注明核对日期，修订版发布后按阶段 2 计划的跟踪任务更新条款号。

## 5. OWASP Agentic Top 10 2026（ASI）接入设计【新增标准】

本项目的 `INTERNAL_ATTACK_REFS` 已有 11 个 attack_type，与 ASI 天然对应。新增 `tools/taxonomies/owasp_agentic_2026.py`：

| 内部 attack_type | ASI 映射（初稿） |
|---|---|
| direct/indirect_prompt_injection | ASI01 Agent Goal Hijack |
| tool_overreach | ASI02 Tool Misuse & Exploitation |
| excessive_agency / unsafe_autonomy | ASI03 Agent Identity & Privilege Abuse |
| source_poisoning | ASI06 Memory & Context Poisoning |
| policy_bypass | ASI09 Human-Agent Trust Exploitation |
| evaluator_gaming | ASI10 Rogue Agents（映射存疑项，落地时按官方定义复核） |

- risk_type 侧同样给出映射（`over_autonomy` → ASI03 等）。
- 该文件与 `owasp_llm_2025.py` 并列，`mapper.py` 聚合顺序追加。
- 上表为设计初稿，**落地第一步是通读 genai.owasp.org 的 ASI 正式定义后逐条复核**，映射不确定的条目宁缺毋滥。

## 6. TC260《智能体部署使用安全指引》映射设计

2026-07 该指引已正式发布（覆盖评估/准备/部署/使用/停用五阶段），路线图中"文件真实性待确认"的前提已解除。设计分两步：

1. **前置任务**：从 TC260 官网获取全文（官网 upload 区可下载 PDF），存档条款摘要至 `.upgrade/reports/`。
2. **映射落地**：新增 `tools/taxonomies/tc260_agent_deployment.py`，两类映射：
   - 五阶段 ↔ 本项目四阶段工作流的对应关系表（评估≈Stage1 失败模式识别、准备≈Stage2 工作流设计、部署/使用≈Stage3 压力测试+Stage4 触发策略、停用=当前无对应——这本身是一个值得记录的产品缺口）；
   - 指引中的安全要求（最小权限运行、目录访问限制、敏感数据最小必要提供等）→ 对应 attack_type/control_refs 标签。
3. 同源政策背景一并纳入参考：《智能体规范应用与创新发展实施意见》（网信办/发改委/工信部，2026-05）、GB/T 45654-2025《生成式人工智能服务安全基本要求》（TC260-003 升级版，已实施）。

## 7. 领域扩展标签接入生产链路

`refs_for_risk_type_extended` / `controls_for_risk_type_extended`（`mapper.py:139-163`）当前仅测试可达。目标形态：
- `apply_taxonomy_to_safety_finding(finding, domain=None)` 增加可选 domain 参数；`stages/base.py` / `safety_classifier.py` 调用侧从 `ctx` 取当前 domain profile 名称传入；domain 命中 `medical_ai` / `university_ai` 时叠加领域标签。
- 行为变化仅为 taxonomy_refs 增量，无破坏性。

## 8. 风险分级链（机制 B）的处理决策

`core/gates/risk_profile.py` 的关键词分级**本阶段不重写**：
- 确定性关键词匹配符合"工作流转换确定性、代码控制"的架构原则，FIXME 中的 embedding/LLM 分类方案引入不确定性，需配套人工确认机制，归入阶段 3 的 LLM Judge 设计统一考虑（见 [governance-platform.md](governance-platform.md) 第 5 节）。
- 本阶段仅做增量：关键词表补充《指引》与 GB/T 45654 提示的智能体场景词（如"自主执行/工具调用/无人值守"→ HIGH 及以上）。

## 9. 兼容性与验证

- 存量数据：risk_type 枚举只增；taxonomy_refs 为字符串列表追加新前缀——SQLite/PostgreSQL 存储层与 alembic 均无 schema 变更（`ProjectContext` 新增计数字段走 `core/migrations/` 的数据 schema 迁移）。
- 测试基线：现有 `tests/test_domain_profile_*.py` 继续通过；新增每个新 risk_type 的判定用例（正例+反例）、每张新标签表的完整性用例（所有 risk_type/attack_type key 均有条目）、LLM10 阈值触发用例。
- 验收口径（对应路线图阶段 2）：OWASP LLM 覆盖 ≥9/10（LLM08 有记录的缓办决策）；任一 finding 的 taxonomy_refs 能给出 NIST 具体动作项；ASI 与 TC260 映射表入库并有测试。
