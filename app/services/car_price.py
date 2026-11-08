"""车价查询编排：内存缓存 -> 数据库缓存 -> 实时 RAG -> 过期缓存/示例库兜底。"""
import asyncio

from sqlalchemy.orm import Session

from app import config
from app.db.session import SessionLocal
from app.services.llm import fetch_live_prices
from app.services.price_cache import get_cached, get_stale_cached, set_cached
from app.services.sample_cars import find_sample
from app.services.search_stats import normalize_keyword
from app.types import CarPrice, CarPriceResult
from app.utils.cache import cache
from app.utils.validate import validate_price

# 线上同步等待上限：默认 14s，墙钟目标 ≤15s（含框架开销）
DEFAULT_LIVE_TIMEOUT = 14


async def get_car_price(
    keyword: str,
    db: Session,
    force_refresh: bool = False,
    live_timeout: int = DEFAULT_LIVE_TIMEOUT,
) -> CarPriceResult:
    """查询车型价格，按 内存缓存 -> DB 缓存 -> 实时 -> 过期缓存 -> 示例库 顺序降级。

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

    live_attempted = False
    # 3) 实时检索增强（仅在配置了 key 时），返回全部版本
    if config.live_mode():
        live_attempted = True
        cars: list[CarPrice] = []
        try:
            cars = await asyncio.wait_for(
                fetch_live_prices(kw, timeout=live_timeout),
                timeout=live_timeout,
            ) or []
        except asyncio.TimeoutError:
            print(f"[car_price] live 超时 {live_timeout}s：{kw}", flush=True)
            cars = []
        except Exception as e:
            print(f"[car_price] live 异常：{type(e).__name__}: {e}", flush=True)
            cars = []
        cars = [c for c in cars if validate_price(c)]
        if cars:
            cache.set(kw, cars, ttl=config.CACHE_TTL)
            try:
                set_cached(db, kw, cars, config.CACHE_TTL)
            except Exception:
                db.rollback()
            return CarPriceResult(data=cars[0], options=cars, source="live")

    # 4) 过期/已有 DB 缓存（live 失败时立刻返回；上层会 schedule_refresh）
    if not force_refresh:
        stale = get_stale_cached(db, kw)
        if stale:
            valid = [c for c in stale if validate_price(c)]
            if valid:
                cache.set(kw, valid, ttl=min(300, config.CACHE_TTL))
                return CarPriceResult(
                    data=valid[0],
                    options=valid,
                    is_reference=True,
                    source="cache",
                    note="当前为缓存报价，正在后台更新最新价",
                )

    # 5) 示例库兜底（标注为参考值）
    sample = find_sample(kw)
    if sample:
        note = (
            "当前为内置示例价（参考值），正在后台更新最新报价"
            if live_attempted
            else "当前为内置示例价（参考值），接入实时检索后将返回实时报价"
        )
        return CarPriceResult(
            data=sample,
            options=[sample],
            is_reference=True,
            source="sample",
            note=note,
        )

    return CarPriceResult(
        data=None,
        options=[],
        source="none",
        note="未找到该车型，请尝试更具体的品牌+车型，如「比亚迪 海豹」",
    )


# 后台刷新：本次查询超时/未命中时，用更长超时继续取价并写入缓存。
_refreshing: set[str] = set()
_refresh_tasks: set[asyncio.Task] = set()


async def refresh_cache_in_background(keyword: str) -> None:
    kw = normalize_keyword(keyword)
    if not kw or kw in _refreshing:
        return

    _refreshing.add(kw)
    db = SessionLocal()
    try:
        await get_car_price(kw, db, force_refresh=True, live_timeout=180)
    except Exception:
        pass
    finally:
        db.close()
        _refreshing.discard(kw)


def schedule_refresh(keyword: str) -> None:
    """把关键词放进后台刷新队列，不阻塞当前请求。"""
    task = asyncio.create_task(refresh_cache_in_background(keyword))
    _refresh_tasks.add(task)
    task.add_done_callback(_refresh_tasks.discard)
