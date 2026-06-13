# api/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import settings

# SQLite/lite mode has no Redis — fall back to in-process memory storage.
_storage_uri = "memory://" if settings.storage_backend == "sqlite" else settings.redis_url

limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri)
