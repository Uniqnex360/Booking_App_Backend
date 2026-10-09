from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user_optional, get_current_user
from app.auth.interfaces import User as AuthUserDomain
from app.partner.dependencies import required_approved_partner
from app.partner.interfaces import Partner
from app.coupon.dependencies import get_coupon_service
from app.coupon.services import CouponService
from app.coupon.schemas import (
    CouponCreateRequest,
    CouponUpdateRequest,
    CouponResponse,
    ApplyCouponRequest,
    ApplyCouponResponse,
    RemoveCouponRequest,
    RedemptionDetailResponse,
)
from app.coupon.interfaces import (
    CouponError,
    CouponNotFoundError,
    CouponInactiveError,
    CouponExpiredError,
    CouponNotApplicableError,
    MinOrderNotMetError,
    UsageLimitReachedError,
    AlreadyUsedError,
)
from app.shared.exceptions import EntityNotFoundError, ForbiddenError, ValidationError
from app.shared.response import success_response, error_response

partner_coupon_router = APIRouter(prefix="/v1/partner/coupons", tags=["Partner Coupons"])
checkout_coupon_router = APIRouter(prefix="/v1/checkout", tags=["Checkout Coupons"])


# ---------------------------------------------------------------------------
# Partner Coupon Endpoints
# ---------------------------------------------------------------------------

@partner_coupon_router.post("", status_code=status.HTTP_201_CREATED)
async def create_coupon(
    payload: CouponCreateRequest,
    partner: Partner = Depends(required_approved_partner),
    service: CouponService = Depends(get_coupon_service),
):
    try:
        coupon = await service.create_coupon(partner.id, payload)
        return success_response(
            data=CouponResponse.model_validate(coupon).model_dump(mode="json"),
            message="Coupon created successfully",
            code=201,
        )
    except ValidationError as exc:
        return error_response("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
    except ForbiddenError as exc:
        return error_response("FORBIDDEN", str(exc), status.HTTP_403_FORBIDDEN)
    except EntityNotFoundError as exc:
        return error_response("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return error_response("SERVER_ERROR", str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)


@partner_coupon_router.get("", status_code=status.HTTP_200_OK)
async def list_coupons(
    partner: Partner = Depends(required_approved_partner),
    service: CouponService = Depends(get_coupon_service),
):
    coupons = await service.list_partner_coupons(partner.id)
    return success_response(
        data=[CouponResponse.model_validate(c).model_dump(mode="json") for c in coupons],
        message="Coupons retrieved successfully",
    )


@partner_coupon_router.get("/{coupon_id}", status_code=status.HTTP_200_OK)
async def get_coupon_detail(
    coupon_id: UUID,
    partner: Partner = Depends(required_approved_partner),
    service: CouponService = Depends(get_coupon_service),
):
    try:
        coupon = await service.get_coupon(partner.id, coupon_id)
        return success_response(
            data=CouponResponse.model_validate(coupon).model_dump(mode="json"),
            message="Coupon details retrieved",
        )
    except EntityNotFoundError:
        return error_response("NOT_FOUND", "Coupon not found", status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        return error_response("FORBIDDEN", "Access denied", status.HTTP_403_FORBIDDEN)


@partner_coupon_router.patch("/{coupon_id}", status_code=status.HTTP_200_OK)
async def update_coupon(
    coupon_id: UUID,
    payload: CouponUpdateRequest,
    partner: Partner = Depends(required_approved_partner),
    service: CouponService = Depends(get_coupon_service),
):
    try:
        coupon = await service.update_coupon(partner.id, coupon_id, payload)
        return success_response(
            data=CouponResponse.model_validate(coupon).model_dump(mode="json"),
            message="Coupon updated successfully",
        )
    except EntityNotFoundError:
        return error_response("NOT_FOUND", "Coupon not found", status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        return error_response("FORBIDDEN", "Access denied", status.HTTP_403_FORBIDDEN)


@partner_coupon_router.delete("/{coupon_id}", status_code=status.HTTP_200_OK)
async def delete_coupon(
    coupon_id: UUID,
    partner: Partner = Depends(required_approved_partner),
    service: CouponService = Depends(get_coupon_service),
):
    try:
        await service.soft_delete_coupon(partner.id, coupon_id)
        return success_response(data={"id": str(coupon_id), "is_active": False}, message="Coupon deactivated successfully")
    except EntityNotFoundError:
        return error_response("NOT_FOUND", "Coupon not found", status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        return error_response("FORBIDDEN", "Access denied", status.HTTP_403_FORBIDDEN)


@partner_coupon_router.get("/{coupon_id}/redemptions", status_code=status.HTTP_200_OK)
async def list_coupon_redemptions(
    coupon_id: UUID,
    partner: Partner = Depends(required_approved_partner),
    service: CouponService = Depends(get_coupon_service),
):
    try:
        redemptions = await service.list_coupon_redemptions(partner.id, coupon_id)
        return success_response(
            data=[RedemptionDetailResponse.model_validate(r).model_dump(mode="json") for r in redemptions],
            message="Redemptions retrieved successfully",
        )
    except EntityNotFoundError:
        return error_response("NOT_FOUND", "Coupon not found", status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        return error_response("FORBIDDEN", "Access denied", status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Customer Checkout Coupon Endpoints
# ---------------------------------------------------------------------------

@checkout_coupon_router.post("/apply-coupon", status_code=status.HTTP_200_OK)
async def apply_coupon(
    payload: ApplyCouponRequest,
    current_user: Optional[AuthUserDomain] = Depends(get_current_user_optional),
    service: CouponService = Depends(get_coupon_service),
):
    try:
        user_id = current_user.id if current_user else None
        res = await service.validate_and_calculate_discount(
            code=payload.code,
            event_id=payload.event_id,
            cart_paise=payload.cart_paise,
            user_id=user_id,
            for_update=False,
        )
        return success_response(
            data={
                "valid": True,
                "code": res["coupon"].code,
                "discount_paise": res["discount_paise"],
                "final_paise": res["final_paise"],
                "message": res["message"],
            },
            message=res["message"],
        )
    except CouponError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "error",
                "code": 400,
                "reason": exc.code.lower(),
                "message": exc.message,
                "error": {
                    "type": exc.code,
                    "message": exc.message,
                },
            },
        )
    except Exception as exc:
        return error_response("APPLY_COUPON_FAILED", str(exc), status.HTTP_400_BAD_REQUEST)


@checkout_coupon_router.post("/remove-coupon", status_code=status.HTTP_200_OK)
async def remove_coupon(
    payload: RemoveCouponRequest,
):
    return success_response(data={"status": "ok"}, message="Coupon removed")


@checkout_coupon_router.get("/available-coupons", status_code=status.HTTP_200_OK)
async def list_available_coupons(
    event_id: UUID,
    current_user: Optional[AuthUserDomain] = Depends(get_current_user_optional),
    service: CouponService = Depends(get_coupon_service),
):
    user_id = current_user.id if current_user else None
    coupons = await service.list_available_coupons_for_event(event_id, user_id=user_id)
    return success_response(
        data=coupons,
        message="Available coupons retrieved successfully",
    )

