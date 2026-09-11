"""
Abstract base and domain types for external cinema ticketing providers.

Contract:
- Zero imports from fastapi / starlette / sqlalchemy / app.booking.
- Provider-domain exceptions only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID


# ---------------------------------------------------------------------------
# Value Objects / DTOs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProviderShowtime:
    provider_showtime_ref: str
    movie_title: str
    screen_name: str
    cinema_name: str
    starts_at: datetime
    language: str | None = None
    certificate: str | None = None
    duration_min: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderSeat:
    seat_ref: str
    row_label: str
    seat_number: int
    seat_code: str
    price_paise: int
    is_available: bool


@dataclass(frozen=True, slots=True)
class ProviderSeatMap:
    showtime_ref: str
    movie_title: str
    screen_name: str
    cinema_name: str
    starts_at: datetime
    seats: list[ProviderSeat]
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderHeldSeat:
    seat_ref: str
    seat_code: str
    price_paise: int


@dataclass(frozen=True, slots=True)
class ProviderHold:
    hold_id: str
    expires_at: datetime
    seats: list[ProviderHeldSeat]
    total_paise: int
    currency: str


@dataclass(frozen=True, slots=True)
class ProviderTicketSeat:
    seat_ref: str
    seat_code: str
    price_paise: int


@dataclass(frozen=True, slots=True)
class ProviderTicket:
    booking_id: str
    ref_code: str
    status: str
    total_paise: int
    currency: str
    seats: list[ProviderTicketSeat]
    created_at: datetime
    barcode: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderHoldState:
    hold_id: str
    showtime_ref: str
    status: str  # ACTIVE | COMMITTED | EXPIRED | RELEASED
    expires_at: datetime
    quote_total_paise: int
    currency: str
    seats: list[ProviderHeldSeat]


# ---------------------------------------------------------------------------
# Provider Exceptions (Domain-level, never inherit HTTPException)
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Base exception for all provider operations."""


class ProviderUnavailable(ProviderError):
    """Upstream provider is unreachable, timed out, or returning 5xx."""


class SeatUnavailableRemote(ProviderError):
    """One or more requested seats are not available on the upstream provider."""

    def __init__(self, seats: list[str]) -> None:
        super().__init__(f"Seats unavailable remotely: {', '.join(seats)}")
        self.seats = seats


class HoldExpiredRemote(ProviderError):
    """Hold expired on the upstream provider."""


class HoldAlreadyCommitted(ProviderError):
    """Hold was already committed on the upstream provider."""

    def __init__(self, booking_ref: str | None = None, booking_id: str | None = None) -> None:
        super().__init__(f"Hold already committed (ref: {booking_ref}, id: {booking_id})")
        self.booking_ref = booking_ref
        self.booking_id = booking_id


class ProviderContractError(ProviderError):
    """Provider response violates expected shape or could not be parsed."""

    def __init__(self, message: str, raw_body: str | None = None) -> None:
        truncated = (raw_body[:500] + "...") if raw_body and len(raw_body) > 500 else raw_body
        super().__init__(f"{message} (raw: {truncated})")
        self.raw_body = truncated


# ---------------------------------------------------------------------------
# Provider Interface Port
# ---------------------------------------------------------------------------

class ITheatreProvider(ABC):
    @abstractmethod
    async def list_showtimes(self, target_date: date) -> list[ProviderShowtime]:
        """List showtimes on a given date."""
        ...

    @abstractmethod
    async def seat_map(self, showtime_ref: str) -> ProviderSeatMap:
        """Fetch real-time seat map and availability."""
        ...

    @abstractmethod
    async def hold(
        self,
        showtime_ref: str,
        seat_refs: list[str],
        idem_key: str,
        end_user_ref: str | None,
    ) -> ProviderHold:
        """Place a temporary hold on seats."""
        ...

    @abstractmethod
    async def commit(
        self, hold_id: str, payment_ref: str | None = None
    ) -> ProviderTicket:
        """Commit an active hold into a confirmed ticket."""
        ...

    @abstractmethod
    async def release(self, hold_id: str) -> None:
        """Release a hold idempotently."""
        ...

    @abstractmethod
    async def hold_state(self, hold_id: str) -> ProviderHoldState:
        """Query the remote status of a hold."""
        ...

    @abstractmethod
    async def bookings_between(
        self, start: datetime, end: datetime
    ) -> list[ProviderTicket]:
        """Fetch all confirmed provider bookings in a time range for reconciliation."""
        ...