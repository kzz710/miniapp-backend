"""ORM 模型：用户 / 买车计划 / 审批。"""
from datetime import datetime, timezone

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    """返回不带时区的 UTC 时间，便于统一序列化为 ISO8601 + Z。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    openid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    unionid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    avatar_text: Mapped[str] = mapped_column(String(4))
    avatar_color: Mapped[str] = mapped_column(String(7))
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CarPost(Base):
    __tablename__ = "car_posts"
    __table_args__ = (
        Index("idx_square", "status", "created_at"),
        Index("idx_user", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)

    title: Mapped[str] = mapped_column(String(80))
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    car_brand: Mapped[str] = mapped_column(String(32))
    car_model: Mapped[str] = mapped_column(String(64))
    car_config: Mapped[str] = mapped_column(String(64), default="")
    energy_type: Mapped[str] = mapped_column(String(8), default="gas")
    guide_price: Mapped[float] = mapped_column(default=0.0)
    ref_price: Mapped[float] = mapped_column(default=0.0)

    price: Mapped[float] = mapped_column(default=0.0)
    mode: Mapped[str] = mapped_column(String(8), default="full")
    down_payment_ratio: Mapped[float] = mapped_column(default=0.3)
    months: Mapped[int] = mapped_column(default=36)
    annual_rate: Mapped[float] = mapped_column(default=0.045)

    landed_price: Mapped[float] = mapped_column(default=0.0)
    monthly_payment: Mapped[float] = mapped_column(default=0.0)
    total_interest: Mapped[float] = mapped_column(default=0.0)
    energy_cost_month: Mapped[float] = mapped_column(default=0.0)
    verdict: Mapped[str] = mapped_column(String(8), default="consider")
    verdict_text: Mapped[str] = mapped_column(String(16), default="")
    reason: Mapped[str] = mapped_column(Text, default="")

    show_finance: Mapped[int] = mapped_column(default=0)
    income: Mapped[float | None] = mapped_column(nullable=True)
    monthly_expense: Mapped[float | None] = mapped_column(nullable=True)
    savings: Mapped[float | None] = mapped_column(nullable=True)
    disposable_income: Mapped[float | None] = mapped_column(nullable=True)
    safe_monthly_payment: Mapped[float | None] = mapped_column(nullable=True)

    review_count: Mapped[int] = mapped_column(default=0)
    buy_count: Mapped[int] = mapped_column(default=0)
    consider_count: Mapped[int] = mapped_column(default=0)
    avoid_count: Mapped[int] = mapped_column(default=0)

    status: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class SearchStat(Base):
    """关键词搜索次数统计，用于计算热门车型。"""

    __tablename__ = "search_stats"

    keyword: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    last_searched_at: Mapped[datetime] = mapped_column(default=utcnow)


class PriceCache(Base):
    """车价结果持久化缓存（重启后仍生效，避免部署后首批查询全部走慢链路）。"""

    __tablename__ = "price_cache"

    keyword: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, default="[]")
    expires_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class PostReview(Base):
    __tablename__ = "post_reviews"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uk_post_user"),
        Index("idx_review_post", "post_id", "created_at"),
        Index("idx_review_user", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    decision: Mapped[str] = mapped_column(String(8))
    comment: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
