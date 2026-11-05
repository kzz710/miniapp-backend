"""热门车型统计与车价持久化缓存测试。"""
import asyncio

from fastapi.testclient import TestClient

from app import config as app_config
from app.main import app
from app.services import car_price as cp
from app.types import CarPrice
from app.utils.cache import cache
from app.utils.helpers import now_iso

client = TestClient(app)


def _car(config: str = "标准版") -> CarPrice:
    return CarPrice(
        car_id=f"test-{config}",
        brand="测试品牌",
        model="测试车",
        config=config,
        guide_price=10.0,
        ref_discount_price=9.0,
        energy_type="gas",
        fuel_consumption=6.0,
        power_consumption=0.0,
        source="test",
        fetched_at=now_iso(),
    )


def test_hot_keywords_sorted_by_search_count_and_padded():
    for keyword in ["比亚迪 海豹", "特斯拉 Model 3", "比亚迪 海豹"]:
        client.post("/api/queryCarPrice", json={"keyword": keyword})

    items = client.get("/api/hotKeywords").json()["items"]

    assert len(items) == 5
    assert items[0] == "比亚迪 海豹"
    assert "特斯拉 Model 3" in items
    assert len(set(items)) == 5


def test_hot_keywords_normalizes_whitespace():
    client.post("/api/queryCarPrice", json={"keyword": "  比亚迪   海豹  "})

    items = client.get("/api/hotKeywords").json()["items"]

    assert "比亚迪 海豹" in items
    assert all("  " not in item for item in items)


def test_price_cache_persists_after_memory_clear(monkeypatch):
    calls = {"count": 0}

    async def fake_live(_keyword: str, timeout: int = 50):
        calls["count"] += 1
        return [_car("标准版"), _car("高配版")]

    monkeypatch.setattr(cp, "fetch_live_prices", fake_live)
    monkeypatch.setattr(app_config, "live_mode", lambda: True)

    first = client.post("/api/queryCarPrice", json={"keyword": "缓存测试车"})
    assert first.json()["source"] == "live"
    assert len(first.json()["options"]) == 2

    # 模拟服务重启：内存缓存清空，但数据库缓存应仍然有效
    cache.clear()

    second = client.post("/api/queryCarPrice", json={"keyword": "缓存测试车"})
    assert second.json()["source"] == "cache"
    assert len(second.json()["options"]) == 2
    assert calls["count"] == 1


def test_background_refresh_writes_cache(monkeypatch, session_factory):
    async def fake_live(_keyword: str, timeout: int = 180):
        return [_car("标准版")]

    monkeypatch.setattr(cp, "fetch_live_prices", fake_live)
    monkeypatch.setattr(app_config, "live_mode", lambda: True)
    monkeypatch.setattr(cp, "SessionLocal", session_factory)

    # 模拟“本次查询超时”，后台任务用更长超时补取并写缓存
    asyncio.run(cp.refresh_cache_in_background("后台刷新车"))
    cache.clear()

    hit = client.post("/api/queryCarPrice", json={"keyword": "后台刷新车"})
    assert hit.json()["source"] == "cache"
    assert len(hit.json()["options"]) == 1
