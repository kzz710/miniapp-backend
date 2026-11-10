"""用户 / 发布 / 审批接口测试（内存 SQLite，不依赖网络）。"""
from fastapi.testclient import TestClient

from app import config as app_config
from app.main import app

client = TestClient(app)


def login(code: str) -> tuple[dict, dict]:
    resp = client.post("/api/auth/login", json={"code": code})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["user"], {"Authorization": f"Bearer {body['token']}"}


def post_payload(price: float = 17.5) -> dict:
    return {
        "car": {
            "brand": "比亚迪",
            "model": "海豹",
            "config": "650 长续航版",
            "energy_type": "ev",
            "guide_price": 18.98,
            "ref_discount_price": price,
            "fuel_consumption": 0,
            "power_consumption": 13.0,
        },
        "plan": {
            "price": price,
            "mode": "loan",
            "down_payment_ratio": 0.3,
            "months": 36,
            "annual_rate": 0.045,
            "income": 2.0,
            "monthly_expense": 0.5,
            "savings": 10,
            "energy_type": "ev",
            "fuel_consumption": 0,
            "power_consumption": 13.0,
            "monthly_km": 1000,
            "fuel_price": 7.5,
            "electricity_price": 0.6,
        },
        "remark": "通勤刚需，纠结要不要上",
        "show_finance": False,
    }


def test_login_is_stable_and_assigns_identity():
    user1, headers1 = login("same-code")
    user2, headers2 = login("same-code")

    assert user1["user_id"] == user2["user_id"]
    assert user1["username"] == user2["username"]
    assert user1["avatar_text"] == user1["username"][0]
    assert user1["avatar_color"].startswith("#")

    me = client.get("/api/users/me", headers=headers1)
    assert me.status_code == 200
    assert me.json()["user_id"] == user1["user_id"]


def test_rename_updates_avatar_and_rejects_duplicate():
    user1, headers1 = login("rename-a")
    user2, headers2 = login("rename-b")

    resp = client.patch("/api/users/me", json={"username": "老司机张三"}, headers=headers1)
    assert resp.status_code == 200
    assert resp.json()["username"] == "老司机张三"
    assert resp.json()["avatar_text"] == "老"
    assert resp.json()["user_id"] == user1["user_id"]

    dup = client.patch("/api/users/me", json={"username": "老司机张三"}, headers=headers2)
    assert dup.status_code == 409


def test_h5_device_login_is_stable():
    first = client.post("/api/auth/login/h5", json={"device_id": "h5-device-000001"})
    assert first.status_code == 200, first.text

    again = client.post("/api/auth/login/h5", json={"device_id": "h5-device-000001"})
    assert again.json()["user"]["user_id"] == first.json()["user"]["user_id"]

    # 设备标识格式非法（过短）应被拒绝
    assert client.post("/api/auth/login/h5", json={"device_id": "短"}).status_code == 422


def test_daily_post_limit_counts_deleted_posts(monkeypatch):
    monkeypatch.setattr(app_config, "POST_DAILY_LIMIT", 1)
    _, headers = login("limit-user")

    first = client.post("/api/posts", json=post_payload(), headers=headers)
    assert first.status_code == 201

    # 删除后当天仍占用额度，避免「发了删、删了又发」绕过上限
    assert client.delete(f"/api/posts/{first.json()['id']}", headers=headers).status_code == 204
    blocked = client.post("/api/posts", json=post_payload(), headers=headers)
    assert blocked.status_code == 429


def test_rename_validation_and_auth_required():
    _, headers = login("rename-invalid")

    too_short = client.patch("/api/users/me", json={"username": "a"}, headers=headers)
    assert too_short.status_code == 400

    reserved = client.patch("/api/users/me", json={"username": "admin"}, headers=headers)
    assert reserved.status_code == 400

    assert client.get("/api/users/me").status_code == 401
    assert client.post("/api/posts", json=post_payload()).status_code == 401
    assert client.post("/api/posts/1/reviews", json={"decision": "buy", "tags": ["high_payment"]}).status_code == 401


def test_publish_and_square_list():
    _, headers = login("publisher")
    resp = client.post("/api/posts", json=post_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    post = resp.json()
    assert post["verdict"] in ("buy", "consider", "avoid")
    assert post["review_count"] == 0
    assert post["is_mine"] is True

    square = client.get("/api/posts")
    assert square.status_code == 200
    body = square.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == post["id"]


def test_review_flow_and_self_review_forbidden():
    _, author_headers = login("author")
    _, reviewer_headers = login("reviewer")
    post = client.post("/api/posts", json=post_payload(), headers=author_headers).json()

    own = client.post(
        f"/api/posts/{post['id']}/reviews",
        json={"decision": "buy", "tags": ["high_payment"]},
        headers=author_headers,
    )
    assert own.status_code == 403

    review = client.post(
        f"/api/posts/{post['id']}/reviews",
        json={"decision": "consider", "tags": ["high_payment", "save_more"]},
        headers=reviewer_headers,
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["review_count"] == 1
    assert body["consider_count"] == 1
    assert body["my_review"]["tags"] == ["high_payment", "save_more"]

    # 修改审批：计数不重复累加
    updated = client.put(
        f"/api/posts/{post['id']}/reviews/me",
        json={"decision": "avoid", "tags": ["high_cost"]},
        headers=reviewer_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["review_count"] == 1
    assert updated.json()["consider_count"] == 0
    assert updated.json()["avoid_count"] == 1

    detail = client.get(f"/api/posts/{post['id']}")
    assert detail.json()["review_count"] == 1


def test_review_requires_preset_tags():
    _, author_headers = login("tag-author")
    _, reviewer_headers = login("tag-reviewer")
    post = client.post("/api/posts", json=post_payload(), headers=author_headers).json()

    empty = client.post(
        f"/api/posts/{post['id']}/reviews",
        json={"decision": "consider", "tags": []},
        headers=reviewer_headers,
    )
    assert empty.status_code == 400

    invalid = client.post(
        f"/api/posts/{post['id']}/reviews",
        json={"decision": "consider", "tags": ["free_text"]},
        headers=reviewer_headers,
    )
    assert invalid.status_code == 400

    too_many = client.post(
        f"/api/posts/{post['id']}/reviews",
        json={
            "decision": "consider",
            "tags": ["high_payment", "low_down", "high_cost", "negotiate"],
        },
        headers=reviewer_headers,
    )
    assert too_many.status_code in (400, 422)


def test_publish_ignores_remark():
    _, headers = login("remark-ignore")
    payload = post_payload()
    payload["remark"] = "用户自由输入不应落库"

    post = client.post("/api/posts", json=payload, headers=headers).json()
    assert post["remark"] is None

    detail = client.get(f"/api/posts/{post['id']}").json()
    assert detail["remark"] is None


def test_delete_only_by_owner():
    _, author_headers = login("del-owner")
    _, other_headers = login("del-other")
    post = client.post("/api/posts", json=post_payload(), headers=author_headers).json()

    denied = client.delete(f"/api/posts/{post['id']}", headers=other_headers)
    assert denied.status_code == 403

    ok = client.delete(f"/api/posts/{post['id']}", headers=author_headers)
    assert ok.status_code == 204

    assert client.get(f"/api/posts/{post['id']}").status_code == 404
    assert client.get("/api/posts").json()["total"] == 0
    assert len(client.get("/api/me/posts", headers=author_headers).json()["items"]) == 0


def test_private_finance_hidden_by_default():
    _, author_headers = login("finance")
    post = client.post("/api/posts", json=post_payload(), headers=author_headers).json()

    public = client.get(f"/api/posts/{post['id']}")
    assert public.json()["finance"] is None

    mine = client.get(f"/api/posts/{post['id']}", headers=author_headers)
    assert mine.json()["finance"] is not None
    assert mine.json()["finance"]["income"] == 2.0
