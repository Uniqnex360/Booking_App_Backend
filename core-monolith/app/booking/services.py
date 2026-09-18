
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional, Any
from uuid import UUID
from app.booking.schemas import BaseBookingDetail,EventBookingDetail,MovieBookingDetail

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.shared.providers.base import (
    HoldAlreadyCommitted,
    HoldExpiredRemote,
    ITheatreProvider,
    ProviderHold,
    ProviderSeatMap,
    ProviderTicket,
    ProviderUnavailable,
    SeatUnavailableRemote,
)
from app.shared.providers.registry import ProviderRegistryModel, create_provider_client
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
    # Payment and Hold Context Integrations
    # -----------------------------------------------------------------------
    async def get_booking_detail(self, user_id: UUID, booking_id: UUID):
        """
        Return the enriched booking detail for a user, or raise BookingNotFoundError.
        Delegates joins to the repository; builds the typed response DTO here.
        """
        result = await self.booking_repo.get_booking_with_context(booking_id)
        if not result:
            raise BookingNotFoundError()

        booking, context = result

        # Ownership check — must be here, not in the router
        if booking.user_id != user_id:
            raise BookingNotFoundError()

        if context is None:
            return BaseBookingDetail.from_domain(booking)

        kind = context.get("kind")
        if kind == "MOVIE":
            return MovieBookingDetail.from_context(booking, context)
        if kind == "EVENT":
            return EventBookingDetail.from_context(booking, context)

        return BaseBookingDetail.from_domain(booking)
    async def payment_context(self, booking_id: UUID) -> Optional[dict]:
        b = await self.booking_repo.get_by_id(booking_id)
        if not b:
            return None
        is_provider = bool(b.provider_id)
        if not is_provider and b.showtime_id and self.session:
            from app.movie.models import Showtime
            st = (await self.session.execute(select(Showtime).where(Showtime.id == b.showtime_id))).scalar_one_or_none()
            if st and st.provider_id is not None:
                is_provider = True
        return {
            "booking_id": b.id,
            "total_paise": b.total_paise,
            "currency": b.currency,
            "user_id": b.user_id,
            "status": b.status.value if hasattr(b.status, "value") else b.status,
            "held_until": b.held_until,  # providers
            "showtime_id": b.showtime_id,
            "tier_id": b.tier_id,
            "is_provider": is_provider,
        }

    async def mark_paid(self, booking_id: UUID, payment_id: str) -> Booking:
        b = await self.booking_repo.get_by_id(booking_id)
        if not b:
            raise BookingNotFoundError()

        await self.booking_repo.update_status(booking_id, b.status, BookingStatus.CONFIRMED)

        if self.session:
            import importlib
            movie_models = importlib.import_module("app.movie.models")
            SeatStateModel = getattr(movie_models, "SeatState")
            await self.session.execute(
                update(SeatStateModel)
                .where(SeatStateModel.booking_id == booking_id, SeatStateModel.status == "LOCKED")
                .values(status="BOOKED")
            )
        return await self.booking_repo.get_by_id(booking_id)

    async def force_cancel_after_refund(self, booking_id: UUID, payment_id: str) -> Booking:
        """Called only by Payment after a refund has been issued at the gateway.
        The CONFIRMED/CANCELLED transition rule stays here, inside Booking."""
        b = await self.booking_repo.get_by_id(booking_id)
        if not b:
            raise BookingNotFoundError()

        await self.booking_repo.update_status(booking_id, b.status, BookingStatus.CANCELLED)

        if self.session and b.showtime_id:
            import importlib
            movie_models = importlib.import_module("app.movie.models")
            SeatStateModel = getattr(movie_models, "SeatState")
            await self.session.execute(
                delete(SeatStateModel).where(SeatStateModel.booking_id == booking_id)
            )
            await self.session.commit()

        return await self.booking_repo.get_by_id(booking_id)

    async def mark_expired(self, booking_id: UUID) -> Booking:
        """Called only by Payment's recovery sweep for a stale HELD booking.
        The transition rule stays here, inside Booking."""
        b = await self.booking_repo.get_by_id(booking_id)
        if not b:
            raise BookingNotFoundError()
        await self.booking_repo.update_status(booking_id, b.status, BookingStatus.EXPIRED)
        return await self.booking_repo.get_by_id(booking_id)

    async def create_seat_hold(
        self,
        user_id: UUID,
        showtime_id: UUID,
        seat_ids: list[UUID],
        idempotency_key: str,
        hold_seconds: int = 600,
    ) -> Booking:
        if idempotency_key:
            existing = await self.booking_repo.get_by_idempotency(user_id, idempotency_key)
            if existing:
                return existing

        import importlib
        movie_models = importlib.import_module("app.movie.models")
        ShowtimeModel = getattr(movie_models, "Showtime")
        ScreenRowModel = getattr(movie_models, "ScreenRow")
        SeatModel = getattr(movie_models, "Seat")
        SeatStateModel = getattr(movie_models, "SeatState")

        st_stmt = select(ShowtimeModel).where(ShowtimeModel.id == showtime_id)
        st_res = await self.session.execute(st_stmt)
        showtime = st_res.scalar_one_or_none()
        if not showtime:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")

        if showtime.provider_id is not None:
            raise ValidationError("Showtime is provider-backed. Use provider hold instead.")

        if not seat_ids:
            raise ValidationError("Must select at least 1 seat")
        if len(seat_ids) != len(set(seat_ids)):
            raise ValidationError("Duplicate seat IDs in selection")
        if len(seat_ids) > MAX_SEATS_PER_BOOKING:
            raise ValidationError(f"Cannot hold more than {MAX_SEATS_PER_BOOKING} seats")

        seats_stmt = (
            select(SeatModel, ScreenRowModel)
            .join(ScreenRowModel, SeatModel.row_id == ScreenRowModel.id)
            .where(SeatModel.id.in_(seat_ids), ScreenRowModel.screen_id == showtime.screen_id)
        )
        rows = (await self.session.execute(seats_stmt)).all()
        if len(rows) != len(seat_ids):
            raise ValidationError("One or more seats do not belong to this screen")

        now = utcnow()
        from datetime import timedelta
        held_until = now + timedelta(seconds=hold_seconds)

        active_states_stmt = select(SeatStateModel.seat_id).where(
            SeatStateModel.showtime_id == showtime_id,
            SeatStateModel.seat_id.in_(seat_ids),
        )
        existing_states = (await self.session.execute(active_states_stmt)).scalars().all()

        conflicts = []
        for sid in existing_states:
            s_row = (await self.session.execute(
                select(SeatStateModel).where(SeatStateModel.showtime_id == showtime_id, SeatStateModel.seat_id == sid)
            )).scalar_one_or_none()
            if s_row:
                if s_row.status in ("BOOKED", "BLOCKED"):
                    conflicts.append(sid)
                elif s_row.status == "LOCKED":
                    if s_row.held_until and s_row.held_until > now:
                        conflicts.append(sid)
                    else:
                        await self.session.execute(
                            delete(SeatStateModel).where(SeatStateModel.showtime_id == showtime_id, SeatStateModel.seat_id == sid)
                        )

        if conflicts:
            raise ValidationError(f"Seat unavailable: {conflicts}")

        total_paise = sum(row.price_paise for _, row in rows)
        booking_id = uuid.uuid4()
        ref_code = f"BK{uuid.uuid4().hex[:8].upper()}"

        booking = Booking(
            id=booking_id,
            user_id=user_id,
            status=BookingStatus.HELD,
            showtime_id=showtime_id,
            total_paise=total_paise,
            held_until=held_until,  # providers
            idempotency_key=idempotency_key,
            ref_code=ref_code,
            created_at=now,
            seat_refs=[str(s) for s in seat_ids],
        )

        try:
            await self.booking_repo.create(booking)
            for sid in seat_ids:
                self.session.add(
                    SeatStateModel(
                        showtime_id=showtime_id,
                        seat_id=sid,
                        status="LOCKED",
                        booking_id=booking_id,
                        held_until=held_until,
                    )
                )
            await self.session.commit()
            return booking
        except IntegrityError:
            await self.session.rollback()
            if idempotency_key:
                existing = await self.booking_repo.get_by_idempotency(user_id, idempotency_key)
                if existing:
                    return existing
            raise ValidationError("Seat reservation conflict")

    async def release_seat_hold(self, user_id: UUID, booking_id: UUID) -> None:
        b = await self.booking_repo.get_by_id(booking_id)
        if not b:
            return
        if b.user_id != user_id:
            raise BookingNotFoundError()

        import importlib
        movie_models = importlib.import_module("app.movie.models")
        SeatStateModel = getattr(movie_models, "SeatState")
        await self.session.execute(
            delete(SeatStateModel).where(SeatStateModel.booking_id == booking_id, SeatStateModel.status == "LOCKED")
        )
        if b.status == BookingStatus.HELD:
            await self.booking_repo.update_status(booking_id, BookingStatus.HELD, BookingStatus.CANCELLED)
        await self.session.commit()

    async def get_user_bookings(self, user_id: UUID) -> list[Booking]:
        return await self.booking_repo.get_user_bookings(user_id)

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
        movie_models = importlib.import_module("app.movie.models")
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
        # TODO(merge-packages): Merge app/providers and app/shared/providers into a single shared provider library
        except HoldExpiredRemote as exc:
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
            raise exc
        except HoldAlreadyCommitted as exc:
            raise exc
        except Exception as exc:
            logger.warning(
                "Commit call failed for booking %s: %s",
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

        import importlib
        booking_models = importlib.import_module("app.booking.models")
        BookingModel = getattr(booking_models, "BookingModel")
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
