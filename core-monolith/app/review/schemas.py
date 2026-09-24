from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


ALLOWED_HASHTAGS = {
    "DirectionWorks", "Entertaining", "Interesting", "NiceStory",
    "Timepass", "CoolMusic", "OneTimeWatch", "Fun", "QuiteNice",
    "OkDirection", "GoodActing", "GoodMusic",
    "HitMovie", "Enjoyable", "LovelyMusic", "FunWatch",
    "SuperDirection", "GreatActing", "WowMusic", "AwesomeStory",
    "Blockbuster", "Rocking", "Inspiring", "Wellmade", "Unbelievable",
}


class CreateReviewRequest(BaseModel):
    rating: float = Field(ge=0, le=10)
    hashtags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("rating")
    @classmethod
    def half_step(cls, v: float) -> float:
        if round(v * 2) != v * 2:
            raise ValueError("rating must be a multiple of 0.5")
        return v

    @field_validator("hashtags")
    @classmethod
    def known_hashtags(cls, v: list[str]) -> list[str]:
        unknown = [h for h in v if h not in ALLOWED_HASHTAGS]
        if unknown:
            raise ValueError(f"Unknown hashtags: {unknown}")
        return list(dict.fromkeys(v))


class ReviewBaseResponse(BaseModel):
    id: UUID
    rating: float
    hashtags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewResponse(ReviewBaseResponse):
    user_id: UUID
    movie_id: UUID


class ReviewListItemResponse(ReviewBaseResponse):
    user_name: str