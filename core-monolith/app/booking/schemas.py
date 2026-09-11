
from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class BookingCreateRequest(BaseModel):
    # Event Booking parameters
    event_id: UUID | None = None
    tier_id: UUID | None = None
    quantity: int | None = Field(default=None, ge=1, le=10)

    # Movie Booking parameters
    showtime_id: UUID | None = None
    seat_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=10)

    # Common
    idempotency_key: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_booking_type(self) -> BookingCreateRequest:
        is_event = self.event_id is not None and self.tier_id is not None and self.quantity is not None
        is_movie = self.showtime_id is not None and self.seat_ids is not None and len(self.seat_ids) > 0

        if not is_event and not is_movie:
            raise ValueError(
                "Must provide either Event parameters (event_id, tier_id, quantity) "
                "or Movie parameters (showtime_id, seat_ids)."
            )
        if is_event and is_movie:
            raise ValueError("Cannot combine Event and Movie bookings in a single request.")
        return self


class ProviderHoldCreateRequest(BaseModel):
    showtime_id: UUID
    seat_ids: list[str] = Field(min_length=1, max_length=10)


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