"""接口集成测试：用 TestClient 验证两个核心接口与降级逻辑。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_query_car_price_sample_fallback():
    # 离线 Mock 下应命中示例库兜底
    r = client.post("/api/queryCarPrice", json={"keyword": "比亚迪 海豹"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"] is not None
    assert body["data"]["brand"] == "比亚迪"
    assert body["source"] in ("sample", "cache", "live")


def test_query_car_price_empty():
    r = client.post("/api/queryCarPrice", json={"keyword": ""})
    assert r.status_code == 200
    assert r.json()["data"] is None


def test_query_car_price_live_fetch_returns_none_does_not_500(monkeypatch):
    """回归：实时取价失败返回 None 时，必须优雅降级而非 500。"""
    import app.services.car_price as cp
    from app import config

    async def _none(*a, **k):
        return None

    monkeypatch.setattr(cp, "fetch_live_prices", _none)
    monkeypatch.setattr(config, "live_mode", lambda: True)
    # 该关键词不在示例库，触发 live=None -> 应走 none 兜底且 HTTP 200
    r = client.post("/api/queryCarPrice", json={"keyword": "长安启源Q06"})
    assert r.status_code == 200
    assert r.json()["source"] == "none"


def test_calc_plan_full():
    r = client.post(
        "/api/calcPlan",
        json={
            "price": 17.5,
            "mode": "full",
            "income": 2.0,
            "monthly_expense": 0.5,
            "savings": 30,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "full"
    assert body["monthly_payment"] == 0.0
    assert body["verdict"] == "buy"


def test_calc_plan_loan_red():
    # 月供远超可支配收入 -> 红灯
    r = client.post(
        "/api/calcPlan",
        json={
            "price": 30,
            "mode": "loan",
            "down_payment_ratio": 0.1,
            "months": 36,
            "annual_rate": 0.06,
            "income": 0.8,
            "monthly_expense": 0.5,
            "savings": 2,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "loan"
    assert body["verdict"] == "avoid"
