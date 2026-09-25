"""
Booking module interfaces, domain entities, exceptions, and state machine transitions.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID
from app.shared.exceptions import DomainError, EntityNotFoundError
MAX_SEATS_PER_BOOKING = 10
class BookingStatus(str, Enum):
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
VALID_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.HELD: {
        BookingStatus.CONFIRMED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
        BookingStatus.PENDING_CONFIRMATION,
    },
    BookingStatus.CONFIRMED: {
        BookingStatus.CANCELLED,
    },
    BookingStatus.PENDING_CONFIRMATION: {
        BookingStatus.CONFIRMED,
        BookingStatus.CANCELLED,
    },
    BookingStatus.CANCELLED: set(),
    BookingStatus.EXPIRED: set(),
}
def can_transition(current: BookingStatus, target: BookingStatus) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())
@dataclass(frozen=True)
class TierInfo:
    id: UUID
    event_id: UUID
    event_status: str
    is_active: bool
    max_per_booking: int
    price_paise: int
    capacity: int
    sales_open_at: Optional[datetime]
    sales_close_at: Optional[datetime]
    event_ends_at: Optional[datetime] = None
    event_starts_at: Optional[datetime] = None
@dataclass(frozen=True)
class Booking:
    id: UUID
    user_id: Optional[UUID] 
    status: BookingStatus
    total_paise: int
    created_at: datetime
    currency: str = "INR"
    event_id: Optional[UUID] = None
    tier_id: Optional[UUID] = None
    showtime_id: Optional[UUID] = None
    provider_id: Optional[UUID] = None
    provider_hold_id: Optional[str] = None
    provider_booking_id: Optional[str] = None
    held_until: Optional[datetime] = None
    quantity: Optional[int] = None
    unit_price_paise: Optional[int] = None
    ref_code: Optional[str] = None
    idempotency_key: Optional[str] = None
    barcode: Optional[str] = None
    seat_refs: Optional[list[str]] = None
    seat_codes: Optional[list[str]] = None
    contact_email: Optional[str] = None      
    contact_phone: Optional[str] = None 
class ValidationError(ValueError, DomainError):
    pass
class SoldOutError(DomainError):
    def __init__(self) -> None:
        super().__init__("Ticket tier is sold out")
class EventNotBookableError(DomainError):
    def __init__(self) -> None:
        super().__init__("Event is not in a bookable state (must be PUBLISHED)")
class EventConcludedError(DomainError):
    def __init__(self, message: str = "This event has already ended") -> None:
        super().__init__(message)
class TierInactiveError(DomainError):
    def __init__(self) -> None:
        super().__init__("This ticket tier is currently inactive")
class SalesClosedError(DomainError):
    def __init__(self) -> None:
        super().__init__("Sales for this tier are either not open yet or have closed")
class QuantityExceedsMaxError(DomainError):
    def __init__(self) -> None:
        super().__init__("Requested quantity exceeds the maximum allowed per booking")
class BookingNotFoundError(EntityNotFoundError):
    def __init__(self) -> None:
        super().__init__("Booking not found")
class BookingNotCancellableError(ValidationError):
    def __init__(self, message: str = "Booking cannot be cancelled in its current state") -> None:
        super().__init__(message)
class IllegalBookingTransition(DomainError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(f"Cannot transition booking from {from_status} to {to_status}")
        self.from_status = from_status
        self.to_status = to_status
class ShowtimeNotFoundError(EntityNotFoundError):
    def __init__(self, message: str = "Showtime not found") -> None:
        super().__init__(message)
class ShowtimeNotProviderError(DomainError):
    def __init__(self, message: str = "Showtime is self-hosted, not an external provider showtime") -> None:
        super().__init__(message)
class ShowtimeDisabledError(DomainError):
    def __init__(self, message: str = "Provider or showtime is disabled") -> None:
        super().__init__(message)
class IBookingRepository(ABC):
    @abstractmethod
    async def get_by_id(self, booking_id: UUID) -> Optional[Booking]: ...
    @abstractmethod
    async def get_by_idempotency(self, user_id: UUID, key: str) -> Optional[Booking]: ...
    @abstractmethod
    async def get_booking_with_context(
        self, booking_id: UUID
    ) -> Optional[tuple[Booking, Optional[dict]]]: ...
    @abstractmethod
    async def create(self, booking: Booking) -> Booking: ...
    @abstractmethod
    async def update_status(
        self, booking_id: UUID, old_status: BookingStatus, new_status: BookingStatus
    ) -> bool: ...
    @abstractmethod
    async def update_booking(self, booking: Booking) -> Booking: ...
    @abstractmethod
    async def get_expired_held_bookings(self) -> list[Booking]: ...
class ITierCounterRepository(ABC):
    @abstractmethod
    async def get_tier_info(self, tier_id: UUID) -> Optional[TierInfo]: ...
    @abstractmethod
    async def ensure_counter_row(self, tier_id: UUID): ...
    @abstractmethod
    async def increment(self, tier_id: UUID, quantity: int) -> bool: ...
    @abstractmethod
    async def decrement(self, tier_id: UUID, quantity: int) -> bool: ...