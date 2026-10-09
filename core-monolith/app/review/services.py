from __future__ import annotations

from uuid import UUID

from app.movie.interfaces import IMovieRepository, MovieNotFoundError
from app.review.interfaces import (
    IReviewRepository,
    MovieReviewDTO,
    MovieReviewListItemDTO,
)


class ReviewService:
    def __init__(
        self,
        repo: IReviewRepository,
        movie_repo: IMovieRepository,
    ) -> None:
        self._repo = repo
        self._movie_repo = movie_repo

    async def submit_review(
        self, user_id: UUID, movie_id: UUID, rating: float, hashtags: list[str]
    ) -> MovieReviewDTO:
        movie = await self._movie_repo.get_movie_details(movie_id)
        if movie is None:
            raise MovieNotFoundError(f"Movie '{movie_id}' not found")
        review = await self._repo.upsert_review(user_id, movie_id, rating, hashtags)
        await self._repo.recompute_movie_rating(movie_id)
        return review

    async def get_my_review(
        self, user_id: UUID, movie_id: UUID
    ) -> MovieReviewDTO | None:
        return await self._repo.get_review_for_user(user_id, movie_id)

    async def list_reviews(
        self, movie_id: UUID, page: int, limit: int
    ) -> tuple[list[MovieReviewListItemDTO], int]:
        return await self._repo.list_reviews_for_movie(movie_id, page, limit)