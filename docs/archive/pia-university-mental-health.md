# university_mental_health 场景 PIA 评估

> 评估对象：使用本平台评估"高校学生心理健康风险预测系统"这一 AI 项目。
> 评估依据：PIPL 第 28 条（敏感个人信息）、第 55 条、第 56 条。
> 评估日期：2026-07-14；代码事实复核：2026-07-27。
> 场景输入：[examples/university_ai_mental_health_input.md](../../examples/university_ai_mental_health_input.md)

## 1. 场景描述

研究对象：基于多源行为数据的学生心理健康风险预测系统。
领域：高校学生事务管理。
目标：早期识别存在心理健康风险的学生，向心理咨询中心发出预警。

## 2. 敏感度判定

### 2.1 PIPL 第 28 条双重敏感场景

本场景涉及两个敏感维度：
1. **未成年人/学生群体**：高校学生可能含未满 18 岨的未成年人
2. **心理健康**：精神健康数据属于敏感个人信息

结论：本场景**必须**作为敏感个人信息处理活动进行 PIA。

### 2.2 平台数据分级

- `data_classification`：内置示例创建时为 `public_demo`。示例文本不含当前正则可识别的身份证号、手机号、邮箱或银行卡号，不会自动升为 `sensitive_personal`；处理真实学生/健康数据前必须人工升级
- 风险档位：T1.2 修复后升为 `HIGH`（关键词"心理健康"+"学生"命中 _HIGH_KEYWORDS）

## 3. 平台保护措施实测

| 措施 | 预期行为 | 实测结果 |
|------|----------|----------|
| T1.2 风险升档 | 场景关键词命中 → HIGH | ✅ classify_project_risk 返回 HIGH（"mental health domain" + "student/minor-adjacent population"） |
| T1.1 数据分级 | 真实敏感场景应为 sensitive_personal | ⚠️ 示例默认为 public_demo；真实数据需人工升级，或由四类正则命中触发自动升级 |
| T1.3 字段加密 | user_materials 加密 | ✅ enc:v1: 前缀（配置 DATA_ENCRYPTION_KEY 后） |
| T1.4 PII 检测 | 身份证/手机号/邮箱/银行卡号检出 | ⚠️ 当前示例未包含这些模式；学号、姓名和健康语义不在当前检测范围 |
| T1.5 AI 标识 | 报告首屏中文标识 | ✅ "本报告由 AI 辅助生成" |
| T1.6 会话删除 | DELETE 端点可用 | ✅ admin 可删除，审计归档保留 |

## 4. 风险措施适配性评估

### 4.1 HIGH 风险档位要求

HIGH 档位（Stage3GateProfile）要求：
- require_eval_coverage: True
- require_failed_eval_resolution: True
- require_redteam_coverage: True
- require_eval_regression: True
- require_trace_backfill: True

本场景作为 HIGH 风险项目，必须完成上述全部门禁才能推进到 Stage 4。

### 4.2 跨境传输

本场景真实材料可能含学生 PII。`PII_MASK_BEFORE_LLM=true` 只掩码 evidence/user_materials 注入路径中的四类正则命中项；学号、姓名、健康语义、直接聊天消息和历史消息当前不覆盖，且默认配置为 false。处理真实数据时除开启该开关外，还必须做入口级脱敏并避免在聊天消息中提交原文。

### 4.3 留存与删除

- 建议将 30 天作为外部运维留存策略；仅设置 `SESSION_RETENTION_DAYS=30` **不会自动删除数据**，当前代码没有消费该配置的清理任务
- 评估完成后立即通过 `DELETE /sessions/{id}` 删除会话
- 审计事件归档到 `audit_events_archive`；183 天是配置目标值，当前需外部流程执行到期清理

## 5. 结论

| 评估项 | 结论 |
|--------|------|
| 是否可在本平台评估 | ⚠️ 脱敏示例可以；真实学生数据须先补齐部署侧告知同意、入口脱敏和人工数据分级 |
| 需补充措施 | 人工设为 sensitive_personal；启用材料路径掩码；直接消息禁入 PII；评估后立即删除会话 |
| 风险档位 | HIGH（门禁要求 eval + redteam + trace_backfill） |
| 数据分级 | 业务上应为 sensitive_personal；当前示例不会自动得到该值 |
| 复评触发 | 如场景输入含真实学生数据，需重新评估 |

## 6. 互链

- [pia-platform.md](pia-platform.md) — 平台自身 PIA
- [incident-response.md](incident-response.md) — 应急响应
- [../plan/phase-1-design.md](../plan/phase-1-design.md) — Phase 1 设计方案
