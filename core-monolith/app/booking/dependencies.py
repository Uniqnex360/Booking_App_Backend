

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.booking.movie_service import MovieBookingService
from app.booking.repository import BookingRepository, TierCounterRepository
from app.booking.services import BookingService
from app.core.database import get_db


async def get_booking_service(
    session: AsyncSession = Depends(get_db),
) -> BookingService:
    booking_repo = BookingRepository(session)
    counter_repo = TierCounterRepository(session)
    return BookingService(
        booking_repo=booking_repo,
        counter_repo=counter_repo,
        session=session,
    )


async def get_movie_booking_service(
    session: AsyncSession = Depends(get_db),
) -> MovieBookingService:
    return MovieBookingService(session)