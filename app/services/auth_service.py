"""用户体系：微信登录、用户名/头像分配、JWT 签发与校验。"""
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


async def _code2session(code: str) -> tuple[str, str | None]:
    """用 code 换 openid；返回 (openid, unionid)。"""
    if config.WX_MOCK_LOGIN or not (config.WX_APPID and config.WX_SECRET):
        if not config.WX_MOCK_LOGIN:
            print("[警告] 未配置 WX_APPID/WX_SECRET，登录降级为 mock 模式（仅限开发）")
        if config.WX_MOCK_OPENID:
            return config.WX_MOCK_OPENID, None
        return f"mock_{code}", None

    params = {
        "appid": config.WX_APPID,
        "secret": config.WX_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.weixin.qq.com/sns/jscode2session", params=params)
            data = resp.json()
    except Exception as exc:  # 网络异常
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"微信登录服务不可用：{exc}")

    if data.get("errcode"):
        code_num = data.get("errcode")
        msg = data.get("errmsg", "登录失败")
        hint = "登录凭证已失效，请重新进入小程序" if code_num in (40029, 40163) else msg
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"{hint}（{code_num}）")

    openid = data.get("openid")
    if not openid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未获取到微信身份")
    return openid, data.get("unionid")


def _upsert_user(db: Session, openid: str, unionid: str | None) -> User:
    """按 openid 建档或更新最后登录时间，返回用户。"""
    user = db.scalar(select(User).where(User.openid == openid))

    if user is None:
        user = User(
            openid=openid,
            unionid=unionid,
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


async def login(db: Session, code: str) -> User:
    """小程序登录：code 换 openid 后建档。"""
    openid, unionid = await _code2session(code)
    return _upsert_user(db, openid, unionid)


def login_h5(db: Session, device_id: str) -> User:
    """H5 匿名登录：以设备标识建档。

    浏览器端没有 wx.login，用本地生成的稳定设备标识作为身份。
    仅用于 H5 端多人共用浏览；小程序端请使用 login()。
    """
    return _upsert_user(db, f"h5_{device_id}", None)


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
