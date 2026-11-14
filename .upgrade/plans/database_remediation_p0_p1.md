# 数据库修复实施方案（P0 / P1）

适用基线：`290846eaee368d2118483c8f8a9e8708ad136337`。本文中的路径均相对于项目根目录，行号对应此基线；实施前如代码已变化，以当前代码重新定位并核对语义。

本文的 **P0、P1 表示实施批次**，不是重新定义审查严重度，也不表示审查发现了 P0 事故：先实施的 P0 包括原审查 P1 的 T01、T02、T04、T05、T09；随后实施的 P1 包括原审查 P2 的 T03、T06、T08。若实际评估目标已确认存在重大不可重复副作用或高费用，可将 T03 提前安排；这不改变跨系统至少一次的限制。T07 只列为附录中的待核验事项，不计入确认缺陷。

本文是待实施方案，不表示代码、数据迁移或历史清理已经完成。动态证据、未执行的验证及上线依赖见附录。

## P0：优先修复安全与删除完整性

### T01｜删除后旧上下文重新创建会话

**原审查级别：P1。**

**根因和触发。** `storage/backends/postgres.py:411-448` 和 `storage/backends/sqlite_store.py:1277-1315` 的 `save` 在查无父行时插入，只有行存在时才检查版本。请求读取上下文后，管理员或留存任务删除会话并提交，旧请求随后保存，就会重新创建已删除会话及其投影。`core/models.py:886-887` 的默认版本和首次保存版本均为 0；真实 SQLite 存储验证中，已保存的版本 0、1 均可复现，不能用版本 0 判定新对象。

**修改方案。**

1. 在两个后端和存储接口增加显式 `create(ctx)`，由 `core/services/session_workflow.py:58-73` 及其他确实创建会话的入口调用。只执行 INSERT；ID 已存在时报冲突；主行与投影在同一事务提交。新会话 ID 继续由服务端生成 UUID，不允许客户端指定并重用旧 ID。
2. `save(ctx)` 只更新已存在的租户所属父行：行缺失时抛专用的会话不存在或已删除错误，不再 INSERT；行存在时保留版本比较和投影同步，提交成功后才更新 `_storage_version`。跨租户访问保持 fail-closed。
3. 将新错误接入现有 API 冲突处理及当前租户缓存清理，旧写返回明确的 409；后台任务识别错误后停止，不再写缓存或尝试重建。保留 `model_copy`、缓存序列化、`graph/langgraph_interrupt_runner.py:34-65` 重建和 `core/execution_service.py:50-73` 后台保存中的原版本。新建或更新由调用方法表达，不以易丢失的私有标志判断。
4. 搜索并调整所有真正的新建调用、测试替身与脚本中依赖 `save(new_ctx)` 自动插入的用法；不得把所有缺行都默认为可创建。

**迁移、兼容与回退。** 无需 schema 迁移。部署时排空旧 worker 和在途写入，避免旧版本继续执行缺行 INSERT。回滚到旧代码会重新开放该缺陷；先停写并明确接受风险，不能新旧版本混跑。

**收益与代价。** 删除后的旧上下文不能通过正常保存复活；既有内部调用和测试需要适配显式创建。

**验收。** PostgreSQL、SQLite 均覆盖已持久化 version 0 和 1，读取后删除再保存，主行和投影均不得重新出现；覆盖缓存往返、浅/深复制、LangGraph 重建和后台 job。正常创建、重复 ID 冲突、版本冲突、租户隔离及错误返回保持预期。

### T02｜删除摘要将敏感内容写入归档

**原审查级别：P1。**

**根因和触发。** `core/services/session_workflow.py:184-215` 用解密后的 `research_target` 和自由输入的 `session_name` 构造删除摘要；`storage/backends/postgres.py:1698-1710`、`storage/backends/sqlite_store.py:1581-1593` 将该摘要直接写入 `session_purged.after_snapshot`。管理员删除非 `public_demo` 会话时，受保护的研究目标和名称可能随独立归档继续保存。真实 SQLite 路径曾观察到归档中的明文标记；这不代表已经发生外部泄露。

**修改方案。** 在归档写入边界构造专用白名单摘要，仅保留必要的会话/租户标识、状态、分类、时间和删除者等，不保留 `research_target`、`goal`、`session_name` 原文。两个后端的 `purge_session` 与仍暴露的 `archive_audit_events` 必须共用该边界，不信任调用方传入的任意 summary。若现有删除响应须兼容，可保留响应结构，但不能把响应摘要直接用于归档。与 T09 共用递归脱敏和历史修复措施。

**迁移、兼容与回退。** 先部署并排空旧写入者，再备份、盘点并按 T09 的受控脚本清理活动审计、归档、事件及缓存中的历史副本，包括没有父会话的 `session_purged` 孤儿归档；无法可靠证明事件发生时为 `public_demo` 的记录保守脱敏。保留原事件 ID、时间、actor 和原 hash，并记录修复版本、批次与时间；异常 JSON 隔离并人工处理。备份与已导出副本按既有访问和留存策略单独处置。删除响应兼容性需按实际客户端确认；历史脱敏不可逆，恢复旧备份后须重新执行受控修复，回退旧写入代码会重新产生风险。

**收益与代价。** 新的删除归档不再复制不必要的原文；历史审计可读内容可能减少，保留的摘要或 hash 不能视为加密。

**验收。** 在两个后端分别手动删除带短文本、超 200 字符文本和嵌套标记的非 `public_demo` 会话，检查删除归档及缓存原始载荷均无目标、名称等标记原文；检查孤儿归档、旧截断值、非法 JSON 隔离、原 ID/hash 保留及脚本重跑幂等。`public_demo` 新事件行为按既有契约验证。

### T04｜旧管理员令牌继续使用原角色

**原审查级别：P1。**

**根因和触发。** `auth/jwt.py:50-59,68-80` 从 access JWT 取角色，`auth/permissions.py:17-33` 直接据此授权；`auth/router.py:101-108` 允许修改本人，`auth/service.py:220-234` 按租户更新角色。持有有效 admin token 的成员被降为 viewer 后，旧 token 仍可能调用管理员操作，甚至自行恢复 admin。隔离 FastAPI/真实 SQLite 试验观察到这一行为，但 JWT 使用 HS256 兼容替身，尚非生产 python-jose 与完整应用验证。

**修改方案。** `get_current_tenant` 先验证签名、类型、到期时间和非空租户，再调用现有 `get_user_by_id` 查询当前成员，核对 token 的 user_id、tenant_id 与 DB 一致，且角色属于 `viewer/editor/admin`；以 DB 当前角色构造 `TenantContext`。成员不存在、租户不匹配或非法角色返回 401/403；DB 不可用时返回 503 或其他 fail-closed 错误，不回退 token role。同一请求复用 FastAPI 依赖缓存。当前依赖是 `async def`，同步 DB 查询须经 `run_in_threadpool`/`asyncio.to_thread`，或将依赖改为同步 `def` 交 FastAPI 线程池，避免阻塞事件循环。`verify_token` 保持纯解析供 refresh 与 409 处理使用；refresh 继续重读当前角色，机器 release gate 继续使用自己的 service token。

**迁移、兼容与回退。** 无 schema 迁移；排空旧鉴权进程后才可认为新请求全部使用当前角色。DB 需承受每个人类请求一次轻量查询，容量与错误行为须在发布前验证。回滚旧鉴权逻辑会重新允许旧角色持续生效；不应将混跑期间视作已完成撤权。

**收益与代价。** 请求时降权、删除成员和租户不匹配可立即生效；增加 DB 读取和对 DB 可用性的依赖。已经通过鉴权的在途操作不在此保证范围内；如要求在途操作也立即撤权，需另行确定同事务授权语义。

**验收。** 使用真实 python-jose、真实 DB 和完整应用中间件，将 admin 降为 viewer 后，旧 token 读取按 viewer、PATCH 本人及邀请、删除、创建 service token 均被拒；refresh 获得 viewer。覆盖用户删除、租户不匹配、非法角色、DB 故障、机器 service token 和事件循环非阻塞行为。

### T05｜留存候选更新后仍被删除

**原审查级别：P1。**

**根因和触发。** 仅在 `SESSION_RETENTION_DAYS>0` 且 `RETENTION_DRY_RUN=false` 启用实际留存删除时，`core/retention_service.py:132-147` 先列出过期候选，之后的删除未复核活跃时间；最终 DELETE 位于 `storage/backends/postgres.py:1726-1735`、`storage/backends/sqlite_store.py:1610-1621`。候选选出后用户成功更新，清理器仍可删除刚更新的会话。真实 SQLite 存储组合已复现。

**修改方案。** 扩展 `purge_session` 接受可选 `retention_cutoff`，结果明确区分成功删除及归档条数、已更新跳过、已不存在；管理员调用不传 cutoff。PG 在单事务内先以 session_id 和 tenant_id 查询 `sessions ... FOR UPDATE`，系统历史空租户仅通过明确的 system access 且 `tenant_id IS NULL` 处理，不允许空租户变成跨租户无条件删除。锁内按候选筛选相同的 UTC、严格 `< cutoff` 语义复查最新 `updated_at`，不合条件立即结束，不归档也不删除；合格后再按 T06 顺序读取审计、归档、插入脱敏删除事件、级联删除并检查 rowcount，任一步失败全部回滚。

SQLite 在**读取和复检之前**执行 `BEGIN IMMEDIATE`，并在同一连接中完成复检、归档、删除、提交；实例内 `threading.Lock` 不足以替代跨进程写事务。busy 等锁错误返回失败或可重试，不得计作删除成功。`_purge_one_session` 将原 cutoff 传入，只有 DB 真正删除后才按现有留存契约清 checkpoint、缓存并递增 `sessions_purged`；跳过单独计数或反馈，不清理已更新会话的 checkpoint。管理员删除现有 checkpoint 顺序与留存路径分开处理。

**迁移、兼容与回退。** 无新增 schema；T01 先上线，避免删除先锁时旧保存随后复活父行；T05 与 T06 尽量共同修改同一个 purge 事务。保留可选参数以兼容管理员删除调用，并调整调用方对结果的处理。回退会恢复候选过时误删窗口；有实际留存任务时先停用或切回 dry-run，再决定回退。

**收益与代价。** 活跃会话不会因过期候选快照被误删；SQLite 写锁覆盖归档阶段，需结合批量大小和 busy 超时控制争用。

**验收。** 两后端强制候选选出后更新、严格截止边界及两个清理器竞争：更新或边界不合条件时不删除、不归档、不清 checkpoint/缓存，真实删除计数准确；注入归档或 DELETE 异常验证全事务回滚，SQLite 锁争用不报成功。PG 及 SQLite 均用独立连接/进程验证锁语义。

### T09｜评估自由文本进入审计和事件

**原审查级别：P1。**

**根因和触发。** `core/eval_runner.py:179-206,369-376`、`core/eval_service.py:67-97`、`core/eval_judgment_service.py:201-254` 将评估用例、运行或校准交给 `core/audit_service.py:47-58`。`core/data_protection.py:19-38,71-89` 未覆盖 `input_payload`、`expected_behavior`、`actual_output`、`human_comment`、`judge_reason`；短值可原样保留，长值仅截断前缀。双后端 `_sync_audit_events`（`storage/backends/postgres.py:755-789`、`storage/backends/sqlite_store.py:863-892`）写入活动审计，删除时再复制到归档。`core/services/evaluation.py:846-853` 经 `core/services/access.py:221-236` 也可将 `human_comment` 写入 `session_events.payload`。评估投影中对应字段受 `storage/field_security.py:35-61,273-314` 保护，并不保护这些副本。真实 SQLite 存储曾验证 input/expected/actual 标记进入活动审计；其他字段及 session_events 路径为代码确认。

**修改方案。**

1. 在 `core/data_protection.py` 扩展已追通的自由文本键：至少上述五项及 `research_target`、`goal`、`session_name`；对实际校准/判定模型已保护的 `disagreement_reason`、`rationale`、`error_message`、`llm_judge_suggestion` 同样处理。非 `public_demo` 递归替换为现有摘要信封，保留 ID、状态、时间及原 `before_hash`/`after_hash`；`public_demo` 的新事件仍可读。对已脱敏信封重复处理必须幂等；仅截断文本或直接调用字段未补齐的旧函数不够。
2. 将同一策略覆盖审计 snapshot、metadata 和 `_log_event`。缓存序列化 `storage/field_security.py:566-569` 只针对 context 内各 `audit_events` 的快照与 metadata 保护，不递归改写整个业务 context 的可用字段。配合 T02 的归档白名单覆盖所有删除入口。
3. 停止/排空旧写入者后备份和盘点，运行可重复、限批、事务化、可恢复的历史修复脚本，遍历 `audit_events.before_snapshot/after_snapshot/metadata`、`audit_events_archive` 对应列及 `session_events.payload`，按已追通字段和事件类型处理。逐行保留 event_id、时间、actor、原 hash，在 metadata 或修复清单记录脱敏版本和时间，记录批次、行数和错误，不打印原文。正常审计仍 append-only；历史修复是有记录的受控例外，不伪装为原事件。
4. 归档可能没有父会话、当前分类也可能不同于事件发生时：不得依赖 JOIN sessions 或假设未知分类为 `public_demo`。无法可靠证明当时为 `public_demo` 时保守脱敏；非法 JSON 与异常行隔离、计数并人工处置。若旧值已被截断，新摘要只描述现存截断值，应标记来源，原 hash 原样保留，不声称恢复原文或原文 hash。
5. 将缓存键升级版本，并按本应用命名空间扫描清理旧 Redis 键；重启所有进程以清除 MemoryCache，清理前不允许旧 worker 回写。不得清空其他应用缓存。备份和已导出副本按既有备份访问/留存策略单独处理；活动库修复不等于清除所有历史备份。

**迁移、兼容与回退。** 不要求新增数据库列，但需要受控数据修复、缓存切换及审计变更记录。历史演示内容可能被保守脱敏，原文不可逆；先备份供受控恢复。回滚旧代码或恢复旧备份均会重新引入明文风险，恢复后必须重新执行清理，且不得让旧版本在切换期间写入。

**收益与代价。** 覆盖删除以外的新评估审计、事件及历史副本；历史可读性下降，短文本的确定性摘要仍可能被猜测，不能作为保密加密。

**验收。** 短值、超 200 字符、嵌套、空值和已脱敏信封均覆盖；非 `public_demo` 新审计、事件、手动删除归档、历史孤儿归档和缓存原始载荷不含标记原文，新 `public_demo` 事件按原契约可读。原 ID/hash 不变，历史脚本中断后可续跑、重跑不再变化；异常行有清单并处置，旧 Redis 命名空间和 MemoryCache 不再提供旧快照。

## P1：后续完善并发、归档和缓存一致性

### T03｜多 worker 重复执行与旧尝试覆盖终态

**原审查级别：P2。** 对已确认有重大不可重复副作用或高费用的真实目标，可提前实施；不能仅凭目标使用 POST 推定影响达到该程度。

**根因和触发。** `core/eval_execution.py:21-24,38-52` 的 in-flight 登记只在单进程内；`core/services/evaluation.py:641-693` 提交前没有共享领取；`core/eval_experiment_service.py:196-203,256-283` 首次外部调用后才保存进度。两个 worker 同时读到 pending 时可能重复调用首项。落败 job 的 `core/services/evaluation.py:593-609` 不核对 owner/attempt；若读取到赢家已提交的 completed 版本，可能写回 interrupted。同步入口 `core/services/evaluation.py:708-716` 同样须覆盖。双 worker 实际交错尚待集成验证。

**数据模型。** 在现有 `eval_experiments` 增加 `claim_owner`、`claim_attempt`、`claim_request_key`、`claim_heartbeat_at`、`claim_lease_until`，双后端类型、默认值和迁移见附录。业务状态、attempt、run_ids 仍以 `ProjectContext.eval_experiments` 为权威，协调列以 owner/租约为权威。普通投影同步不能覆盖协调列：SQLite `storage/backends/sqlite_store.py:1158-1188` 当前的 `INSERT OR REPLACE` 改为 `INSERT ... ON CONFLICT(experiment_id) DO UPDATE`，只更新投影列；PG `storage/backends/postgres.py:1208-1256` 同样明确不写协调列。保留 session 和租户核验，不新增独立队列或无实测依据的索引。

**领取与执行。**

1. 合并后台与同步入口的领取规则。从 DB 直读 context 并校验 dataset 和目标配置；提交 job、调用任何目标之前，在短事务中按 `sessions` → `eval_experiments` 加锁，SQLite 使用 `BEGIN IMMEDIATE`。复核租户、context 版本、实验状态、request key 和领取列；将 context 实验标记 running，attempt 取业务 context 与协调列较大值加一，写启动审计，并原子更新 session 版本、实验投影、owner/attempt/request key/租约后提交。
2. 只允许成功领取者执行：同键重复请求返回当前状态而不再次执行；不同键或无键竞争返回明确 409；已 completed 的同键按既有行为返回结果。DB 写失败或行缺失不得调用目标。后台提交失败仅允许同 owner/attempt 在事务中将该尝试标记 interrupted；准确区分提交结果与实际运行状态。`run_experiment` 消费已领取 attempt，不再次标记 running 或双增 attempt。
3. 每项结果、失败和 completed 在同一事务写入：先锁父行并比较 context version，再锁实验行，验证 running、owner、attempt 和未过期租约；通过后同步 context、投影和审计，终态清理领取。每次新的外部调用前也以 DB 原子验证相同条件，失去领取、冲突或 DB 不可用即停止进一步调用。`StaleContextError` 只能在重新从 DB 读取并确认同 owner、同 attempt 且仍 running 后条件写 interrupted，不覆盖 completed 或新 attempt；`_safe_notify` 不得吞掉失去领取或 DB 不可用的错误后继续调用。

**独立心跳与恢复。** 领取后立即启动覆盖线程池等待和长 HTTP 的周期心跳，使用独立短事务、数据库时钟及条件 `claim_owner=? AND claim_attempt=? AND status='running' AND claim_lease_until > DB_NOW()` 只更新心跳/租约，不推进 context version；过期旧 owner 不得迟到续活。PG 取锁后使用 `clock_timestamp()`，SQLite 使用 UTC `strftime` 写入并用 `julianday` 比较；心跳间隔不超过租约长度三分之一，并为正常 DB 延迟及调度抖动留余量。status 端点读取协调列显示心跳，不以进程内 `_futures` 判断全局存活。

租约到期时，状态查询或**现有 run 入口**按相同锁顺序在 DB 事务内重新检查，只有 owner 和 attempt 仍相同、状态仍 running 且租约仍过期，才原子标记 context 和投影 interrupted、推进版本、清理 owner/租约并记录原因；否则不修改。原有权限用户通过现有 run 入口领取新 owner 和 attempt；发现过期的 run 请求可在同一事务中断旧尝试并新领取，无需新增管理员恢复端点。恢复时跳过已持久化 completed/failed case；旧 owner 的心跳、逐项保存和终态都须被条件拒绝。提交失败和停机也按同 owner/attempt 条件处理。

**外部调用边界。** 不持有数据库锁跨 HTTP。租约过期不证明旧进程已死：旧 HTTP 可能仍在途，检查与发送之间也有窗口，新 attempt 可能重发，因此只承诺至少一次，不保证 exactly-once。`core/eval_experiment_service.py:134-149` 的确定性 `_run_idempotency_key` 仅在明确配置且目标支持对应幂等协议时，由 `core/eval_runner.py:114-127` 经 `core/target_testing/http_json.py:164-190` 透传稳定键，默认不改变目标接口。对确认存在严重不可重复副作用的目标，运营方恢复前核实目标执行结果。

**迁移、兼容与回退。** PostgreSQL 先执行 Alembic 新增协调列，SQLite 更新新库 DDL 及旧库幂等补列；历史行保留表中默认值。然后排空所有旧 worker 和在途任务，人工核对并处理旧 running 实验，再启用领取逻辑；仅升级 schema 不允许与绕过领取的旧版混跑。降级前停任务并保存、核对状态；旧版不识别协调列，直接回退会恢复并发缺陷。按实际客户端确认 409、状态显示及租约配置兼容性。

**收益与代价。** 消除正常竞争下多 worker 同时领取和旧尝试篡改新终态；增加协调列、领取和每项进度短事务及周期心跳，仍保留跨系统重发窗口。

**验收。** 真实 PG 双连接及双进程用屏障并发提交同键、不同键及同步/后台请求，正常竞争首项只发送一次；检查同键返回、409、session/context/投影/协调列一致。模拟提交失败、worker 崩溃、DB 断连、超时、长调用跨多个租约周期、过期后现有 run 重试、旧 owner 迟到及赢家先 completed；旧尝试不得续活或改写新状态，心跳不产生 context 版本冲突。用可控本地目标验证分区和检查/发送窗口仍可能重复，不把它误称为完全消除。

### T06｜并发写入的审计可能漏归档

**原审查级别：P2。**

**根因和触发。** PostgreSQL `storage/backends/postgres.py:1662-1668` 先读取 audit_events，直到 `:1726-1735` 才删除父会话；普通保存先锁父行并提交审计（`:413-417,489-499,523-524`），子审计表的 FK 会级联删除（`alembic/versions/V001_initial_schema.py:83-100`）。在已分析的 Read Committed 交错中，purge 读完旧审计后、删除前，另一事务可完成保存并提交新审计；新事件不在已读取集合中，随后随父行级联删除。此交错尚未在真实 PG 双连接复现，不能外推所有隔离级别。

**修改方案。** 与 T05 共用 purge 事务：PG 首先按租户对 `sessions` 父行 `FOR UPDATE`，再读取完整活动审计、逐条归档、插入 T02 的脱敏删除事件并删除父行；任何失败回滚。统一顺序为父行 → 审计/投影。保存先提交时，其审计进入删除事务读取集合；删除先取锁时，保存等待，删除后由 T01 的仅更新语义拒绝旧保存。SQLite 在读取前 `BEGIN IMMEDIATE` 并在同一事务内完成相同流程，避免跨进程插入交错。

**迁移、兼容与回退。** 无新增 schema；依赖 T01 防止删除后的旧保存重建，建议与 T05 合并修改。空租户系统访问及 cutoff 管理员/留存差异沿用 T05 约束。回退会恢复漏归档窗口，需在停止相关写入与删除后进行。

**收益与代价。** 删除时的审计集合与级联删除受同一父行锁保护；较长归档事务可能增加锁等待，SQLite 需注意批量和 busy 超时。

**验收。** 真实 PG 双连接强制“保存先提交”和“删除先锁”两种顺序，逐事件核对归档完整且无重复；注入归档/DELETE 故障确认回滚。SQLite 双进程验证锁和失败处理；同时覆盖留存 cutoff 跳过时不归档、不删除。

### T08｜缓存旧值续期、乱序覆盖及删除后回填

**原审查级别：P2。**

**根因和触发。** `storage/cache.py:81-109` 使用无版本比较的 SETEX，写失败仅警告；`core/services/access.py:81-90` 命中缓存后直接续期返回，MemoryCache 也有类似行为（`storage/backends/memory_cache.py:34-41,72-78`）。DB 已提交而新缓存写入失败、旧 SET 晚于新 SET，或旧读者在 purge 和 cache.delete 后回填，均可能让后续读取看到旧 context；持续读取还会续期。`api/main.py:237-246` 已在 409 时尝试删除当前租户缓存，不能断言写入必然永久 409；发布门禁 `core/services/governance.py:565-585` 已直读 DB，不据此推断误放行。

**修改方案。** 在两个后端增加轻量、租户限定的 `get_session_version(session_id, tenant_id)`，明确区分行不存在与合法 version 0。所有缓存读取（包括 MemoryCache）统一经过 `SessionAccess._load_session_direct` 边界：每次命中先查 DB；父行存在且缓存 `_storage_version` 与 DB 相同才返回，行不存在则删除或忽略缓存并返回不存在，版本不等或旧缓存缺持久化版本则视为 miss，完整 `store.load` 后可回填。DB 不可用时不信任缓存并返回服务不可用；Redis 故障则正常回源。所有实际会话写入必须推进版本，新会话只使用新 UUID，不得重用旧 ID。升级缓存 key 命名空间并与 T02/T09 清理配合。

每次命中都检查 DB 存在性与版本即可覆盖旧写乱序和删除后回填，不额外叠加 CAS 或墓碑。并发写入与版本校验重叠时，读取结果以 DB 版本查询瞬间为准，不声称撤销已在途读取。

**迁移、兼容与回退。** 无 schema 迁移；新增读方法并升级/清理缓存命名空间，旧格式一律 miss；排空旧进程以防其绕过校验或回写旧敏感内容。回退读取逻辑将恢复陈旧读窗口，回滚时需评估清理缓存和接受风险。每次命中增加一次轻量 DB 读，部署前实测延迟与容量。

**收益与代价。** 后续缓存命中不会接受数据库中不存在或版本不符的会话，代价是每次命中依赖 DB；DB 失效时宁可返回错误而非陈旧数据。

**验收。** 使用真实 Redis 注入 v1 延迟 SET 覆盖 v2、写失败但旧 GET 成功、读取 v1 暂停后 purge+清缓存再回填、DB 不可用而 Redis 可读、持续 GET；覆盖多 worker、MemoryCache、旧格式 key、合法 version 0 和租户隔离。非重叠新请求不得返回旧版或已删除 context；对重叠读取按校验瞬间解释。

## 附录：实施依赖、迁移与验证

### 实施顺序与发布门槛

1. 先遏制新写入：实施 T04、T02/T09 和 T01；排空旧 worker 后执行 T02/T09 历史修复、缓存版本切换及命名空间清理。历史脱敏不可逆；备份恢复后须重新修复。
2. T01 是完整删除闭环的前置。T05 和 T06 修改同一 purge 事务，宜共同实施；其中 T05 属于 P0，若两者无法同批交付，P0 至少先提供锁内 cutoff 复检和正确事务边界，不等待后续功能而留下误删窗口。
3. T08 的缓存版本核验与 T02/T09 缓存切换协调部署。T03 领取必须从 DB 直读，不能依赖缓存；普通 API 的缓存读取完整性依赖 T08。
4. T03 先升级 schema，再排空旧 worker/在途任务并处理旧 running 实验，然后启用领取、心跳及恢复。确认 T03 目标有重大不可重复副作用或高费用时，可提前，但仍须满足这些迁移门槛。
5. 交付时更新相关现行规格、API 行为、迁移 head 和项目升级记录。部署中禁止新旧版本混跑导致绕过创建、鉴权、脱敏、领取或缓存核验；按各项风险制定停写和回退窗口。

### T03 双后端协调列

仅按既有 `experiment_id` 主键定位单实验，并核对 `session_id`、租户；当前没有按租约到期时间全表扫描的需求，不增加 owner 或租约索引。

| 列 | PostgreSQL | SQLite | 默认值与语义 |
|---|---|---|---|
| `claim_owner` | `TEXT` | `TEXT` | `NULL`，可空；随机本次执行者 ID，空值表示无持有者。 |
| `claim_attempt` | `INTEGER NOT NULL` | `INTEGER NOT NULL` | `DEFAULT 0`；单实验单调增长的尝试序号。 |
| `claim_request_key` | `TEXT NOT NULL` | `TEXT NOT NULL` | `DEFAULT ''`；沿用现有请求键语义，空串表示未提供。 |
| `claim_heartbeat_at` | `TIMESTAMPTZ` | `TEXT` | `NULL`，可空；最近持有者心跳的数据库时间，SQLite 存规范 UTC ISO-8601。 |
| `claim_lease_until` | `TIMESTAMPTZ` | `TEXT` | `NULL`，可空；租约到期时间，使用相同数据库时钟和 UTC 口径。 |

PG 用 Alembic `ALTER TABLE eval_experiments ADD COLUMN` 新增；SQLite 同时修改 `_INIT_DDL` 和 `_ADDED_COLUMNS`，旧库幂等补列。旧行保留默认值，领取时 attempt 取 context 与协调列的最大值再加一。普通投影同步必须保留协调列。

### 全局迁移与测试矩阵

以下是实施后的**待执行验收**，不是已经通过的测试结果。

| 测试层 | 必须覆盖的验证 |
|---|---|
| 双后端存储 | T01 version 0/1 删除后保存、显式创建冲突和租户隔离；T02/T09 新旧 JSON、孤儿归档、保留 hash 和清理幂等；T05 锁内 cutoff 复查、准确计数与事务异常回滚。 |
| PostgreSQL 双连接 | T05 候选与用户保存交错；T06 两种父行锁顺序及逐事件归档；T03 领取、进度、心跳和终态的 owner/attempt 条件。核对实际库隔离级别，不以 SQLite 代替。 |
| 双进程 | SQLite `BEGIN IMMEDIATE`；PG 多 worker 的同步/后台竞争、正常竞争首项单次发送、长调用跨多个租约周期、崩溃及现有 run 恢复。外部目标使用本地可控替身。 |
| Redis 故障 | SET 失败而 GET 成功、乱序覆盖、删除后旧读回填、DB 不可用、旧 key、持续读取、MemoryCache；确认现有 409 处理与门禁直读行为。 |
| 完整应用身份 | 使用实际 python-jose、真实 DB 和全应用中间件，验证降权后旧 JWT 无法自恢复、refresh、成员/租户异常、机器 service token，及异步事件循环不被同步 DB 阻塞。 |
| 迁移与历史 | PG 从当前 Alembic head 升级/回滚；SQLite 新库和旧库重复补列；历史清洗中断恢复、异常隔离和重新运行；备份恢复后重新修复；验证旧 worker 已排空。 |
| 项目回归 | 按项目 `AGENTS.md` 在项目环境运行相关 pytest、规定的完整基线及 `git diff --check`，明确记录 PG、Redis 或其他跳过项，不把以往测试当成本次结果。 |

### 已有证据与尚未确认事项

- 已有动态验证使用真实 SQLite 存储、模型和审计代码的组合；T01 已覆盖已持久化 version 0/1 删除后保存，T02/T09 和 T05 的相关路径有实际 SQLite 观察。T04 使用隔离 FastAPI 与真实 SQLite，但 JWT 为兼容替身。上述证据均不是完整应用或生产环境验证。
- 未运行真实 PostgreSQL 双连接、Redis 故障注入、双 worker、真实外部目标、完整 JWT 应用、Alembic 或项目全量测试。T03、T06、T08 的并发和故障行为须按矩阵实测，不能以静态分析冒充通过。
- T03 的租约时长、心跳余量、客户端 409/状态兼容和目标幂等能力待部署环境确认。目标可能已收到超时请求；对于确认有严重不可重复副作用的目标，恢复前须核实执行结果。
- T04 的请求级检查不撤销已通过鉴权的在途操作；更严格的要求需另定事务内授权。T08 的额外 DB 读容量与延迟需测量。
- 历史未知分类、已截断值、异常 JSON、备份与导出副本的处置结果需盘点；未知分类保守脱敏，异常不得静默跳过。恢复旧备份可能重新引入明文。
- **T07［需核验，不计确认缺陷］：** `storage/backends/postgres.py:358-373,1780-1798` 和 `storage/backends/sqlite_store.py:674-687,1662-1680` 表明活动及归档审计表清理后，活动会话 `context_json` 仍保留 event_id、actor、类型、目标和时间等摘要；不能据此说仍保留完整 before/after 快照。当前尚无明确产品口径要求所有摘要和派生副本同期限清除。先确认范围；若确需清除，再设计 context、缓存、projection_state 与并发旧写处理，防止回填。

现有有限状态继续使用项目已有枚举或 `Literal`；本方案不要求新增通用字典表、ORM、通用队列或未经负载证据支持的索引。性能优化应依据实际数据量、慢查询及执行计划决定。
