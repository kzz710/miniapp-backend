"""四端按平台换票登录：mock / 缺配置 / 非法 platform / 不串用微信换票。"""
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config as app_config
from app.db.base import Base
from app.db.migrate import migrate_users_platform
from app.db.models import User
from app.main import app
from app.services import auth_service

client = TestClient(app)


def _login(payload: dict):
    return client.post("/api/auth/login", json=payload)


def test_weixin_default_platform_hits_same_user():
    first = _login({"code": "same-wx-code"})
    again = _login({"code": "same-wx-code", "platform": "weixin"})
    empty = _login({"code": "same-wx-code", "platform": ""})
    assert first.status_code == 200, first.text
    assert again.status_code == 200
    assert empty.status_code == 200
    uid = first.json()["user"]["user_id"]
    assert again.json()["user"]["user_id"] == uid
    assert empty.json()["user"]["user_id"] == uid


def test_other_platforms_do_not_collide_with_weixin():
    wx = _login({"code": "shared-code", "platform": "weixin"}).json()
    tt = _login({"code": "shared-code", "platform": "toutiao"}).json()
    ks = _login({"code": "shared-code", "platform": "kuaishou"}).json()
    bd = _login({"code": "shared-code", "platform": "baidu"}).json()
    ids = {
        wx["user"]["user_id"],
        tt["user"]["user_id"],
        ks["user"]["user_id"],
        bd["user"]["user_id"],
    }
    assert len(ids) == 4

    tt_again = _login({"code": "shared-code", "platform": "toutiao"}).json()
    assert tt_again["user"]["user_id"] == tt["user"]["user_id"]


def test_illegal_platform_is_400_and_not_weixin():
    resp = _login({"code": "any-code", "platform": "alipay"})
    assert resp.status_code == 400
    assert "weixin" in resp.json()["detail"]
    assert "toutiao" in resp.json()["detail"]


def test_h5_login_uses_h5_platform_and_stays_stable():
    first = client.post("/api/auth/login/h5", json={"device_id": "h5-device-000009"})
    again = client.post("/api/auth/login/h5", json={"device_id": "h5-device-000009"})
    assert first.status_code == 200, first.text
    assert again.json()["user"]["user_id"] == first.json()["user"]["user_id"]

    from app.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        user = db.query(User).one()
        assert user.platform == "h5"
        assert user.openid == "h5_h5-device-000009"
    finally:
        db.close()


def test_missing_secret_in_production_returns_503(monkeypatch):
    monkeypatch.setattr(app_config, "JWT_SECRET", "prod-not-default-secret")
    monkeypatch.setattr(app_config, "TT_APPID", "")
    monkeypatch.setattr(app_config, "TT_SECRET", "")
    monkeypatch.setattr(app_config, "TT_MOCK_LOGIN", False)
    monkeypatch.setattr(app_config, "WX_MOCK_LOGIN", False)
    resp = _login({"code": "tt-code", "platform": "toutiao"})
    assert resp.status_code == 503
    assert "抖音端登录未配置" in resp.json()["detail"]


def test_explicit_mock_switch_works_even_when_jwt_is_production(monkeypatch):
    monkeypatch.setattr(app_config, "JWT_SECRET", "prod-not-default-secret")
    monkeypatch.setattr(app_config, "KS_APPID", "")
    monkeypatch.setattr(app_config, "KS_SECRET", "")
    monkeypatch.setattr(app_config, "KS_MOCK_LOGIN", True)
    monkeypatch.setattr(app_config, "KS_MOCK_OPENID", "ks-fixed-openid")
    first = _login({"code": "one", "platform": "kuaishou"})
    again = _login({"code": "another", "platform": "kuaishou"})
    assert first.status_code == 200, first.text
    assert again.json()["user"]["user_id"] == first.json()["user"]["user_id"]


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _RecordingClient:
    calls: list = []
    replies: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        _RecordingClient.calls.append(SimpleNamespace(method="GET", url=url, params=params, json=None, data=None))
        return _FakeResp(_RecordingClient.replies[url])

    async def post(self, url, json=None, data=None):
        _RecordingClient.calls.append(SimpleNamespace(method="POST", url=url, params=None, json=json, data=data))
        return _FakeResp(_RecordingClient.replies[url])


def _enable_real_exchange(monkeypatch, platform: str):
    prefixes = {"weixin": "WX", "toutiao": "TT", "kuaishou": "KS", "baidu": "BD"}
    pre = prefixes[platform]
    monkeypatch.setattr(app_config, "JWT_SECRET", "prod-not-default-secret")
    monkeypatch.setattr(app_config, "WX_MOCK_LOGIN", False)
    monkeypatch.setattr(app_config, f"{pre}_MOCK_LOGIN", False)
    monkeypatch.setattr(app_config, f"{pre}_APPID", f"{pre.lower()}-appid")
    monkeypatch.setattr(app_config, f"{pre}_SECRET", f"{pre.lower()}-secret")


def test_toutiao_exchange_hits_official_url_not_weixin(monkeypatch):
    _enable_real_exchange(monkeypatch, "toutiao")
    _RecordingClient.calls = []
    _RecordingClient.replies = {
        auth_service.TT_CODE2SESSION_URL: {"err_no": 0, "data": {"openid": "tt-open-1", "unionid": "tt-union-1"}},
    }
    monkeypatch.setattr("httpx.AsyncClient", _RecordingClient)

    resp = _login({"code": "tt-real-code", "platform": "toutiao"})
    assert resp.status_code == 200, resp.text
    assert len(_RecordingClient.calls) == 1
    call = _RecordingClient.calls[0]
    assert call.method == "POST"
    assert call.url == auth_service.TT_CODE2SESSION_URL
    assert "weixin" not in call.url
    assert call.json == {"appid": "tt-appid", "secret": "tt-secret", "code": "tt-real-code"}

    from app.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        user = db.query(User).one()
        assert user.platform == "toutiao"
        assert user.openid == "tt-open-1"
        assert user.unionid == "tt-union-1"
    finally:
        db.close()


def test_kuaishou_and_baidu_exchange_shapes(monkeypatch):
    _enable_real_exchange(monkeypatch, "kuaishou")
    _enable_real_exchange(monkeypatch, "baidu")
    _RecordingClient.calls = []
    _RecordingClient.replies = {
        auth_service.KS_CODE2SESSION_URL: {"result": 1, "open_id": "ks-open-1"},
        auth_service.BD_CODE2SESSION_URL: {"openid": "bd-open-1"},
    }
    monkeypatch.setattr("httpx.AsyncClient", _RecordingClient)

    ks = _login({"code": "ks-code", "platform": "kuaishou"})
    bd = _login({"code": "bd-code", "platform": "baidu"})
    assert ks.status_code == 200, ks.text
    assert bd.status_code == 200, bd.text

    urls = [c.url for c in _RecordingClient.calls]
    assert auth_service.KS_CODE2SESSION_URL in urls
    assert auth_service.BD_CODE2SESSION_URL in urls
    assert all("weixin.qq.com" not in u for u in urls)

    ks_call = next(c for c in _RecordingClient.calls if "kuaishou" in c.url)
    assert ks_call.data["app_id"] == "ks-appid"
    assert ks_call.data["js_code"] == "ks-code"
    bd_call = next(c for c in _RecordingClient.calls if "spapi.baidu.com" in c.url)
    assert bd_call.params["client_id"] == "bd-appid"
    assert bd_call.params["sk"] == "bd-secret"
    assert bd_call.params["code"] == "bd-code"


def test_invalid_code_from_upstream_is_401(monkeypatch):
    _enable_real_exchange(monkeypatch, "toutiao")
    _RecordingClient.calls = []
    _RecordingClient.replies = {
        auth_service.TT_CODE2SESSION_URL: {"err_no": 40018, "err_tips": "bad code"},
    }
    monkeypatch.setattr("httpx.AsyncClient", _RecordingClient)
    resp = _login({"code": "expired", "platform": "toutiao"})
    assert resp.status_code == 401
    assert "重新进入小程序" in resp.json()["detail"]


def test_network_error_is_502(monkeypatch):
    _enable_real_exchange(monkeypatch, "weixin")

    class _Boom(_RecordingClient):
        async def get(self, url, params=None):
            raise RuntimeError("dns failed")

    monkeypatch.setattr("httpx.AsyncClient", _Boom)
    resp = _login({"code": "wx-code", "platform": "weixin"})
    assert resp.status_code == 502
    assert "微信登录服务不可用" in resp.json()["detail"]


def test_migrate_backfills_weixin_and_h5_and_drops_openid_unique():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    openid VARCHAR(64) NOT NULL UNIQUE,
                    unionid VARCHAR(64),
                    username VARCHAR(32) NOT NULL UNIQUE,
                    avatar_text VARCHAR(4) NOT NULL,
                    avatar_color VARCHAR(7) NOT NULL,
                    last_login_at DATETIME,
                    status INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO users (openid, username, avatar_text, avatar_color, status, created_at, updated_at)
                VALUES
                ('wx-open-old', '车友WX0001', '车', '#2F6BFF', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
                ('h5_device-old', '车友H50001', '车', '#FF6B2F', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00')
                """
            )
        )

    migrate_users_platform(engine)
    migrate_users_platform(engine)  # 幂等

    with engine.connect() as conn:
        rows = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT openid, platform FROM users")).all()
        }
    assert rows["wx-open-old"] == "weixin"
    assert rows["h5_device-old"] == "h5"
    assert not any(
        (idx.get("unique") and list(idx.get("column_names") or []) == ["openid"])
        for idx in inspect(engine).get_indexes("users")
    )
    assert any(
        set(idx.get("column_names") or []) == {"platform", "openid"} or set((uq.get("column_names") or [])) == {"platform", "openid"}
        for idx in inspect(engine).get_indexes("users")
        for uq in (inspect(engine).get_unique_constraints("users") or [{}])
    ) or any(
        set(uq.get("column_names") or []) == {"platform", "openid"}
        for uq in inspect(engine).get_unique_constraints("users")
    )
