"""SQLAlchemy repository implementation for Bookings."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.booking.interfaces import (
    Booking,
    BookingStatus,
    IBookingRepository,
    ITierCounterRepository,
    TierInfo,
)
from app.booking.models import BookingModel, TicketSoldCountModel
from app.event.models import EventORM, TicketCategoryORM
from app.shared.timeutil import utcnow


class BookingRepository(IBookingRepository):

    async def get_user_bookings(self, user_id: UUID) -> list[Booking]:
        res = await self.session.execute(
            select(BookingModel)
            .where(BookingModel.user_id == user_id)
            .order_by(BookingModel.created_at.desc())
        )
        rows = res.scalars().all()
        return [self._to_domain(r) for r in rows]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, booking_id: UUID) -> Optional[Booking]:
        res = await self.session.execute(
            select(BookingModel).where(BookingModel.id == booking_id)
        )
        row = res.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_by_idempotency(
        self, user_id: UUID, idempotency_key: str
    ) -> Optional[Booking]:
        result = await self.session.execute(
            select(BookingModel).where(
                BookingModel.user_id == user_id,
                BookingModel.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def create(self, b: Booking) -> Booking:
        seat_refs_str = json.dumps(b.seat_refs) if b.seat_refs else None
        seat_codes_str = json.dumps(b.seat_codes) if b.seat_codes else None
        model = BookingModel(
            id=b.id,
            user_id=b.user_id,
            booking_type="MOVIE" if b.showtime_id else "EVENT",
            event_id=b.event_id,
            tier_id=b.tier_id,
            showtime_id=b.showtime_id,
            provider_id=b.provider_id,
            provider_hold_id=b.provider_hold_id,
            provider_booking_id=b.provider_booking_id,
            held_until=b.held_until,
            currency=b.currency,
            ref_code=b.ref_code,
            quantity=b.quantity,
            unit_price_paise=b.unit_price_paise,
            total_paise=b.total_paise,
            status=b.status.value,
            idempotency_key=b.idempotency_key,
            barcode=b.barcode,
            seat_refs_json=seat_refs_str,
            seat_codes_json=seat_codes_str,
            contact_email=b.contact_email,          
            contact_phone=b.contact_phone, 
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def update_status(
        self, booking_id: UUID, old_status: BookingStatus, new_status: BookingStatus
    ) -> bool:
        res = await self.session.execute(
            update(BookingModel)
            .where(
                BookingModel.id == booking_id,
                BookingModel.status == old_status.value,
            )
            .values(status=new_status.value)
        )
        return res.rowcount > 0
    async def get_booking_with_context(
        self, booking_id: UUID
    ) -> Optional[tuple[Booking, Optional[dict]]]:
       
        from app.movie.models import Showtime, Movie, Screen, Venue

        stmt = (
            select(
                BookingModel,
                Showtime, Movie, Screen, Venue,
                EventORM, TicketCategoryORM,
            )
            .select_from(BookingModel)
            .outerjoin(Showtime, BookingModel.showtime_id == Showtime.id)
            .outerjoin(Movie, Showtime.movie_id == Movie.id)
            .outerjoin(Screen, Showtime.screen_id == Screen.id)
            .outerjoin(Venue, Screen.venue_id == Venue.id)
            .outerjoin(EventORM, BookingModel.event_id == EventORM.id)
            .outerjoin(TicketCategoryORM, BookingModel.tier_id == TicketCategoryORM.id)
            .where(BookingModel.id == booking_id)
        )
        row = (await self.session.execute(stmt)).first()
        if not row:
            return None

        b_model, st, movie, screen, venue, event, tier = row
        booking = self._to_domain(b_model)

        context: Optional[dict] = None
        if movie and st:
            context = {
                "kind": "MOVIE",
                "showtime": st,
                "movie": movie,
                "screen": screen,
                "venue": venue,
            }
        elif event:
            context = {
                "kind": "EVENT",
                "event": event,
                "tier": tier,
            }

        return booking, context
    async def update_booking(self, b: Booking) -> Booking:
        seat_refs_str = json.dumps(b.seat_refs) if b.seat_refs else None
        await self.session.execute(
            update(BookingModel)
            .where(BookingModel.id == b.id)
            .values(
                status=b.status.value,
                provider_booking_id=b.provider_booking_id,
                barcode=b.barcode,
                held_until=b.held_until,
                ref_code=b.ref_code,
                total_paise=b.total_paise,
                seat_refs_json=seat_refs_str,
            )
        )
        await self.session.flush()
        return b

    async def get_expired_held_bookings(self) -> list[Booking]:
        now = utcnow()
        res = await self.session.execute(
            select(BookingModel).where(
                BookingModel.status == BookingStatus.HELD.value,
                BookingModel.held_until < now,
            )
        )
        rows = res.scalars().all()
        return [self._to_domain(r) for r in rows]

    def _to_domain(self, m: BookingModel) -> Booking:
        seat_refs = None
        if m.seat_refs_json:
            try:
                seat_refs = json.loads(m.seat_refs_json)
            except Exception:
                seat_refs = None

        seat_codes = None
        if m.seat_codes_json:
            try:
                seat_codes = json.loads(m.seat_codes_json)
            except Exception:
                seat_codes = None

        return Booking(
            id=m.id,
            user_id=m.user_id,
            event_id=m.event_id,
            tier_id=m.tier_id,
            showtime_id=m.showtime_id,
            provider_id=m.provider_id,
            provider_hold_id=m.provider_hold_id,
            provider_booking_id=m.provider_booking_id,
            held_until=m.held_until,
            currency=m.currency or "INR",
            quantity=m.quantity,
            unit_price_paise=m.unit_price_paise,
            total_paise=m.total_paise,
            status=BookingStatus(m.status),
            ref_code=m.ref_code,
            idempotency_key=m.idempotency_key,
            created_at=m.created_at,
            barcode=m.barcode,
            seat_refs=seat_refs,
            seat_codes=seat_codes,
            contact_email=m.contact_email,      
            contact_phone=m.contact_phone,
        )


class TierCounterRepository(ITierCounterRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_tier_info(self, tier_id: UUID) -> Optional[TierInfo]:
        stmt = (
            select(TicketCategoryORM, EventORM)
            .join(EventORM)
            .where(TicketCategoryORM.id == tier_id)
        )
        res = await self.session.execute(stmt)
        row = res.fetchone()
        if not row:
            return None
        tier, event = row
        return TierInfo(
            id=tier.id,
            event_id=event.id,
            event_status=event.status,
            is_active=tier.is_active,
            max_per_booking=tier.max_per_booking,
            price_paise=tier.price_paise,
            capacity=tier.capacity,
            sales_open_at=tier.sales_open_at,
            sales_close_at=tier.sales_close_at,
        )

    async def ensure_counter_row(self, tier_id: UUID):
        stmt = text("""
            INSERT INTO ticket_sold_counts (tier_id, sold) VALUES (:t, 0)
            ON CONFLICT (tier_id) DO NOTHING
        """)
        await self.session.execute(stmt, {"t": tier_id})

    async def increment(self, tier_id: UUID, quantity: int) -> bool:
        stmt = text("""
            UPDATE ticket_sold_counts SET sold = sold + :q
            WHERE tier_id = :t
              AND sold + :q <= (SELECT capacity FROM event_ticket_categories WHERE id = :t)
        """)
        res = await self.session.execute(stmt, {"q": quantity, "t": tier_id})
        await self.session.flush()
        return res.rowcount > 0

    async def decrement(self, tier_id: UUID, quantity: int) -> bool:
        stmt = text("""
            UPDATE ticket_sold_counts SET sold = sold - :q
            WHERE tier_id = :t AND sold >= :q
        """)
        res = await self.session.execute(stmt, {"q": quantity, "t": tier_id})
        return res.rowcount > 0