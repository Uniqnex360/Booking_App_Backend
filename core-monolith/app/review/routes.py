from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import get_current_user
from app.auth.interfaces import User as AuthUserDomain
from app.movie.interfaces import MovieNotFoundError
from app.review.dependencies import get_review_service
from app.review.schemas import (
    CreateReviewRequest,
    ReviewListItemResponse,
    ReviewResponse,
)
from app.review.services import ReviewService
from app.shared.response import error_response
from app.shared.schemas import PaginatedResponse, PaginationMeta


router = APIRouter(tags=["Review"])


@router.post("/movies/{id}/reviews", response_model=ReviewResponse)
async def submit_review(
    id: UUID,
    body: CreateReviewRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    try:
        review = await service.submit_review(
            user_id=current_user.id,
            movie_id=id,
            rating=body.rating,
            hashtags=body.hashtags,
        )
        return ReviewResponse.model_validate(review, from_attributes=True)
    except MovieNotFoundError as exc:
        return error_response("MOVIE_NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)


@router.get("/movies/{id}/reviews/me", response_model=ReviewResponse | None)
async def get_my_review(
    id: UUID,
    current_user: AuthUserDomain = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    review = await service.get_my_review(current_user.id, id)
    if review is None:
        return None
    return ReviewResponse.model_validate(review, from_attributes=True)


@router.get(
    "/movies/{id}/reviews",
    response_model=PaginatedResponse[ReviewListItemResponse],
)
async def list_reviews(
    id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ReviewService = Depends(get_review_service),
):
    items, total = await service.list_reviews(id, page, limit)
    responses = [
        ReviewListItemResponse.model_validate(r, from_attributes=True) for r in items
    ]
    total_pages = (total + limit - 1) // limit if limit else 0
    return PaginatedResponse(
        data=responses,
        meta=PaginationMeta(total=total, page=page, limit=limit, total_pages=total_pages),
    )