"""买车计划与审批相关模型。"""
from typing import Literal

from pydantic import BaseModel, Field

from app.types import CalcParams

VerdictLike = Literal["buy", "consider", "avoid"]


class CarSnapshot(BaseModel):
    brand: str = Field(..., min_length=1, max_length=32)
    model: str = Field(..., min_length=1, max_length=64)
    config: str = Field("", max_length=64)
    energy_type: Literal["gas", "ev", "hybrid"] = "gas"
    guide_price: float = Field(0.0, ge=0, le=1000)
    ref_discount_price: float = Field(..., gt=0, le=1000)
    fuel_consumption: float = Field(0.0, ge=0)
    power_consumption: float = Field(0.0, ge=0)


class PostCreate(BaseModel):
    car: CarSnapshot
    plan: CalcParams
    # 审核期不接收用户补充说明：字段保留仅为兼容旧客户端，服务端一律忽略
    remark: str | None = Field(None, max_length=200)
    show_finance: bool = False


class AuthorOut(BaseModel):
    user_id: str
    username: str
    avatar_text: str
    avatar_color: str


class FinanceOut(BaseModel):
    income: float | None = None
    monthly_expense: float | None = None
    savings: float | None = None
    disposable_income: float | None = None
    safe_monthly_payment: float | None = None


class ReviewCreate(BaseModel):
    decision: VerdictLike
    # 标签为预设白名单，最多 3 个；不再接收自由文本
    tags: list[str] = Field(default_factory=list, max_length=3)
    # 兼容旧客户端：即使传入也会被忽略
    comment: str | None = Field(None, max_length=200)


class ReviewOut(BaseModel):
    id: int
    decision: str
    decision_text: str
    tags: list[str] = Field(default_factory=list)
    comment: str = ""
    author: AuthorOut
    created_at: str | None = None


class ReviewSubmitOut(BaseModel):
    my_review: ReviewOut
    review_count: int
    buy_count: int
    consider_count: int
    avoid_count: int


class PostListItem(BaseModel):
    id: int
    title: str
    # 审核期不再返回用户补充说明（历史数据也不透出）
    remark: str | None = None
    car_brand: str
    car_model: str
    car_config: str
    energy_type: str
    ref_price: float
    price: float
    mode: str
    landed_price: float
    monthly_payment: float
    total_interest: float = 0.0
    energy_cost_month: float = 0.0
    verdict: str
    verdict_text: str
    review_count: int
    buy_count: int
    consider_count: int
    avoid_count: int
    author: AuthorOut
    is_mine: bool = False
    my_review: ReviewOut | None = None
    created_at: str | None = None


class PostDetail(PostListItem):
    reason: str = ""
    show_finance: bool = False
    finance: FinanceOut | None = None
