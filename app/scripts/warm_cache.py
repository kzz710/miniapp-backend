"""预热热门车型车价缓存。

用法（在项目目录、激活 venv 后）：
    python -m app.scripts.warm_cache

建议由 systemd timer 每天低峰期执行一次；TTL 为 24h，正好覆盖一天。
"""
import asyncio

from app.db.session import SessionLocal, init_db
from app.services.car_price import get_car_price
from app.services.search_stats import HOT_LIMIT, hot_keywords


async def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        keywords = hot_keywords(db, HOT_LIMIT)
        print(f"[warm] 目标车型（{len(keywords)}）：{keywords}", flush=True)
        ok = 0
        for keyword in keywords:
            try:
                # 强制刷新，避免命中旧缓存导致“预热”实际没更新
                result = await get_car_price(keyword, db, force_refresh=True)
                print(
                    f"[warm] {keyword} -> {result.source} / {len(result.options)} 个版本",
                    flush=True,
                )
                if result.source == "live":
                    ok += 1
            except Exception as exc:
                print(f"[warm] {keyword} 失败：{type(exc).__name__}: {exc}", flush=True)
        print(f"[warm] 完成：{ok}/{len(keywords)} 个车型实时刷新成功", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
