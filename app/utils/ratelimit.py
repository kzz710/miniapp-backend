"""极简内存限流（MVP 用）。

多 worker 不共享计数，生产可替换为 Redis；limit <= 0 表示不限制。
"""
import time

from fastapi import Request

from app.utils.cache import cache


def client_ip(request: Request) -> str:
    """取真实客户端 IP：优先 X-Forwarded-For（nginx 已设置），回退到直连地址。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit(key: str, limit: int, window_seconds: int = 60) -> bool:
    """记一次访问；返回 True 表示已超过限制。"""
    if limit <= 0:
        return False
    now = time.time()
    entry = cache.get(key)
    if not isinstance(entry, dict) or entry.get("reset", 0) <= now:
        cache.set(key, {"count": 1, "reset": now + window_seconds}, ttl=window_seconds + 5)
        return False
    entry["count"] = int(entry.get("count", 0)) + 1
    return entry["count"] > limit
