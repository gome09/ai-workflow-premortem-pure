# storage/cache.py
from __future__ import annotations

import logging

import redis

from core.config import settings
from core.models import ProjectContext

logger = logging.getLogger(__name__)

CONTEXT_TTL = settings.session_ttl_hours * 3600


class ContextCache:
    """
    Redis 热上下文缓存。
    活跃会话的 ProjectContext 存在 Redis，减少 PG 读写频率。
    会话超时或服务重启后，从 PG 恢复。
    """

    def __init__(self):
        self._client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )

    def _key(self, session_id: str) -> str:
        return f"session:ctx:{session_id}"

    def set(self, ctx: ProjectContext) -> None:
        try:
            self._client.setex(
                self._key(ctx.session_id),
                CONTEXT_TTL,
                ctx.model_dump_json(),
            )
        except redis.RedisError as e:
            # Redis 故障不应阻断主流程，降级到纯 PG 模式
            logger.warning(f"Redis set failed, degrading to PG-only: {e}")

    def get(self, session_id: str) -> ProjectContext | None:
        try:
            raw = self._client.get(self._key(session_id))
            if not raw:
                return None
            return ProjectContext.model_validate_json(raw)
        except redis.RedisError as e:
            logger.warning(f"Redis get failed: {e}")
            return None

    def delete(self, session_id: str) -> None:
        try:
            self._client.delete(self._key(session_id))
        except redis.RedisError as e:
            logger.warning(f"Redis delete failed: {e}")

    def refresh_ttl(self, session_id: str) -> None:
        """刷新活跃会话的 TTL"""
        try:
            self._client.expire(self._key(session_id), CONTEXT_TTL)
        except redis.RedisError as e:
            logger.warning(f"Redis expire failed: {e}")


# 全局单例
context_cache = ContextCache()
