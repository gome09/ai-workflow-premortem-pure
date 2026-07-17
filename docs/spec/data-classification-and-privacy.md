# 数据分类分级与隐私保护设计规格

> Status: Implemented（自 v1.0.3 起落地 T1.1–T1.9：数据分级 / 字段加密 / PII 掩码 / AI 生成标识 / PIA，沿用至今。落地任务见 [../plan/phase-1-security-compliance.md](../plan/phase-1-security-compliance.md)）
> Last updated: 2026-07-18
> 合规依据：PIPL 第 28/51/55/56/57 条、DSL 第 21 条、《人工智能生成合成内容标识办法》（2025-09-01 施行）、EU AI Act Art.50 透明度义务（2026-08-02 生效）、GB/T 22239-2019 日志留存要求

---

## 1. 现状事实（已核实，2026-07-13）

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
| `sensitive_personal` | 材料含敏感个人信息（PIPL 28 条：医疗健康、未成年人、生物识别等） | PII 扫描命中敏感类别时自动升级；或人工标记 |

### 3.2 判定与覆写

- 自动判定发生在会话创建与 `add_materials` 时（`core/session_service.py` 的 `scan_user_materials` 已有挂载点）。
- 人工覆写走新增端点 `PATCH /sessions/{id}/data-classification`（editor/admin），**只允许升级或同级修改，降级必须 admin** 且写 `AuditEvent`。
- 分级**向上联动 AI 风险分级**：`sensitive_personal` 会话在 `core/gates/risk_profile.py:classify_project_risk` 中作为升档信号（至少 HIGH）——这同时修复第 1 节事实 6 的缺口。数据分级与 AI 风险分级仍是两个独立维度（一个关于"处理的数据"，一个关于"被评估的 AI 系统"），仅单向联动。

### 3.3 关键词修正（配套）

`risk_profile.py` 关键词表补充：`_HIGH_KEYWORDS` 增加"心理|精神|抑郁|自杀|self.?harm|mental health|心理健康"与"学生|student"（与既有"儿童|未成年人"同组）。修正后 `university_mental_health` 示例输入应实测落入 HIGH 及以上（作为回归测试固化）。

## 4. 子系统②：敏感数据保护

### 4.1 字段级静态加密

- **方案**：应用层对称加密（`cryptography.Fernet`），密钥来自环境变量 `DATA_ENCRYPTION_KEY`（走 `.env`/secrets，与 `JWT_SECRET` 同级管理）。
- **加密范围**：`data_classification ∈ {business_internal, sensitive_personal}` 会话的用户材料字段——`user_materials`、`evidence_sources.summary/claims`（source_type=user_material 的记录）。`public_demo` 保持明文（保住"零配置离线演示"这一核心亮点）。
- **实现位置**：`storage/backends/` 的 `_build_context_json_for_storage`（写侧）与 `load()`（读侧）各加一层 encode/decode 钩子，密文带 `enc:v1:` 前缀以便识别与将来轮换；PostgreSQL 与 SQLite 两个后端行为一致。
- **降级行为**：未配置密钥时——demo/lite 模式静默明文（现状不回退）；生产模式（postgres backend）启动时打 WARNING 并在 `/health` 暴露 `data_encryption: disabled`。
- **不做**：全库透明加密（TDE 属部署层，不属应用层）、可搜索加密（当前无按材料内容检索的需求）。

### 4.2 PII 检测与出境前掩码

动机：用户材料会随 prompt 发送到外部 LLM API（DeepSeek），这是一次"向第三方提供个人信息"的数据流转，PIPL 视角必须可控。

- `tools/safety_classifier.py` 新增 `PII_PATTERNS` 规则组：中国大陆身份证号（18 位含校验特征）、手机号（`1[3-9]\d{9}`）、邮箱、银行卡号（Luhn 可后置）。命中产出 `sensitive_info` finding（复用现有 risk_type），敏感类别（如身份证）severity=high。
- 新增配置 `PII_MASK_BEFORE_LLM`（默认 `false`，避免破坏现有演示行为）：开启后 `core/evidence_service.py:format_evidence_for_prompt` 在拼 prompt 前对命中 PII 做模式保留掩码（`110***********1234`）。
- 掩码只作用于**发往 LLM 的 prompt 路径**，落库仍存原文（由 4.1 加密保护）——保证人工审核者看到的是真实材料。

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

- **留存策略配置化**：`core/config.py` 新增 `audit_retention_days`（默认 **183**，对齐等保"日志留存不少于 6 个月"）与 `session_retention_days`（默认 0=永久）。留存策略首期只做**声明与检查**（`/health` 暴露配置值 + 文档承诺），自动清理任务后置——审计数据 append-only 优先级高于自动删除。
- **删除能力**：新增 `DELETE /sessions/{id}`（admin），级联删除各独立表记录，但**审计事件不删除**（改为写入一条 `session_purged` 审计事件保留处置痕迹）——PIPL 删除权与审计完整性的平衡点。
- **备份指引**：`docs/` 补充生产部署备份章节（`pg_dump` 定时 + volume 快照 + 恢复演练清单），属文档交付，不写代码。

## 7. 子系统⑤：PIA 支持（PIPL 55/56 条）

产品定位（路线图第 8.4 节的两层结构，均需要）：

1. **平台自身的 PIA**（工具提供方责任）：对"本平台处理用户上传材料"这一活动做一次评估，覆盖 PIPL 56 条三要素（目的合法性/对个人权益的影响与风险/保护措施与风险适配性），重点评估"材料流向外部 LLM API"数据流。产出 `docs/compliance/pia-platform.md`，留存 3 年，随重大架构变更复评。
2. **内置 PIA 模板供用户使用**（平台功能）：`docs/compliance/pia-template.md` 模板 + 对 `university_mental_health` 场景实际填写一份评估存档（`docs/compliance/pia-university-mental-health.md`），作为高敏场景的示范样本。首期是文档交付；"PIA 表单化进平台（表单/审批/到期提醒）"列为阶段 3 治理平台候选功能，不在阶段 1 承诺。

## 8. 数据流转全景（设计后目标态）

```
用户粘贴材料
  → PII 扫描（新）→ sensitive_info finding + 自动数据分级（新）
  → 落库：business_internal 及以上字段级加密（新）
  → 进 prompt：可选 PII 掩码（新）→ DeepSeek API（既有数据流，PIA 中披露）
  → 报告导出：首屏双语 AI 标识（新）+ 分级标签展示
  → 生命周期：留存策略声明 / admin 删除 + 审计痕迹（新）
```

## 9. 兼容性与验证

- `data_classification` 字段经 `core/migrations/` 的 ProjectContext schema 迁移添加（默认 `business_internal`，存量演示会话由场景 ID 回填 `public_demo`）；数据库表结构无新表，PostgreSQL 侧无 alembic 变更。
- 加密开关关闭时全部现有测试不回退；开启时新增读写往返测试（两后端各一组）。
- 验收口径（对应路线图阶段 1）：存储层敏感字段加密"已在代码里生效"（非计划中）；PIA 文档对高敏场景实际跑过一次；报告标识中文化且首屏可见。
