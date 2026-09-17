import json
import uuid
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.payment.models import PaymentModel, PaymentEventModel
from app.payment.interfaces import PaymentStatus
from app.shared.timeutil import utcnow


class PaymentRepository:

    async def list_uncommitted_captured_payments(self) -> List[PaymentModel]:
        res = await self.session.execute(
            select(PaymentModel).where(
                PaymentModel.status == PaymentStatus.CAPTURED.value,
                PaymentModel.refund_id.is_(None),
            )
        )
        return res.scalars().all()

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_payment(
        self,
        booking_id: UUID,
        order_id: str,
        amount_paise: int,
        currency: str = "INR",
        gateway: str = "RAZORPAY",
    ) -> PaymentModel:
        now = utcnow()
        payment = PaymentModel(
            id=uuid.uuid4(),
            booking_id=booking_id,
            gateway=gateway,
            order_id=order_id,
            amount_paise=amount_paise,
            currency=currency,
            status=PaymentStatus.CREATED.value,
            signature_verified=False,
            created_at=now,
            updated_at=now,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_id(self, payment_id: UUID) -> Optional[PaymentModel]:
        res = await self.session.execute(select(PaymentModel).where(PaymentModel.id == payment_id))
        return res.scalar_one_or_none()

    async def get_by_order_id(self, order_id: str) -> Optional[PaymentModel]:
        res = await self.session.execute(select(PaymentModel).where(PaymentModel.order_id == order_id))
        return res.scalar_one_or_none()

    async def get_by_booking_id(self, booking_id: UUID) -> Optional[PaymentModel]:
        res = await self.session.execute(
            select(PaymentModel)
            .where(PaymentModel.booking_id == booking_id)
            .order_by(PaymentModel.created_at.desc())
        )
        return res.scalars().first()

    async def update_status(
        self,
        payment_id: UUID,
        status: PaymentStatus,
        payment_gateway_id: Optional[str] = None,
        signature_verified: bool = False,
        failure_code: Optional[str] = None,
        failure_reason: Optional[str] = None,
        refund_id: Optional[str] = None,
    ) -> Optional[PaymentModel]:
        payment = await self.get_by_id(payment_id)
        if not payment:
            return None

        payment.status = status.value
        payment.updated_at = utcnow()
        if payment_gateway_id:
            payment.payment_id = payment_gateway_id
        if signature_verified:
            payment.signature_verified = signature_verified
        if failure_code:
            payment.failure_code = failure_code
        if failure_reason:
            payment.failure_reason = failure_reason
        if refund_id:
            payment.refund_id = refund_id

        await self.session.flush()
        return payment

    async def record_event(
        self,
        event_id: str,
        event_type: str,
        payload_json: str,
        order_id: Optional[str] = None,
        payment_id: Optional[str] = None,
    ) -> PaymentEventModel:
        now = utcnow()
        event = PaymentEventModel(
            id=uuid.uuid4(),
            event_id=event_id,
            event_type=event_type,
            order_id=order_id,
            payment_id=payment_id,
            payload=payload_json,
            received_at=now,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_event_by_id(self, event_id: str) -> Optional[PaymentEventModel]:
        res = await self.session.execute(select(PaymentEventModel).where(PaymentEventModel.event_id == event_id))
        return res.scalar_one_or_none()

    async def list_stale_created_payments(self, cutoff: datetime) -> List[PaymentModel]:
        res = await self.session.execute(
            select(PaymentModel).where(
                PaymentModel.status == PaymentStatus.CREATED.value,
                PaymentModel.created_at < cutoff,
            )
        )
        return res.scalars().all()
