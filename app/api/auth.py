"""登录与个人中心路由。"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import config
from app.api.deps import get_current_user, pagination
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import H5LoginRequest, LoginRequest, LoginResponse, UserOut, UserUpdate
from app.schemas.post import PostListItem
from app.schemas.common import PageResult
from app.services import auth_service, post_service
from app.utils import ratelimit

router = APIRouter(prefix="/api", tags=["users"])


def _login_response(user: User) -> LoginResponse:
    token, expires_in = auth_service.issue_token(user)
    return LoginResponse(
        token=token,
        expires_in=expires_in,
        user=auth_service.serialize_user(user),
    )


def _guard_login_rate(request: Request) -> None:
    """登录接口按 IP 限流，避免脚本批量刷号。"""
    if ratelimit.hit(
        f"login:{ratelimit.client_ip(request)}",
        config.LOGIN_RATE_LIMIT_PER_MINUTE,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录过于频繁，请稍后再试",
        )


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """微信 code 换取登录态；首次登录自动分配用户名与文字头像。"""
    _guard_login_rate(request)
    user = await auth_service.login(db, body.code)
    return _login_response(user)


@router.post("/auth/login/h5", response_model=LoginResponse)
def login_h5(
    body: H5LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """H5 匿名登录：没有微信身份，用浏览器本地设备标识建档。"""
    _guard_login_rate(request)
    user = auth_service.login_h5(db, body.device_id)
    return _login_response(user)


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return auth_service.serialize_user(user)


@router.patch("/users/me", response_model=UserOut)
def update_me(
    body: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """修改用户名；头像文字同步为新用户名首字，userId 与底色不变。"""
    updated = auth_service.update_username(db, user, body.username)
    return auth_service.serialize_user(updated)


@router.get("/me/summary")
def summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return post_service.get_summary(db, user)


@router.get("/me/posts", response_model=PageResult[PostListItem])
def my_posts(
    pager: tuple[int, int] = Depends(pagination),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResult[PostListItem]:
    page, size = pager
    return post_service.list_my_posts(db, user, page, size)
