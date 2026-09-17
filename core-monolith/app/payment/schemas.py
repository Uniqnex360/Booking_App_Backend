from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class CreateOrderRequest(BaseModel):
    booking_id: UUID


class CreateOrderResponse(BaseModel):
    order_id: str
    key_id: str
    amount_paise: int
    currency: str
    hold_expires_at: Optional[str] = None


class VerifyPaymentRequest(BaseModel):
    booking_id: UUID
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RefundRequest(BaseModel):
    payment_id: str
    booking_id: UUID
    amount_paise: int = Field(gt=0)
    reason: Optional[str] = None
