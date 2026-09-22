# 生产部署备份指引

## 备份范围

| 数据 | 工具 | 频率 | 保留 |
|------|------|------|------|
| PostgreSQL 业务数据 | pg_dump | 每日全量 | 30 天滚动 |
| SQLite lite 模式 | cp data/workflow.db | 每日全量 | 7 天滚动 |
| DATA_ENCRYPTION_KEY | secrets manager / 离线介质 | 变更时 | 永久（密钥丢失=数据不可读） |
| CHECKPOINT_ENCRYPTION_KEY | secrets manager / 离线介质 | 变更时 | 启用 PostgreSQL 中断模式期间及其 checkpoint 备份保留期内（丢失=checkpoint payload 不可读） |
| JWT_SECRET | secrets manager / 离线介质 | 变更时 | 永久 |
| Docker volumes | 宿主机/云盘快照，或临时容器将 volume 内容打包到受控备份目录 | 每周 | 4 周滚动 |

## 恢复演练清单

1. [ ] 从 pg_dump 恢复到新数据库，启动 API 验证 /health/ready 通过
2. [ ] 加载最近一个会话，导出报告，与生产对比内容哈希
3. [ ] 若生产已启用字段加密，模拟密钥丢失：用备份 DATA_ENCRYPTION_KEY 解密密文字段，验证可读
4. [ ] 若启用 PostgreSQL LangGraph checkpoint，用备份 CHECKPOINT_ENCRYPTION_KEY 恢复一次暂停会话，确认 checkpoint 可解密且 `/health/ready` 通过
5. [ ] 模拟审计归档：DELETE /sessions/{id} 后查 audit_events_archive 含 session_purged 事件，并确认对应 tenant-scoped checkpoint 已清理

## 密钥备份责任

生产环境仅在显式配置 `DATA_ENCRYPTION_KEY` 后启用业务字段加密；可通过 `/health.data_encryption` 核验。启用 PostgreSQL `langgraph_interrupt` 时还必须配置独立的 `CHECKPOINT_ENCRYPTION_KEY`，并通过 `/health/ready` 与 `/health.interrupt_adapter` 核验持久化、加密状态。两把 key 不得复用，应分别备份、授权和轮换；任一密钥丢失都会使其对应密文不可读。
