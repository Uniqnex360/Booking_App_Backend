from __future__ import annotations

import dataclasses
import hmac
from uuid import UUID

from fastapi import Depends, Header, Query, Request
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
from app.booking.interfaces import BookingStatus


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
    booking_token: str | None = None,
    ref_code: str | None = None,
    is_write: bool = False,
) -> Booking:
    """Resolve the acting identity for a booking.

    User-owned booking: requires current_user matching booking.user_id.
    Guest-owned booking: requires matching X-Hold-Token, signed booking token, or matching ref code.
    Ref code and booking token are strictly limited to read-only (GET) requests.
    Any mismatch or missing credential raises BookingNotFoundError (404).
    """
    booking = await booking_service.get_booking_for_actor(booking_id)
    if booking is None:
        raise BookingNotFoundError()

    # 0. Admin access: Admins can view any booking with full privileges
    user_role = getattr(current_user, "role", None)
    if user_role and (user_role == "ADMIN" or getattr(user_role, "value", None) == "ADMIN"):
        return dataclasses.replace(booking, actor_role="ADMIN")

    # 1. User-owned booking: if user is authenticated and matches booking owner
    if booking.user_id is not None:
        if current_user is not None and current_user.id == booking.user_id:
            return dataclasses.replace(booking, actor_role="OWNER")

    # 2. Hold-token authentication (valid for guest bookings or user holding sessions)
    if x_hold_token and booking.hold_token_hash:
        if verify_hold_token(x_hold_token, booking.hold_token_hash):
            if booking.status == BookingStatus.HELD:
                if booking.hold_token_expires_at and booking.hold_token_expires_at <= utcnow():
                    raise BookingNotFoundError()
            return dataclasses.replace(booking, actor_role="GUEST")

    # Read-only access (ref_code cannot mutate bookings)
    if not is_write:
        # 3. Confirmed booking reference code (e.g. confirmation page with ?ref=... or ?ref_code=...)
        if ref_code and booking.status == BookingStatus.CONFIRMED and booking.ref_code:
            if hmac.compare_digest(ref_code.strip(), booking.ref_code.strip()):
                if booking.id != booking_id:
                    raise BookingNotFoundError()
                return dataclasses.replace(booking, actor_role="GUEST")

    # If no identity check succeeded, deny access
    raise BookingNotFoundError()


async def get_booking_actor(
    request: Request,
    booking_id: UUID,
    x_hold_token: str | None = Header(default=None, alias="X-Hold-Token"),
    ref: str | None = Query(default=None, alias="ref"),
    ref_code: str | None = Query(default=None, alias="ref_code"),
    current_user: AuthUserDomain | None = Depends(get_current_user_optional),
    booking_service: BookingService = Depends(get_booking_service),
) -> Booking:
    is_write = request.method not in ("GET", "HEAD")
    effective_ref = ref or ref_code
    return await resolve_actor(
        booking_id=booking_id,
        x_hold_token=x_hold_token,
        current_user=current_user,
        booking_service=booking_service,
        ref_code=effective_ref,
        is_write=is_write,
    )