# 生产部署备份指引

## 备份范围

| 数据 | 工具 | 频率 | 保留 |
|------|------|------|------|
| PostgreSQL 业务数据 | pg_dump | 每日全量 | 30 天滚动 |
| SQLite lite 模式 | cp data/workflow.db | 每日全量 | 7 天滚动 |
| DATA_ENCRYPTION_KEY | secrets manager / 离线介质 | 变更时 | 永久（密钥丢失=数据不可读） |
| JWT_SECRET | secrets manager / 离线介质 | 变更时 | 永久 |
| Docker volume 快照 | docker volume snapshot | 每周 | 4 周滚动 |

## 恢复演练清单

1. [ ] 从 pg_dump 恢复到新数据库，启动 API 验证 /health/ready 通过
2. [ ] 加载最近一个会话，导出报告，与生产对比内容哈希
3. [ ] 模拟密钥丢失：用备份 DATA_ENCRYPTION_KEY 解密密文字段，验证可读
4. [ ] 模拟审计归档：DELETE /sessions/{id} 后查 audit_events_archive 含 session_purged 事件

## 密钥备份责任

DATA_ENCRYPTION_KEY 丢失 = 所有加密字段不可读。**必须**离线备份（打印 + USB + 密码管理器三处冗余），与 JWT_SECRET 同级管理。
