
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
from app.auth.interfaces import INotificationService

from app.shared.providers.registry import ProviderRegistryModel, create_provider_client
from app.shared.timeutil import utcnow

logger = logging.getLogger(__name__)


class BookingService:
    def __init__(
        self,
        booking_repo: IBookingRepository,
        counter_repo: ITierCounterRepository,
        session: Optional[AsyncSession] = None,
        notification: "INotificationService | None" = None,
    ):
        self.booking_repo = booking_repo
        self.counter_repo = counter_repo
        self.session = session
        self._notification = notification
    
    
    def _ticket_email_body(self, booking: Booking) -> str:
        from datetime import timezone
        from zoneinfo import ZoneInfo

        # Booking has: id, user_id, status, total_paise, created_at, currency,
        # showtime_id, provider_id, provider_hold_id, provider_booking_id,
        # held_until, ref_code, barcode, idempotency_key, seat_refs, seat_codes,
        # contact_email, contact_phone.
        #
        # Movie title, cinema, screen, and starts_at are NOT on the Booking object.
        # If you want them in the email, fetch them before calling this method and
        # pass them in, or build a lookup here. Placeholders below.

        dt = booking.held_until or booking.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        starts_at_ist = dt.astimezone(ZoneInfo("Asia/Kolkata")).strftime(
            "%A, %d %B %Y at %I:%M %p"
        )

        seat_codes = ", ".join(booking.seat_codes or booking.seat_refs or [])
        amount_formatted = f"₹{booking.total_paise / 100:.2f}"
        ref_code = booking.ref_code or "—"

        return f"""\
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0a0a0a; color: #f5f5f5; margin: 0; padding: 20px; }}
        .ticket-card {{ max-width: 520px; margin: 0 auto; background: #171717; border-radius: 16px; border: 1px solid #262626; overflow: hidden; }}
        .ticket-header {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: #000; padding: 24px; }}
        .ticket-header h1 {{ margin: 0; font-size: 24px; font-weight: 900; letter-spacing: 1px; }}
        .ticket-ref {{ font-family: monospace; font-size: 14px; font-weight: bold; opacity: 0.9; margin-top: 4px; }}
        .ticket-body {{ padding: 24px; }}
        .movie-title {{ font-size: 22px; font-weight: bold; color: #ffffff; margin: 0 0 4px 0; }}
        .cinema-name {{ color: #a3a3a3; font-size: 14px; margin-bottom: 20px; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; background: #262626; padding: 16px; border-radius: 12px; margin-bottom: 24px; }}
        .info-label {{ font-size: 11px; text-transform: uppercase; color: #737373; font-weight: bold; }}
        .info-val {{ font-size: 14px; color: #f5f5f5; font-weight: bold; margin-top: 2px; }}
        .btn {{ display: block; text-align: center; background: #f59e0b; color: #000; text-decoration: none; font-weight: bold; padding: 14px; border-radius: 10px; font-size: 14px; }}
        .footer {{ text-align: center; color: #525252; font-size: 12px; margin-top: 20px; }}
    </style>
    </head>
    <body>
    <div class="ticket-card">
        <div class="ticket-header">
        <h1>VYHBZ</h1>
        <div class="ticket-ref">BOOKING CONFIRMED: {ref_code}</div>
        </div>
        <div class="ticket-body">
        <div class="movie-title">Your tickets are confirmed</div>
        <div class="cinema-name">Booking reference {ref_code}</div>

        <div class="info-grid">
            <div>
            <div class="info-label">Booked on</div>
            <div class="info-val">{starts_at_ist}</div>
            </div>
            <div>
            <div class="info-label">Seats ({len(booking.seat_codes or booking.seat_refs or [])})</div>
            <div class="info-val" style="color: #f59e0b;">{seat_codes}</div>
            </div>
            <div>
            <div class="info-label">Total Amount</div>
            <div class="info-val">{amount_formatted}</div>
            </div>
            <div>
            <div class="info-label">Status</div>
            <div class="info-val" style="color: #4ade80;">{booking.status.value if hasattr(booking.status, "value") else booking.status}</div>
            </div>
        </div>

        <div class="footer">
            Show this reference at the venue. You'll receive a reminder before your show.
        </div>
        </div>
    </div>
    </body>
    </html>
    """
    async def get_booking_detail(self, user_id: UUID, booking_id: UUID):
        
        result = await self.booking_repo.get_booking_with_context(booking_id)
        if not result:
            raise BookingNotFoundError()

        booking, context = result

        
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
            "held_until": b.held_until,  
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
            held_until=held_until,  
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
        user_id: UUID | None,
        showtime_id: UUID,
        seat_ids: list[str],
        idem_key: str,
        seat_codes: list[str] | None = None,
        contact_email: str | None = None,
        contact_phone: str | None = None,
    ) -> Booking:
        if user_id is None and not (contact_email or contact_phone):
            raise ValidationError(
                "Guest bookings require contact_email or contact_phone"
            )

        if user_id is not None and idem_key:
            existing = await self.booking_repo.get_by_idempotency(user_id, idem_key)
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
            end_user_ref=str(user_id) if user_id else (contact_email or contact_phone or "guest"),
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
            held_until=remote_hold.expires_at,
            currency=remote_hold.currency,
            total_paise=remote_hold.total_paise,
            idempotency_key=idem_key,
            created_at=now,
            seat_refs=seat_ids,
            seat_codes=seat_codes,
            contact_email=contact_email,
            contact_phone=contact_phone,
        )

        try:
            created = await self.booking_repo.create(local_booking)
            if self.session:
                await self.session.commit()
            return created
        except IntegrityError:
            if self.session:
                await self.session.rollback()
            if user_id is not None and idem_key:
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
        if not booking:
            raise BookingNotFoundError()
        if booking.user_id is not None and booking.user_id != user_id:
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
                held_until=booking.held_until,  
                currency=ticket.currency,
                total_paise=ticket.total_paise,
                ref_code=ticket.ref_code,
                barcode=ticket.barcode,
                idempotency_key=booking.idempotency_key,
                created_at=booking.created_at,
                seat_refs=booking.seat_refs,
                contact_email=booking.contact_email,     
                contact_phone=booking.contact_phone,  
            )
            await self.booking_repo.update_booking(updated_booking)
            if self.session:
                await self.session.commit()
            if self._notification and updated_booking.contact_email:
                try:
                    await self._notification.send_email(
                        email=updated_booking.contact_email,
                        subject=f"Your ticket is confirmed — {updated_booking.ref_code}",
                        body=self._ticket_email_body(updated_booking),
                    )
                except Exception as exc:
                    logger.error(
                        "Ticket email failed for booking %s: %s",
                        updated_booking.id, exc,
                    )
            return updated_booking
        
        except HoldExpiredRemote as exc:
            updated_booking = Booking(
                id=booking.id,
                user_id=booking.user_id,
                status=BookingStatus.EXPIRED,
                showtime_id=booking.showtime_id,
                provider_id=booking.provider_id,
                provider_hold_id=booking.provider_hold_id,
                held_until=booking.held_until,  
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
                held_until=booking.held_until,  
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
        if not booking:
            raise BookingNotFoundError()
        if booking.user_id is not None and booking.user_id != user_id:
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
            held_until=booking.held_until,  
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

    async def release_expired_holds(self) -> list[UUID]:  
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
