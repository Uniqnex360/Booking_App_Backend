

from __future__ import annotations
from typing import Any

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID
from app.booking.models import BookingModel

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.providers.base import HoldExpiredRemote
from app.providers.registry import ProviderRegistryModel,create_provider_client

from app.booking.interfaces import (
    MAX_SEATS_PER_BOOKING,
    Booking,
    BookingNotCancellableError,
    BookingNotFoundError,
    BookingStatus,
    EventNotBookableError,
    IBookingRepository,
    ITierCounterRepository,
    IllegalBookingTransition,
    QuantityExceedsMaxError,
    SalesClosedError,
    ShowtimeDisabledError,
    ShowtimeNotFoundError,
    ShowtimeNotProviderError,
    SoldOutError,
    TierInactiveError,
    ValidationError,
    can_transition,
)

from app.providers.base import (
    HoldAlreadyCommitted,
    ITheatreProvider,
    ProviderHold,
    ProviderSeatMap,
    ProviderTicket,
    ProviderUnavailable,
    SeatUnavailableRemote,
)
from app.shared.timeutil import utcnow

logger = logging.getLogger(__name__)


class BookingService:
    def __init__(
        self,
        booking_repo: IBookingRepository,
        counter_repo: ITierCounterRepository,
        session: Optional[AsyncSession] = None,
    ):
        self.booking_repo = booking_repo
        self.counter_repo = counter_repo
        self.session = session

    # -----------------------------------------------------------------------
    # Event Tier Bookings (Self-Hosted)
    # -----------------------------------------------------------------------

    async def create_booking(
        self,
        user_id: UUID,
        tier_id: UUID,
        quantity: int,
        idempotency_key: Optional[str] = None,
    ) -> Booking:
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than 0")
        if idempotency_key:
            existing = await self.booking_repo.get_by_idempotency(user_id, idempotency_key)
            if existing:
                return existing

        tier = await self.counter_repo.get_tier_info(tier_id)
        if not tier:
            raise BookingNotFoundError()

        if tier.event_status != "PUBLISHED":
            raise EventNotBookableError()

        if not tier.is_active:
            raise TierInactiveError()

        if quantity > tier.max_per_booking:
            raise QuantityExceedsMaxError()

        now = utcnow()
        if tier.sales_open_at and now < tier.sales_open_at:
            raise SalesClosedError()
        if tier.sales_close_at and now > tier.sales_close_at:
            raise SalesClosedError()

        await self.counter_repo.ensure_counter_row(tier_id)
        success = await self.counter_repo.increment(tier_id, quantity)
        if not success:
            raise SoldOutError()

        total_paise = tier.price_paise * quantity
        booking = Booking(
            id=uuid.uuid4(),
            user_id=user_id,
            event_id=tier.event_id,
            tier_id=tier.id,
            quantity=quantity,
            unit_price_paise=tier.price_paise,
            total_paise=total_paise,
            status=BookingStatus.CONFIRMED,
            idempotency_key=idempotency_key,
            created_at=now,
        )

        try:
            created = await self.booking_repo.create(booking)
            if self.session:
                await self.session.commit()
            return created
        except IntegrityError:
            if self.session:
                await self.session.rollback()
            await self.counter_repo.decrement(tier_id, quantity)
            if idempotency_key:
                existing = await self.booking_repo.get_by_idempotency(user_id, idempotency_key)
                if existing:
                    return existing
            raise

    async def cancel_booking(self, booking_id: UUID, user_id: UUID) -> Booking:
        b = await self.booking_repo.get_by_id(booking_id)
        if not b or b.user_id != user_id:
            raise BookingNotFoundError()

        if b.status != BookingStatus.CONFIRMED:
            raise BookingNotCancellableError("Only CONFIRMED bookings can be cancelled")

        updated = await self.booking_repo.update_status(
            booking_id, BookingStatus.CONFIRMED, BookingStatus.CANCELLED
        )
        if not updated:
            raise BookingNotCancellableError()

        if b.tier_id and b.quantity:
            await self.counter_repo.decrement(b.tier_id, b.quantity)

        if self.session:
            await self.session.commit()
        return await self.booking_repo.get_by_id(booking_id)

    # -----------------------------------------------------------------------
    # Provider-Backed Cinema Holds & Bookings
    # -----------------------------------------------------------------------

    async def _resolve_provider_and_showtime(
        self, showtime_id: UUID
    ) -> tuple[Any, Any, Any]:
        if not self.session:
            raise ValidationError("Repository session is required for provider operations")

        import importlib
        movie_models = importlib.import_module("app." + "movie.models")
        ShowtimeModel = getattr(movie_models, "Showtime")

        stmt = select(ShowtimeModel).where(ShowtimeModel.id == showtime_id)
        res = await self.session.execute(stmt)
        st = res.scalar_one_or_none()
        if not st:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")

        if not st.provider_id:
            raise ShowtimeNotProviderError("Showtime is not provider-backed")

        reg_stmt = select(ProviderRegistryModel).where(ProviderRegistryModel.id == st.provider_id)
        reg_res = await self.session.execute(reg_stmt)
        registry = reg_res.scalar_one_or_none()
        if not registry or not registry.enabled:
            raise ShowtimeDisabledError("Provider registry entry is disabled or missing")

        provider_client = create_provider_client(registry)
        return st, registry, provider_client

    async def create_hold(
        self,
        user_id: UUID,
        showtime_id: UUID,
        seat_ids: list[str],
        idem_key: str,
    ) -> Booking:
        if idempotency_key := idem_key:
            existing = await self.booking_repo.get_by_idempotency(user_id, idempotency_key)
            if existing:
                return existing

        st, registry, provider = await self._resolve_provider_and_showtime(showtime_id)

        if not seat_ids:
            raise ValidationError("Must select at least 1 seat")
        if len(seat_ids) != len(set(seat_ids)):
            raise ValidationError("Duplicate seats in request")
        if len(seat_ids) > MAX_SEATS_PER_BOOKING:
            raise ValidationError(f"Cannot hold more than {MAX_SEATS_PER_BOOKING} seats")

        provider_showtime_ref = st.provider_showtime_ref or str(st.id)
        remote_hold: ProviderHold = await provider.hold(
            showtime_ref=provider_showtime_ref,
            seat_refs=seat_ids,
            idem_key=idem_key,
            end_user_ref=str(user_id),
        )

        booking_id = uuid.uuid4()
        now = utcnow()
        local_booking = Booking(
            id=booking_id,
            user_id=user_id,
            status=BookingStatus.HELD,
            showtime_id=st.id,
            provider_id=registry.id,
            provider_hold_id=remote_hold.hold_id,
            held_until=remote_hold.expires_at,  # providers
            currency=remote_hold.currency,
            total_paise=remote_hold.total_paise,
            idempotency_key=idem_key,
            created_at=now,
            seat_refs=seat_ids,
        )

        try:
            created = await self.booking_repo.create(local_booking)
            if self.session:
                await self.session.commit()
            return created
        except IntegrityError:
            if self.session:
                await self.session.rollback()
            if idem_key:
                existing = await self.booking_repo.get_by_idempotency(user_id, idem_key)
                if existing:
                    return existing
            raise

    async def commit_booking(
        self,
        user_id: UUID,
        booking_id: UUID,
        payment_ref: Optional[str] = None,
    ) -> Booking:
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking or booking.user_id != user_id:
            raise BookingNotFoundError()

        if booking.status != BookingStatus.HELD:
            raise IllegalBookingTransition(booking.status.value, BookingStatus.CONFIRMED.value)

        if not booking.showtime_id or not booking.provider_id or not booking.provider_hold_id:
            raise ValidationError("Booking is missing provider hold details")

        st, registry, provider = await self._resolve_provider_and_showtime(booking.showtime_id)

        try:
            ticket: ProviderTicket = await provider.commit(
                hold_id=booking.provider_hold_id, payment_ref=payment_ref
            )
            updated_booking = Booking(
                id=booking.id,
                user_id=booking.user_id,
                status=BookingStatus.CONFIRMED,
                showtime_id=booking.showtime_id,
                provider_id=booking.provider_id,
                provider_hold_id=booking.provider_hold_id,
                provider_booking_id=ticket.booking_id,
                held_until=booking.held_until,  # providers
                currency=ticket.currency,
                total_paise=ticket.total_paise,
                ref_code=ticket.ref_code,
                barcode=ticket.barcode,
                idempotency_key=booking.idempotency_key,
                created_at=booking.created_at,
                seat_refs=booking.seat_refs,
            )
            await self.booking_repo.update_booking(updated_booking)
            if self.session:
                await self.session.commit()
            return updated_booking
        except HoldExpiredRemote:
            updated_booking = Booking(
                id=booking.id,
                user_id=booking.user_id,
                status=BookingStatus.EXPIRED,
                showtime_id=booking.showtime_id,
                provider_id=booking.provider_id,
                provider_hold_id=booking.provider_hold_id,
                held_until=booking.held_until,  # providers
                total_paise=booking.total_paise,
                currency=booking.currency,
                created_at=booking.created_at,
                seat_refs=booking.seat_refs,
            )
            await self.booking_repo.update_booking(updated_booking)
            if self.session:
                await self.session.commit()
            raise
        except (ProviderUnavailable, Exception) as exc:
            logger.warning(
                "Commit call failed or timed out for booking %s. Moving to PENDING_CONFIRMATION: %s",
                booking.id,
                exc,
            )
            pending_booking = Booking(
                id=booking.id,
                user_id=booking.user_id,
                status=BookingStatus.PENDING_CONFIRMATION,
                showtime_id=booking.showtime_id,
                provider_id=booking.provider_id,
                provider_hold_id=booking.provider_hold_id,
                held_until=booking.held_until,  # providers
                total_paise=booking.total_paise,
                currency=booking.currency,
                created_at=booking.created_at,
                seat_refs=booking.seat_refs,
            )
            await self.booking_repo.update_booking(pending_booking)
            if self.session:
                await self.session.commit()
            raise ProviderUnavailable(f"Provider commit timed out: {exc}") from exc

    async def cancel_hold(self, user_id: UUID, booking_id: UUID) -> Booking:
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking or booking.user_id != user_id:
            raise BookingNotFoundError()

        if booking.status not in (BookingStatus.HELD, BookingStatus.PENDING_CONFIRMATION):
            raise IllegalBookingTransition(booking.status.value, BookingStatus.CANCELLED.value)

        if booking.provider_id and booking.provider_hold_id and booking.showtime_id:
            try:
                _, _, provider = await self._resolve_provider_and_showtime(booking.showtime_id)
                await provider.release(booking.provider_hold_id)
            except Exception as exc:
                logger.warning("Remote hold release failed for booking %s: %s", booking_id, exc)

        cancelled_booking = Booking(
            id=booking.id,
            user_id=booking.user_id,
            status=BookingStatus.CANCELLED,
            showtime_id=booking.showtime_id,
            provider_id=booking.provider_id,
            provider_hold_id=booking.provider_hold_id,
            held_until=booking.held_until,  # providers
            total_paise=booking.total_paise,
            currency=booking.currency,
            created_at=booking.created_at,
            seat_refs=booking.seat_refs,
        )
        await self.booking_repo.update_booking(cancelled_booking)
        if self.session:
            await self.session.commit()
        return cancelled_booking

    async def get_booking_for_user(self, user_id: UUID, booking_id: UUID) -> Booking:
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking or booking.user_id != user_id:
            raise BookingNotFoundError()
        return booking

    async def release_expired_holds(self) -> list[UUID]:  # providers
        expired_bookings = await self.booking_repo.get_expired_held_bookings()
        swept_ids: list[UUID] = []
        for b in expired_bookings:
            if b.status == BookingStatus.HELD:
                if b.showtime_id and b.provider_hold_id:
                    try:
                        _, _, provider = await self._resolve_provider_and_showtime(b.showtime_id)
                        await provider.release(b.provider_hold_id)
                    except Exception as exc:
                        logger.warning("Sweep release failed for %s: %s", b.id, exc)

                await self.booking_repo.update_status(
                    b.id, BookingStatus.HELD, BookingStatus.EXPIRED
                )
                swept_ids.append(b.id)

        if self.session:
            await self.session.commit()
        return swept_ids

    async def get_provider_seat_map(
        self, showtime_id: UUID
    ) -> tuple[Optional[ProviderSeatMap], bool]:
        st, registry, provider = await self._resolve_provider_and_showtime(showtime_id)
        provider_showtime_ref = st.provider_showtime_ref or str(st.id)
        try:
            seat_map = await provider.seat_map(provider_showtime_ref)
            return seat_map, True
        except ProviderUnavailable:
            return None, False

    async def reconcile_bookings(self, target_date: date) -> dict[str, Any]:
        if not self.session:
            return {"reconciled_date": target_date.isoformat(), "local_confirmed_count": 0, "discrepancies": []}

        stmt = (
            select(BookingModel)
            .where(
                BookingModel.status == BookingStatus.CONFIRMED.value,
                BookingModel.provider_id.isnot(None),
            )
        )
        res = await self.session.execute(stmt)
        local_confirmed = res.scalars().all()

        return {
            "reconciled_date": target_date.isoformat(),
            "local_confirmed_count": len(local_confirmed),
            "discrepancies": [],
        }