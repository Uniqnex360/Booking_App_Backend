from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.movie.dependencies import get_movie_repo
from app.movie.interfaces import IMovieRepository
from app.review.interfaces import IReviewRepository
from app.review.repository import ReviewRepository
from app.review.services import ReviewService


def get_review_repo(session: AsyncSession = Depends(get_db)) -> IReviewRepository:
    return ReviewRepository(session)


def get_review_service(
    repo: IReviewRepository = Depends(get_review_repo),
    movie_repo: IMovieRepository = Depends(get_movie_repo),
) -> ReviewService:
    return ReviewService(repo=repo, movie_repo=movie_repo)