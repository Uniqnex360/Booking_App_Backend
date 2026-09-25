
from __future__ import annotations

import uuid
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.booking.interfaces import BookingNotFoundError, BookingNotCancellableError, ValidationError
from app.booking.models import BookingModel
from app.movie.interfaces import (
    SeatAlreadyBookedError,
    SeatNotFoundError,
    ShowtimeNotFoundError,
)
from app.movie.models import Movie, MovieSoldCount, MovieStatus, Screen, ScreenRow, Seat, SeatState, SeatStateStatus, Showtime, ShowtimeStatus
from app.shared.timeutil import utcnow
import logging
logger = logging.getLogger(__name__)

class MovieBookingService:
    def __init__(self, session: AsyncSession):
        self.session = session
    async def _resolve_provider_client(self, showtime_id: UUID):
        from app.movie.models import Showtime as ShowtimeModel
        from app.shared.providers.registry import (
            ProviderRegistryModel,
            create_provider_client,
        )
        st = (await self.session.execute(
            select(ShowtimeModel).where(ShowtimeModel.id == showtime_id)
        )).scalar_one_or_none()
        if not st or not st.provider_id:
            return None
        registry = (await self.session.execute(
            select(ProviderRegistryModel).where(
                ProviderRegistryModel.id == st.provider_id
            )
        )).scalar_one_or_none()
        if not registry:
            return None
        return create_provider_client(registry)
    async def create_booking(
        self,
        user_id: UUID,
        showtime_id: UUID,
        seat_ids: list[UUID],
        idempotency_key: Optional[str] = None,
    ) -> BookingModel:
        
        if idempotency_key:
            existing = await self.session.execute(
                select(BookingModel).where(
                    BookingModel.idempotency_key == idempotency_key,
                    BookingModel.user_id == user_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                return row

        
        st_stmt = select(Showtime, Movie).join(Movie, Showtime.movie_id == Movie.id).where(Showtime.id == showtime_id)
        st_res = await self.session.execute(st_stmt)
        st_row = st_res.first()
        if not st_row:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")
        showtime, movie = st_row

        if showtime.provider_id is not None:
            raise ValidationError("Showtime is provider-backed. Use /v1/bookings/hold instead.")

        
        if showtime.status != ShowtimeStatus.ACTIVE.value:
            raise ValidationError("Showtime is not ACTIVE")

        
        if not seat_ids:
            raise ValidationError("Must select at least 1 seat")
        if len(seat_ids) != len(set(seat_ids)):
            raise ValidationError("Duplicate seat IDs in selection")
        if len(seat_ids) > 10:
            raise ValidationError("Cannot book more than 10 seats")

        seats_stmt = (
            select(Seat, ScreenRow)
            .join(ScreenRow, Seat.row_id == ScreenRow.id)
            .where(
                Seat.id.in_(seat_ids),
                ScreenRow.screen_id == showtime.screen_id,
            )
        )
        rows = (await self.session.execute(seats_stmt)).all()
        if len(rows) != len(seat_ids):
            raise SeatNotFoundError("One or more seats do not belong to this screen")

        total_paise = sum(row.price_paise for _, row in rows)
        booking_id = uuid.uuid4()
        ref_code = f"BK{uuid.uuid4().hex[:8].upper()}"

        booking = BookingModel(
            id=booking_id,
            user_id=user_id,
            booking_type="MOVIE",
            showtime_id=showtime_id,
            ref_code=ref_code,
            total_paise=total_paise,
            status="CONFIRMED",
            idempotency_key=idempotency_key,
        )

        try:
            self.session.add(booking)
            for seat, _ in rows:
                self.session.add(
                    SeatState(
                        showtime_id=showtime_id,
                        seat_id=seat.id,
                        status=SeatStateStatus.BOOKED.value,
                        booking_id=booking_id,
                    )
                )
            await self.session.flush()

            
            for seat, row in rows:
                sold_row = (await self.session.execute(
                    select(MovieSoldCount).where(
                        MovieSoldCount.showtime_id == showtime_id,
                        MovieSoldCount.row_id == row.id,
                    )
                )).scalar_one_or_none()
                if not sold_row:
                    self.session.add(MovieSoldCount(showtime_id=showtime_id, row_id=row.id, sold_count=1))
                else:
                    sold_row.sold_count += 1

            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if idempotency_key:
                existing = await self.session.execute(
                    select(BookingModel).where(
                        BookingModel.idempotency_key == idempotency_key,
                        BookingModel.user_id == user_id,
                    )
                )
                row = existing.scalar_one_or_none()
                if row:
                    return row
            raise SeatAlreadyBookedError("One or more seats are already booked or blocked") from exc

        return booking

    async def cancel_booking(self, booking_id: UUID, user_id: UUID) -> BookingModel:
        row = (
            await self.session.execute(select(BookingModel).where(BookingModel.id == booking_id))
        ).scalar_one_or_none()

        if not row or row.user_id != user_id:
            raise BookingNotFoundError()

        if row.status != "CONFIRMED":
            raise BookingNotCancellableError()

        row.status = "CANCELLED"

        states = (await self.session.execute(
            select(SeatState, Seat.row_id)
            .join(Seat, SeatState.seat_id == Seat.id)
            .where(SeatState.booking_id == booking_id)
        )).all()

        for _, row_id in states:
            sold_row = (await self.session.execute(
                select(MovieSoldCount).where(
                    MovieSoldCount.showtime_id == row.showtime_id,
                    MovieSoldCount.row_id == row_id,
                )
            )).scalar_one_or_none()
            if sold_row and sold_row.sold_count > 0:
                sold_row.sold_count -= 1

                await self.session.execute(
            delete(SeatState).where(SeatState.booking_id == booking_id)
        )
        await self.session.commit()

        if row.provider_id and row.provider_booking_id and row.showtime_id:
            try:
                provider = await self._resolve_provider_client(row.showtime_id)
                if provider is not None:
                    await provider.cancel_booking(row.provider_booking_id)
                    logger.info(
                        "Provider cancel succeeded for booking %s "
                        "(provider_booking_id=%s)",
                        row.id, row.provider_booking_id,
                    )
                else:
                    logger.warning(
                        "No provider client resolvable for booking %s "
                        "(provider_id=%s, showtime_id=%s)",
                        row.id, row.provider_id, row.showtime_id,
                    )
            except Exception as exc:
                logger.warning(
                    "Provider cancel failed for booking %s "
                    "(provider_id=%s, provider_booking_id=%s): %s — "
                    "local cancel stands, reconciliation required",
                    row.id, row.provider_id, row.provider_booking_id, exc,
                )

        return row
