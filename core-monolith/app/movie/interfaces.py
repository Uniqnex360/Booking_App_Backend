"""
Ports, domain exceptions, and value objects for the Movie Module.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.shared.exceptions import (
    DomainError,
    EntityNotFoundError,
    ForbiddenError,
)


class MovieStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SeatStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Value Objects / DTOs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MovieSummaryDTO:
    id: UUID
    title: str
    original_title: str | None
    language: str
    duration_min: int
    certificate: str
    release_date: datetime | None
    poster_url: str | None
    banner_url: str | None 
    status: str
    genre: str | None = None    


@dataclass(frozen=True, slots=True)
class ShowtimeSlotDTO:
    id: UUID
    screen_id: UUID
    screen_name: str
    starts_at: datetime
    language: str
    format: str
    status: str


@dataclass(frozen=True, slots=True)
class VenueShowtimesDTO:
    venue_id: UUID
    venue_name: str
    city: str
    address: str | None
    showtimes: list[ShowtimeSlotDTO]


@dataclass(frozen=True, slots=True)
class MovieDetailsDTO:
    id: UUID
    title: str
    original_title: str | None
    language: str
    duration_min: int
    certificate: str
    release_date: datetime | None
    poster_url: str | None
    banner_url: str | None 
    trailer_url: str | None
    synopsis: str | None
    status: str
    venues: list[VenueShowtimesDTO]
    genre: str | None = None   
    


@dataclass(frozen=True, slots=True)
class SeatProjectionDTO:
    seat_id: UUID
    number: int
    code: str
    x: int
    label: str | None
    status: SeatStatus
    price_paise: int


@dataclass(frozen=True, slots=True)
class RowProjectionDTO:
    row_id: UUID
    label: str
    section: str | None
    price_paise: int
    seats: list[SeatProjectionDTO]


@dataclass(frozen=True, slots=True)
class SeatMapDTO:
    showtime_id: UUID
    movie_id: UUID
    movie_title: str
    venue_name: str
    screen_name: str
    starts_at: datetime
    format: str
    language: str
    rows: list[RowProjectionDTO]


@dataclass(frozen=True, slots=True)
class ShowtimeAvailabilityDTO:
    showtime_id: UUID
    total_seats: int
    available_seats: int
    booked_seats: int
    blocked_seats: int
    locked_seats: int = 0


# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------

class MovieNotFoundError(EntityNotFoundError):
    """Movie entity not found."""


class ShowtimeNotFoundError(EntityNotFoundError):
    """Showtime entity not found."""


class ScreenNotFoundError(EntityNotFoundError):
    """Screen entity not found."""


class VenueNotFoundError(EntityNotFoundError):
    """Venue entity not found."""


class SeatNotFoundError(EntityNotFoundError):
    """Seat entity not found."""


class PartnerOwnershipError(ForbiddenError):
    """Partner does not own this resource."""


class UnapprovedPartnerError(ForbiddenError):
    """Partner is not approved to perform this action."""


class MovieNotPublishedError(DomainError):
    """Showtime cannot be created for an unpublished movie."""


class ScreenLayoutLockedError(DomainError):
    """M12: Screen layout cannot be modified when active seat states exist."""


class SeatAlreadyBookedError(DomainError):
    """Seat is already booked and cannot be blocked."""


# ---------------------------------------------------------------------------
# Repository Port
# ---------------------------------------------------------------------------

@runtime_checkable
class IMovieRepository(Protocol):
    async def list_movies(
        self,
        *,
        city: str | None = None,
        language: str | None = None,
        format: str | None = None,
        target_date: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[MovieSummaryDTO], int]: ...

    async def get_movie_details(self, movie_id: UUID) -> MovieDetailsDTO | None: ...

    async def get_seat_map(self, showtime_id: UUID) -> SeatMapDTO | None: ...

    async def get_showtime_availability(
        self, showtime_id: UUID
    ) -> ShowtimeAvailabilityDTO | None: ...

    async def create_movie(
        self,
        *,
        title: str,
        original_title: str | None,
        language: str,
        duration_min: int,
        certificate: str,
        partner_id: UUID,
        poster_url: str | None = None,
        banner_url: str | None = None,      
        synopsis: str | None = None,
    ) -> MovieSummaryDTO: ...

    async def update_movie(
        self, movie_id: UUID, partner_id: UUID, updates: dict
    ) -> MovieSummaryDTO: ...

    async def update_movie_status(
        self, movie_id: UUID, new_status: str
    ) -> MovieSummaryDTO: ...

    async def create_screen(
        self, venue_id: UUID, name: str, partner_id: UUID
    ) -> UUID: ...

    async def apply_screen_layout(
        self, screen_id: UUID, parsed_rows: list, is_admin_override: bool = False
    ) -> int: ...

    async def create_showtime(
        self,
        *,
        screen_id: UUID,
        movie_id: UUID,
        starts_at: datetime,
        language: str,
        format: str,
        partner_id: UUID,
    ) -> UUID: ...

    async def cancel_showtime(
        self, showtime_id: UUID, partner_id: UUID
    ) -> bool: ...

    async def block_seats(
        self, showtime_id: UUID, seat_ids: list[UUID], reason: str
    ) -> bool: ...

    async def unblock_seats(
        self, showtime_id: UUID, seat_ids: list[UUID]
    ) -> bool: ...
