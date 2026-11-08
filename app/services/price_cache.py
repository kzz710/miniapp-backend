"""车价结果持久化缓存（SQLite/MySQL）。

内存缓存命中时最快，但进程重启即失效；这里把结果同时落库，
保证部署/重启后热门车型仍能直接命中，不必重新联网取价。
"""
import json
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import PriceCache, utcnow
from app.types import CarPrice


def get_cached(db: Session, keyword: str) -> list[CarPrice] | None:
    """读取未过期的缓存；过期不删，留给 get_stale_cached 作降级。"""
    row = db.get(PriceCache, keyword)
    if row is None:
        return None

    if row.expires_at <= utcnow():
        return None

    try:
        raw = json.loads(row.payload)
        return [CarPrice(**item) for item in raw]
    except Exception:
        return None


def get_stale_cached(db: Session, keyword: str) -> list[CarPrice] | None:
    """读取库里已有缓存（含过期），供 live 超时后立刻返回。"""
    row = db.get(PriceCache, keyword)
    if row is None:
        return None
    try:
        raw = json.loads(row.payload)
        return [CarPrice(**item) for item in raw]
    except Exception:
        return None


def set_cached(db: Session, keyword: str, cars: list[CarPrice], ttl: int) -> None:
    """写入缓存，并顺带清理过期记录。"""
    payload = json.dumps([car.model_dump() for car in cars], ensure_ascii=False)

    row = db.get(PriceCache, keyword)
    if row is None:
        row = PriceCache(keyword=keyword)
        db.add(row)
    row.payload = payload
    row.expires_at = utcnow() + timedelta(seconds=ttl)

    db.execute(delete(PriceCache).where(PriceCache.expires_at <= utcnow()))
    db.commit()
