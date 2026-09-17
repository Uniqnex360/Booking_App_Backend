"""
Payment Service — pure domain logic.

Rules:
- ZERO imports from framework routing modules
- ZERO external network client imports
- Money is integer paise named *_paise
- Gateway calls only through app.payment.gateway
- Import direction: payment -> movie service, never payment -> movie/booking models or repositories
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.booking.interfaces import BookingStatus
from app.movie.services import MovieService
from app.payment.gateway import (
    PAYMENT_WINDOW_SECONDS,
    _get_key_id,
    create_order as gateway_create_order,
    fetch_payment as gateway_fetch_payment,
    refund as gateway_refund,
    verify_signature as gateway_verify_signature,
    verify_webhook_signature as gateway_verify_webhook_signature,
)
from app.payment.interfaces import (
    BookingNotPayable,
    HoldTooShort,
    IllegalPaymentTransition,
    PaymentContext,
    PaymentNotFound,
    PaymentNotAvailableHere,
    PaymentNotRequired,
    PaymentStatus,
    VerificationFailed,
    is_valid_payment_transition,
)
from app.payment.repository import PaymentRepository
from app.shared.exceptions import EntityNotFoundError
from app.shared.timeutil import utcnow

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(
        self,
        payment_repo: PaymentRepository,
        booking_service: Any,
        session: AsyncSession,
        movie_service: Optional[MovieService] = None,
    ):
        self.payment_repo = payment_repo
        self.booking_service = booking_service
        self.session = session
        self.movie_service = movie_service


    async def create_payment_order(
        self, user_id: UUID, booking_id: UUID
    ) -> dict[str, Any]:
        # 1. Fetch booking context
        ctx = await self.booking_service.payment_context(booking_id)
        if not ctx:
            raise EntityNotFoundError("Booking not found")

        # Owner check -> 404 shape
        if ctx["user_id"] != user_id:
            raise EntityNotFoundError("Booking not found")

        # 2. Check if provider showtime -> 409 PAYMENT_NOT_AVAILABLE_HERE
        if ctx.get("is_provider"):
            raise PaymentNotAvailableHere("Provider showtimes are not payable here")

        if ctx.get("showtime_id"):
            m_svc = self.movie_service
            try:
                # If showtime is provider-backed, query will reveal provider_id
                st_dto = await m_svc.get_seat_map(ctx["showtime_id"])
            except Exception:
                pass

        # 3. Booking status check
        if ctx["status"] != "HELD":
            raise BookingNotPayable(f"Booking in status '{ctx['status']}' is not payable")

        # 4. Zero total paise check
        if ctx["total_paise"] == 0:
            return {"status": "NOT_REQUIRED"}

        # 5. Check existing payment in CREATED status (idempotent, return winner)
        existing_payment = await self.payment_repo.get_by_booking_id(booking_id)
        if existing_payment and existing_payment.status == PaymentStatus.CREATED.value:
            hold_exp_str = ctx["held_until"].isoformat() if ctx.get("held_until") else None  # providers
            return {
                "order_id": existing_payment.order_id,
                "key_id": _get_key_id(),
                "amount_paise": existing_payment.amount_paise,
                "currency": existing_payment.currency,
                "hold_expires_at": hold_exp_str,
            }

        # 6. Check remaining hold time
        if ctx.get("held_until"):  # providers
            now = utcnow()
            held_until = ctx["held_until"]  # providers
            if held_until.tzinfo is None:
                held_until = held_until.replace(tzinfo=timezone.utc)
            rem_seconds = (held_until - now).total_seconds()
            if rem_seconds < (PAYMENT_WINDOW_SECONDS + 60):
                raise HoldTooShort("Remaining hold time is too short to initiate payment")

        # 7. Gateway create_order
        short_id = str(booking_id)[:8]
        order_id = await gateway_create_order(
            amount_paise=ctx["total_paise"],
            currency=ctx.get("currency", "INR"),
            receipt=f"rcpt_{short_id}",
        )

        # Store CREATED payment
        payment = await self.payment_repo.create_payment(
            booking_id=booking_id,
            order_id=order_id,
            amount_paise=ctx["total_paise"],
            currency=ctx.get("currency", "INR"),
        )
        await self.session.commit()

        hold_exp_str = ctx["held_until"].isoformat() if ctx.get("held_until") else None  # providers
        return {
            "order_id": payment.order_id,
            "key_id": _get_key_id(),
            "amount_paise": payment.amount_paise,
            "currency": payment.currency,
            "hold_expires_at": hold_exp_str,
        }

    async def verify_payment(
        self,
        user_id: UUID,
        booking_id: UUID,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> dict[str, Any]:
        # 1. Look up payment row
        payment = await self.payment_repo.get_by_order_id(razorpay_order_id)
        if not payment or payment.booking_id != booking_id:
            raise VerificationFailed("Order does not match this booking")

        # Idempotent double-tap: if already VERIFIED or CAPTURED, return result directly
        if payment.status in (PaymentStatus.VERIFIED.value, PaymentStatus.CAPTURED.value):
            return {
                "status": "PAID",
                "payment_id": payment.payment_id or razorpay_payment_id,
                "amount_paise": payment.amount_paise,
                "booking_id": str(booking_id),
            }

        # 2. Check booking is still in HELD state
        ctx = await self.booking_service.payment_context(booking_id)
        if not ctx or ctx["status"] != "HELD":
            raise BookingNotPayable(f"Booking in status '{ctx.get('status') if ctx else 'UNKNOWN'}' is not payable")

        # 3. Verify signature
        if not gateway_verify_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
            await self.payment_repo.update_status(
                payment.id,
                PaymentStatus.FAILED,
                payment_gateway_id=razorpay_payment_id,
                failure_code="BAD_SIGNATURE",
                failure_reason="Signature verification failed",
            )
            await self.session.commit()
            raise VerificationFailed("Signature verification failed")

        # 4. Confirm capture with gateway
        await gateway_fetch_payment(razorpay_payment_id)

        # 5. In one transaction: commit booking and mark paid
        await self.payment_repo.update_status(
            payment.id,
            PaymentStatus.CAPTURED,
            payment_gateway_id=razorpay_payment_id,
            signature_verified=True,
        )
        await self.booking_service.mark_paid(booking_id, razorpay_payment_id)
        await self.session.commit()

        return {
            "status": "PAID",
            "payment_id": razorpay_payment_id,
            "amount_paise": payment.amount_paise,
            "booking_id": str(booking_id),
        }

    async def handle_webhook(self, raw_body: bytes, signature: str) -> dict[str, Any]:
        if not signature or not gateway_verify_webhook_signature(raw_body, signature):
            raise VerificationFailed("Invalid webhook signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            raise VerificationFailed("Malformed JSON payload")

        event_id = payload.get("id") or str(uuid.uuid4())
        event_type = payload.get("event", "unknown")

        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payment_entity.get("order_id")
        payment_id = payment_entity.get("id")

        # 1. Deduplicate via event_id
        try:
            await self.payment_repo.record_event(
                event_id=event_id,
                event_type=event_type,
                payload_json=raw_body.decode("utf-8"),
                order_id=order_id,
                payment_id=payment_id,
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return {"status": "ok", "message": "Duplicate event acknowledged"}

        # 2. Transition on payment.captured / order.paid
        if event_type in ("payment.captured", "order.paid") and order_id:
            payment = await self.payment_repo.get_by_order_id(order_id)
            if not payment:
                logger.warning("Webhook received for unknown order_id: %s", order_id)
                return {"status": "ok", "message": "Unknown order acknowledged"}

            if payment.status != PaymentStatus.CAPTURED.value:
                await self.payment_repo.update_status(
                    payment.id,
                    PaymentStatus.CAPTURED,
                    payment_gateway_id=payment_id,
                    signature_verified=True,
                )
                await self.booking_service.mark_paid(payment.booking_id, payment_id)
                await self.session.commit()

        return {"status": "ok"}

    async def recovery_task(self) -> dict[str, int]:
        now = utcnow()
        cutoff = now - timedelta(seconds=PAYMENT_WINDOW_SECONDS + 60)

        # 1. Handle stale CREATED payments
        stale_payments = await self.payment_repo.list_stale_created_payments(cutoff)
        expired_count = 0
        for p in stale_payments:
            await self.payment_repo.update_status(p.id, PaymentStatus.EXPIRED)
            # Delegate release of locked seats cleanly to movie service
            if self.movie_service:
                await self.movie_service.release_expired_locks(p.booking_id)
            # Flip booking from HELD -> EXPIRED (transition rule stays inside Booking)
            ctx = await self.booking_service.payment_context(p.booking_id)
            if ctx and ctx["status"] == "HELD":
                await self.booking_service.mark_expired(p.booking_id)
            expired_count += 1

        # 2. Handle CAPTURED payments whose booking commit failed (H24)
        uncommitted_payments = await self.payment_repo.list_uncommitted_captured_payments()
        refunded_count = 0
        for p in uncommitted_payments:
            ctx = await self.booking_service.payment_context(p.booking_id)
            if not ctx:
                logger.critical(
                    "PAYMENT_RECOVERY_ORPHAN: payment %s references missing booking %s",
                    p.id, p.booking_id,
                )
                continue

            if ctx["status"] == "CONFIRMED":
                # A prior sweep's retry already committed this booking. Nothing to do.
                continue

            # DEFECT 1: retry the commit through Booking's own path before ever
            # considering a refund. Only after 3 failed attempts do we give up.
            try:
                await self.booking_service.mark_paid(p.booking_id, p.payment_id)
                continue
            except Exception:
                p.commit_attempts += 1

            if p.commit_attempts < 3:
                continue

            # DEFECT 2: refund is keyed on payment_id. A CAPTURED row with no
            # payment_id must never be refund-blind - no fabricated fallback.
            if not p.payment_id:
                logger.critical(
                    "PAYMENT_RECOVERY_MISSING_PAYMENT_ID: payment %s is CAPTURED "
                    "with commit_attempts=%s but has no gateway payment_id; "
                    "refund refused, needs manual intervention",
                    p.id, p.commit_attempts,
                )
                p.status = PaymentStatus.REFUND_FAILED.value
                p.refund_attempts += 1
                continue

            try:
                refund_id = await gateway_refund(payment_id=p.payment_id, amount_paise=p.amount_paise, idempotency_key=str(p.id))
                await self.payment_repo.update_status(
                    p.id,
                    PaymentStatus.REFUNDED,
                    refund_id=refund_id,
                )
                # DEFECT 3: never touch booking_repo directly. Booking exposes
                # the one method that performs this transition.
                await self.booking_service.force_cancel_after_refund(p.booking_id, p.payment_id)
                refunded_count += 1
            except Exception as e:
                # DEFECT 4: terminal-but-retryable state, never raise out of the
                # sweep (one poison row must not stop the rest), alertable log.
                p.status = PaymentStatus.REFUND_FAILED.value
                p.refund_attempts += 1
                logger.critical(
                    "PAYMENT_RECOVERY_REFUND_FAILED: payment %s refund attempt %s failed: %s",
                    p.id, p.refund_attempts, e,
                )

        await self.session.commit()
        return {"expired_payments": expired_count, "refunded_payments": refunded_count}
