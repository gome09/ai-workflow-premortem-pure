"""连接池契约：池大小与排队超时必须来自 settings，而不是硬编码。"""

from __future__ import annotations

from core.config import settings
from storage.backends import postgres as pg


def test_pool_uses_configured_size_and_timeout(monkeypatch):
    captured: dict[str, object] = {}

    class _Pool:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(pg, "ConnectionPool", _Pool)
    store = pg.PostgresSessionStore()
    store._get_pool()

    assert captured["min_size"] == settings.db_pool_min_size
    assert captured["max_size"] == settings.db_pool_max_size
    assert captured["timeout"] == settings.db_pool_timeout_seconds
    assert captured["open"] is True
