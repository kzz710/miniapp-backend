"""公共依赖：鉴权与分页。"""
from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.services.auth_service import decode_token


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = decode_token(token)
    user = db.get(User, user_id)
    if user is None or user.status != 1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")
    return user


def get_optional_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    token = _bearer_token(authorization)
    if not token:
        return None
    try:
        user_id = decode_token(token)
    except HTTPException:
        return None
    user = db.get(User, user_id)
    return user if user is not None and user.status == 1 else None


def pagination(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
) -> tuple[int, int]:
    return page, size
