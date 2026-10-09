from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True, slots=True)
class FnbItem:
    id: uuid.UUID
    venue_id: uuid.UUID
    name: str
    description: Optional[str]
    category: str
    price_paise: int
    image_url: Optional[str]
    is_veg: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class BookingFnbLine:
    item_id: uuid.UUID
    name: str
    quantity: int
    unit_price_paise: int


class FnbItemNotFoundError(Exception):
    """An item_id in the request does not exist or is not active."""


class FnbItemWrongVenueError(Exception):
    """An item_id belongs to a venue other than the showtime's."""


class HoldExpiredError(Exception):
    """Booking is not HELD, or held_until has passed."""


class IFnbRepository(Protocol):
    async def list_by_venue(self, venue_id: uuid.UUID) -> list[FnbItem]: ...

    async def get_many_for_venue(
        self, venue_id: uuid.UUID, item_ids: list[uuid.UUID]
    ) -> list[FnbItem]: ...

    async def list_for_booking(self, booking_id: uuid.UUID) -> list[BookingFnbLine]: ...