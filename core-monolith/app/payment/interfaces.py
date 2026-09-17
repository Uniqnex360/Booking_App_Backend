from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID
from app.shared.exceptions import DomainError


class PaymentStatus(str, Enum):
    CREATED = "CREATED"
    VERIFIED = "VERIFIED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"


VALID_PAYMENT_TRANSITIONS = {
    PaymentStatus.CREATED: {PaymentStatus.VERIFIED, PaymentStatus.FAILED, PaymentStatus.EXPIRED},
    PaymentStatus.VERIFIED: {PaymentStatus.CAPTURED, PaymentStatus.FAILED},
    PaymentStatus.CAPTURED: {PaymentStatus.REFUNDED},
    PaymentStatus.FAILED: set(),
    PaymentStatus.EXPIRED: set(),
    PaymentStatus.REFUNDED: set(),
}


def is_valid_payment_transition(current: PaymentStatus, target: PaymentStatus) -> bool:
    return target in VALID_PAYMENT_TRANSITIONS.get(current, set())


@dataclass(frozen=True)
class PaymentContext:
    total_paise: int
    currency: str
    user_id: UUID
    status: str
    held_until: Optional[datetime]


# --- Payment Exceptions ---

class PaymentNotFound(DomainError):
    code = "PAYMENT_NOT_FOUND"

class VerificationFailed(DomainError):
    code = "PAYMENT_VERIFICATION_FAILED"

class GatewayUnavailable(DomainError):
    code = "PAYMENT_GATEWAY_UNAVAILABLE"

class BookingNotPayable(DomainError):
    code = "BOOKING_NOT_PAYABLE"

class HoldTooShort(DomainError):
    code = "HOLD_TOO_SHORT"

class PaymentNotRequired(DomainError):
    code = "PAYMENT_NOT_REQUIRED"

class PaymentNotAvailableHere(DomainError):
    code = "PAYMENT_NOT_AVAILABLE_HERE"

class IllegalPaymentTransition(DomainError):
    code = "ILLEGAL_PAYMENT_TRANSITION"
