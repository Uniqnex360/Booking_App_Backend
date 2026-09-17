from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user
from app.auth.interfaces import User as AuthUserDomain
from app.payment.dependencies import get_payment_service
from app.payment.interfaces import (
    BookingNotPayable,
    HoldTooShort,
    IllegalPaymentTransition,
    PaymentNotAvailableHere,
    PaymentNotFound,
    PaymentNotRequired,
    VerificationFailed,
    GatewayUnavailable,
)
from app.payment.schemas import (
    CreateOrderRequest,
    VerifyPaymentRequest,
    RefundRequest,
)
from app.payment.services import PaymentService
from app.shared.exceptions import EntityNotFoundError
from app.shared.response import error_response, success_response

router = APIRouter(tags=["Payments"])


@router.post("/payments/order", status_code=status.HTTP_200_OK)
async def create_order(
    payload: CreateOrderRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    try:
        data = await payment_service.create_payment_order(
            user_id=current_user.id, booking_id=payload.booking_id
        )
        return success_response(data=data, message="Payment order created successfully")
    except EntityNotFoundError:
        return error_response("PAYMENT_NOT_FOUND", "Booking not found", status.HTTP_404_NOT_FOUND)
    except PaymentNotAvailableHere as exc:
        return error_response("PAYMENT_NOT_AVAILABLE_HERE", str(exc), status.HTTP_409_CONFLICT)
    except BookingNotPayable as exc:
        return error_response("BOOKING_NOT_PAYABLE", str(exc), status.HTTP_409_CONFLICT)
    except HoldTooShort as exc:
        return error_response("HOLD_TOO_SHORT", str(exc), status.HTTP_409_CONFLICT)
    except GatewayUnavailable as exc:
        return error_response("PAYMENT_GATEWAY_UNAVAILABLE", str(exc), status.HTTP_502_BAD_GATEWAY)


@router.post("/payments/verify", status_code=status.HTTP_200_OK)
async def verify_payment(
    payload: VerifyPaymentRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    try:
        data = await payment_service.verify_payment(
            user_id=current_user.id,
            booking_id=payload.booking_id,
            razorpay_order_id=payload.razorpay_order_id,
            razorpay_payment_id=payload.razorpay_payment_id,
            razorpay_signature=payload.razorpay_signature,
        )
        return success_response(data=data, message="Payment verified and booking confirmed")
    except EntityNotFoundError:
        return error_response("PAYMENT_NOT_FOUND", "Booking not found", status.HTTP_404_NOT_FOUND)
    except BookingNotPayable as exc:
        return error_response("BOOKING_NOT_PAYABLE", str(exc), status.HTTP_409_CONFLICT)
    except VerificationFailed as exc:
        return error_response("PAYMENT_VERIFICATION_FAILED", str(exc), status.HTTP_402_PAYMENT_REQUIRED)
    except GatewayUnavailable as exc:
        return error_response("PAYMENT_GATEWAY_UNAVAILABLE", str(exc), status.HTTP_502_BAD_GATEWAY)


@router.post("/payments/refund", status_code=status.HTTP_200_OK)
async def refund_payment(
    payload: RefundRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    return success_response(data={"status": "INITIATED"}, message="Refund initiated")


@router.post("/webhooks/razorpay", status_code=status.HTTP_200_OK)
async def razorpay_webhook(
    request: Request,
    payment_service: PaymentService = Depends(get_payment_service),
):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    try:
        res = await payment_service.handle_webhook(raw_body=body, signature=signature)
        return JSONResponse(status_code=200, content=res)
    except VerificationFailed:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Bad signature"})
