# 平台自身个人信息保护影响评估（PIA）

> 评估对象：本平台（ai-workflow-premortem）处理用户上传材料这一个人信息处理活动。
> 评估依据：PIPL 第 55 条、第 56 条；DSL 第 21 条。
> 评估日期：2026-07-14。
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
| LLM 交互 | conversation_history, llm_traces | DeepSeek API 返回 | 不含用户 PII（除非 prompt 携带） |

### 1.3 数据流

```
用户 → 平台 API → [PII 检测] → [字段加密] → PostgreSQL/SQLite 存储
                 → [PII 掩码（可选）] → DeepSeek API（跨境） → 平台 → 报告
```

### 1.4 跨境传输披露

- **传输对象**：DeepSeek API（深度求索）
- **传输内容**：用户材料 + 证据摘要 + 阶段 prompt
- **传输路径**：平台服务器 → DeepSeek API 端点
- **保护措施**：PII_MASK_BEFORE_LLM=true 时在传输前掩码 PII（默认 false，需手动开启）
- **法律依据**：PIPL 第 38 条（需单独同意 + 评估）
- **第三方合规**：DeepSeek 隐私政策参见其官方声明

## 2. PIPL 第 56 条三要素评估

### 2.1 目的合法性

- 处理目的明确、合理：AI 项目风险分析
- 用户明示同意：通过 API 调用隐含同意（创建会话即同意处理）
- 最小必要原则：仅处理用户主动提供的材料，不主动采集 PII

### 2.2 对个人权益的影响与风险

| 风险项 | 影响 | 严重度 | 现有措施 |
|--------|------|--------|----------|
| 用户材料含 PII 被存储 | 隐私泄露 | 高 | T1.3 字段加密（enc:v1:） |
| PII 通过 prompt 传到 DeepSeek | 跨境传输 | 高 | T1.4 PII 检测 + 可选掩码 |
| 审计日志含操作者信息 | 关联分析 | 中 | 审计事件仅记录角色（system/user/ai），不记录 PII |
| 数据库泄露 | 批量泄露 | 高 | Fernet 加密 + JWT 认证 + 租户隔离 |
| 会话长期留存 | 留存过度 | 中 | T1.6 DELETE 端点 + 可配置留存期 |

### 2.3 保护措施与风险适配性

| 措施 | 对应风险 | 依据 | 状态 |
|------|----------|------|------|
| 数据分类分级（T1.1） | 适配性控制 | DSL 21 条 / PIPL 51 条 | ✅ 已实现 |
| 字段级加密（T1.3） | 存储泄露 | PIPL 51 条 | ✅ 已实现 |
| PII 检测与掩码（T1.4） | 跨境传输 | PIPL 38/39 条 | ✅ 已实现（默认关闭掩码） |
| 会话删除与审计归档（T1.6） | 留存过度 | PIPL 47 条 | ✅ 已实现 |
| 应急响应（T1.9） | 事件响应 | PIPL 57 条 | ✅ 已实现 |

## 3. 留存期限

| 数据 | 留存期 | 删除方式 |
|------|--------|----------|
| 审计事件 | 183 天（AUDIT_RETENTION_DAYS） | DELETE /sessions/{id} 触发归档+删除 |
| 会话数据 | 默认永久（SESSION_RETENTION_DAYS=0） | DELETE /sessions/{id} 级联删除 |
| 归档审计事件 | 永久（audit_events_archive 表） | 不自动删除（合规留痕） |
| LLM traces | 跟随会话 | 级联删除 |

## 4. 复评计划

- 触发条件：更换 LLM provider、新增数据字段、新增跨境传输路径、重大安全事件
- 复评负责人：平台维护者
- 复评输出：更新本文档 + 记录到 `.upgrade/decisions/`

## 5. 互链

- [incident-response.md](incident-response.md) — 数据泄露应急响应
- [backup.md](backup.md) — 备份指引
- [pia-template.md](pia-template.md) — 用户使用 PIA 模板
- [pia-university-mental-health.md](pia-university-mental-health.md) — 高敏场景实测评估
