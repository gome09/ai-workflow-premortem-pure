# 阶段 1 详细设计方案：安全与合规硬缺口修复

> 关系定位：本文档是 [phase-1-security-compliance.md](phase-1-security-compliance.md)（实施计划 / 任务清单 + 验收标准）的**落地设计层**——给出每个任务的具体文件改动、代码草稿、配置参数、决策依据、执行顺序与并行策略、风险。
> 配套规格：[../spec/data-classification-and-privacy.md](../spec/data-classification-and-privacy.md)（子系统①-⑤）、[../spec/supply-chain-security.md](../spec/supply-chain-security.md) 第 4-5 节（SAST）。
> 现状核实日期：2026-07-14（全部条目经代码仓库直接实测，非估算）。
> 状态：设计完成，待用户决策 3 项后可启动执行。
>
> **关于 spec 文件**：现有两份 spec 已完整覆盖阶段 1 全部 9 个任务的设计意图（数据分级 / 加密 / PII / AI 标识 / 生命周期 / PIA / SAST / 应急响应），**不新增 spec 文件**，本设计方案直接落地。

---

## 1. 现状复核（对实施计划基线表的修正与补充）

实施计划 §2 的基线表已核实准确，本节补充 12 项实测发现，其中第 1、5、9 项直接影响任务设计：

| # | 实施计划基线 | 2026-07-14 实测补充 |
|---|---|---|
| 1 | **`ProjectContext` 无 `data_classification` 字段** | 确认。`core/models.py:761-890` ProjectContext 类无此字段；`selected_scenario_id: str \| None`（line 774）已存在，**场景会话 ≠ 用户会话的判定依据现成**：`selected_scenario_id is not None` ⇒ 场景会话 ⇒ `public_demo` |
| 2 | 用户材料入口 `ProjectContext.user_materials: list[str]` | 确认。`core/models.py:789`，纯文本 list，无嵌套结构，加密/掩码作用对象简单 |
| 3 | `evidence_sources` 含 `summary` / `claims` | 确认。`core/models.py:383-` EvidenceSource 类，`source_type: Literal[...]` 已含 `"user_material"`（line 398），加密范围判定有现成字段 |
| 4 | `AuditEvent.event_type` 为自由字符串 | 确认。`core/models.py:277` `event_type: str`（非 Literal），新增 `data_classification_changed` / `session_purged` 等事件类型无需改 schema |
| 5 | **`risk_profile.py` 关键词表无心理健康/学生词** | 确认。`core/gates/risk_profile.py:72-101` `_HIGH_KEYWORDS` 含金融/法律/儿童/认证/访问控制/公开发布/自动发送/核电/自动驾驶，**无"心理/精神/抑郁/自杀/学生/mental health"**；`university_ai_mental_health_input.md` 含"学生心理健康风险预测"会落入 MEDIUM 档（实测） |
| 6 | `classify_project_risk` 返回 `ProjectGateRiskTier` 枚举 | 确认。`core/gates/risk_profile.py:25-29` 枚举值 LOW/MEDIUM/HIGH/CRITICAL；`classify_project_risk(ctx)` 函数 line 196-260，**目前不读取 `data_classification`**——T1.1 联动的设计挂载点 |
| 7 | `scan_user_materials()` 已存在 | 确认。`tools/safety_classifier.py:225-243` 已实现，被 `core/session_service.py:216, 260` 调用。**PII 检测可直接挂载在 `scan_text()`（line 107）内**，无需新增调用点 |
| 8 | `format_evidence_for_prompt()` 是 PII 掩码挂载点 | 确认。`core/evidence_service.py:74-104`，函数签名 `(evidence_sources, user_materials) -> str`，拼 prompt 前的最后一道关口 |
| 9 | **`_build_context_json_for_storage()` 是加密挂载点** | 确认。两后端各有一份：`storage/backends/postgres.py:51-116`、`storage/backends/sqlite_store.py:400-455`，均为 `@staticmethod`，操作 `data = ctx.model_dump(mode="json")` 后的 dict。读侧 `load()` 通过 `migrate_context()` 还原。**两份逻辑高度重复，加密钩子应抽到共享模块** |
| 10 | `Settings` 类无加密/PII/留存配置 | 确认。`core/config.py:10-105` Settings 类有 `jwt_secret`/`deepseek_api_key` 等密钥配置 + `validate_secrets()` model_validator 模式，**新增 `data_encryption_key` 等字段直接复用此模式** |
| 11 | CI 已有 `permissions: contents: read` | 确认。`.github/workflows/ci.yml:9-10` 阶段 0 已收紧权限；两个 job（lint-and-unit-tests / docker-lite-integration）均无 SAST/pip-audit 步骤 |
| 12 | ruff 规则集为 `["E", "F", "I", "UP"]` | 确认。`pyproject.toml:57` `select = ["E", "F", "I", "UP"]`，无 `S`；`per-file-ignores` 已有 `tests/test_auth.py = ["E402", "I001"]` 模式，可复用豁免 `tests/` 的 `S101`（assert 使用） |

### 关键发现影响：T1.6 删除端点的设计修正

实施计划 T1.6 原文「`DELETE /sessions/{id}`（admin，审计不删、写 `session_purged` 事件）」**与现有 schema 冲突**：`audit_events` 表在 SQLite（`sqlite_store.py:99`）与 PostgreSQL（V001/V003）均声明 `session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE`——删除 session 会级联删除审计事件，与"审计不删"矛盾。

正确设计：新增 `audit_events_archive` 表（无 FK 约束），删除会话前先归档审计事件 + 写 `session_purged` 归档事件，再删除会话。详见 §2.6。

---

## 2. 任务级详细设计

### T1.2 敏感场景风险升档修正【最小最优先，独立】

**改动文件**：
- [core/gates/risk_profile.py](../../core/gates/risk_profile.py)（`_HIGH_KEYWORDS` 表 + `classify_project_risk` 函数）
- `tests/test_risk_profile_mental_health.py`（新建回归测试）

**具体改动**：

1. `_HIGH_KEYWORDS` 表（line 72-101）追加两条：

```python
# 在 _HIGH_KEYWORDS 列表末尾、最后一项后追加：
(
    re.compile(
        r"(?i)(心理|精神|抑郁|自杀|自残|self.?harm|mental.?health|心理健康|精神健康|psycholog|psychiatr|suicid|depress)"
    ),
    "mental health domain",
),
(
    re.compile(r"(?i)(学生|student|pupil|校园|campus|高校|大学|university|college)"),
    "student/minor-adjacent population",
),
```

2. `classify_project_risk()` 函数（line 196-260）在 step 3「High automation / sensitive data → raise」之后追加 step 3.5「Data classification → raise」：

```python
# 在 sensitive_hits 检查后（line 232-237 之后）、low_hits 检查前插入：
# 3.5 Sensitive personal data classification → raise to at least HIGH
if getattr(ctx, "data_classification", None) == "sensitive_personal":
    reasons.append("sensitive_personal data classification")
    if tier == ProjectGateRiskTier.MEDIUM:
        tier = ProjectGateRiskTier.HIGH
    elif tier == ProjectGateRiskTier.HIGH:
        tier = ProjectGateRiskTier.CRITICAL
```

> 设计说明：用 `getattr(ctx, "data_classification", None)` 而非 `ctx.data_classification`，保证在 T1.1 未完成时（字段不存在）不报错。T1.1 完成后此挂载点自动生效。

3. 回归测试 `tests/test_risk_profile_mental_health.py`：

```python
"""T1.2 回归测试：university_mental_health 场景必须升为 HIGH 及以上。"""
from core.gates.risk_profile import classify_project_risk, ProjectGateRiskTier
from core.models import ProjectContext


def _build_mental_health_ctx() -> ProjectContext:
    """复刻 examples/university_ai_mental_health_input.md 的关键词分布。"""
    return ProjectContext(
        research_target="基于多源行为数据的学生心理健康风险预测系统",
        domain="高校学生事务管理",
        goal="早期识别存在心理健康风险的学生，向心理咨询中心发出预警",
    )


def test_mental_health_scenario_raises_to_high():
    ctx = _build_mental_health_ctx()
    tier, reasons = classify_project_risk(ctx)
    assert tier in {ProjectGateRiskTier.HIGH, ProjectGateRiskTier.CRITICAL}, (
        f"university_mental_health should be HIGH+, got {tier}; reasons={reasons}"
    )
    assert any("mental health" in r or "student" in r for r in reasons)


def test_non_mental_health_session_stays_medium():
    """无关键词的普通会话仍为 MEDIUM（防回归）。"""
    ctx = ProjectContext(
        research_target="内部知识库问答",
        domain="企业内部工具",
        goal="提升员工查找文档效率",
    )
    tier, _ = classify_project_risk(ctx)
    assert tier == ProjectGateRiskTier.MEDIUM
```

**验收**：`make test` 通过；`university_mental_health` 场景实测落入 HIGH 及以上。

**工作量**：S（30 分钟）。

---

### T1.1 数据分类分级【基础，T1.3/T1.4/T1.6/T1.7 依赖】

**改动文件**：
- [core/models.py](../../core/models.py)（ProjectContext 新增字段）
- `core/migrations/v070_to_v080.py`（新建应用层迁移）
- `core/migrations/registry.py`（注册迁移 + bump CURRENT_CONTEXT_SCHEMA_VERSION）
- `core/migrations/__init__.py`（导出新迁移模块）
- [core/session_service.py](../../core/session_service.py)（`create_session` 设默认分级）
- [api/routers/session.py](../../api/routers/session.py)（新增 PATCH 端点）
- `api/schemas.py`（新增 request/response schema）
- `tests/test_data_classification.py`（新建）

**具体改动**：

1. `core/models.py` ProjectContext 类（line 789 后，`user_materials` 字段下方）新增：

```python
# ── 数据分类分级（DSL 21 条 / PIPL 51 条）────────
data_classification: Literal["public_demo", "business_internal", "sensitive_personal"] = "business_internal"
```

> 默认值 `business_internal`：新创建的非场景会话默认此级别；场景会话由 `create_session` 显式设为 `public_demo`。`Literal` 类型保证取值受控。

2. `core/migrations/v070_to_v080.py`（新建，参照 `v060_alpha8_to_v070.py` 模式）：

```python
"""Context schema migration: v0.7.0 → v0.8.0.

Adds data_classification field with default 'business_internal'.
Scenario sessions (selected_scenario_id is not None) are backfilled to 'public_demo'.
"""
from __future__ import annotations
from typing import Any
from core.migrations.base import MigrationFn
from core.migrations.registry import (
    CURRENT_CONTEXT_SCHEMA_VERSION,
    LEGACY_CONTEXT_SCHEMA_VERSION,
    register_migration,
)

TO_VERSION = "0.8.0"


def _migrate_v070_to_v080(ctx_dict: dict[str, Any]) -> dict[str, Any]:
    ctx_dict["context_schema_version"] = TO_VERSION
    # 默认 business_internal；场景会话回填 public_demo
    if "data_classification" not in ctx_dict:
        if ctx_dict.get("selected_scenario_id"):
            ctx_dict["data_classification"] = "public_demo"
        else:
            ctx_dict["data_classification"] = "business_internal"
    return ctx_dict


def register() -> None:
    register_migration("0.7.0", TO_VERSION, _migrate_v070_to_v080)
```

3. `core/migrations/registry.py` 改动：
   - `CURRENT_CONTEXT_SCHEMA_VERSION = "0.8.0"`（line 10）
   - 在模块末尾或 `__init__.py` 中导入并注册：`from core.migrations import v070_to_v080; v070_to_v080.register()`

4. `core/session_service.py` `create_session()` 方法（line 121-128）追加：

```python
def create_session(self, tenant_id: str = "", scenario_id: str | None = None) -> ProjectContext:
    """创建新会话"""
    ctx = ProjectContext(tenant_id=tenant_id)
    ctx = attach_scenario_to_context(ctx, scenario_id or settings.default_scenario_id or None)
    # T1.1: 数据分类分级——场景会话 public_demo，用户会话 business_internal
    ctx.data_classification = "public_demo" if ctx.selected_scenario_id else "business_internal"
    session_store.save(ctx)
    context_cache.set(ctx)
    logger.info(f"Session created: {ctx.session_id}")
    return ctx
```

> PII 命中时的自动升级到 `sensitive_personal` 由 T1.4 在 `scan_user_materials` 路径中实现，此处只设默认值。

5. `api/schemas.py` 新增：

```python
class UpdateDataClassificationRequest(BaseModel):
    data_classification: Literal["public_demo", "business_internal", "sensitive_personal"]
    note: str = ""
```

6. `api/routers/session.py` 新增 PATCH 端点：

```python
from api.schemas import UpdateDataClassificationRequest
from core.audit_service import append_audit_event

@router.patch(
    "/{session_id}/data-classification",
    dependencies=[require_roles(Role.editor, Role.admin)],
)
def update_data_classification(
    session_id: str,
    body: UpdateDataClassificationRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """覆写会话数据分级。

    规则：升级或同级修改允许 editor+；降级必须 admin，且写 AuditEvent。
    """
    project_ctx = session_service.get_session(session_id, tenant_id=ctx.tenant_id)
    if not project_ctx:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    before = project_ctx.data_classification
    after = body.data_classification
    order = {"public_demo": 0, "business_internal": 1, "sensitive_personal": 2}
    is_downgrade = order[after] < order[before]

    if is_downgrade:
        # 降级必须 admin
        if ctx.role != Role.admin.value:
            raise HTTPException(
                status_code=403,
                detail="Downgrading data_classification requires admin role",
            )

    append_audit_event(
        project_ctx,
        actor=ctx.role,
        event_type="data_classification_changed",
        target_type="session",
        target_id=session_id,
        before={"data_classification": before},
        after={"data_classification": after},
        metadata={"note": body.note, "is_downgrade": is_downgrade},
    )
    project_ctx.data_classification = after
    session_store.save(project_ctx)
    context_cache.set(project_ctx)
    return {
        "ok": True,
        "session_id": session_id,
        "before": before,
        "after": after,
        "is_downgrade": is_downgrade,
    }
```

> 注意：`ctx.role` 来自 `TenantContext`（`auth/jwt.py`），需确认字段名；若实际字段名不同，按实际调整。

7. 回归测试 `tests/test_data_classification.py`（场景）：
   - 场景会话创建后 `data_classification == "public_demo"`
   - 用户会话创建后 `data_classification == "business_internal"`
   - PATCH 升级 editor 可操作；降级 editor 403、admin 可操作
   - 降级操作产出 `AuditEvent(event_type="data_classification_changed", metadata.is_downgrade=True)`

**验收**：场景会话=public_demo、用户会话=business_internal、PII 命中自动升 sensitive_personal（T1.4 完成后联测）、降级有 AuditEvent。

**工作量**：M。

---

### T1.3 存储层字段级加密【高风险，必须单独执行 + SQLite 全量回归】

**改动文件**：
- `storage/field_security.py`（新建共享模块）
- [storage/backends/postgres.py](../../storage/backends/postgres.py)（`_build_context_json_for_storage` + `load`）
- [storage/backends/sqlite_store.py](../../storage/backends/sqlite_store.py)（同上）
- [core/config.py](../../core/config.py)（新增 `data_encryption_key` 字段）
- [pyproject.toml](../../pyproject.toml)（显式声明 `cryptography` 依赖）
- [.env.example](../../.env.example) / `.env.demo`（新增配置项）
- `tests/test_field_encryption.py`（新建）

**具体改动**：

1. `core/config.py` Settings 类（line 80 后，Auth 区块内）新增：

```python
# Data encryption (T1.3) — Fernet key, base64-encoded 32 bytes
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
data_encryption_key: str = ""
```

`validate_secrets()` 不强制要求（demo/lite 模式允许空，生产模式告警）。生产告警逻辑在 `field_security.py` 实现。

2. `pyproject.toml` dependencies 列表（line 9-32）追加显式依赖：

```toml
"cryptography>=42.0.0",  # T1.3 字段级静态加密（python-jose[cryptography] 已传递依赖，此处显式声明便于 pip-audit 跟踪）
```

3. `storage/field_security.py`（新建）：

```python
"""T1.3 字段级静态加密 — Fernet 应用层加密。

设计：
- 加密范围：data_classification ∈ {business_internal, sensitive_personal} 会话的
  user_materials (list[str]) 与 evidence_sources[*].summary/claims (str / list[str])。
- 密文带 enc:v1: 前缀，便于识别与未来轮换。
- 未配置密钥时：demo/lite 模式（storage_backend=sqlite）静默明文；
  生产模式（postgres）启动时 WARNING，/health 暴露 data_encryption: disabled。
- public_demo 永远明文（保住"零配置离线演示"亮点）。
"""
from __future__ import annotations

import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

_ENCRYPTION_PREFIX = "enc:v1:"
_fernet = None  # lazy init


def _get_fernet():
    """Lazily initialize Fernet. Returns None if no key configured."""
    global _fernet
    if _fernet is not None:
        return _fernet
    key = settings.data_encryption_key
    if not key:
        if settings.storage_backend != "sqlite":
            logger.warning(
                "DATA_ENCRYPTION_KEY not set; sensitive fields stored in plaintext "
                "(storage_backend=%s). Set DATA_ENCRYPTION_KEY in production.",
                settings.storage_backend,
            )
        return None
    from cryptography.fernet import Fernet
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def is_encryption_enabled() -> bool:
    return _get_fernet() is not None


def _encrypt_value(text: str) -> str:
    """Encrypt a string. Returns 'enc:v1:<ciphertext>' or original if encryption disabled."""
    if not text or text.startswith(_ENCRYPTION_PREFIX):
        return text  # idempotent
    f = _get_fernet()
    if f is None:
        return text
    return _ENCRYPTION_PREFIX + f.encrypt(text.encode("utf-8")).decode("ascii")


def _decrypt_value(text: str) -> str:
    """Decrypt a string. Returns original if not encrypted or decryption fails."""
    if not text or not text.startswith(_ENCRYPTION_PREFIX):
        return text
    f = _get_fernet()
    if f is None:
        return text  # can't decrypt without key; return as-is (likely demo mode reading prod data)
    try:
        return f.decrypt(text[len(_ENCRYPTION_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        logger.warning("Failed to decrypt field (wrong key? corrupted?) — returning ciphertext")
        return text


def encrypt_fields_for_storage(data: dict[str, Any], classification: str) -> dict[str, Any]:
    """Mutate `data` dict in-place: encrypt user_materials and evidence_sources summary/claims.

    Called from _build_context_json_for_storage AFTER truncation, BEFORE json.dumps.
    """
    if classification == "public_demo":
        return data  # demo 永远明文
    if not is_encryption_enabled():
        return data  # 未配置密钥静默明文

    # user_materials: list[str]
    materials = data.get("user_materials") or []
    data["user_materials"] = [_encrypt_value(m) for m in materials]

    # evidence_sources: list[dict] with summary (str) and claims (list[str])
    sources = data.get("evidence_sources") or []
    for ev in sources:
        if ev.get("source_type") != "user_material":
            continue  # 仅加密 user_material 类型的证据
        if ev.get("summary"):
            ev["summary"] = _encrypt_value(ev["summary"])
        if ev.get("claims"):
            ev["claims"] = [_encrypt_value(c) for c in ev["claims"]]

    return data


def decrypt_fields_after_load(ctx) -> None:
    """Decrypt encrypted fields on a loaded ProjectContext (in-place).

    Called from backend load() AFTER migrate_context() returns ProjectContext.
    """
    if not is_encryption_enabled():
        return  # 未配置密钥：要么 demo 模式（数据本就明文），要么生产但未配 key（ciphertext 原样返回，无法解密）

    # user_materials
    ctx.user_materials = [_decrypt_value(m) for m in ctx.user_materials]

    # evidence_sources
    for ev in ctx.evidence_sources:
        if ev.source_type != "user_material":
            continue
        if ev.summary:
            ev.summary = _decrypt_value(ev.summary)
        if ev.claims:
            ev.claims = [_decrypt_value(c) for c in ev.claims]
```

4. `storage/backends/postgres.py` `_build_context_json_for_storage()` 末尾（line 116 前）追加：

```python
from storage.field_security import encrypt_fields_for_storage

# 在 return json.dumps(data, default=str) 之前：
encrypt_fields_for_storage(data, ctx.data_classification)
return json.dumps(data, default=str)
```

5. `storage/backends/postgres.py` `load()` 方法（line 942 后）追加：

```python
from storage.field_security import decrypt_fields_after_load

# 在 ctx = migrate_context(...) 之后、return ctx 之前：
if ctx:
    decrypt_fields_after_load(ctx)
return ctx
```

6. `storage/backends/sqlite_store.py` 同样改动 `_build_context_json_for_storage()` 和 `load()`。

7. `/health` 端点（`api/main.py:160-172`）追加字段：

```python
from storage.field_security import is_encryption_enabled

# 在 return dict 中追加：
"data_encryption": "enabled" if is_encryption_enabled() else "disabled",
```

8. `.env.example` 与 `.env.demo` 在 Auth 区块后追加：

```bash
# === Data Encryption (T1.3) ===
# Fernet key for field-level encryption of sensitive session data.
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Leave empty in demo/sqlite mode (plaintext). MUST set in production with storage_backend=postgres.
DATA_ENCRYPTION_KEY=
```

9. 测试 `tests/test_field_encryption.py`：
   - `is_encryption_enabled() == False` 时不加密、不报错
   - 配置 key 后 `encrypt_fields_for_storage` 在密文中带 `enc:v1:` 前缀
   - `decrypt_fields_after_load` 还原原文
   - `public_demo` 会话不被加密
   - 往返测试：encrypt → decrypt → 与原文相等
   - 双 backend 各一组（sqlite 用现有测试夹具，postgres 用 mock 连接）

**验收**：
- 配置密钥后两后端读写往返测试通过；
- 数据库文件/表内直接查看为密文（用 sqlite3 CLI 或 psql 查 `context_json` 字段验证）；
- 关闭密钥时现有全部测试不回退（`make test` 全绿）。

**工作量**：L（高风险，必须 SQLite 全量回归后再考虑 PostgreSQL）。

**风险**：
- 密钥丢失 = 数据不可读。`.env.example` 与备份指引必须写清密钥备份责任。
- `_build_context_json_for_storage` 是写主路径，加密失败会导致整个 save 失败——`_encrypt_value` 必须吞异常并 fallback 到明文（已设计：仅在 fernet 为 None 时跳过，fernet 加密本身失败应抛错以便发现）。

---

### T1.4 PII 检测与出境前掩码【依赖 T1.1】

**改动文件**：
- [tools/safety_classifier.py](../../tools/safety_classifier.py)（新增 `PII_PATTERNS` + `scan_pii` 函数 + 在 `scan_text` 中调用）
- [core/evidence_service.py](../../core/evidence_service.py)（`format_evidence_for_prompt` 加掩码）
- [core/config.py](../../core/config.py)（新增 `pii_mask_before_llm` 字段）
- [.env.example](../../.env.example)（新增配置项）
- `tests/test_pii_detection.py`（新建）

**具体改动**：

1. `tools/safety_classifier.py` 在 `SECRET_PATTERNS`（line 16）后新增 `PII_PATTERNS`：

```python
# PII 检测（T1.4）— 命中产出 sensitive_info finding；身份证/银行卡 severity=high
PII_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, kind, severity)
    # 中国大陆身份证号（18 位，最后一位校验可为 X）
    (r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b",
     "cn_id_card", "high"),
    # 中国大陆手机号
    (r"\b1[3-9]\d{9}\b", "cn_mobile", "medium"),
    # 邮箱
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email", "low"),
    # 银行卡号（16-19 位，Luhn 校验后置）
    (r"\b\d{16,19}\b", "bank_card", "high"),
]
```

2. 新增 `scan_pii()` 函数并在 `scan_text()` 中调用：

```python
def _mask_pii(text: str, kind: str) -> str:
    """掩码 PII：保留首尾字符，中间用 * 替换。"""
    if not text or len(text) <= 4:
        return "***"
    if kind == "email":
        # 邮箱掩码：u***@domain.com
        local, _, domain = text.partition("@")
        if not domain:
            return text
        return f"{local[0]}***@{domain}"
    if kind == "cn_id_card":
        return f"{text[:6]}********{text[-4:]}"
    if kind == "cn_mobile":
        return f"{text[:3]}****{text[-4:]}"
    if kind == "bank_card":
        return f"{text[:4]}************{text[-4:]}"
    return text[:2] + "*" * (len(text) - 4) + text[-2:]


def scan_pii(text: str) -> list[tuple[str, str, str]]:
    """检测文本中的 PII。返回 [(matched_text, kind, severity), ...]。"""
    import re
    findings: list[tuple[str, str, str]] = []
    for pattern, kind, severity in PII_PATTERNS:
        for match in re.finditer(pattern, text or ""):
            findings.append((match.group(0), kind, severity))
    return findings


def mask_pii_in_text(text: str) -> str:
    """对文本中的所有 PII 进行掩码（用于 prompt 路径）。"""
    import re
    masked = text or ""
    for pattern, kind, _severity in PII_PATTERNS:
        masked = re.sub(pattern, lambda m: _mask_pii(m.group(0), kind), masked)
    return masked
```

3. 在 `scan_text()`（line 107-189）的 `SECRET_PATTERNS` 检查后追加 PII 检查：

```python
# PII 检测（T1.4）
pii_hits = scan_pii(content)
if pii_hits:
    pii_kinds = sorted({kind for _, kind, _ in pii_hits})
    max_severity = max((sev for _, _, sev in pii_hits), key=lambda s: {"low": 0, "medium": 1, "high": 2}[s])
    findings.append(
        _finding(
            ctx,
            stage_id=stage_id,
            risk_type="sensitive_info",
            severity=max_severity,
            location=location,
            description=f"用户材料包含 PII：{', '.join(pii_kinds)}。",
            recommended_action="确认 PII 是否必要；如必要，启用 PII_MASK_BEFORE_LLM 掩码后再发送 LLM。",
        )
    )
    # T1.1 联动：PII 命中自动升级数据分级到 sensitive_personal
    if hasattr(ctx, "data_classification"):
        if ctx.data_classification != "sensitive_personal":
            ctx.data_classification = "sensitive_personal"
```

> 注意：`scan_pii` 不应在 LLM 输出文本中误报（如 LLM 生成的示例身份证号），所以 PII 检测**仅对 `location.startswith("user_materials")` 或 `location.startswith("evidence_source")` 的文本启用**。在 `scan_text` 内加 location 判断：

```python
# 仅对用户材料/证据源启用 PII 检测，避免 LLM 输出误报
if location.startswith(("user_materials", "evidence_source")):
    pii_hits = scan_pii(content)
    ...
```

4. `core/config.py` Settings 类新增：

```python
# PII masking before sending to LLM (T1.4)
# Default false: 先让检测跑起来积累误报数据，再决定是否默认开启。
pii_mask_before_llm: bool = False
```

5. `core/evidence_service.py` `format_evidence_for_prompt()`（line 74-104）追加掩码：

```python
from core.config import settings
from tools.safety_classifier import mask_pii_in_text

def format_evidence_for_prompt(
    evidence_sources: list[EvidenceSource],
    user_materials: list[str],
) -> str:
    mask = settings.pii_mask_before_llm
    sections: list[str] = []
    if evidence_sources:
        sections.append("### Evidence Sources（阶段输出必须引用 evidence_id）")
        for ev in evidence_sources:
            summary = mask_pii_in_text(ev.summary[:800]) if mask else ev.summary[:800]
            sections.append(
                f"[{ev.evidence_id}]\n"
                f"Title: {ev.title}\n"
                f"Source Type: {ev.source_type}\n"
                f"Credibility: {ev.credibility_score}\n"
                f"URL: {ev.url or 'N/A'}\n"
                f"Summary: {summary}\n"
            )

    material_ids = {
        ev.evidence_id
        for ev in evidence_sources
        if ev.source_type == "user_material" and ev.evidence_id.startswith("USER-EVID-")
    }
    if user_materials and not material_ids:
        sections.append("### 人工补充资料")
        for i, material in enumerate(user_materials, 1):
            masked_material = mask_pii_in_text(material) if mask else material
            sections.append(f"[USER-MATERIAL-{i}]\n{masked_material}\n")

    if not sections:
        return "（暂无外部资料，请基于已有知识进行分析，并对不确定项标注【需核验】）"
    return "\n".join(sections)
```

6. `.env.example` 在 T1.3 区块后追加：

```bash
# === PII Masking (T1.4) ===
# When true, PII (ID card / mobile / email / bank card) is masked before sending to LLM.
# Default false: let detection run first to accumulate false-positive data before enabling.
PII_MASK_BEFORE_LLM=false
```

7. 测试 `tests/test_pii_detection.py`：
   - 含身份证号的材料产出 `sensitive_info` finding，severity=high
   - `ctx.data_classification` 自动升 `sensitive_personal`（T1.1 联动）
   - `pii_mask_before_llm=True` 时 prompt 中身份证号被掩码为 `110***********1234` 形式
   - `pii_mask_before_llm=False` 时 prompt 中保留原文
   - 落库原文不受影响（加密由 T1.3 处理，掩码只作用于 prompt 路径）
   - LLM 输出文本（`location=stage_X.ai_output`）不触发 PII 检测（防误报）

**验收**：含 PII 的材料触发 finding；开关开启时发往 LLM 的 prompt 中 PII 已掩码；落库原文不受影响。

**工作量**：M。

---

### T1.5 报告 AI 生成内容标识补强【独立】

**改动文件**：
- [core/report_service.py](../../core/report_service.py)（`build_report_dict` + `build_markdown_report`）
- `tests/test_report_ai_notice.py`（新建）

**具体改动**：

1. `build_report_dict()` 在 `disclaimer` 键**之前**（line 377 前）插入 `ai_generated_notice` 结构化字段：

```python
# 在 build_report_dict 返回 dict 中，"disclaimer" 之前插入：
"ai_generated_notice": {
    "zh": "本报告由 AI 辅助生成。依据《人工智能生成合成内容标识办法》进行显式标识。报告内容须经人工审核确认后方可用于实际决策。",
    "en": "AI-generated outputs must be reviewed by humans before real-world use.",
    "basis": "《人工智能生成合成内容标识办法》（2025-09-01 施行）",
    "generator": "ai-workflow-premortem",
    "generator_version": REPORT_SCHEMA_VERSION,
},
"disclaimer": "AI-generated outputs must be reviewed by humans before real-world use.",  # 保留向后兼容
```

> `REPORT_SCHEMA_VERSION` 已在文件顶部定义，复用即可。

2. `build_markdown_report()` 在首屏（`# AI Workflow Pre-mortem Report` 标题后、`- Report Schema Version:` 前）插入双语标识块 + HTML 注释隐式标识：

```python
# 在 build_markdown_report 的 lines 列表初始化后（line 425-429 区域）插入：
lines: list[str] = [
    "# AI Workflow Pre-mortem Report",
    "",
    "<!-- ai-generated: true; generator: ai-workflow-premortem; "
    f"version: {REPORT_SCHEMA_VERSION} -->",
    "",
    "> **本报告由 AI 辅助生成（AI-Generated Content）**",
    "> 依据《人工智能生成合成内容标识办法》进行显式标识。"
    "报告内容须经人工审核确认后方可用于实际决策。",
    "> AI-generated outputs must be reviewed by humans before real-world use.",
    "",
    f"- Report Schema Version: `{REPORT_SCHEMA_VERSION}`",
    # ... 其余原有内容
]
```

3. 现有 `## 19. Disclaimer`（line 843-844）保留不动（向后兼容）。

4. 测试 `tests/test_report_ai_notice.py`：
   - 导出 JSON 报告：`content["ai_generated_notice"]` 存在且含 `zh`/`en`/`basis` 三个键
   - 导出 JSON 报告：`content["disclaimer"]` 仍存在（向后兼容）
   - 导出 Markdown 报告：首屏（前 10 行内）可见中文标识"本报告由 AI 辅助生成"
   - 导出 Markdown 报告：含 HTML 注释 `<!-- ai-generated: true`
   - 现有报告快照测试（`test_report_creation_large_session.py` / `test_report_export_robustness.py`）不回退

**验收**：导出任一报告，首屏可见中文标识；`content_json["disclaimer"]` 仍存在。

**工作量**：S。

---

### T1.6 数据生命周期最小集【依赖 T1.1，含 schema 修正】

**改动文件**：
- `alembic/versions/V004_audit_archive.py`（新建迁移：audit_events_archive 表）
- [core/config.py](../../core/config.py)（新增 `audit_retention_days` / `session_retention_days`）
- [api/routers/session.py](../../api/routers/session.py)（新增 DELETE 端点）
- [core/session_service.py](../../core/session_service.py)（新增 `delete_session` 方法）
- `storage/backends/postgres.py` + `storage/backends/sqlite_store.py`（新增 `archive_audit_events` + `delete_session_cascade` 方法）
- [api/main.py](../../api/main.py)（`/health` 暴露留存配置）
- `docs/compliance/backup.md`（新建备份指引文档）
- [.env.example](../../.env.example)（新增配置项）
- `tests/test_session_lifecycle.py`（新建）

**具体改动**：

1. `alembic/versions/V004_audit_archive.py`（新建，参照 V003 模式）：

```python
"""Audit events archive table for session purge audit trail.

Revision ID: V004
Revises: V003
Create Date: 2026-07-14

Changes
-------
1. audit_events_archive — CREATE TABLE (no FK to sessions; preserves audit trail after session deletion)
"""
from __future__ import annotations
from alembic import op

revision = "V004"
down_revision = "V003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_events_archive (
        archive_id      TEXT PRIMARY KEY,
        original_session_id TEXT NOT NULL,
        event_id        TEXT NOT NULL,
        actor           TEXT NOT NULL,
        event_type      TEXT NOT NULL,
        target_type     TEXT NOT NULL,
        target_id       TEXT NOT NULL,
        before_hash     TEXT,
        after_hash      TEXT,
        before_snapshot JSONB,
        after_snapshot  JSONB,
        metadata        JSONB NOT NULL DEFAULT '{}',
        original_created_at TIMESTAMPTZ NOT NULL,
        archived_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_archive_session "
        "ON audit_events_archive (original_session_id, original_created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_events_archive CASCADE")
```

2. SQLite 侧在 `_INIT_DDL`（`sqlite_store.py:22-361`）追加等价表定义：

```sql
CREATE TABLE IF NOT EXISTS audit_events_archive (
    archive_id           TEXT PRIMARY KEY,
    original_session_id  TEXT NOT NULL,
    event_id             TEXT NOT NULL,
    actor                TEXT NOT NULL,
    event_type           TEXT NOT NULL,
    target_type          TEXT NOT NULL,
    target_id            TEXT NOT NULL,
    before_hash          TEXT,
    after_hash           TEXT,
    before_snapshot      TEXT,
    after_snapshot       TEXT,
    metadata             TEXT NOT NULL DEFAULT '{}',
    original_created_at  TEXT NOT NULL,
    archived_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_archive_session
    ON audit_events_archive (original_session_id, original_created_at DESC);
```

3. `core/config.py` Settings 类新增：

```python
# Data lifecycle (T1.6) — retention declarations (days)
audit_retention_days: int = 183       # 等保 6 个月
session_retention_days: int = 0       # 0 = 永久
```

> 留存策略首期只做**声明与检查**（`/health` 暴露 + 文档承诺），自动清理任务后置——审计数据 append-only 优先级高于自动删除。

4. `storage/backends/postgres.py` + `sqlite_store.py` 新增方法：

```python
def archive_and_purge_session(self, session_id: str, purged_by: str, session_summary: dict) -> None:
    """归档审计事件 + 写 session_purged 归档事件 + 删除会话（级联）。"""
    import uuid
    from datetime import datetime
    now = datetime.utcnow().isoformat()

    with self._get_conn() as conn:
        # 1. 归档现有 audit_events（含原始 session_id）
        conn.execute("""
            INSERT INTO audit_events_archive (
                archive_id, original_session_id, event_id, actor, event_type,
                target_type, target_id, before_hash, after_hash,
                before_snapshot, after_snapshot, metadata, original_created_at, archived_at
            )
            SELECT
                gen_random_uuid()::text, session_id, event_id, actor, event_type,
                target_type, target_id, before_hash, after_hash,
                before_snapshot::jsonb, after_snapshot::jsonb,
                metadata::jsonb, created_at, %s
            FROM audit_events WHERE session_id = %s
        """, (now, session_id))  # PostgreSQL 版本

        # 2. 写 session_purged 归档事件
        conn.execute("""
            INSERT INTO audit_events_archive (
                archive_id, original_session_id, event_id, actor, event_type,
                target_type, target_id, before_hash, after_hash,
                before_snapshot, after_snapshot, metadata, original_created_at, archived_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            str(uuid.uuid4()), session_id, str(uuid.uuid4())[:8],
            purged_by, "session_purged", "session", session_id,
            None, None, None, None,
            json.dumps(session_summary, default=str), now, now,
        ))

        # 3. 删除会话（级联删除所有 FK 表，包括 audit_events）
        conn.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
        conn.commit()
```

> SQLite 版本用 `?` 占位符 + `json()` 函数；逻辑相同。

5. `core/session_service.py` 新增 `delete_session` 方法：

```python
def delete_session(self, session_id: str, *, purged_by: str, tenant_id: str = "") -> dict:
    """Admin 删除会话：归档审计 + 写 session_purged + 级联删除。"""
    ctx = self.get_session(session_id, tenant_id)
    if not ctx:
        raise ValueError(f"Session not found: {session_id}")

    session_summary = {
        "session_id": session_id,
        "research_target": ctx.research_target,
        "domain": ctx.domain,
        "created_at": ctx.created_at.isoformat(),
        "data_classification": ctx.data_classification,
        "audit_event_count": len(ctx.audit_events),
    }

    session_store.archive_and_purge_session(
        session_id=session_id,
        purged_by=purged_by,
        session_summary=session_summary,
    )
    # 清缓存
    try:
        context_cache.delete(session_id, tenant_id)
    except Exception:
        pass  # cache miss 容忍
    session_store.log_event(
        session_id="purged:" + session_id,  # 占位 session_id（session_events 也 FK sessions，但允许写入失败）
        event_type="session_purged",
        stage=None,
        payload=session_summary,
    )
    return {"ok": True, "session_id": session_id, "purged": True, "summary": session_summary}
```

> `context_cache.delete` 需确认是否存在；若不存在，用 `context_cache.delete(session_id, tenant_id)` 或忽略。`session_store.log_event` 在会话已删除后会失败（FK 约束），用 try/except 容忍或直接不调用。

6. `api/routers/session.py` 新增 DELETE 端点：

```python
@router.delete(
    "/{session_id}",
    dependencies=[require_roles(Role.admin)],
)
def delete_session(
    session_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Admin 删除会话（审计事件归档保留，写 session_purged 处置事件）。"""
    try:
        return session_service.delete_session(
            session_id, purged_by=ctx.user_id or ctx.role, tenant_id=ctx.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

> `ctx.user_id` 字段需确认 `TenantContext` 中是否存在；若仅有 `tenant_id`/`role`，用 `ctx.role`。

7. `api/main.py` `/health` 端点追加留存配置：

```python
"audit_retention_days": settings.audit_retention_days,
"session_retention_days": settings.session_retention_days,
```

8. `.env.example` 在 T1.4 区块后追加：

```bash
# === Data Lifecycle (T1.6) ===
# Audit event retention in days (default 183 = 6 months, aligns with 等保)
AUDIT_RETENTION_DAYS=183
# Session retention in days (0 = forever)
SESSION_RETENTION_DAYS=0
```

9. `docs/compliance/backup.md`（新建）—— 备份指引文档：

```markdown
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
```

10. 测试 `tests/test_session_lifecycle.py`：
    - DELETE /sessions/{id} 非 admin 返回 403
    - DELETE 后会话不可再 GET（404）
    - DELETE 后 `audit_events_archive` 表含原会话所有审计事件 + 1 条 `session_purged` 事件
    - DELETE 后 `sessions`/`evidence_sources`/`safety_findings`/`report_artifacts` 等表对应记录已清空
    - `/health` 返回 `audit_retention_days` 与 `session_retention_days`

**验收**：删除端点有权限测试与级联测试；`/health` 暴露留存配置；备份章节入 docs。

**工作量**：M。

---

### T1.7 PIA 双层交付【依赖 T1.1-T1.4 设计定稿】

**改动文件**（纯文档）：
- `docs/compliance/pia-platform.md`（新建：平台自身 PIA）
- `docs/compliance/pia-template.md`（新建：用户使用模板）
- `docs/compliance/pia-university-mental-health.md`（新建：高敏场景实测评估）
- [docs/README.md](../README.md)（索引追加 docs/compliance/ 段落）

**内容大纲**：

1. **`pia-platform.md`** — 平台自身 PIA（工具方责任）：
   - 评估对象：本平台处理用户上传材料这一活动
   - PIPL 56 条三要素：
     - 目的合法性：AI 工作流预验尸分析，用户明示同意
     - 对个人权益的影响与风险：材料可能含 PII，流转到外部 LLM API（DeepSeek）
     - 保护措施与风险适配性：T1.3 字段加密 + T1.4 PII 掩码 + T1.1 数据分级 + T1.6 留存/删除
   - 数据流图：用户 → 平台 → DeepSeek API → 平台 → 报告
   - 跨境传输披露：DeepSeek API 调用涉及数据出境（PIPL 38-39 条）
   - 留存期限：审计 183 天，会话默认永久（可 admin 删除）
   - 复评触发：重大架构变更（如更换 LLM provider、新增数据字段）
   - 留存：3 年

2. **`pia-template.md`** — 用户使用模板：
   - 字段：项目名称、AI 系统描述、处理数据类型、数据来源、传输对象、留存期限、风险措施、责任人、复评日期
   - 占位符 + 填写指引

3. **`pia-university-mental-health.md`** — 高敏场景实测评估：
   - 用 `examples/university_ai_mental_health_input.md` 实际跑一遍流程，记录：
     - T1.2 修复后该场景升为 HIGH（实测证据）
     - T1.1 自动分级：`sensitive_personal`（PIPL 28 条双重敏感场景：未成年人/学生 + 心理健康）
     - T1.3 加密生效证据（context_json 中 user_materials 字段为密文）
     - T1.4 PII 检测（若示例输入含学号等）
     - 风险措施适配性评估：HIGH 风险档位要求 eval_coverage + redteam_coverage + trace_backfill
   - 结论：该场景是否可在本平台评估、需补充哪些保护措施

4. `docs/README.md` 在 `## spec/` 段后追加：

```markdown
## compliance/ — 合规文档

| 文档 | 说明 |
|------|------|
| [compliance/pia-platform.md](compliance/pia-platform.md) | 平台自身 PIA（PIPL 55/56 条评估，含材料→DeepSeek 数据流披露） |
| [compliance/pia-template.md](compliance/pia-template.md) | PIA 模板（用户填写用） |
| [compliance/pia-university-mental-health.md](compliance/pia-university-mental-health.md) | university_mental_health 场景实测 PIA 存档 |
| [compliance/incident-response.md](compliance/incident-response.md) | 数据泄露应急响应 checklist（T1.9 产物） |
| [compliance/backup.md](compliance/backup.md) | 生产部署备份指引（T1.6 产物） |
```

**验收**：三份文档存在且非模板占位；平台 PIA 覆盖 PIPL 56 条三要素；`university_mental_health` 评估含实测证据。

**工作量**：M（纯文档，但需要真实思考 + 跑一遍场景）。

---

### T1.8 CI 接入 SAST 与依赖审计【独立】

**改动文件**：
- [pyproject.toml](../../pyproject.toml)（ruff `select` 加 `S` + `per-file-ignores` 加 `tests/` 豁免 `S101`）
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)（lint job 追加 pip-audit 步骤）
- [Makefile](../../Makefile)（新增 `audit` target）
- `.github/workflows/codeql.yml`（新建，仓库公开后启用——本阶段先建文件，触发条件设为 `workflow_dispatch` 手动）
- 现有代码中存量 `S` 告警的逐条豁免注释（在 `# noqa: Sxxx` 形式或 `per-file-ignores` 集中豁免）

**具体改动**：

1. `pyproject.toml` ruff 配置（line 56-64）：

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "S"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
# Auth tests set env vars before imports (JWT_SECRET etc. must be set before module load).
"tests/test_auth.py" = ["E402", "I001"]
"tests/conftest.py" = ["E402"]
# tests 用 assert 是正常的，豁免 S101（assert 使用）
"tests/**" = ["S101"]
# mock_llm 模式下硬编码的 fake API key / secret，不构成真实泄露
"core/llm/adapters/mock.py" = ["S105", "S106"]
"core/llm/adapters/mock_fixtures/**" = ["S105", "S106"]
```

2. `.github/workflows/ci.yml` lint-and-unit-tests job（line 36-42 后）追加 pip-audit 步骤：

```yaml
      - name: Lint
        run: make lint

      - name: Dependency vulnerability audit (non-blocking)
        run: uv run pip-audit --strict
        continue-on-error: true   # 先告警不阻断，观察一轮后再评估升级

      - name: Unit tests (sqlite + mock)
        run: |
          cp -f .env.demo .env
          uv run pytest tests/ -v
```

3. `pyproject.toml` dev dependencies 追加 `pip-audit`：

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "pip-audit>=2.7.0",  # T1.8 依赖漏洞审计
]
```

4. `Makefile` 在 `lint:` target 后追加：

```makefile
# 依赖漏洞审计（非阻断）
audit:
	uv run pip-audit --strict

# SAST + 漏洞审计组合
security-check: lint audit
```

5. `.github/workflows/codeql.yml`（新建，仓库公开后启用）：

```yaml
name: codeql

on:
  workflow_dispatch:   # 阶段 1 先手动触发；仓库公开后改 push/PR + weekly cron
  schedule:
    - cron: '22 3 * * 1'  # 每周一 03:22 UTC

permissions:
  contents: read
  security-events: write   # CodeQL 需要写 security events

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: python
      - uses: github/codeql-action/analyze@v3
        with:
          category: "/language:python"
```

6. 存量 `S` 告警清零或豁免：执行 `make lint` 后逐条处理。常见模式：
   - `S101`（assert 使用）：tests/ 已集中豁免
   - `S105`/`S106`（硬编码密码）：mock 模式豁免，真实密码用环境变量
   - `S301`（pickle 反序列化）：若 mock 夹具用 pickle，加 `# noqa: S301` + 注释说明
   - `S603`/`S605`（subprocess 调用）：`postgres.py:41` 的 alembic 调用加 `# noqa: S603` + 注释说明输入受控
   - `S311`（伪随机数）：测试用 random 不影响安全，豁免

**验收**：
- `make lint` 通过（含 `S` 规则）；
- CI 真实跑出 SAST/pip-audit 结果（哪怕暂不 block 合并）；
- 存量 `S` 告警清零或逐条豁免注释。

**工作量**：M（存量告警处理是大头）。

---

### T1.9 数据泄露应急响应流程【独立】

**改动文件**：
- `docs/compliance/incident-response.md`（新建）
- [SECURITY.md](../../SECURITY.md)（追加"应急响应"段落 + 互链）

**`docs/compliance/incident-response.md` 内容**：

```markdown
# 数据泄露应急响应 Checklist

> 适用范围：本平台（ai-workflow-premortem）发生或疑似发生数据泄露事件。
> 互链：[../SECURITY.md](../SECURITY.md)（漏洞报告渠道）。
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
```

**`SECURITY.md` 末尾追加**：

```markdown
## 应急响应

发生或疑似发生数据泄露事件时，按 [docs/compliance/incident-response.md](docs/compliance/incident-response.md) 的 checklist 处置。
```

**验收**：文档存在；操作项与本项目实际架构对应（能指到具体的配置/表/端点）；与 SECURITY.md 互链。

**工作量**：S。

---

## 3. 执行顺序与并行策略（Subagent-Driven）

### 依赖关系

```
Wave 1（4 个任务互相独立，可并行 subagent）：
  T1.2 风险关键词修正（core/gates/risk_profile.py + tests）
  T1.5 AI 标识补强（core/report_service.py + tests）
  T1.8 CI SAST + pip-audit（pyproject.toml + ci.yml + Makefile + codeql.yml）
  T1.9 应急响应 checklist（docs/compliance/incident-response.md + SECURITY.md）

Wave 2（基础任务，Wave 1 完成后单独执行）：
  T1.1 数据分类分级（core/models.py + migrations + session_service + router + tests）

Wave 3（高风险任务，T1.1 完成后单独执行）：
  T1.3 存储层加密（storage/field_security.py + 两后端 + config + pyproject + .env + tests）
  → 必须先在 SQLite lite 模式全量回归，再验证 PostgreSQL

Wave 4（T1.3 完成后执行，共享 config.py）：
  T1.4 PII 检测与掩码（tools/safety_classifier.py + evidence_service + config + .env + tests）

Wave 5（T1.4 完成后并行）：
  T1.6 数据生命周期（alembic V004 + 两后端 + router + session_service + main + docs/backup.md）
  T1.7 PIA 文档（docs/compliance/pia-*.md + docs/README.md）— 纯文档，可与 T1.6 并行

Wave 6（全部任务完成后）：
  集成验证、更新 STATE.md / CHANGELOG / docs/README、打 tag
```

### 文件冲突分析（并行安全前提）

| 任务 | 改动文件 | 冲突风险 |
|------|----------|----------|
| T1.2 | `core/gates/risk_profile.py`, `tests/test_risk_profile_mental_health.py` | 无 |
| T1.5 | `core/report_service.py`, `tests/test_report_ai_notice.py` | 无 |
| T1.8 | `pyproject.toml`, `.github/workflows/ci.yml`, `Makefile`, `.github/workflows/codeql.yml` | 无 |
| T1.9 | `docs/compliance/incident-response.md`, `SECURITY.md` | 无 |
| T1.1 | `core/models.py`, `core/migrations/*`, `core/session_service.py`, `api/routers/session.py`, `api/schemas.py`, `tests/test_data_classification.py` | 无 |
| T1.3 | `storage/field_security.py`, `storage/backends/postgres.py`, `storage/backends/sqlite_store.py`, `core/config.py`, `pyproject.toml`, `.env.example`, `tests/test_field_encryption.py` | ⚠️ `pyproject.toml` 与 T1.8 改动同文件 |
| T1.4 | `tools/safety_classifier.py`, `core/evidence_service.py`, `core/config.py`, `.env.example`, `tests/test_pii_detection.py` | ⚠️ `core/config.py` / `.env.example` 与 T1.3 改动同文件 |
| T1.6 | `alembic/versions/V004_audit_archive.py`, `storage/backends/postgres.py`, `storage/backends/sqlite_store.py`, `core/config.py`, `api/routers/session.py`, `core/session_service.py`, `api/main.py`, `docs/compliance/backup.md`, `.env.example`, `tests/test_session_lifecycle.py` | ⚠️ `storage/backends/*` / `core/config.py` / `api/routers/session.py` / `core/session_service.py` / `.env.example` 与 T1.1/T1.3/T1.4 改动同文件 |
| T1.7 | `docs/compliance/pia-*.md`, `docs/README.md` | ⚠️ `docs/README.md` 与 T1.9 改动同文件（但 T1.9 不改 README） |

**冲突缓解策略**：
- **Wave 1 内 4 任务文件级无冲突**，可安全并行。
- **Wave 3、Wave 4 串行执行**：T1.3 完成提交后再启动 T1.4，避免 `core/config.py` 与 `.env.example` 的合并冲突。
- **Wave 5 内 T1.6 与 T1.7 可并行**：T1.6 改 storage/api，T1.7 改 docs，文件级无交集。
- 每个 Wave 完成后**显式 `git add <file>` + commit**，再启动下一个 Wave，便于回滚。

### Subagent 分工建议

| Wave | Agent | 负责任务 | 改动文件 |
|------|-------|----------|----------|
| 1 | Agent A | T1.2 + T1.5 | `core/gates/risk_profile.py`, `core/report_service.py`, tests |
| 1 | Agent B | T1.8 | `pyproject.toml`, `.github/workflows/ci.yml`, `Makefile`, `.github/workflows/codeql.yml` |
| 1 | Agent C | T1.9 | `docs/compliance/incident-response.md`, `SECURITY.md` |
| 2 | Agent D | T1.1 | `core/models.py`, `core/migrations/*`, `core/session_service.py`, `api/routers/session.py`, `api/schemas.py`, tests |
| 3 | Agent E | T1.3 | `storage/field_security.py`, `storage/backends/*`, `core/config.py`, `pyproject.toml`, `.env.example`, tests |
| 4 | Agent F | T1.4 | `tools/safety_classifier.py`, `core/evidence_service.py`, `core/config.py`, `.env.example`, tests |
| 5 | Agent G | T1.6 | `alembic/V004`, `storage/backends/*`, `api/routers/session.py`, `core/session_service.py`, `api/main.py`, `docs/compliance/backup.md`, tests |
| 5 | Agent H | T1.7 | `docs/compliance/pia-*.md`, `docs/README.md` |
| 6 | Agent I | 收尾 | `.upgrade/STATE.md`, `CHANGELOG.md`, `docs/README.md`, validation, git tag |

**执行后统一校验**（每 Wave 结束）：
- `git status --short` 检查改动范围
- `make lint && make test && make version-check` 三步全绿
- 提交策略：按 AGENTS.md 要求显式 `git add <file>`，**禁用** `git add .`；每任务一个 commit

---

## 4. 风险与注意事项

| 风险 | 来源 | 缓解 |
|------|------|------|
| T1.3 加密失败导致 save 全部失败 | storage 主路径改动 | `_encrypt_value` 在 fernet 为 None 时跳过；fernet 实例化失败应抛错以便发现（不应静默） |
| T1.3 密钥丢失 = 数据不可读 | Fernet 对称加密特性 | `.env.example` + `docs/compliance/backup.md` 写清密钥备份责任；`/health` 暴露 `data_encryption: enabled/disabled` |
| T1.3 与 T1.4 共改 `core/config.py` / `.env.example` | 文件级冲突 | Wave 3、Wave 4 串行执行，每 Wave 完成后 commit |
| T1.4 PII 检测在 LLM 输出中误报 | `scan_text` 通用入口 | PII 检测仅对 `location.startswith(("user_materials", "evidence_source"))` 启用 |
| T1.4 掩码开关默认关闭 | 刻意设计 | 先让检测跑起来积累误报数据，再决定是否默认开启；spec 4.2 节已说明 |
| T1.6 与现有 `audit_events` FK CASCADE 冲突 | schema 设计矛盾 | 新增 `audit_events_archive` 表（无 FK），删除前归档；alembic V004 + SQLite DDL 双写 |
| T1.6 `session_store.log_event` 在会话删除后失败 | `session_events` 也 FK sessions | 用 try/except 容忍或直接不调用 |
| T1.8 存量 `S` 告警数量未知 | ruff `S` 规则集启用 | 先在 Wave 1 跑一次 `make lint` 统计告警数，预估工作量；告警逐条 `# noqa: Sxxx` + 注释说明 |
| T1.8 pip-audit 发现未修复漏洞 | 上游依赖未发版 | `continue-on-error: true` 先告警不阻断；记录到 `.upgrade/reports/pip-audit-<date>.md` + 复查日期 |
| `university_mental_health` 场景升级后门控变严 | T1.2 修复 + T1.1 联动 | 修复后 HIGH 档要求 eval_coverage + redteam_coverage + trace_backfill；场景演示流程需同步更新（不阻塞本阶段） |
| 路线图 3.5 节错误描述未订正 | T1.2 修复后事实变化 | T1.2 完成后在 `improvement-roadmap.md` 3.5 节订正（追加"2026-07-14 修订"说明） |

---

## 5. 验收清单（对齐实施计划 §6，补充实测校验点）

- [ ] `university_mental_health` 场景实测升为 HIGH 及以上（`tests/test_risk_profile_mental_health.py` 通过）
- [ ] 数据分级字段生效且有覆写审计（`tests/test_data_classification.py` 通过；PATCH 端点降级产 AuditEvent）
- [ ] 存储层敏感字段加密在代码里生效（`tests/test_field_encryption.py` 通过；sqlite3 CLI 查 `context_json` 字段为密文）
- [ ] PII 检测 finding 可产出；掩码开关可用（`tests/test_pii_detection.py` 通过；`PII_MASK_BEFORE_LLM=true` 时 prompt 中 PII 掩码）
- [ ] 报告首屏中文 AI 标识可见（`tests/test_report_ai_notice.py` 通过；导出 Markdown 前 10 行含"本报告由 AI 辅助生成"）
- [ ] PIA 三份文档存档（`docs/compliance/pia-platform.md` / `pia-template.md` / `pia-university-mental-health.md`）
- [ ] CI 中 SAST + pip-audit 真实运行有结果（CI workflow 运行记录可见；本地 `make lint` 含 `S` 规则通过）
- [ ] 泄露应急响应 checklist 与会话删除能力就位（`docs/compliance/incident-response.md` 存在；`DELETE /sessions/{id}` 端点测试通过；`audit_events_archive` 表存在）
- [ ] **（新增）** `/health` 暴露 `data_encryption` / `audit_retention_days` / `session_retention_days`
- [ ] **（新增）** `docs/compliance/` 目录建立，`docs/README.md` 索引追加
- [ ] **（新增）** 路线图 3.5 节订正（`university_mental_health` 修复说明）
- [ ] **（新增）** `make lint && make test && make version-check` 三步全绿
- [ ] **（新增）** `.upgrade/STATE.md` 更新为 Phase 1 complete
- [ ] **（新增）** `CHANGELOG.md` 追加 v1.0.3 版本条目
- [ ] **（新增）** `core/version.py` / `pyproject.toml` / `README.md` 版本号 bump 到 1.0.3，打 git tag `v1.0.3`

---

## 6. 需用户决策项

1. **是否授权启动执行**：按本设计方案 Subagent-Driven 推进 6 个 Wave（Wave 1 四任务并行 → Wave 2 T1.1 → Wave 3 T1.3 → Wave 4 T1.4 → Wave 5 T1.6+T1.7 并行 → Wave 6 收尾）。
2. **PII_MASK_BEFORE_LLM 默认值**：保持 `false`（spec 4.2 节建议，先积累误报数据）还是改为 `true`（更保守但可能影响演示流畅度）？
3. **T1.8 pip-audit 阻断策略**：阶段 1 先 `continue-on-error: true`（不阻断，观察一轮）还是直接阻断（更严格但可能被上游未修复漏洞卡死）？

> 决策项 1 阻塞所有任务；决策项 2、3 不阻塞 Wave 1-2 启动，但影响 Wave 4 与 Wave 5 的具体实现。
