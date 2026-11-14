"""用户体系：多端登录换票、用户名/头像分配、JWT 签发与校验。"""
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.db.models import User, utcnow
from app.schemas.auth import UserOut
from app.schemas.common import iso

# 头像底色板：与前端主题保持一致，按 userId 稳定取色
PALETTE = [
    "#2F6BFF",
    "#FF6B2F",
    "#16B98A",
    "#F2994A",
    "#6A5CFF",
    "#D6453B",
    "#0E9B57",
    "#B7791F",
]

USERNAME_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9_]{2,16}$")
_BANNED_WORDS = ("admin", "root", "官方", "客服", "系统")

LOGIN_PLATFORMS = config.LOGIN_PLATFORMS
PLATFORM_LABELS = config.PLATFORM_LABELS

# 各端官方换票地址（仅路径与协议，密钥走配置）
WX_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
TT_CODE2SESSION_URL = "https://developer.toutiao.com/api/apps/v2/jscode2session"
KS_CODE2SESSION_URL = "https://open.kuaishou.com/oauth2/mp/code2session"
BD_CODE2SESSION_URL = "https://spapi.baidu.com/oauth/jscode2sessionkey"


def normalize_platform(value: str | None) -> str:
    """缺省或空字符串按 weixin；非法值 400，不回落到微信换票。"""
    if value is None or not str(value).strip():
        return "weixin"
    platform = str(value).strip()
    if platform not in LOGIN_PLATFORMS:
        allowed = " / ".join(LOGIN_PLATFORMS)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"platform 须为 {allowed} 之一",
        )
    return platform


def _random_suffix(n: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def generate_username(db: Session) -> str:
    """生成全局唯一的用户名：车友 + 6 位大写字母数字。"""
    for _ in range(8):
        name = "车友" + _random_suffix()
        exists = db.scalar(select(User.id).where(User.username == name))
        if not exists:
            return name
    # 极端兜底：用更长的随机串
    return "车友" + secrets.token_hex(6).upper()


def avatar_text_of(username: str) -> str:
    """取用户名首个字符作为头像文字（英文转大写）。"""
    ch = username.strip()[:1] or "车"
    return ch.upper()


def avatar_color_of(user_id: int) -> str:
    return PALETTE[user_id % len(PALETTE)]


def validate_username(username: str) -> str:
    name = username.strip()
    if not USERNAME_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名需为 2~16 个中文、字母、数字或下划线",
        )
    lowered = name.lower()
    if any(word in lowered for word in _BANNED_WORDS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该用户名不可用")
    return name


def _label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


def _mock_identity(platform: str, code: str) -> tuple[str, str | None]:
    mock_openid = config.platform_auth(platform)["mock_openid"]
    if mock_openid:
        return mock_openid, None
    return f"mock_{code}", None


async def _code2session(code: str, platform: str) -> tuple[str, str | None]:
    """按平台用 code 换 openid；返回 (openid, unionid)。"""
    if config.uses_mock_login(platform):
        auth = config.platform_auth(platform)
        if not auth["mock_login"]:
            print(
                f"[警告] 未配置 {_label(platform)} 登录密钥，登录降级为 mock 模式（仅限开发）",
                flush=True,
            )
        return _mock_identity(platform, code)

    auth = config.platform_auth(platform)
    if not auth["configured"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{_label(platform)}端登录未配置",
        )

    try:
        if platform == "weixin":
            return await _exchange_weixin(code, auth)
        if platform == "toutiao":
            return await _exchange_toutiao(code, auth)
        if platform == "kuaishou":
            return await _exchange_kuaishou(code, auth)
        if platform == "baidu":
            return await _exchange_baidu(code, auth)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{_label(platform)}登录服务不可用：{exc}",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"platform 须为 {' / '.join(LOGIN_PLATFORMS)} 之一",
    )


def _invalid_code(platform: str, hint: str, code_num=None) -> HTTPException:
    suffix = f"（{code_num}）" if code_num is not None else ""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"{hint}{suffix}",
    )


async def _exchange_weixin(code: str, auth: dict) -> tuple[str, str | None]:
    params = {
        "appid": auth["appid"],
        "secret": auth["secret"],
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(WX_CODE2SESSION_URL, params=params)
        data = resp.json()

    if data.get("errcode"):
        code_num = data.get("errcode")
        msg = data.get("errmsg", "登录失败")
        hint = "登录凭证已失效，请重新进入小程序" if code_num in (40029, 40163) else msg
        raise _invalid_code("weixin", hint, code_num)

    openid = data.get("openid")
    if not openid:
        raise _invalid_code("weixin", "未获取到微信身份")
    return openid, data.get("unionid")


async def _exchange_toutiao(code: str, auth: dict) -> tuple[str, str | None]:
    payload = {"appid": auth["appid"], "secret": auth["secret"], "code": code}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(TT_CODE2SESSION_URL, json=payload)
        data = resp.json()

    err_no = data.get("err_no")
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    openid = inner.get("openid") or data.get("openid")
    if err_no not in (0, "0") and not (err_no is None and openid):
        raise _invalid_code("toutiao", "登录凭证已失效，请重新进入小程序", err_no)
    if not openid:
        raise _invalid_code("toutiao", "未获取到抖音身份")
    return openid, inner.get("unionid") or data.get("unionid")


async def _exchange_kuaishou(code: str, auth: dict) -> tuple[str, str | None]:
    form = {
        "app_id": auth["appid"],
        "app_secret": auth["secret"],
        "js_code": code,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(KS_CODE2SESSION_URL, data=form)
        data = resp.json()

    result = data.get("result")
    if result not in (1, "1"):
        msg = data.get("error_msg") or data.get("msg") or "登录失败"
        raise _invalid_code("kuaishou", "登录凭证已失效，请重新进入小程序", result)

    openid = data.get("open_id") or data.get("openid")
    if not openid:
        raise _invalid_code("kuaishou", "未获取到快手身份")
    return openid, data.get("union_id") or data.get("unionid")


async def _exchange_baidu(code: str, auth: dict) -> tuple[str, str | None]:
    params = {
        "code": code,
        "client_id": auth["appid"],
        "sk": auth["secret"],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(BD_CODE2SESSION_URL, params=params)
        data = resp.json()

    errno = data.get("errno")
    if errno not in (0, "0", None):
        msg = data.get("error") or data.get("errmsg") or data.get("msg") or "登录失败"
        raise _invalid_code("baidu", "登录凭证已失效，请重新进入小程序", errno)

    openid = data.get("openid")
    if not openid:
        raise _invalid_code("baidu", "未获取到百度身份")
    return openid, data.get("unionid")


def _upsert_user(db: Session, openid: str, unionid: str | None, platform: str) -> User:
    """按 (platform, openid) 建档或更新最后登录时间，各端互不合并。"""
    user = db.scalar(
        select(User).where(User.platform == platform, User.openid == openid)
    )

    if user is None:
        user = User(
            openid=openid,
            unionid=unionid,
            platform=platform,
            username=generate_username(db),
            avatar_text="车",
            avatar_color=PALETTE[0],
            last_login_at=utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        # 依赖自增 ID 生成稳定头像色
        user.avatar_text = avatar_text_of(user.username)
        user.avatar_color = avatar_color_of(user.id)
        db.commit()
        db.refresh(user)
    else:
        user.last_login_at = utcnow()
        if unionid and not user.unionid:
            user.unionid = unionid
        db.commit()

    return user


async def login(db: Session, code: str, platform: str | None = None) -> User:
    """小程序登录：按平台 code 换 openid 后建档。"""
    platform = normalize_platform(platform)
    openid, unionid = await _code2session(code, platform)
    return _upsert_user(db, openid, unionid, platform)


def login_h5(db: Session, device_id: str) -> User:
    """H5 匿名登录：以设备标识建档。

    浏览器端没有 wx.login，用本地生成的稳定设备标识作为身份。
    仅用于 H5 端多人共用浏览；小程序端请使用 login()。
    """
    return _upsert_user(db, f"h5_{device_id}", None, platform="h5")


def update_username(db: Session, user: User, username: str) -> User:
    name = validate_username(username)
    exists = db.scalar(select(User.id).where(User.username == name, User.id != user.id))
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被占用")

    user.username = name
    # 头像文字跟随新用户名首字，底色保持不变
    user.avatar_text = avatar_text_of(name)
    db.commit()
    db.refresh(user)
    return user


def issue_token(user: User) -> tuple[str, int]:
    ttl = timedelta(days=config.TOKEN_TTL_DAYS)
    payload = {
        "sub": str(user.id),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + ttl,
    }
    token = jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    return token, int(ttl.total_seconds())


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        return int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效，请重新登录")


def serialize_user(user: User) -> UserOut:
    return UserOut(
        user_id=f"U{user.id}",
        username=user.username,
        avatar_text=user.avatar_text,
        avatar_color=user.avatar_color,
        created_at=iso(user.created_at),
    )
