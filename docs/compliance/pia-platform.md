# 平台自身个人信息保护影响评估（PIA）

> 评估对象：本平台（ai-workflow-premortem）处理用户上传材料这一个人信息处理活动。
> 评估依据：PIPL 第 55 条、第 56 条；DSL 第 21 条。
> 评估日期：2026-07-14；代码事实复核：2026-07-27。
> 复评触发：重大架构变更（如更换 LLM provider、新增数据字段、新增跨境传输路径）。
> 留存期限：3 年。

## 1. 处理活动描述

### 1.1 处理目的

本平台为 AI 工作流预验尸（pre-mortem）分析工具，接收用户上传的项目资料（文本形式），通过四阶段 LLM 工作流生成风险分析报告。处理目的：
- 识别 AI 项目的潜在失败模式
- 设计工作流与人工监督策略
- 压力测试与红队测试
- 生成审计就绪报告

### 1.2 处理的数据类型

| 数据类别 | 字段 | 来源 | 是否含 PII |
|----------|------|------|------------|
| 项目基本信息 | research_target, domain, goal | 用户输入 | 可能 |
| 用户补充材料 | user_materials (list[str]) | 用户粘贴/上传 | 可能（文本内容任意） |
| 证据来源 | evidence_sources (summary, claims) | Tavily 搜索 / 用户材料资产化 | 可能 |
| 会话审计 | audit_events | 系统自动记录 | actor 字段含角色信息 |
| LLM 交互 | conversation_history, llm_traces | 用户消息 + DeepSeek API 返回 | 可能包含用户消息原文与 prompt 内容 |

### 1.3 数据流

```
用户 → 平台 API → [四类正则 PII 检测] → [指定材料字段加密（需有效密钥）] → PostgreSQL/SQLite
                 → [evidence/user_materials 路径可选掩码；直接消息/历史不覆盖] → DeepSeek API → 报告
```

### 1.4 跨境传输披露

- **传输对象**：DeepSeek API（深度求索）
- **传输内容**：用户材料 + 证据摘要 + 阶段 prompt
- **传输路径**：平台服务器 → DeepSeek API 端点
- **保护措施**：`PII_MASK_BEFORE_LLM=true` 时，仅 evidence summary / user_materials 格式化路径会掩码四类正则 PII；直接用户消息与历史消息当前不覆盖，且该开关默认关闭
- **法律依据**：PIPL 第 38 条（需单独同意 + 评估）
- **第三方合规**：DeepSeek 隐私政策参见其官方声明

## 2. PIPL 第 56 条三要素评估

### 2.1 目的合法性

- 处理目的明确、合理：AI 项目风险分析
- 当前代码没有独立的告知、同意或单独同意记录机制；“调用 API”不能等同于已经取得明示同意。部署方必须在收集材料前履行告知并取得适用同意，涉及跨境提供时另行满足 PIPL 第 38 条要求
- 最小必要原则：仅处理用户主动提供的材料，不主动采集 PII

### 2.2 对个人权益的影响与风险

| 风险项 | 影响 | 严重度 | 现有措施 |
|--------|------|--------|----------|
| 用户材料含 PII 被存储 | 隐私泄露 | 高 | T1.3 支持字段加密（enc:v1:）；必须配置 `DATA_ENCRYPTION_KEY`，否则仍为明文 |
| PII 通过 prompt 传到 DeepSeek | 跨境传输 | 高 | evidence/user_materials 路径支持可选掩码；直接消息/历史仍是缺口，默认关闭时不掩码 |
| 审计日志含操作者信息 | 关联分析 | 中 | 审计事件仅记录角色（system/user/ai），不记录 PII |
| 数据库泄露 | 批量泄露 | 高 | JWT 认证 + 租户隔离；Fernet 仅在 `DATA_ENCRYPTION_KEY` 有效时启用 |
| 会话长期留存 | 留存过度 | 中 | T1.6 DELETE 端点；留存天数目前只展示配置，尚无自动清理任务 |

### 2.3 保护措施与风险适配性

| 措施 | 对应风险 | 依据 | 状态 |
|------|----------|------|------|
| 数据分类分级（T1.1） | 适配性控制 | DSL 21 条 / PIPL 51 条 | ✅ 已实现 |
| 字段级加密（T1.3） | 存储泄露 | PIPL 51 条 | ⚠️ 代码已实现，部署时需显式配置密钥并验证 `/health.data_encryption` |
| PII 检测与掩码（T1.4） | 跨境传输 | PIPL 38/39 条 | ⚠️ 部分实现：四类正则 + 材料注入路径；默认关闭，直接消息/历史不覆盖 |
| 会话删除与审计归档（T1.6） | 留存过度 | PIPL 47 条 | ✅ 已实现 |
| 应急响应（T1.9） | 事件响应 | PIPL 57 条 | ✅ 已实现 |

## 3. 留存期限

| 数据 | 留存期 | 删除方式 |
|------|--------|----------|
| 审计事件 | 目标值 183 天（`AUDIT_RETENTION_DAYS`） | 当前无自动期限清理；删除会话时转入归档表 |
| 会话数据 | 配置值默认 0=永久（`SESSION_RETENTION_DAYS`） | 当前无自动期限清理；管理员调用 `DELETE /sessions/{id}` 级联删除 |
| 归档审计事件 | 未配置自动删除 | 当前不自动删除（合规留痕） |
| LLM traces | 跟随会话 | 级联删除 |

> **当前缺口**：`AUDIT_RETENTION_DAYS` 与 `SESSION_RETENTION_DAYS` 只由 `/health` 展示，尚无调度器消费。生产环境必须通过外部作业或人工流程执行留存策略，直至项目实现自动清理任务。

## 4. 复评计划

- 触发条件：更换 LLM provider、新增数据字段、新增跨境传输路径、重大安全事件
- 复评负责人：平台维护者
- 复评输出：更新本文档 + 记录到 `.upgrade/decisions/`

## 5. 互链

- [incident-response.md](incident-response.md) — 数据泄露应急响应
- [backup.md](backup.md) — 备份指引
- [pia-template.md](pia-template.md) — 用户使用 PIA 模板
- [pia-university-mental-health.md](pia-university-mental-health.md) — 高敏场景实测评估
