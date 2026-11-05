"""对外接口数据模型（Pydantic）。"""
from app.schemas.auth import H5LoginRequest, LoginRequest, LoginResponse, UserOut, UserUpdate
from app.schemas.common import PageResult
from app.schemas.post import (
    AuthorOut,
    CarSnapshot,
    FinanceOut,
    PostCreate,
    PostDetail,
    PostListItem,
    ReviewCreate,
    ReviewOut,
)

__all__ = [
    "H5LoginRequest",
    "LoginRequest",
    "LoginResponse",
    "UserOut",
    "UserUpdate",
    "PageResult",
    "AuthorOut",
    "CarSnapshot",
    "FinanceOut",
    "PostCreate",
    "PostDetail",
    "PostListItem",
    "ReviewCreate",
    "ReviewOut",
]
