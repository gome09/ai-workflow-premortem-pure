# 数据泄露应急响应 Checklist

> 适用范围：本平台（ai-workflow-premortem）发生或疑似发生数据泄露事件。
> 互链：[SECURITY.md](../../SECURITY.md)（漏洞报告渠道）。
> 依据：PIPL 第 57 条（事件通知义务）、《网络安全事件应急预案》。

## 1. 发现与确认（0-1h）

- [ ] 记录发现时间、发现人、初步现象
- [ ] 判断泄露类型：
  - [ ] DATA_ENCRYPTION_KEY 泄露 → 加密字段可被解密
  - [ ] JWT_SECRET 泄露 → 任意用户可伪造
  - [ ] 数据库未授权访问 → 业务数据泄露
  - [ ] LLM API Key 泄露 → 第三方 API 滥用
  - [ ] PII 通过 prompt 泄露到 LLM provider → 跨境传输事件
- [ ] 确认泄露范围：哪些 tenant_id / session_id / 时间段

## 2. 止损（1-4h）

- [ ] **吊销密钥**：
  - DATA_ENCRYPTION_KEY 泄露：生成新 key，但**旧密文不可读**（需先用旧 key 解密再用新 key 加密，若无旧 key 则数据不可恢复）
  - JWT_SECRET 泄露：更换 JWT_SECRET，所有现有 token 失效，强制重新登录
- [ ] **下线端点**：
  - 数据库泄露：暂停 API 服务（`docker compose down`），断开数据库网络
  - LLM API Key 泄露：在 DeepSeek/Tavily 控制台吊销 key
- [ ] **保留证据**：日志、数据库快照、Loki/Grafana 截图，勿清理

## 3. 影响评估（4-24h）

- [ ] 查 `audit_events_archive` 表确认受影响会话清单
- [ ] 查 `audit_events` 表确认受影响用户操作
- [ ] 评估泄露数据敏感度：
  - `data_classification = sensitive_personal` 的会话：PIPL 28 条双重敏感，必须通知
  - `data_classification = business_internal`：评估是否含 PII（查 `safety_findings` 表 `risk_type=sensitive_info`）
  - `data_classification = public_demo`：演示数据，无通知义务

## 4. 通知义务判断（PIPL 57 条）

- [ ] 是否"发生或可能发生个人信息泄露、篡改、丢失"？
  - 否 → 内部记录归档，无需通知
  - 是 → 继续
- [ ] 通知监管部门：设区的市级以上网信部门
- [ ] 通知受影响个人：通知方式（邮件/站内信/公告）、内容（泄露类型、原因、可能危害、已采取措施、用户可采取措施）

## 5. 复盘与归档（1 周内）

- [ ] 撰写事件复盘报告（时间线、根因、影响、改进措施）
- [ ] 归档到 `.upgrade/decisions/incident-<date>.md`
- [ ] 更新本 checklist（如有流程改进）
- [ ] 更新 `pia-platform.md`（如保护措施需调整）
- [ ] 触发密钥轮换（如未在止损阶段完成）

## 6. 本项目特有架构定位

| 概念 | 本项目对应 |
|------|------------|
| "敏感数据存储位置" | PostgreSQL `sessions.context_json` 字段（加密后）/ SQLite `sessions.context_json` |
| "审计日志位置" | `audit_events` 表 + `audit_events_archive` 表（删除会话后归档） |
| "密钥存储位置" | 环境变量 `DATA_ENCRYPTION_KEY` / `JWT_SECRET`，生产部署走 Docker secrets |
| "外部数据流" | 用户材料 → DeepSeek API（`core/evidence_service.py:format_evidence_for_prompt`） |
| "PII 掩码开关" | 环境变量 `PII_MASK_BEFORE_LLM` |
| "会话删除端点" | `DELETE /sessions/{id}`（admin only，归档审计后级联删除） |
| "/health 暴露项" | `data_encryption` / `audit_retention_days` / `session_retention_days` |
