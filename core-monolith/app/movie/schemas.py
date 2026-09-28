from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
class MovieBaseResponse(BaseModel):
    id: UUID
    title: str
    original_title: str | None = None
    language: str
    duration_min: int
    certificate: str
    release_date: datetime | None = None
    poster_url: str | None = None
    banner_url: str | None = None
    trailer_url: str | None = None
    synopsis: str | None = None
    external_rating: float | None = None
    rating: float | None = None
    rating_count: int = 0
    genre: str | None = None
    status: str
class MovieSummaryResponse(MovieBaseResponse):
    pass
class MovieDetailsResponse(MovieBaseResponse):
    venues: list[VenueShowtimesResponse]
class ShowtimeSlotResponse(BaseModel):
    id: UUID
    screen_id: UUID
    screen_name: str
    starts_at: datetime
    language: str
    format: str
    status: str
class VenueShowtimesResponse(BaseModel):
    venue_id: UUID
    venue_name: str
    city: str
    address: str | None = None
    showtimes: list[ShowtimeSlotResponse]
class SeatProjectionResponse(BaseModel):
    seat_id: UUID
    number: int
    code: str
    x: int
    label: str | None = None
    status: str
    price_paise: int
class RowProjectionResponse(BaseModel):
    row_id: UUID
    label: str
    section: str | None = None
    price_paise: int
    seats: list[SeatProjectionResponse]
class SeatMapResponse(BaseModel):
    showtime_id: UUID
    movie_id: UUID
    movie_title: str
    venue_name: str
    screen_name: str
    starts_at: datetime
    format: str
    language: str
    rows: list[RowProjectionResponse]
class AvailabilityResponse(BaseModel):
    showtime_id: UUID
    total_seats: int
    available_seats: int
    booked_seats: int
    blocked_seats: int
    locked_seats: int = 0
class CreateMovieRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    original_title: str | None = None
    language: str = Field(default="Malayalam")
    duration_min: int = Field(gt=0, le=600)
    certificate: str = Field(default="UA")
    poster_url: str | None = None
    synopsis: str | None = None
class UpdateMovieRequest(BaseModel):
    title: str | None = None
    original_title: str | None = None
    language: str | None = None
    duration_min: int | None = None
    certificate: str | None = None
    poster_url: str | None = None
    synopsis: str | None = None
class CreateScreenRequest(BaseModel):
    venue_id: UUID
    name: str = Field(min_length=1, max_length=100)
class ApplyLayoutRequest(BaseModel):
    text_grid: str = Field(
        description="Text grid specification (e.g. 'A: 1111 2 1111')"
    )
    default_price_paise: int = Field(default=29000, ge=0)
    section: str | None = None  
class AdminApplyLayoutRequest(ApplyLayoutRequest):
    override_reason: str = Field(min_length=5, description="Audit reason for admin layout override")
class CreateShowtimeRequest(BaseModel):
    screen_id: UUID
    movie_id: UUID
    starts_at: datetime
    language: str = Field(default="Malayalam")
    format: str = Field(default="2D")  
class BlockSeatsRequest(BaseModel):
    seat_ids: list[UUID] = Field(min_length=1)
    reason: str = Field(default="Maintenance / VIP Hold")
class UnblockSeatsRequest(BaseModel):
    seat_ids: list[UUID] = Field(min_length=1)
class ContentStatusUpdateRequest(BaseModel):
    status: str  
class CreateVenueRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    city: str = Field(min_length=1, max_length=64)
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str = "Asia/Kolkata"
