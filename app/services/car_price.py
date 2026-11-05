"""车价查询编排：内存缓存 -> 数据库缓存 -> 实时 RAG -> 示例库兜底。"""
from sqlalchemy.orm import Session

from app import config
from app.services.llm import fetch_live_prices
from app.services.price_cache import get_cached, set_cached
from app.services.sample_cars import find_sample
from app.services.search_stats import normalize_keyword
from app.types import CarPrice, CarPriceResult
from app.utils.cache import cache
from app.utils.validate import validate_price


async def get_car_price(
    keyword: str,
    db: Session,
    force_refresh: bool = False,
) -> CarPriceResult:
    """查询车型价格，按 内存缓存 -> DB 缓存 -> 实时 -> 示例库 顺序降级。

    force_refresh=True 时跳过两层缓存，强制联网取价（供缓存预热使用）。
    返回该车型全部版本（options），data 取 options[0] 作为默认推荐版本。
    """
    kw = normalize_keyword(keyword)
    if not kw:
        return CarPriceResult(data=None, options=[], source="none", note="车型关键词不能为空")

    if not force_refresh:
        # 1) 内存缓存（进程内，最快）
        cached = cache.get(kw)
        if isinstance(cached, list) and cached:
            valid = [c for c in cached if validate_price(c)]
            if valid:
                return CarPriceResult(data=valid[0], options=valid, source="cache")

        # 2) 数据库缓存（重启/部署后仍有效）
        persisted = get_cached(db, kw)
        if persisted:
            valid = [c for c in persisted if validate_price(c)]
            if valid:
                cache.set(kw, valid, ttl=config.CACHE_TTL)
                return CarPriceResult(data=valid[0], options=valid, source="cache")

    # 3) 实时检索增强（仅在配置了 key 时），返回全部版本
    if config.live_mode():
        cars: list[CarPrice] = await fetch_live_prices(kw) or []
        cars = [c for c in cars if validate_price(c)]
        if cars:
            cache.set(kw, cars, ttl=config.CACHE_TTL)
            try:
                set_cached(db, kw, cars, config.CACHE_TTL)
            except Exception:
                # 缓存落库失败不影响本次返回
                db.rollback()
            return CarPriceResult(data=cars[0], options=cars, source="live")

    # 4) 示例库兜底（标注为参考值）
    sample = find_sample(kw)
    if sample:
        return CarPriceResult(
            data=sample,
            options=[sample],
            is_reference=True,
            source="sample",
            note="当前为内置示例价（参考值），接入实时检索后将返回实时报价",
        )

    return CarPriceResult(data=None, options=[], source="none", note="未找到该车型，请尝试更具体的品牌+车型，如「比亚迪 海豹」")
