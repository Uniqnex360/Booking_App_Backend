from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user_optional
from app.auth.interfaces import User as AuthUserDomain
from app.auth.otp_service import NotificationService
from app.booking.hold_token import verify as verify_hold_token
from app.booking.interfaces import Booking, BookingNotFoundError
from app.booking.movie_service import MovieBookingService
from app.booking.repository import BookingRepository, TierCounterRepository
from app.booking.services import BookingService
from app.core.database import get_db
from app.shared.timeutil import utcnow


async def get_booking_service(
    session: AsyncSession = Depends(get_db),
) -> BookingService:
    booking_repo = BookingRepository(session)
    counter_repo = TierCounterRepository(session)
    return BookingService(
        booking_repo=booking_repo,
        counter_repo=counter_repo,
        session=session,
        notification=NotificationService(),
    )


async def get_movie_booking_service(
    session: AsyncSession = Depends(get_db),
) -> MovieBookingService:
    return MovieBookingService(session)

async def resolve_actor(
    booking_id: UUID,
    x_hold_token: str | None,
    current_user: AuthUserDomain | None,
    booking_service: BookingService,
) -> Booking:
    """Resolve the acting identity for a booking.

    User-owned booking: requires current_user matching booking.user_id.
    Guest-owned booking: requires matching X-Hold-Token.
    Any mismatch or missing credential raises BookingNotFoundError (404).
    """
    booking = await booking_service.get_booking_for_actor(booking_id)
    if booking is None:
        raise BookingNotFoundError()

    if booking.user_id is not None:
        if current_user is not None and current_user.id == booking.user_id:
            return booking
        raise BookingNotFoundError()

    if not x_hold_token or not booking.hold_token_hash:
        raise BookingNotFoundError()
    if booking.hold_token_expires_at and booking.hold_token_expires_at <= utcnow():
        raise BookingNotFoundError()
    if not verify_hold_token(x_hold_token, booking.hold_token_hash):
        raise BookingNotFoundError()

    return booking


async def get_booking_actor(
    booking_id: UUID,
    x_hold_token: str | None = Header(default=None, alias="X-Hold-Token"),
    current_user: AuthUserDomain | None = Depends(get_current_user_optional),
    booking_service: BookingService = Depends(get_booking_service),
) -> Booking:
    return await resolve_actor(booking_id, x_hold_token, current_user, booking_service)