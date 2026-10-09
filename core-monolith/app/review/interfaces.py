from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MovieReviewBaseDTO:
    id: UUID
    rating: float
    hashtags: list[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MovieReviewDTO(MovieReviewBaseDTO):
    user_id: UUID
    movie_id: UUID


@dataclass(frozen=True, slots=True)
class MovieReviewListItemDTO(MovieReviewBaseDTO):
    user_name: str


class IReviewRepository(ABC):
    @abstractmethod
    async def upsert_review(
        self, user_id: UUID, movie_id: UUID, rating: float, hashtags: list[str]
    ) -> MovieReviewDTO: ...

    @abstractmethod
    async def get_review_for_user(
        self, user_id: UUID, movie_id: UUID
    ) -> MovieReviewDTO | None: ...

    @abstractmethod
    async def list_reviews_for_movie(
        self, movie_id: UUID, page: int, limit: int
    ) -> tuple[list[MovieReviewListItemDTO], int]: ...

    @abstractmethod
    async def recompute_movie_rating(
        self, movie_id: UUID
    ) -> tuple[float | None, int]: ...