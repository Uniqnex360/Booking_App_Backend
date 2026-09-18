"""Pydantic schemas for the Booking Module."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class BookingCreateRequest(BaseModel):
    # Payment confirmation alias parameters
    lock_id: UUID | None = None
    payment_id: str | None = None

    # Event Booking parameters
    event_id: UUID | None = None
    tier_id: UUID | None = None
    quantity: int | None = Field(default=None, ge=1, le=20)

    # Movie Booking parameters
    showtime_id: UUID | None = None
    seat_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=10)

    # Common
    idempotency_key: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_booking_type(self) -> BookingCreateRequest:
        if self.lock_id and self.payment_id:
            return self

        is_event = self.tier_id is not None and self.quantity is not None
        is_movie = self.showtime_id is not None and self.seat_ids is not None and len(self.seat_ids) > 0

        if not is_event and not is_movie:
            raise ValueError(
                "Must provide either Event parameters (tier_id, quantity) "
                "or Movie parameters (showtime_id, seat_ids)."
            )
        if is_event and is_movie:
            raise ValueError("Cannot combine Event and Movie bookings in a single request.")
        return self


class ProviderHoldCreateRequest(BaseModel):
    showtime_id: UUID
    seat_ids: list[str] = Field(min_length=1, max_length=10)
    seat_codes: list[str] | None = Field(default=None, max_length=10)


class CommitBookingRequest(BaseModel):
    payment_ref: str | None = None


class BookingSeatItemResponse(BaseModel):
    seat_id: str
    code: str
    price_paise: int


class BookingResponse(BaseModel):
    id: UUID
    user_id: UUID
    status: str
    total_paise: int
    created_at: datetime
    currency: str = "INR"
    ref_code: str | None = None
    barcode: str | None = None
    showtime_id: UUID | None = None
    held_until: datetime | None = None
    provider_booking_id: str | None = None
    seats: list[str] | None = None
    seat_codes: list[str] | None = None
from typing import Literal
from pydantic import BaseModel

class BaseBookingDetail(BaseModel):
    type: str
    id: UUID
    status: str
    total_paise: int
    currency: str
    ref_code: str | None = None
    barcode: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_domain(cls, b) -> "BaseBookingDetail":
        return cls(
            type="MOVIE" if b.showtime_id else ("EVENT" if b.event_id else "UNKNOWN"),
            id=b.id,
            status=b.status.value if hasattr(b.status, "value") else b.status,
            total_paise=b.total_paise,
            currency=b.currency,
            ref_code=b.ref_code,
            barcode=b.barcode,
            created_at=b.created_at,
        )


class MovieBookingDetail(BaseBookingDetail):
    type: Literal["MOVIE"] = "MOVIE"
    movie_title: str
    poster_url: str | None = None
    certificate: str | None = None
    duration_min: int | None = None
    language: str | None = None
    format: str | None = None
    starts_at: datetime | None = None
    screen_name: str | None = None
    cinema_name: str | None = None
    cinema_city: str | None = None
    cinema_address: str | None = None
    seat_codes: list[str] | None = None
    quantity: int
    unit_price_paise: int | None = None

    @classmethod
    def from_context(cls, b, ctx) -> "MovieBookingDetail":
        st, movie, screen, venue = ctx["showtime"], ctx["movie"], ctx["screen"], ctx["venue"]
        seats = b.seat_codes or b.seat_refs or []
        base = BaseBookingDetail.from_domain(b).model_dump()
        return cls(
            **base,
            movie_title=movie.title,
            poster_url=movie.poster_url,
            certificate=movie.certificate,
            duration_min=movie.duration_min,
            language=st.language or movie.language,
            format=st.format,
            starts_at=st.starts_at,
            screen_name=screen.name if screen else None,
            cinema_name=venue.name if venue else None,
            cinema_city=venue.city if venue else None,
            cinema_address=venue.address if venue else None,
            seat_codes=seats or None,
            quantity=b.quantity or len(seats) or 1,
            unit_price_paise=b.unit_price_paise,
        )


class EventBookingDetail(BaseBookingDetail):
    type: Literal["EVENT"] = "EVENT"
    title: str
    poster_url: str | None = None
    category: str | None = None
    age_restriction: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    city: str | None = None
    tier_name: str | None = None
    tier_price_paise: int | None = None
    quantity: int

    @classmethod
    def from_context(cls, b, ctx) -> "EventBookingDetail":
        event, tier = ctx["event"], ctx["tier"]
        base = BaseBookingDetail.from_domain(b).model_dump()
        return cls(
            **base,
            title=event.title,
            poster_url=event.poster_image_url,
            category=event.category,
            age_restriction=event.age_restriction,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            venue_name=event.venue_name,
            venue_address=event.venue_address,
            city=event.city,
            tier_name=tier.name if tier else None,
            tier_price_paise=tier.price_paise if tier else None,
            quantity=b.quantity or 1,
        )


BookingDetailResponse = MovieBookingDetail | EventBookingDetail | BaseBookingDetail