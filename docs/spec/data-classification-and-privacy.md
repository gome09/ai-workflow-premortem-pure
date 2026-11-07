# 数据分类分级与隐私保护设计规格

> Status: Implemented（自 v1.0.3 起落地 T1.1–T1.9：数据分级 / 字段加密 / PII 掩码 / AI 生成标识 / PIA，沿用至今；v1.4.0 增加解密 fail-closed 与事件/审计统一脱敏。落地任务见 [../archive/plan/phase-1-security-compliance.md](../archive/plan/phase-1-security-compliance.md)）
> Last updated: 2026-10-31
> 合规依据：PIPL 第 28/51/55/56/57 条、DSL 第 21 条、《人工智能生成合成内容标识办法》（2025-09-01 施行）、EU AI Act Art.50 透明度义务（2026-08-02 生效）、GB/T 22239-2019 日志留存要求

---

> **阅读提示**：第 1 节是 2026-07-13 落地前历史基线，不代表当前实现；当前能力及其启用条件见第 3–6 节。字段加密自 v1.4.0 起为 fail-closed：PostgreSQL 后端或 `APP_ENV=production` 下缺失或错误 `DATA_ENCRYPTION_KEY` 会抛 `FieldDecryptionError`，不会静默返回明文；Docker 部署由 `make setup` 生成密钥，非 Docker 部署仍须显式配置。

## 1. 落地前历史基线（2026-07-13）

| # | 事实 | 证据 |
|---|---|---|
| 1 | `ProjectContext` 经 `model_dump` 整体序列化为 `context_json` **明文落库**；仅 `llm_traces`/`audit_events`/`report_artifacts` 三类大字段被截断分表，用户材料相关字段（`research_target`/`goal`/`user_materials`/`evidence_sources.summary/claims`）无任何脱敏 | `storage/backends/postgres.py:52-116`、`sqlite_store.py:401-455` |
| 2 | 全仓代码**无任何**加密/脱敏/去标识化实现（encrypt/mask/redact/anonym 检索仅命中文档与建议文案） | 全仓检索结论 |
| 3 | 用户材料入口是 `ProjectContext.user_materials: list[str]`（纯文本粘贴，**不存在** `MaterialParser` 类，不支持文件解析），经 `core/evidence_service.py:44-71` 包装为 `EvidenceSource` 后**注入外部 LLM API（DeepSeek）的 prompt** | `core/models.py:789`、`core/evidence_service.py:74-104`、`core/context_manager.py:50-79` |
| 4 | 报告免责声明仅英文一句，位于 JSON 最后一个键 / Markdown 最后一节（"## 19. Disclaimer"），非首屏 | `core/report_service.py:377,840-846` |
| 5 | 审计事件 append-only 无留存/清理策略；无数据库备份配置（仅 Prometheus 指标 15d） | `core/audit_service.py`、`docker-compose.yml:149` |
| 6 | **路线图 3.5 节的认知需修正**：`university_mental_health` 场景并没有"自动升级为高风险"——`core/gates/risk_profile.py` 关键词表不含"心理/精神/学生"，该场景示例输入实测落入 MEDIUM 档 | `core/gates/risk_profile.py:56-101`、`examples/university_ai_mental_health_input.md` |
| 7 | 已有的敏感信息检测仅覆盖密钥泄露（`SECRET_PATTERNS`：`sk-*`/`AKIA*`/`api_key=`），不覆盖个人信息（身份证/手机号/姓名） | `tools/safety_classifier.py:12-16` |
| 8 | 无数据分类分级机制；无面向会话/审计数据的删除接口（唯一 DELETE 端点是评测数据集） | `api/routers/eval_datasets.py:109` |

## 2. 设计总览

五个子系统，可独立落地、互不阻塞：

```
① 数据分类分级        → ProjectContext.data_classification 字段 + 判定与覆写
② 敏感数据保护        → 字段级静态加密（落库前） + PII 检测/掩码（出境到 LLM 前）
③ AI 生成内容标识     → 报告首屏双语标识
④ 数据生命周期        → 留存策略 + 删除接口 + 备份指引
⑤ PIA 支持           → 模板 + 平台自评 + 高敏场景实测存档
```

## 3. 子系统①：数据分类分级（DSL 21 条 / PIPL 51 条）

### 3.1 分级定义

`ProjectContext` 新增字段 `data_classification: Literal["public_demo", "business_internal", "sensitive_personal"]`：

| 级别 | 含义 | 默认判定 |
|---|---|---|
| `public_demo` | 内置演示场景数据，无真实业务信息 | 会话由 `scenarios/registry.py` 场景创建 |
| `business_internal` | 用户输入的真实业务材料 | 非场景创建的会话默认值 |
| `sensitive_personal` | 材料或聊天正文含敏感个人信息（PIPL 28 条：医疗健康、未成年人、生物识别等） | 当前四类正则 PII 命中时自动升级；语义敏感但未命中正则的内容必须人工标记 |

### 3.2 判定与覆写

- 会话创建时只按是否为内置场景设置 `public_demo` / `business_internal`；加入材料以及每轮聊天正文进入模型前都会扫描身份证号、手机号、邮箱、银行卡号四类模式，命中后升级为 `sensitive_personal`（`public_demo` 命中真实 PII 时同样升级）。当前不识别姓名、学号或“心理健康”等语义类别，部署方必须人工覆写这类敏感场景。
- 人工覆写走新增端点 `PATCH /sessions/{id}/data-classification`（editor/admin），**只允许升级或同级修改，降级必须 admin** 且写 `AuditEvent`。
- 分级**向上联动 AI 风险分级**：`sensitive_personal` 会话在 `core/gates/risk_profile.py:classify_project_risk` 中作为升档信号，把 MEDIUM 升为 HIGH、把 HIGH 升为 CRITICAL；该升档同时是**地板值（floor）**，后续 low-scope 降档不得把 `sensitive_personal` 会话拉回 MEDIUM/LOW。数据分级与 AI 风险分级仍是两个独立维度（一个关于"处理的数据"，一个关于"被评估的 AI 系统"），仅单向联动。

  > ✅ **缺口已修复（2026-09-01）**：修复前该升档不是地板值——low-scope 降档在升档之后执行，`sensitive_personal` + 个人/学习类关键词的会话可落到 LOW。修复引入 `_TIER_ORDER` 与 `tier_floor`（`sensitive_personal` → floor HIGH），第 4 步降档与第 5 步 LOW 覆盖分支均尊重 floor；回归测试见 `tests/test_sensitive_personal_floor.py`（6 条）。

### 3.3 关键词修正（配套）

`risk_profile.py` 关键词表补充：`_HIGH_KEYWORDS` 增加"心理|精神|抑郁|自杀|self.?harm|mental health|心理健康"与"学生|student"（与既有"儿童|未成年人"同组）。修正后 `university_mental_health` 示例输入应实测落入 HIGH 及以上（作为回归测试固化）。

## 4. 子系统②：敏感数据保护

### 4.1 字段级静态加密

- **方案**：应用层对称加密（`cryptography.Fernet`），密钥来自环境变量 `DATA_ENCRYPTION_KEY`（走 `.env`/secrets，与 `JWT_SECRET` 同级管理）。
- **加密范围**（`data_classification ∈ {business_internal, sensitive_personal}`；`public_demo` 保持明文）：`research_target`、`goal`、`user_materials`、`evidence_sources[*].summary/claims`（仅 `source_type=user_material`）、`conversation_history[*][*].content`、`pending_actions[*]` 的自由文本与 `payload_before/payload_after`、`report_artifacts[*].content_markdown/content_json`；投影表列级加密由 `ENCRYPTED_COLUMNS` 注册（`human_actions`、`evidence_sources`、`report_artifacts`）。权威实现见 `storage/field_security.py`。
- **实现位置**：上下文写入侧 `encrypt_fields_for_storage`（`_build_context_json_for_storage` 截断之后、`json.dumps` 之前）、读取侧 `decrypt_fields_after_load`（`migrate_context` 之后）；投影表用 `encrypt_row_columns` / `decrypt_row_columns`。密文带 `enc:v1:` 前缀以便识别与将来轮换；PostgreSQL 与 SQLite 两个后端行为一致。
- **历史明文回填（v1.7.0）**：早期版本因字段名拼写错误只加密 `research_goal`，实际字段 `goal` 仍以明文落库。修复后新增 `scripts/encrypt_legacy_goal.py` 与两后端 `backfill_goal_encryption()`：默认 dry-run，`--apply` 才写库，`--verify` 校验密文可解密，`--decrypt --apply --allow-plaintext` 仅用于回退到旧版本代码；脚本幂等且跳过 `public_demo`。回滚旧代码前必须先解密或恢复升级前备份，否则旧代码会把 `goal` 密文当作明文展示。
- **fail-closed（v1.4.0 起）**：`APP_ENV=production` 或 `storage_backend != sqlite` 时，检测到 `enc:v1:` 密文但无密钥、或密钥错误/密文损坏，一律抛 `FieldDecryptionError`，不会把密文当明文返回，也不会静默降级为明文读取。SQLite 离线演示允许无密钥明文。

### 3.x 六因子风险模型与数据敏感性（v1.5.0）

- `ProjectContext.risk_profile` 记录 `impact` / `autonomy` / `data_sensitivity` / `reversibility` / `scale` / `external_exposure` 六个 0–3 因子；`data_sensitivity` 与 `data_classification` 共同参与确定性风险等级计算。
- `data_classification=sensitive_personal` 是硬性风险地板（至少 HIGH）；与高风险结构因子组合时升为 CRITICAL，任何人工 override 都不应突破该 floor。
- 人工风险 override 以 append-only `RiskOverrideRecord` 记录原等级、请求等级、生效等级、floor、原因、操作者、角色与 `tenant_id`，并写入 `risk_tier_overridden` 审计事件；降级仅 admin 可执行且仍受 floor 限制。
- LLM 仅可提供 `llm_explanation` 解释文本，不参与因子或最终等级计算。

- **降级行为**：未配置密钥时——demo/lite 模式静默明文；生产模式（postgres backend）启动时打 WARNING 并在 `/health` 暴露 `data_encryption: disabled`。
- **当前部署事实（2026-10-27）**：`.env.example` 的 `DATA_ENCRYPTION_KEY` 默认为空，但 `make setup` / `scripts/gen_secrets.sh` 会生成 `secrets/data_encryption_key` 并以 Docker secrets 注入；环境变量仍然优先于 secret 文件。非 Docker 部署仍需显式设置 `DATA_ENCRYPTION_KEY`，并在启动后确认 `/health` 返回 `data_encryption=enabled`。
- **不做**：全库透明加密（TDE 属部署层，不属应用层）、可搜索加密（当前无按材料内容检索的需求）。

### 4.2 PII 检测与出境前掩码

动机：用户材料与聊天正文会随 prompt 发送到外部 LLM API（DeepSeek），这是一次"向第三方提供个人信息"的数据流转，PIPL 视角必须可控。

- `tools/safety_classifier.py` 新增 `PII_PATTERNS` 规则组：中国大陆身份证号（18 位含校验特征）、手机号（`1[3-9]\d{9}`）、邮箱、银行卡号（Luhn 可后置）。命中产出 `sensitive_info` finding（复用现有 risk_type），敏感类别（如身份证）severity=high。
- 新增配置 `PII_MASK_BEFORE_LLM`（默认 `false`，避免破坏现有演示行为）：开启后 `core/evidence_service.py:format_evidence_for_prompt` 对 evidence summary 与 `user_materials` 注入文本中的命中项做模式保留掩码（`110***********1234`）。
- **出站守卫（v1.5.0 起）**：`core/llm/outbound_guard.py` 在所有 `llm.invoke` 出站点（阶段执行器、INIT、eval `llm_node`、LLM judge）统一执行掩码。`sensitive_personal` 会话**始终掩码，忽略 `PII_MASK_BEFORE_LLM`**；`business_internal` / `public_demo` 继续遵循该开关。非文本消息在 `sensitive_personal` 下 fail-closed（`OutboundPIIBlockedError`）。
- **聊天正文覆盖（2026-11-07 起）**：`SessionWorkflowService.send_message` 在写入 `pending_input` 前调用 `tools.safety_classifier.scan_user_message_pii`，把聊天正文纳入与补充材料相同的四类正则检测和分级升级。命中后会话升级为 `sensitive_personal`，`guard_messages` 会对 system prompt、历史消息与本轮消息统一掩码，不再存在“直接消息/历史不覆盖”的缺口。
- **当前边界**：掩码仍只覆盖四类正则 PII（身份证 / 手机号 / 邮箱 / 银行卡），语义敏感但未命中正则的内容不会被自动识别；该守卫不替代入口级数据最小化。

### 4.3 LangGraph checkpoint 数据副本

- 默认 `single_step` 不写 LangGraph checkpoint。显式启用 `langgraph_interrupt` 后，checkpoint 会保存完整 `ProjectContext` 执行快照，因而可能包含用户材料、证据、对话历史及其他个人信息；它属于与业务表并列的数据副本，必须纳入数据清单、备份、泄露响应和删除流程。
- PostgreSQL checkpoint 只允许使用持久后端，并由独立 `CHECKPOINT_ENCRYPTION_KEY` 通过 Fernet 加密 payload。`make setup` 会单独生成 `secrets/checkpoint_encryption_key`，该 key 不得复用 `DATA_ENCRYPTION_KEY`，也不能替代业务字段加密。
- SQLite/local 可使用 memory checkpoint，但它不持久化、进程重启后不可恢复，不得用于生产。
- 删除会话时先按 tenant-scoped thread ID 清理 checkpoint；清理失败则保留权威业务会话并返回失败，避免出现“业务记录已删除但敏感执行快照残留”的假性成功。

### 4.4 事件/审计脱敏（v1.4.0）

事件与审计是独立的持久化路径（`session_events` / `audit_events`），不能沿用上下文加密假设，因此统一在写入层脱敏：

- 入口：`core/session_service.py::_log_event` 与 `core/audit_service.py` 在落库前调用 `core/data_protection.py::redact_payload` / `snapshot`。
- 规则：`business_internal` / `sensitive_personal` 的自由文本键（`user_input` / `summary` / `claims` / `description` / `trigger_reason` / `reviewer_note` / `content` / `payload_before` / `payload_after` / `title` 等，权威清单见 `FREE_TEXT_KEYS`）整值替换为确定性摘要信封 `{"_redacted": true, "sha256": ..., "length": ...}`；非敏感字符串超过 `MAX_PLAIN_STRING`（200）截断。
- 用户消息事件只记录 `input_sha256` / `input_length` / 状态，不落原文。
- `public_demo` 保持可读，保住离线演示的审计可观测性。
- 确定性：同一输入与同一分级必得同一信封，不依赖随机数或外部服务，便于测试与审计比对。

## 5. 子系统③：AI 生成内容标识（《标识办法》+ EU AI Act Art.50）

- **Markdown 报告**：标题后首屏插入双语显式标识块（现有"## 19. Disclaimer"保留不动，保证向后兼容）：
  ```markdown
  > **本报告由 AI 辅助生成（AI-Generated Content）**
  > 依据《人工智能生成合成内容标识办法》进行显式标识。报告内容须经人工审核确认后方可用于实际决策。
  > AI-generated outputs must be reviewed by humans before real-world use.
  ```
- **JSON 报告**：`build_report_dict` 新增 `ai_generated_notice` 结构化字段（`{"zh": ..., "en": ..., "basis": "《人工智能生成合成内容标识办法》", "generator": ..., "generator_version": ...}`）。落地位置为字典**尾部、`disclaimer` 键之前**（`core/report_service.py`，与保留的 `disclaimer` 相邻聚合；设计初稿曾拟放在头部 `schema_version` 之后，落地时调整）；首键仍为 `schema_version`。
- **隐式标识**：JSON 本身即文件元数据载体，`ai_generated_notice` + `generated_at` + `schema_version` 组合已满足"文件元数据标注"精神；Markdown 在文首 HTML 注释中附 `<!-- ai-generated: true; generator: ai-workflow-premortem vX.Y.Z -->`。
- 时点提示：EU AI Act 透明度义务 2026-08-02 生效（Digital Omnibus 未推迟该项）——本项目不强制适用，但导出报告若流转出企业，此标识是低成本对齐。

## 6. 子系统④：数据生命周期

- **留存策略执行化**：`core/config.py` 提供 `audit_retention_days`（默认 **183**）与 `session_retention_days`（默认 0=永久）。`core/retention_service.py` 在应用 lifespan 启动后按 `RETENTION_SWEEP_INTERVAL_SECONDS`（默认 86400 秒）周期扫描，首次扫描在启动后一个周期执行。`RETENTION_DRY_RUN` 默认 `true`，只统计候选不写库；显式设为 `false` 才实际删除。到期会话走与管理员删除一致的链路（checkpoint → 审计归档 → 投影表级联 → 缓存失效）；到期审计事件同时删除活动表与归档表，按 `RETENTION_BATCH_SIZE`（默认 1000）分批。`/health` 暴露 `retention_enabled`、`retention_dry_run` 与 `retention_scheduler` 状态。
- **删除能力**：新增 `DELETE /sessions/{id}`（admin），级联删除各独立表记录，但**审计事件不删除**（改为写入一条 `session_purged` 审计事件保留处置痕迹）——PIPL 删除权与审计完整性的平衡点。
- **派生数据与租户边界（v1.4.0）**：`purge_session` 除 `sessions` 外还删除 `gate_evaluation_records` 等投影/派生化数据；所有删除谓词都带 `tenant_id`（PostgreSQL 为 `session_id = %s AND tenant_id = %s::uuid`），仅在 `tenant_id` 为空的历史行上退化为按会话 ID 删除，避免跨租户误删。留存执行器从 `list_expired_sessions` 逐行取 `session_id` + `tenant_id` 后调用同一删除链路，因此 retention 与管理员删除的数据覆盖范围一致，且不会跨租户删除。回归测试见 `tests/test_retention_tenant_scope.py`。
- **备份指引**：`docs/` 补充生产部署备份章节（`pg_dump` 定时 + volume 快照 + 恢复演练清单），属文档交付，不写代码。

## 7. 子系统⑤：PIA 支持（PIPL 55/56 条）

产品定位（路线图第 8.4 节的两层结构，均需要）：

1. **平台自身的 PIA**（工具提供方责任）：对"本平台处理用户上传材料"这一活动做一次评估，覆盖 PIPL 56 条三要素（目的合法性/对个人权益的影响与风险/保护措施与风险适配性），重点评估"材料流向外部 LLM API"数据流。产出 `docs/compliance/pia-platform.md`，留存 3 年，随重大架构变更复评。
2. **内置 PIA 模板供用户使用**（平台功能）：`docs/compliance/pia-template.md` 模板 + 对 `university_mental_health` 场景实际填写一份评估存档（`docs/archive/pia-university-mental-health.md`，已归档），作为高敏场景的示范样本。首期是文档交付；"PIA 表单化进平台（表单/审批/到期提醒）"列为阶段 3 治理平台候选功能，不在阶段 1 承诺。

## 8. 数据流转全景（设计后目标态）

```
用户粘贴材料
  → 四类正则 PII 扫描 → sensitive_info finding + 命中时自动数据升级（其他敏感语义需人工标级）
  → 落库：business_internal 及以上字段级加密；生产/PG 缺密钥或密钥错误 fail-closed
  → 事件/审计：自由文本改写为 {"_redacted", "sha256", "length"}，用户消息只留 input_sha256/input_length
  → 可选中断执行：完整 ProjectContext 写入独立 Fernet 加密的 PostgreSQL checkpoint
  → 进 prompt：聊天正文与 evidence/user_materials 均在模型调用前扫描；命中即升级 sensitive_personal 并强制掩码 → DeepSeek API
  → 报告导出：首屏双语 AI 标识（新）+ 分级标签展示
  → 生命周期：retention 定期清理 / admin 删除（checkpoint → 派生表 → 租户谓词）+ 审计痕迹
```

## 9. 兼容性与验证

- `data_classification` 字段经 `core/migrations/` 的 ProjectContext schema 迁移添加（默认 `business_internal`，存量演示会话由场景 ID 回填 `public_demo`）；数据库表结构无新表，PostgreSQL 侧无 alembic 变更。
- 加密开关关闭时全部现有测试不回退；开启时新增读写往返测试（两后端各一组）。
- v1.4.0 新增回归测试：`tests/test_field_security_extended.py`（加密 round-trip、错误密钥/错误租户 fail-closed）、`tests/test_data_protection_redaction.py`（事件/审计脱敏确定性）、`tests/test_retention_tenant_scope.py`（retention 覆盖派生表且不跨租户）。
- 验收口径（对应路线图阶段 1）：存储层指定敏感字段的加密代码已实现（是否启用取决于密钥）；高敏场景 PIA 已按当前实现边界复核；报告标识中文化且首屏可见。
