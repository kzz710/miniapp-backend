"""买车计划：发布、广场、详情、删除、审批。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user, pagination
from app.db.models import CarPost, User
from app.db.session import get_db
from app.schemas.common import PageResult
from app.schemas.post import (
    PostCreate,
    PostDetail,
    PostListItem,
    ReviewCreate,
    ReviewOut,
    ReviewSubmitOut,
)
from app.services import post_service, review_service

router = APIRouter(prefix="/api", tags=["posts"])


def _get_post_or_404(db: Session, post_id: int) -> CarPost:
    post = db.get(CarPost, post_id)
    if post is None or post.status != 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发布不存在或已删除")
    return post


@router.post("/posts", response_model=PostDetail, status_code=status.HTTP_201_CREATED)
def create_post(
    body: PostCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostDetail:
    """发布买车计划：服务端重算费用与结论，不信任前端结果。"""
    return post_service.create_post(db, user, body)


@router.get("/posts", response_model=PageResult[PostListItem])
def list_posts(
    sort: str = Query("latest", pattern="^(latest|hot)$"),
    pager: tuple[int, int] = Depends(pagination),
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> PageResult[PostListItem]:
    page, size = pager
    return post_service.list_posts(db, page, size, sort, viewer.id if viewer else None)


@router.get("/posts/{post_id}", response_model=PostDetail)
def get_post(
    post_id: int,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> PostDetail:
    return post_service.get_post(db, post_id, viewer.id if viewer else None)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    post = _get_post_or_404(db, post_id)
    post_service.delete_post(db, post, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/posts/{post_id}/reviews", response_model=PageResult[ReviewOut])
def list_reviews(
    post_id: int,
    pager: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> PageResult[ReviewOut]:
    post = _get_post_or_404(db, post_id)
    page, size = pager
    return review_service.list_reviews(db, post, page, size)


@router.post("/posts/{post_id}/reviews", response_model=ReviewSubmitOut)
def submit_review(
    post_id: int,
    body: ReviewCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewSubmitOut:
    post = _get_post_or_404(db, post_id)
    return review_service.upsert_review(db, post, user, body)


@router.put("/posts/{post_id}/reviews/me", response_model=ReviewSubmitOut)
def update_review(
    post_id: int,
    body: ReviewCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewSubmitOut:
    post = _get_post_or_404(db, post_id)
    return review_service.upsert_review(db, post, user, body)
