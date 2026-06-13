# tests/test_storage.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("redis")

from core.models import ProjectContext


class TestContextCache:
    """Redis 缓存测试（Mock Redis）"""

    @patch("storage.cache.redis.from_url")
    def test_set_and_get(self, mock_redis_factory):
        mock_client = MagicMock()
        mock_redis_factory.return_value = mock_client

        from storage.cache import ContextCache

        cache = ContextCache()

        ctx = ProjectContext()
        ctx.research_target = "测试对象"

        # 测试 set
        cache.set(ctx)
        mock_client.setex.assert_called_once()

        # 测试 get（返回序列化后的数据）
        mock_client.get.return_value = ctx.model_dump_json()
        restored = cache.get(ctx.session_id)
        assert restored is not None
        assert restored.research_target == "测试对象"

    @patch("storage.cache.redis.from_url")
    def test_redis_failure_does_not_raise(self, mock_redis_factory):
        """Redis 故障时应静默降级，不抛出异常"""
        import redis

        mock_client = MagicMock()
        mock_client.setex.side_effect = redis.RedisError("连接失败")
        mock_redis_factory.return_value = mock_client

        from storage.cache import ContextCache

        cache = ContextCache()
        ctx = ProjectContext()

        # 不应抛出异常
        cache.set(ctx)

    @patch("storage.cache.redis.from_url")
    def test_get_returns_none_on_miss(self, mock_redis_factory):
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_redis_factory.return_value = mock_client

        from storage.cache import ContextCache

        cache = ContextCache()
        result = cache.get("nonexistent-session-id")
        assert result is None
