"""车价查询编排：缓存 -> 实时 RAG -> 示例库兜底。"""
from typing import Optional

from app import config
from app.types import CarPrice, CarPriceResult
from app.utils.cache import cache
from app.utils.validate import validate_price
from app.services.llm import fetch_live_prices
from app.services.sample_cars import find_sample


async def get_car_price(keyword: str) -> CarPriceResult:
    """查询车型价格，按 缓存 -> 实时 -> 示例库 顺序降级。

    返回该车型全部版本（options），data 取 options[0] 作为默认推荐版本。
    """
    kw = (keyword or "").strip()
    if not kw:
        return CarPriceResult(data=None, options=[], source="none", note="车型关键词不能为空")

    # 1) 缓存（热门车型 TTL 内直接返回；缓存内容为版本列表）
    cached = cache.get(kw)
    if isinstance(cached, list) and cached:
        valid = [c for c in cached if validate_price(c)]
        if valid:
            return CarPriceResult(data=valid[0], options=valid, source="cache")

    # 2) 实时检索增强（仅在配置了 key 时），返回全部版本
    if config.live_mode():
        cars: list[CarPrice] = await fetch_live_prices(kw) or []
        cars = [c for c in cars if validate_price(c)]
        if cars:
            cache.set(kw, cars, ttl=config.CACHE_TTL)
            return CarPriceResult(data=cars[0], options=cars, source="live")

    # 3) 示例库兜底（标注为参考值）
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
