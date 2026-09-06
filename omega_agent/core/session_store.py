"""Pluggable session storage for API / interactive mode (multi-user)."""

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("omega_agent.core.session_store")


class SessionStore(ABC):
    @abstractmethod
    def get(self, session_id: str, tenant_id: str = "default") -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def set(self, session_id: str, data: Dict[str, Any], tenant_id: str = "default") -> None:
        ...

    @abstractmethod
    def delete(self, session_id: str, tenant_id: str = "default") -> None:
        ...

    def _key(self, tenant_id: str, session_id: str) -> str:
        return f"omega:session:{tenant_id}:{session_id}"


class InMemorySessionStore(SessionStore):
    """Thread-safe in-process store — fine for single node, not for multi-replica."""

    def __init__(self, ttl_seconds: int = 86400):
        self._lock = threading.RLock()
        self._data: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._ttl = ttl_seconds

    def get(self, session_id: str, tenant_id: str = "default") -> Optional[Dict[str, Any]]:
        key = self._key(tenant_id, session_id)
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            payload, ts = entry
            if time.time() - ts > self._ttl:
                del self._data[key]
                return None
            return dict(payload)

    def set(self, session_id: str, data: Dict[str, Any], tenant_id: str = "default") -> None:
        key = self._key(tenant_id, session_id)
        with self._lock:
            self._data[key] = (dict(data), time.time())

    def delete(self, session_id: str, tenant_id: str = "default") -> None:
        key = self._key(tenant_id, session_id)
        with self._lock:
            self._data.pop(key, None)


class RedisSessionStore(SessionStore):
    """Shared session store for horizontal scaling (requires redis package)."""

    def __init__(self, url: str, ttl_seconds: int = 86400):
        try:
            import redis
        except ImportError as e:
            raise ImportError("pip install redis") from e
        self._client = redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds

    def get(self, session_id: str, tenant_id: str = "default") -> Optional[Dict[str, Any]]:
        raw = self._client.get(self._key(tenant_id, session_id))
        if not raw:
            return None
        return json.loads(raw)

    def set(self, session_id: str, data: Dict[str, Any], tenant_id: str = "default") -> None:
        self._client.setex(
            self._key(tenant_id, session_id),
            self._ttl,
            json.dumps(data),
        )

    def delete(self, session_id: str, tenant_id: str = "default") -> None:
        self._client.delete(self._key(tenant_id, session_id))


def create_session_store(redis_url: Optional[str] = None, ttl_seconds: int = 86400) -> SessionStore:
    if redis_url:
        try:
            return RedisSessionStore(redis_url, ttl_seconds=ttl_seconds)
        except Exception as e:
            logger.warning("Redis session store unavailable (%s); using in-memory", e)
    return InMemorySessionStore(ttl_seconds=ttl_seconds)
