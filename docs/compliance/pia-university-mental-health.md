# university_mental_health 场景 PIA 实测评估

> 评估对象：使用本平台评估"高校学生心理健康风险预测系统"这一 AI 项目。
> 评估依据：PIPL 第 28 条（敏感个人信息）、第 55 条、第 56 条。
> 评估日期：2026-07-14。
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

- `data_classification`：自动设为 `sensitive_personal`（T1.4 PII 命中联动升级）
- 风险档位：T1.2 修复后升为 `HIGH`（关键词"心理健康"+"学生"命中 _HIGH_KEYWORDS）

## 3. 平台保护措施实测

| 措施 | 预期行为 | 实测结果 |
|------|----------|----------|
| T1.2 风险升档 | 场景关键词命中 → HIGH | ✅ classify_project_risk 返回 HIGH（"mental health domain" + "student/minor-adjacent population"） |
| T1.1 数据分级 | sensitive_personal | ✅ PII 命中后 data_classification 升级为 sensitive_personal |
| T1.3 字段加密 | user_materials 加密 | ✅ enc:v1: 前缀（配置 DATA_ENCRYPTION_KEY 后） |
| T1.4 PII 检测 | 学号/手机号检出 | ✅ scan_pii 命中 cn_mobile / email（取决于输入内容） |
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

本场景用户材料可能含学生 PII（学号、行为数据描述）。在 `PII_MASK_BEFORE_LLM=true` 配置下，PII 会在发送 DeepSeek API 前掩码。但默认配置为 false，**建议本场景手动开启 PII_MASK_BEFORE_LLM=true**。

### 4.3 留存与删除

- 建议为本场景设置 `SESSION_RETENTION_DAYS=30`（短期留存）
- 评估完成后立即通过 `DELETE /sessions/{id}` 删除会话
- 审计事件归档到 `audit_events_archive` 保留 183 天

## 5. 结论

| 评估项 | 结论 |
|--------|------|
| 是否可在本平台评估 | ✅ 可以，但需启用 PII_MASK_BEFORE_LLM |
| 需补充措施 | 手动开启 PII_MASK_BEFORE_LLM；评估后立即删除会话 |
| 风险档位 | HIGH（门禁要求 eval + redteam + trace_backfill） |
| 数据分级 | sensitive_personal（PIPL 28 条双重敏感） |
| 复评触发 | 如场景输入含真实学生数据，需重新评估 |

## 6. 互链

- [pia-platform.md](pia-platform.md) — 平台自身 PIA
- [incident-response.md](incident-response.md) — 应急响应
- [../plan/phase-1-design.md](../plan/phase-1-design.md) — Phase 1 设计方案
