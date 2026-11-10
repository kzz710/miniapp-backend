"""买车计划服务：发布、广场列表、详情、删除、统计。"""
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.db.models import CarPost, PostReview, User
from app.engine import run_plan
from app.schemas.common import PageResult, iso
from app.schemas.post import (
    AuthorOut,
    FinanceOut,
    PostCreate,
    PostDetail,
    PostListItem,
    ReviewOut,
)
from app.services.review_tags import parse_tags
from app.utils.helpers import start_of_today_cn_utc

DECISION_TEXT = {"buy": "买买买", "consider": "理性考虑", "avoid": "买个 der"}


def author_out(user: User) -> AuthorOut:
    return AuthorOut(
        user_id=f"U{user.id}",
        username=user.username,
        avatar_text=user.avatar_text,
        avatar_color=user.avatar_color,
    )


def _user_map(db: Session, user_ids: set[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(user_ids))).all()
    return {u.id: u for u in rows}


def review_out(review: PostReview, author: User | None) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        decision=review.decision,
        decision_text=DECISION_TEXT.get(review.decision, review.decision),
        tags=parse_tags(review.comment),
        # 审核期不透出历史自由文本，只返回结构化标签
        comment="",
        author=author_out(author)
        if author
        else AuthorOut(user_id="U0", username="已注销用户", avatar_text="?", avatar_color="#9AA0AE"),
        created_at=iso(review.created_at),
    )


def _my_review_map(db: Session, post_ids: list[int], viewer_id: int | None) -> dict[int, PostReview]:
    if not viewer_id or not post_ids:
        return {}
    rows = db.scalars(
        select(PostReview).where(
            PostReview.post_id.in_(post_ids),
            PostReview.user_id == viewer_id,
        )
    ).all()
    return {r.post_id: r for r in rows}


def _base_fields(post: CarPost, author: User | None, viewer_id: int | None) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        # 审核期不透出用户补充说明
        "remark": None,
        "car_brand": post.car_brand,
        "car_model": post.car_model,
        "car_config": post.car_config,
        "energy_type": post.energy_type,
        "ref_price": post.ref_price,
        "price": post.price,
        "mode": post.mode,
        "landed_price": post.landed_price,
        "monthly_payment": post.monthly_payment,
        "total_interest": post.total_interest,
        "energy_cost_month": post.energy_cost_month,
        "verdict": post.verdict,
        "verdict_text": post.verdict_text,
        "review_count": post.review_count,
        "buy_count": post.buy_count,
        "consider_count": post.consider_count,
        "avoid_count": post.avoid_count,
        "author": author_out(author)
        if author
        else AuthorOut(user_id="U0", username="已注销用户", avatar_text="?", avatar_color="#9AA0AE"),
        "is_mine": viewer_id is not None and post.user_id == viewer_id,
        "created_at": iso(post.created_at),
    }


def _build_title(car_brand: str, car_model: str, price: float) -> str:
    amount = f"{price:g}"
    title = f"{amount} 万想买{car_brand} {car_model}，大家觉得买得值吗"
    return title[:80]


def create_post(db: Session, user: User, payload: PostCreate) -> PostDetail:
    # 日限流按「当日创建总量」统计（不区分是否已删除），避免删了再发绕过上限
    today = db.scalar(
        select(func.count(CarPost.id)).where(
            CarPost.user_id == user.id,
            CarPost.created_at >= start_of_today_cn_utc(),
        )
    )
    if (today or 0) >= config.POST_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"每天最多发布 {config.POST_DAILY_LIMIT} 条，明天再来吧",
        )

    # 审核期：不接受任何用户补充说明，字段一律置空（旧客户端传入也忽略）
    remark = None

    car = payload.car
    result = run_plan(payload.plan)

    post = CarPost(
        user_id=user.id,
        title=_build_title(car.brand, car.model, payload.plan.price),
        remark=remark,
        car_brand=car.brand,
        car_model=car.model,
        car_config=car.config,
        energy_type=car.energy_type,
        guide_price=car.guide_price,
        ref_price=car.ref_discount_price,
        price=payload.plan.price,
        mode=payload.plan.mode,
        down_payment_ratio=payload.plan.down_payment_ratio,
        months=payload.plan.months,
        annual_rate=payload.plan.annual_rate,
        landed_price=result.landed_price,
        monthly_payment=result.monthly_payment,
        total_interest=result.total_interest,
        energy_cost_month=result.energy_cost_month,
        verdict=result.verdict,
        verdict_text=result.verdict_text,
        reason=result.reason,
        show_finance=1 if payload.show_finance else 0,
        income=payload.plan.income,
        monthly_expense=payload.plan.monthly_expense,
        savings=payload.plan.savings,
        disposable_income=result.disposable_income,
        safe_monthly_payment=result.safe_monthly_payment,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return serialize_detail(db, post, user, user.id)


def serialize_detail(db: Session, post: CarPost, author: User | None, viewer_id: int | None) -> PostDetail:
    my_review = _my_review_map(db, [post.id], viewer_id).get(post.id)
    review_author = (
        _user_map(db, {my_review.user_id}).get(my_review.user_id) if my_review else None
    )
    can_see_finance = bool(viewer_id is not None and post.user_id == viewer_id) or bool(post.show_finance)
    finance = None
    if can_see_finance:
        finance = FinanceOut(
            income=post.income,
            monthly_expense=post.monthly_expense,
            savings=post.savings,
            disposable_income=post.disposable_income,
            safe_monthly_payment=post.safe_monthly_payment,
        )
    return PostDetail(
        **_base_fields(post, author, viewer_id),
        reason=post.reason,
        show_finance=bool(post.show_finance),
        finance=finance,
        my_review=review_out(my_review, review_author) if my_review else None,
    )


def list_posts(db: Session, page: int, size: int, sort: str, viewer_id: int | None) -> PageResult:
    conditions = [CarPost.status == 1]
    total = db.scalar(select(func.count(CarPost.id)).where(*conditions)) or 0

    if sort == "hot":
        order = (CarPost.review_count.desc(), CarPost.created_at.desc(), CarPost.id.desc())
    else:
        order = (CarPost.created_at.desc(), CarPost.id.desc())

    rows = db.scalars(
        select(CarPost).where(*conditions).order_by(*order).offset((page - 1) * size).limit(size)
    ).all()

    authors = _user_map(db, {p.user_id for p in rows})
    mine = _my_review_map(db, [p.id for p in rows], viewer_id)
    review_authors = _user_map(db, {r.user_id for r in mine.values()})

    items = [
        PostListItem(
            **_base_fields(p, authors.get(p.user_id), viewer_id),
            my_review=review_out(mine[p.id], review_authors.get(mine[p.id].user_id)) if p.id in mine else None,
        )
        for p in rows
    ]
    return PageResult[PostListItem](
        items=items,
        total=total,
        page=page,
        size=size,
        has_more=page * size < total,
    )


def list_my_posts(db: Session, user: User, page: int, size: int) -> PageResult:
    conditions = [CarPost.status == 1, CarPost.user_id == user.id]
    total = db.scalar(select(func.count(CarPost.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(CarPost)
        .where(*conditions)
        .order_by(CarPost.created_at.desc(), CarPost.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    items = [
        PostListItem(**_base_fields(p, user, user.id))
        for p in rows
    ]
    return PageResult[PostListItem](
        items=items,
        total=total,
        page=page,
        size=size,
        has_more=page * size < total,
    )


def get_post(db: Session, post_id: int, viewer_id: int | None) -> PostDetail:
    post = db.get(CarPost, post_id)
    if post is None or post.status != 1:
        if post is not None and viewer_id is not None and post.user_id == viewer_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该发布已删除")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发布不存在或已删除")
    author = db.get(User, post.user_id)
    return serialize_detail(db, post, author, viewer_id)


def delete_post(db: Session, post: CarPost, user: User) -> None:
    if post.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能删除自己的发布")
    post.status = 0
    db.commit()


def get_summary(db: Session, user: User) -> dict:
    post_count = db.scalar(
        select(func.count(CarPost.id)).where(CarPost.user_id == user.id, CarPost.status == 1)
    ) or 0
    received = db.scalar(
        select(func.count(PostReview.id))
        .join(CarPost, CarPost.id == PostReview.post_id)
        .where(CarPost.user_id == user.id, CarPost.status == 1)
    ) or 0
    return {"post_count": post_count, "received_review_count": received}
