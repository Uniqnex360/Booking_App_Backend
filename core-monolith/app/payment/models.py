import uuid
import sqlalchemy as sa
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey
from app.core.database import Base
from app.shared.timeutil import utcnow


class PaymentModel(Base):
    __tablename__ = "payments"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    booking_id = Column(sa.Uuid, ForeignKey("bookings.id"), nullable=False, index=True)
    gateway = Column(Text, nullable=False, default="RAZORPAY")
    order_id = Column(Text, nullable=False, unique=True)
    payment_id = Column(Text, nullable=True)
    refund_id = Column(Text, nullable=True, unique=True)
    amount_paise = Column(Integer, nullable=False)
    currency = Column(Text, nullable=False, default="INR")
    status = Column(Text, nullable=False, default="CREATED", index=True)
    signature_verified = Column(Boolean, nullable=False, default=False)
    failure_code = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    raw_event = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PaymentEventModel(Base):
    __tablename__ = "payment_events"

    id = Column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    event_id = Column(Text, nullable=False, unique=True)
    event_type = Column(Text, nullable=False)
    order_id = Column(Text, nullable=True)
    payment_id = Column(Text, nullable=True)
    payload = Column(Text, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
