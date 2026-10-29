# storage/access.py
"""内部系统访问哨兵 — 无请求上下文的跨租户通道。

`load` / `delete` / `list_sessions` 在 tenant 为空时默认拒绝。启动补偿、
429 审计等内部路径确实需要读取任意会话，但布尔开关 `system=True` 无法
区分"有意开启"和"误传真值"：任何上游把配置或参数透传进来都可能静默
绕过租户边界。

因此内部通道改为显式哨兵 `SYSTEM_ACCESS`：
- 只有一个合法实例（Enum 成员，无法伪造、无法外部构造）；
- 每次合法使用都写 warning 级日志，留下可审计痕迹；
- 传入任何非哨兵值（包括 `True`）都按越权拒绝。
"""

from __future__ import annotations

import enum
import logging

from storage.errors import TenantIsolationError

logger = logging.getLogger(__name__)


class SystemAccess(enum.Enum):
    """内部访问标记；唯一合法实例为模块级 `SYSTEM_ACCESS`。"""

    SYSTEM = enum.auto()


SYSTEM_ACCESS = SystemAccess.SYSTEM


def resolve_system_access(
    access: SystemAccess | None, *, operation: str, session_id: str = ""
) -> bool:
    """校验内部访问哨兵，返回是否已授予内部访问。

    Raises:
        TenantIsolationError: 传入了非哨兵值（例如误传的 `True`）。
    """
    if access is None:
        return False
    if access is not SYSTEM_ACCESS:
        raise TenantIsolationError(session_id, operation)
    logger.warning(
        "Internal system access granted: operation=%s session_id=%s",
        operation,
        session_id or "<all>",
    )
    return True
