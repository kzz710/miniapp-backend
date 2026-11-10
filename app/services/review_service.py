"""审批服务：提交/修改审批、审批列表、计数重算。"""
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.db.models import CarPost, PostReview, User
from app.schemas.common import PageResult
from app.schemas.post import ReviewCreate, ReviewOut, ReviewSubmitOut
from app.services.post_service import review_out
from app.services.review_tags import normalize_tags, tags_to_text
from app.utils.helpers import start_of_today_cn_utc

DECISIONS = ("buy", "consider", "avoid")


def _recount(db: Session, post: CarPost) -> None:
    rows = db.execute(
        select(PostReview.decision, func.count(PostReview.id))
        .where(PostReview.post_id == post.id)
        .group_by(PostReview.decision)
    ).all()
    counts = {key: 0 for key in DECISIONS}
    for decision, count in rows:
        if decision in counts:
            counts[decision] = count
    post.buy_count = counts["buy"]
    post.consider_count = counts["consider"]
    post.avoid_count = counts["avoid"]
    post.review_count = sum(counts.values())


def upsert_review(db: Session, post: CarPost, user: User, payload: ReviewCreate) -> ReviewSubmitOut:
    if post.status != 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发布不存在或已删除")
    if post.user_id == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能审批自己的发布")

    # 只接受预设标签，任何自由文本（payload.comment）一律忽略
    tags = normalize_tags(payload.tags)
    if not tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少选择一个评价标签",
        )
    comment = tags_to_text(tags)

    post_id = post.id
    existing = db.scalar(
        select(PostReview).where(PostReview.post_id == post_id, PostReview.user_id == user.id)
    )

    if existing is None:
        today = db.scalar(
            select(func.count(PostReview.id)).where(
                PostReview.user_id == user.id,
                PostReview.created_at >= start_of_today_cn_utc(),
            )
        )
        if (today or 0) >= config.REVIEW_DAILY_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"每天最多审批 {config.REVIEW_DAILY_LIMIT} 条，明天再来吧",
            )
        review = PostReview(
            post_id=post_id,
            user_id=user.id,
            decision=payload.decision,
            comment=comment,
        )
        db.add(review)
        try:
            db.flush()
        except IntegrityError:
            # 并发下另一请求已插入同一 (post_id, user_id)：回滚后按「修改」处理，保证幂等
            db.rollback()
            review = db.scalar(
                select(PostReview).where(
                    PostReview.post_id == post_id, PostReview.user_id == user.id
                )
            )
            if review is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="提交冲突，请重试"
                )
            review.decision = payload.decision
            review.comment = comment
            db.flush()
            refreshed = db.get(CarPost, post_id)
            if refreshed is not None:
                post = refreshed
    else:
        review = existing
        review.decision = payload.decision
        review.comment = comment
        db.flush()

    _recount(db, post)
    db.commit()
    db.refresh(review)
    db.refresh(post)

    return ReviewSubmitOut(
        my_review=review_out(review, user),
        review_count=post.review_count,
        buy_count=post.buy_count,
        consider_count=post.consider_count,
        avoid_count=post.avoid_count,
    )


def list_reviews(db: Session, post: CarPost, page: int, size: int) -> PageResult:
    total = db.scalar(
        select(func.count(PostReview.id)).where(PostReview.post_id == post.id)
    ) or 0
    rows = db.scalars(
        select(PostReview)
        .where(PostReview.post_id == post.id)
        .order_by(PostReview.created_at.desc(), PostReview.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    user_ids = {r.user_id for r in rows}
    users = db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    user_map = {u.id: u for u in users}

    items: list[ReviewOut] = [review_out(r, user_map.get(r.user_id)) for r in rows]
    return PageResult[ReviewOut](
        items=items,
        total=total,
        page=page,
        size=size,
        has_more=page * size < total,
    )
