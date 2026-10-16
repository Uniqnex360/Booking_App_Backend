
from __future__ import annotations

import logging
import secrets
import time
import uuid
from datetime import date, datetime, timezone
from typing import Optional, Any
from uuid import UUID
from app.booking.schemas import BaseBookingDetail,EventBookingDetail,MovieBookingDetail
from datetime import timedelta
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.movie.models import Showtime
from app.booking.models import BookingModel

from app.booking.interfaces import (
    MAX_SEATS_PER_BOOKING,
    Booking,
    BookingNotCancellableError,
    BookingNotFoundError,
    BookingStatus,
    EventConcludedError,
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
    InvalidSeatSelectionRemote,
    ProviderHold,
    ProviderSeatMap,
    ProviderTicket,
    ProviderUnavailable,
    SeatUnavailableRemote,
    ShowtimeNotFoundRemote,
)
from app.auth.interfaces import INotificationService

from app.shared.providers.registry import ProviderRegistryModel, create_provider_client
from app.shared.timeutil import utcnow

logger = logging.getLogger(__name__)

_SEAT_MAP_CACHE: dict[UUID, tuple[float, Optional[Any], bool]] = {}


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
    
    def _cancellation_email_body(self, booking: Booking) -> str:
        from datetime import timezone
        from zoneinfo import ZoneInfo

        dt = booking.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        booked_on_ist = dt.astimezone(ZoneInfo("Asia/Kolkata")).strftime(
            "%A, %d %B %Y at %I:%M %p"
        )
        amount_formatted = f"₹{booking.total_paise / 100:.2f}"
        ref_code = booking.ref_code or "—"

        return f"""\
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0a0a0a; color: #f5f5f5; margin: 0; padding: 20px; }}
            .card {{ max-width: 520px; margin: 0 auto; background: #171717; border-radius: 16px; border: 1px solid #262626; overflow: hidden; }}
            .header {{ background: linear-gradient(135deg, #7f1d1d, #991b1b); color: #ffffff; padding: 24px; }}
            .header h1 {{ margin: 0; font-size: 22px; font-weight: 900; letter-spacing: 1px; }}
            .header .sub {{ font-family: monospace; font-size: 14px; font-weight: bold; opacity: 0.9; margin-top: 4px; }}
            .body {{ padding: 24px; }}
            .headline {{ font-size: 20px; font-weight: bold; color: #ffffff; margin: 0 0 8px 0; }}
            .muted {{ color: #a3a3a3; font-size: 14px; margin-bottom: 20px; }}
            .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; background: #262626; padding: 16px; border-radius: 12px; margin-bottom: 20px; }}
            .info-label {{ font-size: 11px; text-transform: uppercase; color: #737373; font-weight: bold; }}
            .info-val {{ font-size: 14px; color: #f5f5f5; font-weight: bold; margin-top: 2px; }}
            .refund {{ background: #1c1917; border-left: 3px solid #f59e0b; padding: 12px 16px; border-radius: 8px; font-size: 13px; color: #d4d4d4; margin-bottom: 20px; }}
            .footer {{ text-align: center; color: #525252; font-size: 12px; margin-top: 20px; }}
        </style>
        </head>
        <body>
        <div class="card">
            <div class="header">
            <h1>Booking Cancelled</h1>
            <div class="sub">REF: {ref_code}</div>
            </div>
            <div class="body">
            <div class="headline">Your booking has been cancelled</div>
            <div class="muted">We've released your seats back to the pool.</div>

            <div class="info-grid">
                <div>
                <div class="info-label">Booked on</div>
                <div class="info-val">{booked_on_ist}</div>
                </div>
                <div>
                <div class="info-label">Total Paid</div>
                <div class="info-val">{amount_formatted}</div>
                </div>
            </div>

            <div class="refund">
                If you paid for this booking, a refund will be processed to your
                original payment method within 5–7 business days.
            </div>

            <div class="footer">
                Didn't request this? Contact support and we'll sort it out.
            </div>
            </div>
        </div>
        </body>
        </html>
        """
    def _ticket_email_body(self, booking: Booking, showtime_at=None) -> str:
        from datetime import timezone
        from zoneinfo import ZoneInfo

        try:
            from app.core.config import settings
            frontend_url = getattr(settings, "FRONTEND_URL", "https://booking-app-frontend-navy.vercel.app") or "https://booking-app-frontend-navy.vercel.app"
        except Exception:
            frontend_url = "https://booking-app-frontend-navy.vercel.app"
        asset_base = f"{frontend_url.rstrip('/')}/email"

        dt = showtime_at or booking.created_at or booking.held_until
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_ist = dt.astimezone(ZoneInfo("Asia/Kolkata"))
            date_str = dt_ist.strftime("%A, %d %B %Y")
            time_str = dt_ist.strftime("at %I:%M %p")
        else:
            date_str = "Confirmed Schedule"
            time_str = ""

        seats_list = booking.seat_codes or booking.seat_refs or []
        if seats_list:
            seat_label = f"SEATS ({len(seats_list)})"
            seat_val = ", ".join(seats_list)
        else:
            qty = booking.quantity or 1
            seat_label = f"PASSES ({qty})" if booking.event_id else f"SEATS ({qty})"
            seat_val = f"{qty} Confirmed"

        amount_formatted = f"₹{booking.total_paise / 100:.2f}"
        ref_code = booking.ref_code or "AGS-CONFIRMED"
        status_val = booking.status.value if hasattr(booking.status, "value") else str(booking.status or "CONFIRMED")

        return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>Your tickets are confirmed!</title>
<style>
  :root {{
    color-scheme: light dark;
    supported-color-schemes: light dark;
  }}
  @media (prefers-color-scheme: dark) {{
    .email-bg {{ background-color: #121316 !important; }}
    .card-bg {{ background-color: #1E2026 !important; border-color: #2E323D !important; }}
    .text-main {{ color: #F8FAFC !important; }}
    .text-muted {{ color: #94A3B8 !important; }}
    .ref-box {{ background-color: #272A34 !important; }}
    .divider {{ background-color: #2E323D !important; }}
    .notice-box {{ background-color: #132A1F !important; border-color: #1A4D35 !important; }}
    .notice-title {{ color: #34D399 !important; }}
    .notice-text {{ color: #A7F3D0 !important; }}
  }}
</style>
</head>
<body class="email-bg" style="margin: 0; padding: 0; background-color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" class="email-bg" style="background-color: #F8FAFC; padding: 36px 16px 48px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 480px; margin: 0 auto;">
          
          <!-- OFFICIAL APP LOGO (PNG) -->
          <tr>
            <td align="center" style="padding-bottom: 22px;">
              <img src="{asset_base}/logo-v3.png" alt="Vyhbz" width="115" style="display: block; width: 115px; max-width: 100%; height: auto; border: 0; outline: none; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, Arial, sans-serif; font-size: 22px; font-weight: 900; color: #EA580C; text-align: center;" />
            </td>
          </tr>

          <!-- HEADER TITLE -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <div style="font-size: 13px; font-weight: 800; color: #EA580C; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px;">
                BOOKING CONFIRMED
              </div>
              <h1 class="text-main" style="font-size: 30px; font-weight: 900; color: #0F172A; margin: 0 0 8px 0; line-height: 1.2; letter-spacing: -0.5px;">
                Your tickets are confirmed!
              </h1>
              <p class="text-muted" style="font-size: 15px; color: #4B5563; margin: 0; font-weight: 400;">
                Get ready to create amazing memories with Vyhbz.
              </p>
            </td>
          </tr>

          <!-- MAIN CARD -->
          <tr>
            <td>
              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" class="card-bg" style="background-color: #FFFFFF; border-radius: 20px; border: 1px solid #E2E8F0; box-shadow: 0 4px 25px rgba(0, 0, 0, 0.04);">
                <tr>
                  <td style="padding: 24px;">
                    
                    <!-- ROW 1: BOOKED ON -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                      <tr>
                        <td valign="top" style="width: 44px; padding-right: 16px;">
                          <img src="{asset_base}/icon-calendar-v3.png" alt="📅" width="44" height="44" style="display: block; width: 44px; height: 44px; border: 0; border-radius: 12px; font-size: 24px; text-align: center; line-height: 44px;" />
                        </td>
                        <td valign="middle">
                          <div class="text-muted" style="font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 0.6px; text-transform: uppercase; margin-bottom: 3px;">
                            BOOKED ON
                          </div>
                          <div class="text-main" style="font-size: 16px; font-weight: 800; color: #0F172A; line-height: 1.3;">
                            {date_str}
                          </div>
                          <div class="text-main" style="font-size: 15px; font-weight: 700; color: #0F172A; line-height: 1.3;">
                            {time_str}
                          </div>
                        </td>
                      </tr>
                    </table>

                    <div class="divider" style="height: 1px; background-color: #F1F5F9; margin: 18px 0;"></div>

                    <!-- ROW 2: SEATS -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                      <tr>
                        <td valign="top" style="width: 44px; padding-right: 16px;">
                          <img src="{asset_base}/icon-ticket-v3.png" alt="🎟️" width="44" height="44" style="display: block; width: 44px; height: 44px; border: 0; border-radius: 12px; font-size: 24px; text-align: center; line-height: 44px;" />
                        </td>
                        <td valign="middle">
                          <div class="text-muted" style="font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 0.6px; text-transform: uppercase; margin-bottom: 3px;">
                            {seat_label}
                          </div>
                          <div style="font-size: 17px; font-weight: 800; color: #F97316;">
                            {seat_val}
                          </div>
                        </td>
                      </tr>
                    </table>

                    <div class="divider" style="height: 1px; background-color: #F1F5F9; margin: 18px 0;"></div>

                    <!-- ROW 3: TOTAL AMOUNT -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                      <tr>
                        <td valign="top" style="width: 44px; padding-right: 16px;">
                          <img src="{asset_base}/icon-wallet-v3.png" alt="💳" width="44" height="44" style="display: block; width: 44px; height: 44px; border: 0; border-radius: 12px; font-size: 24px; text-align: center; line-height: 44px;" />
                        </td>
                        <td valign="middle">
                          <div class="text-muted" style="font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 0.6px; text-transform: uppercase; margin-bottom: 3px;">
                            TOTAL AMOUNT
                          </div>
                          <div class="text-main" style="font-size: 18px; font-weight: 800; color: #0F172A;">
                            {amount_formatted}
                          </div>
                        </td>
                      </tr>
                    </table>

                    <div class="divider" style="height: 1px; background-color: #F1F5F9; margin: 18px 0;"></div>

                    <!-- ROW 4: STATUS -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                      <tr>
                        <td valign="top" style="width: 44px; padding-right: 16px;">
                          <img src="{asset_base}/icon-status-v3.png" alt="✔" width="44" height="44" style="display: block; width: 44px; height: 44px; border: 0; border-radius: 12px; font-size: 20px; font-weight: 900; color: #16A34A; text-align: center; line-height: 44px;" />
                        </td>
                        <td valign="middle">
                          <div class="text-muted" style="font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 0.6px; text-transform: uppercase; margin-bottom: 3px;">
                            STATUS
                          </div>
                          <div style="font-size: 16px; font-weight: 800; color: #16A34A; letter-spacing: 0.5px;">
                            {status_val}
                          </div>
                        </td>
                      </tr>
                    </table>

                    <!-- GREEN NOTICE BANNER -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" class="notice-box" style="background-color: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 14px; margin-top: 22px;">
                      <tr>
                        <td style="padding: 14px 16px;">
                          <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                            <tr>
                              <td valign="top" style="width: 26px; padding-right: 12px;">
                                <img src="{asset_base}/icon-check-v3.png" alt="✔" width="26" height="26" style="display: block; width: 26px; height: 26px; border: 0; font-size: 16px; font-weight: 900; color: #10B981; text-align: center; line-height: 26px;" />
                              </td>
                              <td valign="middle">
                                <div class="notice-title" style="font-size: 14px; font-weight: 800; color: #065F46; margin-bottom: 2px;">
                                  Booking confirmed!
                                </div>
                                <div class="notice-text" style="font-size: 12px; color: #047857; line-height: 1.4;">
                                  Show this reference at the venue. You'll receive a reminder before your show.
                                </div>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>

                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- BOOKING REFERENCE BOX -->
          <tr>
            <td style="padding-top: 18px;">
              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" class="ref-box" style="background-color: #EEF2F6; border-radius: 14px;">
                <tr>
                  <td align="center" style="padding: 16px 20px;">
                    <div class="text-muted" style="font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 4px;">
                      BOOKING REFERENCE
                    </div>
                    <div class="text-main" style="font-size: 22px; font-weight: 900; color: #0F172A; letter-spacing: 2px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;">
                      {ref_code}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- FOOTER -->
          <tr>
            <td align="center" style="padding-top: 26px; font-size: 12px; color: #64748B; line-height: 1.5;">
              <div class="text-main" style="font-weight: 700; color: #334155; margin-bottom: 4px; font-size: 13px;">
                Thanks for choosing Vyhbz!
              </div>
              <div class="text-muted">
                Explore more movies, events, food, experiences and shopping — all in one place.
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    async def get_booking_detail(self, user_id: UUID, booking_id: UUID):
        
        result = await self.booking_repo.get_booking_with_context(booking_id)
        if not result:
            raise BookingNotFoundError()

        booking, context = result

        if user_id is not None and booking.user_id is not None and booking.user_id != user_id:
            raise BookingNotFoundError()
        if booking.user_id != user_id:
            raise BookingNotFoundError()

        if context is None:
            return BaseBookingDetail.from_domain(booking)

        kind = context.get("kind")
        if kind == "MOVIE":
            from app.fnb.repository import SQLAlchemyFnbRepository
            fnb_repo = SQLAlchemyFnbRepository(session=self.session)
            context["fnb_lines"] = await fnb_repo.list_for_booking(booking_id)
            return MovieBookingDetail.from_context(booking, context)    
        if kind == "EVENT":
            tier = context.get("tier")
            if self.session:
                from app.coupon.models import CouponRedemptionORM, CouponORM
                red_stmt = (
                    select(CouponRedemptionORM, CouponORM)
                    .join(CouponORM, CouponRedemptionORM.coupon_id == CouponORM.id)
                    .where(CouponRedemptionORM.booking_id == booking_id)
                )
                red_row = (await self.session.execute(red_stmt)).first()
                if red_row:
                    redemption, coupon = red_row
                    raw_subtotal = (
                        (tier.price_paise * (booking.quantity or 1))
                        if (tier and tier.price_paise)
                        else (booking.total_paise + redemption.discount_paise)
                    )
                    context["discount_paise"] = redemption.discount_paise
                    context["coupon_code"] = coupon.code
                    context["subtotal_paise"] = raw_subtotal
                    context["paid_paise"] = max(0, raw_subtotal - redemption.discount_paise)
                else:
                    raw_subtotal = (
                        (tier.price_paise * (booking.quantity or 1))
                        if (tier and tier.price_paise)
                        else booking.total_paise
                    )
                    context["discount_paise"] = 0
                    context["coupon_code"] = None
                    context["subtotal_paise"] = raw_subtotal
                    context["paid_paise"] = booking.total_paise

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
        b = await self.booking_repo.get_by_id(booking_id, for_update=True)
        if not b:
            raise BookingNotFoundError()
        if b.status == BookingStatus.CONFIRMED:
            return b

        if self.session and b.total_paise > 0:
            from app.payment.models import PaymentModel
            from sqlalchemy import select as _sel
            stmt = _sel(PaymentModel).where(
                PaymentModel.booking_id == booking_id,
                PaymentModel.status == "CAPTURED",
            )
            pay_row = (await self.session.execute(stmt)).scalars().first()
            if not pay_row:
                raise ValidationError("Payment not captured for this booking")
            if pay_row.amount_paise != b.total_paise:
                raise ValidationError(
                    f"Payment amount mismatch: expected {b.total_paise}, got {pay_row.amount_paise}"
                )

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
    async def get_booking_for_actor(self, booking_id: UUID) -> Booking | None:
        
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
        user_id: UUID | None,
        showtime_id: UUID,
        seat_ids: list[UUID] | list[str],
        idempotency_key: str,
        hold_seconds: int = 600,
        hold_token: str | None = None,
        contact_email: str | None = None,
        contact_phone: str | None = None,
        seat_codes: list[str] | None = None,
    ) -> Booking:
        if idempotency_key and user_id is not None:
            existing = await self.booking_repo.get_by_idempotency(user_id, idempotency_key)
            if existing:
                return existing

        import importlib
        from uuid import UUID as _UUID
        movie_models = importlib.import_module("app.movie.models")
        ShowtimeModel = getattr(movie_models, "Showtime")
        ScreenRowModel = getattr(movie_models, "ScreenRow")
        SeatModel = getattr(movie_models, "Seat")
        SeatStateModel = getattr(movie_models, "SeatState")

        MovieModel = getattr(movie_models, "Movie")
        MovieStatusEnum = getattr(movie_models, "MovieStatus")
        ShowtimeStatusEnum = getattr(movie_models, "ShowtimeStatus")

        st_stmt = (
            select(ShowtimeModel, MovieModel)
            .join(MovieModel, ShowtimeModel.movie_id == MovieModel.id)
            .where(ShowtimeModel.id == showtime_id)
        )
        st_res = await self.session.execute(st_stmt)
        st_row = st_res.first()
        if not st_row:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")
        showtime, movie = st_row

        if movie.status != MovieStatusEnum.PUBLISHED.value:
            raise ValidationError(f"Movie is not available for booking (status: {movie.status})")

        if showtime.status != ShowtimeStatusEnum.ACTIVE.value:
            raise ValidationError(f"Showtime is not ACTIVE (status: {showtime.status})")

        if not seat_ids:
            raise ValidationError("Must select at least 1 seat")

        parsed_seat_ids: list[_UUID] = []
        for sid in seat_ids:
            if isinstance(sid, _UUID):
                parsed_seat_ids.append(sid)
            else:
                parsed_seat_ids.append(_UUID(str(sid)))

        if len(parsed_seat_ids) != len(set(parsed_seat_ids)):
            raise ValidationError("Duplicate seat IDs in selection")
        if len(parsed_seat_ids) > MAX_SEATS_PER_BOOKING:
            raise ValidationError(f"Cannot hold more than {MAX_SEATS_PER_BOOKING} seats")

        seats_stmt = (
            select(SeatModel, ScreenRowModel)
            .join(ScreenRowModel, SeatModel.row_id == ScreenRowModel.id)
            .where(SeatModel.id.in_(parsed_seat_ids), ScreenRowModel.screen_id == showtime.screen_id)
        )
        rows = (await self.session.execute(seats_stmt)).all()
        if len(rows) != len(parsed_seat_ids):
            raise ValidationError("One or more seats do not belong to this screen")

        now = utcnow()
        from datetime import timedelta
        held_until = now + timedelta(seconds=hold_seconds)

        active_states_stmt = select(SeatStateModel.seat_id).where(
            SeatStateModel.showtime_id == showtime_id,
            SeatStateModel.seat_id.in_(parsed_seat_ids),
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
        ref_code = f"BK{secrets.token_hex(16).upper()}"

        from app.booking.hold_token import hash_token
        hold_token_hash = hash_token(hold_token) if hold_token else None
        hold_token_expires_at = (
            held_until + timedelta(hours=24) if hold_token else None
        )
        booking = Booking(
            id=booking_id,
            user_id=user_id,
            status=BookingStatus.HELD,
            showtime_id=showtime_id,
            total_paise=total_paise,
            ticket_paise=total_paise,
            held_until=held_until,
            idempotency_key=idempotency_key,
            ref_code=ref_code,
            created_at=now,
            seat_refs=[str(s) for s in parsed_seat_ids],
            seat_codes=seat_codes,
            contact_email=contact_email,
            contact_phone=contact_phone,
            hold_token_hash=hold_token_hash,
            hold_token_expires_at=hold_token_expires_at,
        )

        try:
            await self.booking_repo.create(booking)
            for sid in parsed_seat_ids:
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
        if tier.event_ends_at:
            event_end = tier.event_ends_at
            if event_end.tzinfo is None:
                event_end = event_end.replace(tzinfo=timezone.utc)
            if now >= event_end:
                raise EventConcludedError()

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
            status=BookingStatus.CONFIRMED if total_paise == 0 else BookingStatus.HELD,
            held_until=None if total_paise == 0 else now + timedelta(minutes=10),
            ref_code=f"BK{secrets.token_hex(16).upper()}",
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
        from app.movie.models import Showtime as ShowtimeModel
        
        movie_models = importlib.import_module("app.movie.models")
        MovieModel = getattr(movie_models, "Movie")
        MovieStatusEnum = getattr(movie_models, "MovieStatus")
        ShowtimeStatusEnum = getattr(movie_models, "ShowtimeStatus")

        stmt = (
            select(ShowtimeModel, MovieModel)
            .join(MovieModel, ShowtimeModel.movie_id == MovieModel.id)
            .where(ShowtimeModel.id == showtime_id)
        )
        res = await self.session.execute(stmt)
        row = res.first()
        if not row:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")
        st, movie = row

        if movie.status != MovieStatusEnum.PUBLISHED.value:
            raise ValidationError(f"Movie is not available for booking (status: {movie.status})")

        if st.status != ShowtimeStatusEnum.ACTIVE.value:
            raise ValidationError(f"Showtime is not ACTIVE (status: {st.status})")

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
        hold_token: str | None = None, 
    ) -> Booking:
        # if user_id is None and not (contact_email or contact_phone):
        #     raise ValidationError(
        #         "Guest bookings require contact_email or contact_phone"
        #     )

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
        if user_id is None and not hold_token:
            raise ValidationError("Guest holds require X-Hold-Token")
        provider_showtime_ref = st.provider_showtime_ref or str(st.id)
        try:
            remote_hold: ProviderHold = await provider.hold(
                showtime_ref=provider_showtime_ref,
                seat_refs=seat_ids,
                idem_key=idem_key,
                end_user_ref=str(user_id) if user_id else (contact_email or contact_phone or "guest"),
            )
        except ShowtimeNotFoundRemote as exc:
            raise ShowtimeNotFoundError(str(exc)) from exc
        except InvalidSeatSelectionRemote as exc:
            raise ValidationError(str(exc)) from exc

        booking_id = uuid.uuid4()
        now = utcnow()
        from app.booking.hold_token import hash_token
        from datetime import timedelta, timezone
        base_expiry = remote_hold.expires_at or (now + timedelta(hours=24))
        if base_expiry.tzinfo is None:
            base_expiry = base_expiry.replace(tzinfo=timezone.utc)
        local_booking = Booking(
            id=booking_id,
            user_id=user_id,
            status=BookingStatus.HELD,
            showtime_id=st.id,
            provider_id=registry.id,
            provider_hold_id=remote_hold.hold_id,
            held_until=remote_hold.expires_at,
            currency=remote_hold.currency,
            ticket_paise=remote_hold.total_paise,
            total_paise=remote_hold.total_paise,
            idempotency_key=idem_key,
            created_at=now,
            seat_refs=seat_ids,
            seat_codes=seat_codes,
            contact_email=contact_email,
            contact_phone=contact_phone,
            hold_token_hash=hash_token(hold_token) if hold_token else None,
            hold_token_expires_at=(base_expiry + timedelta(hours=24)) if hold_token else None,
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
    async def _commit_event_booking(self, booking: Booking, payment_ref: Optional[str]) -> Booking:
        if booking.status == BookingStatus.CONFIRMED:
            return booking  # already done, idempotent
        if booking.status != BookingStatus.HELD:
            raise IllegalBookingTransition(booking.status.value, BookingStatus.CONFIRMED.value)

        payment_row = await self._resolve_and_validate_payment(booking, payment_ref)

        ok = await self.booking_repo.update_status(
            booking.id, BookingStatus.HELD, BookingStatus.CONFIRMED
        )
        if self.session:
            if payment_row and payment_row.amount_paise != booking.total_paise:
                from app.booking.models import BookingModel
                from sqlalchemy import update as _upd
                await self.session.execute(
                    _upd(BookingModel)
                    .where(BookingModel.id == booking.id)
                    .values(total_paise=payment_row.amount_paise)
                )
            await self.session.commit()
        if not ok:
            fresh = await self.booking_repo.get_by_id(booking.id)
            if fresh and fresh.status == BookingStatus.CONFIRMED:
                return fresh
            raise IllegalBookingTransition(
                fresh.status.value if fresh else "UNKNOWN", BookingStatus.CONFIRMED.value
            )
        confirmed = await self.booking_repo.get_by_id(booking.id)
        if confirmed:
            ref_str = confirmed.ref_code or str(confirmed.id)[:8].upper()
            if self.session and confirmed.user_id:
                from app.notification.service import create_user_notification
                await create_user_notification(
                    session=self.session,
                    user_id=confirmed.user_id,
                    title="Event Booking Confirmed! 🎉",
                    description=f"Your booking ({ref_str}) for {confirmed.quantity or 1} pass(es) is confirmed. View your pass in Orders.",
                    notif_type="booking",
                    link=f"/bookings/{confirmed.id}",
                    reference_key=f"booking_confirmed:{confirmed.id}",
                    commit=True,
                )
            if self._notification and confirmed.contact_email:
                try:
                    await self._notification.send_email(
                        email=confirmed.contact_email,
                        subject=f"Your booking is confirmed — {ref_str}",
                        body=self._ticket_email_body(confirmed),
                        content_type="html",
                    )
                except Exception as exc:
                    logger.warning("Failed to send event confirmation email for %s: %s", confirmed.id, exc)
        return confirmed

    async def _verify_razorpay_payment(
        self,
        payment_id: str,
        expected_paise: int,
        booking_id: Optional[UUID] = None,
    ) -> Any:
        import os, httpx, uuid
        from app.payment.models import PaymentModel
        from sqlalchemy import select as _sel

        if self.session and booking_id:
            dup_stmt = _sel(PaymentModel).where(
                PaymentModel.payment_id == payment_id,
                PaymentModel.status == "CAPTURED",
                PaymentModel.booking_id != booking_id,
            )
            existing_payment = (await self.session.execute(dup_stmt)).scalars().first()
            if existing_payment:
                raise ValidationError("Payment has already been used for another booking")

        auth = (os.environ.get("RAZORPAY_KEY_ID", ""), os.environ.get("RAZORPAY_KEY_SECRET", ""))
        base = f"https://api.razorpay.com/v1/payments/{payment_id}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(base, auth=auth)
            if r.status_code != 200:
                raise ValidationError("Payment not found")
            p = r.json()
            if p.get("amount") != expected_paise or p.get("currency") != "INR":
                raise ValidationError("Payment amount mismatch")
            if p.get("status") == "authorized":
                cap = await c.post(
                    f"{base}/capture",
                    auth=auth,
                    json={"amount": expected_paise, "currency": "INR"},
                )
                if cap.status_code != 200:
                    raise ValidationError("Payment capture failed")
            elif p.get("status") != "captured":
                raise ValidationError("Payment not captured")

            if booking_id:
                # 1. Reject if notes are missing or mismatch
                notes = p.get("notes")
                if not notes or not isinstance(notes, dict):
                    raise ValidationError("Payment notes are missing")
                note_booking_id = notes.get("booking_id") or notes.get("bookingId")
                if not note_booking_id or str(note_booking_id).strip() != str(booking_id):
                    raise ValidationError("Payment notes missing or do not match this booking")

                # 2. Require order_id present
                order_id = p.get("order_id")
                if not order_id:
                    raise ValidationError("Payment is missing order_id")

                # 3. Found in payments, linked to this booking
                if self.session:
                    ord_stmt = _sel(PaymentModel).where(
                        PaymentModel.order_id == order_id
                    )
                    order_payment = (await self.session.execute(ord_stmt)).scalars().first()
                    if not order_payment:
                        raise ValidationError("Payment order not found in payments")
                    if order_payment.booking_id != booking_id:
                        raise ValidationError("Payment order is not linked to this booking")

                    order_payment.payment_id = payment_id
                    order_payment.status = "CAPTURED"
                    order_payment.signature_verified = True
                    try:
                        await self.session.flush()
                    except Exception as e:
                        raise ValidationError("Payment has already been used for another booking") from e
                    return order_payment
        return None

    async def _resolve_and_validate_payment(self, booking: Booking, payment_ref: Optional[str]) -> Any:
        if booking.total_paise <= 0:
            return None

        payment_row = None
        if self.session:
            from app.payment.models import PaymentModel
            from sqlalchemy import select as _sel
            stmt = _sel(PaymentModel).where(
                PaymentModel.booking_id == booking.id,
                PaymentModel.status == "CAPTURED",
                PaymentModel.signature_verified.is_(True),
            ).order_by(PaymentModel.created_at.desc())
            payment_row = (await self.session.execute(stmt)).scalars().first()

        if not payment_row and payment_ref:
            payment_row = await self._verify_razorpay_payment(payment_ref, booking.total_paise, booking.id)
        elif not payment_row:
            raise ValidationError("Payment not verified for this booking")

        if payment_row.booking_id != booking.id:
            raise ValidationError("Payment is not tied to this booking")

        expected_amount = booking.total_paise
        if getattr(payment_row, "raw_event", None):
            try:
                import json
                meta = json.loads(payment_row.raw_event)
                if isinstance(meta, dict) and "discount_paise" in meta:
                    expected_amount -= int(meta["discount_paise"])
            except Exception:
                pass
        if payment_row.amount_paise != expected_amount:
            raise ValidationError(
                f"Payment amount mismatch: expected {expected_amount}, got {payment_row.amount_paise}"
            )
        return payment_row

    async def _commit_local_movie_booking(self, booking: Booking, payment_ref: Optional[str]) -> Booking:
        if booking.status == BookingStatus.CONFIRMED:
            return booking
        if booking.status != BookingStatus.HELD:
            raise IllegalBookingTransition(booking.status.value, BookingStatus.CONFIRMED.value)

        payment_row = await self._resolve_and_validate_payment(booking, payment_ref)

        import importlib
        from uuid import UUID as _UUID
        movie_models = importlib.import_module("app.movie.models")
        SeatStateModel = getattr(movie_models, "SeatState")
        SeatModel = getattr(movie_models, "Seat")
        MovieSoldCountModel = getattr(movie_models, "MovieSoldCount")

        seat_uuids = []
        for s in (booking.seat_refs or []):
            try:
                seat_uuids.append(_UUID(str(s)))
            except Exception:
                pass

        if not seat_uuids and self.session:
            locked_seats = (await self.session.execute(
                select(SeatStateModel.seat_id).where(SeatStateModel.booking_id == booking.id)
            )).scalars().all()
            seat_uuids = list(locked_seats)

        if self.session and seat_uuids:
            from sqlalchemy import update as _upd
            await self.session.execute(
                _upd(SeatStateModel)
                .where(
                    SeatStateModel.booking_id == booking.id,
                    SeatStateModel.seat_id.in_(seat_uuids),
                )
                .values(status="BOOKED", held_until=None)
            )
            seats_stmt = select(SeatModel).where(SeatModel.id.in_(seat_uuids))
            seat_objs = (await self.session.execute(seats_stmt)).scalars().all()
            for seat in seat_objs:
                sold_row = (await self.session.execute(
                    select(MovieSoldCountModel).where(
                        MovieSoldCountModel.showtime_id == booking.showtime_id,
                        MovieSoldCountModel.row_id == seat.row_id,
                    )
                )).scalar_one_or_none()
                if not sold_row:
                    self.session.add(MovieSoldCountModel(showtime_id=booking.showtime_id, row_id=seat.row_id, sold_count=1))
                else:
                    sold_row.sold_count += 1

        ok = await self.booking_repo.update_status(
            booking.id, BookingStatus.HELD, BookingStatus.CONFIRMED
        )
        if self.session:
            if payment_row and payment_row.amount_paise != booking.total_paise:
                from app.booking.models import BookingModel
                from sqlalchemy import update as _upd
                await self.session.execute(
                    _upd(BookingModel)
                    .where(BookingModel.id == booking.id)
                    .values(total_paise=payment_row.amount_paise)
                )
            await self.session.commit()

        if not ok:
            fresh = await self.booking_repo.get_by_id(booking.id)
            if fresh and fresh.status == BookingStatus.CONFIRMED:
                return fresh
            raise IllegalBookingTransition(
                fresh.status.value if fresh else "UNKNOWN", BookingStatus.CONFIRMED.value
            )

        confirmed = await self.booking_repo.get_by_id(booking.id)
        if confirmed:
            st_row = None
            movie_title = "Movie"
            if self.session and booking.showtime_id:
                try:
                    st_row = (await self.session.execute(
                        select(Showtime).where(Showtime.id == booking.showtime_id)
                    )).scalar_one_or_none()
                    if st_row:
                        movie_row = (await self.session.execute(
                            select(Movie).where(Movie.id == st_row.movie_id)
                        )).scalar_one_or_none()
                        if movie_row:
                            movie_title = movie_row.title
                except Exception:
                    pass

            ref_str = confirmed.ref_code or str(confirmed.id)[:8].upper()
            seats_str = ", ".join(confirmed.seat_codes or confirmed.seat_refs or [])
            if self.session and confirmed.user_id:
                from app.notification.service import create_user_notification
                await create_user_notification(
                    session=self.session,
                    user_id=confirmed.user_id,
                    title=f"Booking Confirmed: {movie_title} 🎉",
                    description=f"Ref {ref_str} • Seats: {seats_str or 'Confirmed'}. Tap to view your e-ticket.",
                    notif_type="booking",
                    link=f"/bookings/{confirmed.id}",
                    reference_key=f"booking_confirmed:{confirmed.id}",
                    commit=True,
                )

            if self._notification and confirmed.contact_email:
                try:
                    await self._notification.send_email(
                        email=confirmed.contact_email,
                        subject=f"Booking Confirmed: {movie_title} ({ref_str})",
                        body=self._ticket_email_body(confirmed, showtime_at=st_row.starts_at if st_row else None),
                        content_type="html",
                    )
                except Exception as e:
                    logger.warning("Failed to send confirmation email for booking %s: %s", booking.id, e)

            # Record transaction in Central Admin Commission Ledger
            if self.session:
                try:
                    from app.admin.commission_service import CommissionAdminService
                    from app.booking.models import BookingModel
                    b_model = (await self.session.execute(
                        select(BookingModel).where(BookingModel.id == confirmed.id)
                    )).scalar_one_or_none()
                    if b_model:
                        await CommissionAdminService.record_booking_commission(self.session, b_model)
                except Exception as comm_err:
                    logger.warning("Failed to record commission ledger for booking %s: %s", booking.id, comm_err)

        return confirmed

    async def commit_booking(
        self,
        user_id: UUID,
        booking_id: UUID,
        payment_ref: Optional[str] = None,
    ) -> Booking:
        booking = await self.booking_repo.get_by_id(booking_id, for_update=True)
        if not booking:
            raise BookingNotFoundError()
        if booking.user_id is not None and booking.user_id != user_id:
            raise BookingNotFoundError()

        if booking.status == BookingStatus.CONFIRMED:
            if booking.provider_id:
                raise HoldAlreadyCommitted(booking_id=booking.provider_booking_id, booking_ref=booking.ref_code)
            return booking

        if booking.tier_id and not booking.provider_id:
            return await self._commit_event_booking(booking, payment_ref)

        if booking.showtime_id and not booking.provider_id:
            return await self._commit_local_movie_booking(booking, payment_ref)

        if booking.status != BookingStatus.HELD:
            raise IllegalBookingTransition(booking.status.value, BookingStatus.CONFIRMED.value)
        if booking.total_paise > 0:
            from app.payment.models import PaymentModel
            from sqlalchemy import select as _sel
            if not self.session:
                raise ValidationError("Session required")
            stmt = _sel(PaymentModel).where(
                PaymentModel.booking_id == booking.id,
                PaymentModel.status == "CAPTURED",
                PaymentModel.signature_verified.is_(True),
            )
            paid = (await self.session.execute(stmt)).scalar_one_or_none()
            if not paid:
                raise ValidationError("Payment not verified for this booking")
            if paid.amount_paise != booking.total_paise:
                raise ValidationError(
                    f"Payment amount mismatch: expected {booking.total_paise}, got {paid.amount_paise}"
                )
        if not booking.showtime_id or not booking.provider_id or not booking.provider_hold_id:
            raise ValidationError("Booking is missing provider hold details")

        st, registry, provider = await self._resolve_provider_and_showtime(booking.showtime_id)

        try:
            ticket: ProviderTicket = await provider.commit(
                hold_id=booking.provider_hold_id, payment_ref=payment_ref
            )
            st_row = (await self.session.execute(
                select(Showtime).where(Showtime.id == booking.showtime_id)
            )).scalar_one_or_none()

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
                seat_codes=booking.seat_codes,  
                contact_email=booking.contact_email,     
                contact_phone=booking.contact_phone,  
                ticket_paise=booking.ticket_paise,      # ← add
                fnb_paise=booking.fnb_paise,            # ← add
                convenience_fee_paise=booking.convenience_fee_paise,
                terms_accepted_at=booking.terms_accepted_at,
                hold_token_hash=booking.hold_token_hash,
                hold_token_expires_at=booking.hold_token_expires_at,
            )
            await self.booking_repo.update_booking(updated_booking)
            if self.session:
                await self.session.commit()
            if self.session and updated_booking.user_id:
                from app.notification.service import create_user_notification
                seats_str = ", ".join(updated_booking.seat_codes or updated_booking.seat_refs or [])
                await create_user_notification(
                    session=self.session,
                    user_id=updated_booking.user_id,
                    title="Booking Confirmed! 🎉",
                    description=f"Ref {updated_booking.ref_code} • Seats: {seats_str or 'Confirmed'}. Tap to view your e-ticket.",
                    notif_type="booking",
                    link=f"/bookings/{updated_booking.id}",
                    reference_key=f"booking_confirmed:{updated_booking.id}",
                    commit=True,
                )
            if self._notification and updated_booking.contact_email:
                try:
                    await self._notification.send_email(
                        email=updated_booking.contact_email,
                        subject=f"Your ticket is confirmed — {updated_booking.ref_code}",
                        body=self._ticket_email_body(updated_booking, showtime_at=st_row.starts_at if st_row else None),

                        content_type="html",
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
                terms_accepted_at=booking.terms_accepted_at,
                hold_token_hash=booking.hold_token_hash,
                hold_token_expires_at=booking.hold_token_expires_at,
            )
            await self.booking_repo.update_booking(updated_booking)
            if self.session:
                await self.session.commit()
            raise exc
        except HoldAlreadyCommitted as exc:
            fresh = await self.booking_repo.get_by_id(booking.id)
            if fresh and fresh.status == BookingStatus.CONFIRMED:
                return fresh
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
                terms_accepted_at=booking.terms_accepted_at,
                hold_token_hash=booking.hold_token_hash,
                hold_token_expires_at=booking.hold_token_expires_at,
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
        if booking.tier_id and not booking.provider_id:
            changed = await self.booking_repo.update_status(
                booking.id, booking.status, BookingStatus.CANCELLED
            )
            if changed and booking.quantity:
                await self.counter_repo.decrement(booking.tier_id, booking.quantity)
            if self.session:
                await self.session.commit()
            return await self.booking_repo.get_by_id(booking.id)
        if booking.provider_id and booking.provider_hold_id and booking.showtime_id:
            try:
                _, _, provider = await self._resolve_provider_and_showtime(booking.showtime_id)
                await provider.release(booking.provider_hold_id)
            except Exception as exc:
                logger.warning("Remote hold release failed for booking %s: %s", booking_id, exc)
        elif not booking.provider_id and booking.showtime_id and self.session:
            import importlib
            movie_models = importlib.import_module("app.movie.models")
            SeatStateModel = getattr(movie_models, "SeatState")
            await self.session.execute(
                delete(SeatStateModel).where(
                    SeatStateModel.booking_id == booking_id,
                    SeatStateModel.status == "LOCKED",
                )
            )

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
            terms_accepted_at=booking.terms_accepted_at,
            hold_token_hash=booking.hold_token_hash,
            hold_token_expires_at=booking.hold_token_expires_at,
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
    def _recompute_total(self, booking) -> None:
        """The ONLY writer of total_paise for F&B-enabled movie bookings.
        Must be called inside the caller's transaction, after SELECT ... FOR UPDATE
        on the booking row."""
        booking.total_paise = (
            (booking.ticket_paise or 0)
            + (booking.fnb_paise or 0)
            + (booking.convenience_fee_paise or 0)
        )

    async def replace_fnb_for_booking(
        self,
        booking_id: UUID,
        user_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> Booking:
        """Replace all F&B lines for a HELD booking. Returns the updated booking row.
        Fails with HoldExpiredError if the booking is not HELD or held_until has passed.
        Fails with BookingNotFoundError if the booking does not belong to user_id."""
        if not self.session:
            raise ValidationError("Repository session is required")

        # Lock the booking row first — two parallel /fnb calls must serialize.
        stmt = (
            select(BookingModel)
            .where(BookingModel.id == booking_id)
            .with_for_update()
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if not row or (user_id is not None and row.user_id is not None and row.user_id != user_id):
            raise BookingNotFoundError()

        now = utcnow()
        if row.status != "HELD":
            raise IllegalBookingTransition(row.status, "HELD")
        if not row.held_until or row.held_until <= now:
            raise IllegalBookingTransition("EXPIRED", "HELD")

        # Resolve the venue via the showtime for validation
        from app.movie.models import Showtime, Screen
        stmt = (
            select(Screen.venue_id)
            .join(Showtime, Showtime.screen_id == Screen.id)
            .where(Showtime.id == row.showtime_id)
        )
        venue_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if venue_id is None:
            raise BookingNotFoundError()

        # Delegate the actual replace to FnbService
        from app.fnb.services import FnbService
        from app.fnb.repository import SQLAlchemyFnbRepository
        fnb_service = FnbService(
            session=self.session,
            repo=SQLAlchemyFnbRepository(session=self.session),
        )
        lines = await fnb_service.replace_for_booking(booking_id, venue_id, items)

        # Recompute the total
        row.fnb_paise = FnbService.fnb_total_paise(lines)
        self._recompute_total(row)

        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_contact(
        self,
        booking_id: UUID,
        user_id: UUID | None,
        contact_email: str | None,
        contact_phone: str | None,
    ) -> Booking:
        if not self.session:
            raise ValidationError("Repository session is required")

        stmt = (
            select(BookingModel)
            .where(BookingModel.id == booking_id)
            .with_for_update()
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if not row or (user_id is not None and row.user_id is not None and row.user_id != user_id):
            raise BookingNotFoundError()

        if row.status != "HELD":
            raise IllegalBookingTransition(row.status, "HELD")
        if not row.held_until or row.held_until <= utcnow():
            raise IllegalBookingTransition("EXPIRED", "HELD")

        if contact_email is not None:
            row.contact_email = contact_email
        if contact_phone is not None:
            row.contact_phone = contact_phone

        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_booking_detail_with_fnb(self, user_id: UUID, booking_id: UUID):
        """Wrap get_booking_detail but attach fnb_lines to the movie context."""
        result = await self.booking_repo.get_booking_with_context(booking_id)
        if not result:
            raise BookingNotFoundError()
        booking, context = result

        if booking.user_id != user_id:
            raise BookingNotFoundError()

        if context is None or context.get("kind") != "MOVIE":
            if context is None:
                return BaseBookingDetail.from_domain(booking)
            from app.booking.schemas import MovieBookingDetail, EventBookingDetail
            kind = context.get("kind")
            if kind == "EVENT":
                return EventBookingDetail.from_context(booking, context)
            return BaseBookingDetail.from_domain(booking)

        # MOVIE — attach fnb lines
        from app.fnb.repository import SQLAlchemyFnbRepository
        fnb_repo = SQLAlchemyFnbRepository(session=self.session)
        context["fnb_lines"] = await fnb_repo.list_for_booking(booking_id)
        from app.booking.schemas import MovieBookingDetail
        return MovieBookingDetail.from_context(booking, context)
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
        self,
        showtime_id: UUID,
        provider_showtime_ref: Optional[str] = None,
        provider: Optional[Any] = None,
    ) -> tuple[Optional[ProviderSeatMap], bool]:
        now = time.time()
        cached = _SEAT_MAP_CACHE.get(showtime_id)
        if cached and (now - cached[0]) < 15.0:
            return cached[1], cached[2]

        if provider is None or provider_showtime_ref is None:
            st, registry, provider = await self._resolve_provider_and_showtime(showtime_id)
            provider_showtime_ref = str(st.provider_showtime_ref or st.id)
            if self.session:
                await self.session.rollback()

        try:
            seat_map = await provider.seat_map(provider_showtime_ref)
            _SEAT_MAP_CACHE[showtime_id] = (now, seat_map, True)
            return seat_map, True
        except ProviderUnavailable as exc:
            _SEAT_MAP_CACHE.pop(showtime_id, None)
            raise exc

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
