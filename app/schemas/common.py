"""通用模型与序列化辅助。"""
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    has_more: bool


def iso(dt: datetime | None) -> str | None:
    """统一输出 ISO8601（UTC，带 Z 后缀），前端可直接解析。"""
    if dt is None:
        return None
    return dt.replace(microsecond=0).isoformat() + "Z"
