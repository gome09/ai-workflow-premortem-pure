# 阶段 1 实施计划：安全与合规硬缺口修复

> 上游路线图：[improvement-roadmap.md](improvement-roadmap.md) 第 6 节「阶段 1」。
> 配套设计规格：[../spec/data-classification-and-privacy.md](../spec/data-classification-and-privacy.md)（子系统①-⑤）、[../spec/supply-chain-security.md](../spec/supply-chain-security.md) 第 4-5 节（SAST）。
> 现状基线核实日期：2026-07-13。
> 状态：未启动。前置依赖：建议阶段 0 先行（新代码走加固后的 CI）；与阶段 2 可并行。

---

## 1. 目标

补齐企业 IT/安全部门验收内部工具时**一定会问到**的硬缺口：数据怎么分级、敏感数据怎么保护、AI 生成内容怎么标识、数据出了事怎么办、代码有没有安全扫描。

## 2. 现状基线

完整事实清单见 [../spec/data-classification-and-privacy.md](../spec/data-classification-and-privacy.md) 第 1 节，要点：

- 用户材料明文落库，无任何加密/脱敏实现；材料随 prompt 发送到外部 LLM API（DeepSeek）。
- 报告免责声明仅英文、位于文末（JSON 最后一个键 / Markdown 第 19 节）。
- 无数据分类分级、无留存策略、无会话删除接口、无备份配置。
- **重要修正**：路线图 3.5 节认为 `university_mental_health` 已"自动升级为高风险"，实测不成立（关键词表无"心理/学生"，该场景落 MEDIUM 档）。
- CI 无任何 SAST/依赖漏洞扫描。

## 3. 任务分解

### T1.1 数据分类分级

- **内容**：`ProjectContext.data_classification` 三级字段 + 自动判定 + 覆写端点 + 审计。设计见 spec 子系统①（3.1-3.2 节）。
- **涉及文件**：`core/models.py`、`core/migrations/`（新迁移：默认值回填）、`core/session_service.py`、`api/routers/session.py`、`frontend/`（展示标签）。
- **验收**：场景会话=public_demo、用户会话=business_internal、PII 命中敏感类自动升 sensitive_personal 各有测试；降级操作有 AuditEvent。
- 工作量：M

### T1.2 敏感场景风险升档修正

- **内容**：`core/gates/risk_profile.py` 关键词表补"心理/精神/抑郁/自杀/学生/mental health"等词；`sensitive_personal` 数据分级作为升档信号接入 `classify_project_risk`。设计见 spec 3.3 节。
- **验收**：`university_mental_health` 示例输入实测升为 HIGH 及以上，固化为回归测试；路线图 3.5 节的错误描述同步订正。
- 工作量：S
- **优先级说明**：这是本阶段最小、合规意义最直接的任务（PIPL 28 条双重敏感场景），建议最先做。

### T1.3 存储层字段级加密

- **内容**：Fernet 应用层加密，覆盖 business_internal 及以上会话的用户材料字段；`enc:v1:` 前缀；demo 模式静默明文、生产模式无密钥告警。设计见 spec 子系统② 4.1 节。
- **涉及文件**：`storage/backends/postgres.py`、`sqlite_store.py`、`core/config.py`、`pyproject.toml`（新增 `cryptography` 依赖）、`.env.example`。
- **验收**：开启密钥后两后端读写往返测试通过；数据库文件/表内直接查看为密文；关闭时现有全部测试不回退。
- 工作量：L

### T1.4 PII 检测与出境前掩码

- **内容**：`PII_PATTERNS`（身份证/手机号/邮箱）产出 `sensitive_info` finding；`PII_MASK_BEFORE_LLM` 开关控制 prompt 路径掩码。设计见 spec 4.2 节。
- **验收**：含 PII 的材料触发 finding；开关开启时发往 LLM 的 prompt 中 PII 已掩码（mock 模式可断言 prompt 内容）；落库原文不受影响。
- 工作量：M

### T1.5 报告 AI 生成内容标识补强

- **内容**：Markdown 首屏双语标识块 + HTML 注释隐式标识；JSON 头部 `ai_generated_notice` 结构化字段；尾部英文 disclaimer 保留兼容。设计见 spec 子系统③。
- **涉及文件**：`core/report_service.py` + 相关快照测试。
- **验收**：导出任一报告，首屏可见中文标识；`content_json["disclaimer"]` 仍存在（向后兼容）。
- 工作量：S

### T1.6 数据生命周期最小集

- **内容**：留存配置（`audit_retention_days` 默认 183 天对齐等保 6 个月）+ `DELETE /sessions/{id}`（admin，审计不删、写 `session_purged` 事件）+ 备份指引文档。设计见 spec 子系统④。
- **验收**：删除端点有权限测试与级联测试；`/health` 暴露留存配置；备份章节入 docs。
- 工作量：M

### T1.7 PIA 双层交付

- **内容**：平台自身 PIA（重点披露"材料→DeepSeek API"数据流）+ PIA 模板 + `university_mental_health` 场景实测评估。产出 `docs/compliance/` 三份文档，留存 3 年。设计见 spec 子系统⑤。
- **验收**：三份文档存在且非模板占位；平台 PIA 覆盖 PIPL 56 条三要素。
- 工作量：M（纯文档，但需要真实思考）

### T1.8 CI 接入 SAST 与依赖审计

- **内容**：ruff 规则集加 `S`（tests 豁免 S101）+ CI 追加 `pip-audit` 步骤（先告警不阻断）；仓库公开后追加 CodeQL workflow。设计见 [../spec/supply-chain-security.md](../spec/supply-chain-security.md) 第 4-5 节。
- **验收**：CI 真实跑出 SAST/audit 结果（哪怕暂不 block 合并）；存量 `S` 告警清零或逐条豁免注释。
- 工作量：M

### T1.9 数据泄露应急响应流程

- **内容**：一页纸 checklist（`docs/compliance/incident-response.md`）：发现→止损（吊销密钥/下线端点）→影响评估（哪些租户/会话）→通知义务判断（PIPL 57 条）→复盘归档。与 SECURITY.md（阶段 0 产物）互链。
- **验收**：文档存在，其中的操作项与本项目实际架构对应（能指到具体的配置/表/端点）。
- 工作量：S

## 4. 推进顺序与依赖

```
T1.2（最小最优先，独立）
T1.1 → T1.3 / T1.4（分级字段是加密与掩码的范围判定依据）
T1.5 / T1.9（独立，随时可做）
T1.7（依赖 T1.1-T1.4 的设计定稿，因为 PIA 要如实描述保护措施）
T1.8（独立，与 supply-chain spec 联动）
T1.6（独立）
```

## 5. 风险与注意事项

- T1.3 加密是本阶段唯一的高风险改动（触碰两个存储后端的读写主路径），必须先在 SQLite lite 模式全量回归，再动 PostgreSQL；密钥丢失=数据不可读，`.env.example` 与备份指引必须写清密钥备份责任。
- T1.4 掩码开关默认关闭是刻意的：先让检测跑起来积累误报数据，再决定是否默认开启。
- `docs/compliance/` 是新目录，需同步更新 [../README.md](../README.md) 索引（文档维护约定）。
- PIA 责任主体定位（工具方 vs 使用方）已按路线图 8.4 节"两者都要、分层交付"处理，若项目所有者对定位另有决策，T1.7 范围相应调整。

## 6. 阶段验收清单

- [x] `university_mental_health` 场景实测升为 HIGH 及以上（回归测试固化）
- [x] 数据分级字段生效且有覆写审计
- [x] 存储层敏感字段加密在代码里生效（可验证密文），非"计划做"
- [x] PII 检测 finding 可产出；掩码开关可用
- [x] 报告首屏中文 AI 标识可见
- [x] PIA 三份文档存档（含 `university_mental_health` 实测一份）
- [x] CI 中 SAST + pip-audit 真实运行有结果
- [x] 泄露应急响应 checklist 与会话删除能力就位
