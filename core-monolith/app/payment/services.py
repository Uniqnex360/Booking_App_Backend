import uuid


import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
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
        self, user_id: UUID, booking_id: UUID, coupon_code: Optional[str] = None
    ) -> dict[str, Any]:
        
        ctx = await self.booking_service.payment_context(booking_id)
        if not ctx:
            raise EntityNotFoundError("Booking not found")

        if ctx["user_id"] != user_id:
            raise EntityNotFoundError("Booking not found")

        if ctx.get("showtime_id"):
            m_svc = self.movie_service
            try:
                st_dto = await m_svc.get_seat_map(ctx["showtime_id"])
            except Exception:
                pass

        if ctx["status"] != "HELD":
            raise BookingNotPayable(f"Booking in status '{ctx['status']}' is not payable")

        if ctx["total_paise"] == 0:
            return {"status": "NOT_REQUIRED"}

        final_paise = ctx["total_paise"]
        coupon_meta = None

        if coupon_code and coupon_code.strip():
            # Validate that this is an event/dining booking (not cinema)
            if not ctx.get("tier_id"):
                from app.coupon.interfaces import CouponError
                raise CouponError("Coupons can only be applied to event bookings", code="NOT_APPLICABLE")

            from app.event.models import TicketCategoryORM
            tier_stmt = select(TicketCategoryORM).where(TicketCategoryORM.id == ctx["tier_id"])
            tier_res = await self.session.execute(tier_stmt)
            tier = tier_res.scalar_one_or_none()
            if not tier:
                from app.coupon.interfaces import CouponError
                raise CouponError("Event ticket tier not found", code="NOT_APPLICABLE")

            from app.coupon.repository import SQLAlchemyCouponRepository
            from app.coupon.services import CouponService
            c_repo = SQLAlchemyCouponRepository(self.session)
            c_svc = CouponService(c_repo, self.session)

            calc_res = await c_svc.validate_and_calculate_discount(
                code=coupon_code,
                event_id=tier.event_id,
                cart_paise=ctx["total_paise"],
                user_id=user_id,
                for_update=True,
            )
            coupon = calc_res["coupon"]
            discount_paise = calc_res["discount_paise"]
            final_paise = calc_res["final_paise"]
            coupon_meta = {
                "coupon_id": str(coupon.id),
                "coupon_code": coupon.code,
                "discount_paise": discount_paise,
                "user_id": str(user_id),
            }

        existing_payment = await self.payment_repo.get_by_booking_id(booking_id)
        if existing_payment and existing_payment.status == PaymentStatus.CREATED.value:
            if existing_payment.amount_paise == final_paise:
                hold_exp_str = ctx["held_until"].isoformat() if ctx.get("held_until") else None
                return {
                    "order_id": existing_payment.order_id,
                    "key_id": _get_key_id(),
                    "amount_paise": existing_payment.amount_paise,
                    "currency": existing_payment.currency,
                    "hold_expires_at": hold_exp_str,
                }
            await self.payment_repo.update_status(
                existing_payment.id, PaymentStatus.EXPIRED
            )

        if ctx.get("held_until"):  
            now = utcnow()
            held_until = ctx["held_until"]  
            if held_until.tzinfo is None:
                held_until = held_until.replace(tzinfo=timezone.utc)
            rem_seconds = (held_until - now).total_seconds()
            if rem_seconds < (PAYMENT_WINDOW_SECONDS + 60):
                raise HoldTooShort("Remaining hold time is too short to initiate payment")

        short_id = str(booking_id)[:8]
        order_id = await gateway_create_order(
            amount_paise=final_paise,
            currency=ctx.get("currency", "INR"),
            receipt=f"rcpt_{short_id}",
        )

        payment = await self.payment_repo.create_payment(
            booking_id=booking_id,
            order_id=order_id,
            amount_paise=final_paise,
            currency=ctx.get("currency", "INR"),
            raw_event=json.dumps(coupon_meta) if coupon_meta else None,
        )
        await self.session.commit()

        hold_exp_str = ctx["held_until"].isoformat() if ctx.get("held_until") else None  
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
        
        payment = await self.payment_repo.get_by_order_id(razorpay_order_id)
        if not payment or payment.booking_id != booking_id:
            raise VerificationFailed("Order does not match this booking")

        
        if payment.status in (PaymentStatus.VERIFIED.value, PaymentStatus.CAPTURED.value):
            return {
                "status": "PAID",
                "payment_id": payment.payment_id or razorpay_payment_id,
                "amount_paise": payment.amount_paise,
                "booking_id": str(booking_id),
            }

        
        ctx = await self.booking_service.payment_context(booking_id)
        if not ctx or ctx["status"] != "HELD":
            raise BookingNotPayable(f"Booking in status '{ctx.get('status') if ctx else 'UNKNOWN'}' is not payable")

        
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

        
        await gateway_fetch_payment(razorpay_payment_id)

        
        await self.payment_repo.update_status(
            payment.id,
            PaymentStatus.CAPTURED,
            payment_gateway_id=razorpay_payment_id,
            signature_verified=True,
        )
        await self.session.commit()

        # Record coupon redemption if a coupon was used
        if payment.raw_event:
            try:
                meta = json.loads(payment.raw_event)
                if isinstance(meta, dict) and "coupon_id" in meta:
                    from app.coupon.repository import SQLAlchemyCouponRepository
                    c_repo = SQLAlchemyCouponRepository(self.session)
                    cid = UUID(str(meta["coupon_id"]))
                    uid = UUID(str(user_id)) if user_id else UUID(str(meta.get("user_id")))
                    bid = UUID(str(booking_id))
                    await c_repo.record_redemption(
                        coupon_id=cid,
                        user_id=uid,
                        booking_id=bid,
                        discount_paise=int(meta.get("discount_paise", 0)),
                    )
            except Exception as e:
                logger.exception("Failed to record coupon redemption: %s", e)

        await self.booking_service.commit_booking(
            user_id=user_id,
            booking_id=booking_id,
            payment_ref=razorpay_payment_id,
        )
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
                if payment.raw_event:
                    try:
                        meta = json.loads(payment.raw_event)
                        if isinstance(meta, dict) and "coupon_id" in meta:
                            from app.coupon.repository import SQLAlchemyCouponRepository
                            c_repo = SQLAlchemyCouponRepository(self.session)
                            ctx_b = await self.booking_service.payment_context(payment.booking_id)
                            u_id = ctx_b["user_id"] if ctx_b else uuid.UUID(meta.get("user_id"))
                            await c_repo.record_redemption(
                                coupon_id=uuid.UUID(meta["coupon_id"]),
                                user_id=u_id,
                                booking_id=payment.booking_id,
                                discount_paise=meta.get("discount_paise", 0),
                            )
                    except Exception as e:
                        logger.error("Failed to record webhook coupon redemption: %s", e)
                await self.booking_service.mark_paid(payment.booking_id, payment_id)
                await self.session.commit()

        return {"status": "ok"}

    async def recovery_task(self) -> dict[str, int]:
        now = utcnow()
        cutoff = now - timedelta(seconds=PAYMENT_WINDOW_SECONDS + 60)

        
        stale_payments = await self.payment_repo.list_stale_created_payments(cutoff)
        expired_count = 0
        for p in stale_payments:
            await self.payment_repo.update_status(p.id, PaymentStatus.EXPIRED)
            
            if self.movie_service:
                await self.movie_service.release_expired_locks(p.booking_id)
            
            ctx = await self.booking_service.payment_context(p.booking_id)
            if ctx and ctx["status"] == "HELD":
                await self.booking_service.mark_expired(p.booking_id)
            expired_count += 1

        
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
                
                continue

            
            
            try:
                await self.booking_service.mark_paid(p.booking_id, p.payment_id)
                continue
            except Exception:
                p.commit_attempts += 1

            if p.commit_attempts < 3:
                continue

            
            
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
                
                
                await self.booking_service.force_cancel_after_refund(p.booking_id, p.payment_id)
                refunded_count += 1
            except Exception as e:
                
                
                p.status = PaymentStatus.REFUND_FAILED.value
                p.refund_attempts += 1
                logger.critical(
                    "PAYMENT_RECOVERY_REFUND_FAILED: payment %s refund attempt %s failed: %s",
                    p.id, p.refund_attempts, e,
                )

        await self.session.commit()
        return {"expired_payments": expired_count, "refunded_payments": refunded_count}
