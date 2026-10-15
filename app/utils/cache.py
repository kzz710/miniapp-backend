"""极简线程安全 TTL 内存缓存（MVP 用，生产可换 Redis）。"""
import threading
import time
from typing import Any, Optional


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, Optional[float]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            value, exp = item
            if exp is not None and exp < time.time():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            exp = time.time() + ttl if ttl else None
            self._store[key] = (value, exp)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


cache = TTLCache()
