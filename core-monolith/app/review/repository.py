from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.movie.models import Movie
from app.review.interfaces import (
    IReviewRepository,
    MovieReviewDTO,
    MovieReviewListItemDTO,
)
from app.review.models import MovieReview


class ReviewRepository(IReviewRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_review_dto(self, m: MovieReview) -> MovieReviewDTO:
        return MovieReviewDTO(
            id=m.id,
            user_id=m.user_id,
            movie_id=m.movie_id,
            rating=float(m.rating),
            hashtags=list(m.hashtags or []),
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    async def get_review_for_user(
        self, user_id: UUID, movie_id: UUID
    ) -> MovieReviewDTO | None:
        stmt = select(MovieReview).where(
            MovieReview.user_id == user_id, MovieReview.movie_id == movie_id
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return self._to_review_dto(row) if row else None

    async def upsert_review(
        self, user_id: UUID, movie_id: UUID, rating: float, hashtags: list[str]
    ) -> MovieReviewDTO:
        stmt = select(MovieReview).where(
            MovieReview.user_id == user_id, MovieReview.movie_id == movie_id
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.rating = rating
            existing.hashtags = hashtags
            await self.session.flush()
            await self.session.commit()
            return self._to_review_dto(existing)
        review = MovieReview(
            id=uuid.uuid4(),
            user_id=user_id,
            movie_id=movie_id,
            rating=rating,
            hashtags=hashtags,
        )
        self.session.add(review)
        await self.session.flush()
        await self.session.commit()
        return self._to_review_dto(review)

    async def recompute_movie_rating(
        self, movie_id: UUID
    ) -> tuple[float | None, int]:
        stmt = select(
            func.avg(MovieReview.rating), func.count(MovieReview.id)
        ).where(MovieReview.movie_id == movie_id)
        avg, count = (await self.session.execute(stmt)).one()
        movie = (
            await self.session.execute(select(Movie).where(Movie.id == movie_id))
        ).scalar_one_or_none()
        if movie is not None:
            movie.rating = float(avg) if avg is not None else None
            movie.rating_count = int(count or 0)
            await self.session.flush()
            await self.session.commit()
        return (float(avg) if avg is not None else None, int(count or 0))

    async def list_reviews_for_movie(
        self, movie_id: UUID, page: int, limit: int
    ) -> tuple[list[MovieReviewListItemDTO], int]:
        base = (
            select(MovieReview, User.full_name)
            .join(User, User.id == MovieReview.user_id)
            .where(MovieReview.movie_id == movie_id)
        )
        count_stmt = select(func.count()).select_from(
            base.with_only_columns(MovieReview.id).subquery()
        )
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            base.order_by(MovieReview.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        items = [
            MovieReviewListItemDTO(
                id=review.id,
                user_name=(full_name or "Anonymous").split(" ")[0],
                rating=float(review.rating),
                hashtags=list(review.hashtags or []),
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
            for review, full_name in rows
        ]
        return items, total