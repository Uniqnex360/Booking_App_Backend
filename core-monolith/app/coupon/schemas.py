from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class CouponCreateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    event_id: Optional[UUID] = None
    discount_type: Literal["PERCENT", "FLAT"]
    discount_value: int = Field(..., gt=0)
    min_order_paise: int = Field(default=0, ge=0)
    max_discount_paise: Optional[int] = Field(default=None, gt=0)
    valid_from: datetime
    valid_until: datetime
    total_usage_limit: Optional[int] = Field(default=None, gt=0)
    per_user_limit: int = Field(default=1, ge=1)

    @field_validator("code")
    @classmethod
    def clean_code(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Coupon code cannot be empty")
        return cleaned

    @field_validator("discount_value")
    @classmethod
    def validate_discount_value(cls, v: int, info) -> int:
        d_type = info.data.get("discount_type")
        if d_type == "PERCENT" and (v < 1 or v > 100):
            raise ValueError("Percentage discount must be between 1 and 100")
        return v


class CouponUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    valid_until: Optional[datetime] = None
    total_usage_limit: Optional[int] = Field(default=None, gt=0)
    per_user_limit: Optional[int] = Field(default=None, ge=1)


class CouponResponse(BaseModel):
    id: UUID
    code: str
    partner_id: UUID
    event_id: Optional[UUID] = None
    discount_type: str
    discount_value: int
    min_order_paise: int
    max_discount_paise: Optional[int] = None
    valid_from: datetime
    valid_until: datetime
    total_usage_limit: Optional[int] = None
    per_user_limit: int
    used_count: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ApplyCouponRequest(BaseModel):
    code: str
    event_id: UUID
    cart_paise: int = Field(..., gt=0)

    @field_validator("code")
    @classmethod
    def clean_code(cls, v: str) -> str:
        return v.strip().upper()


class ApplyCouponResponse(BaseModel):
    valid: bool
    code: str
    discount_paise: int
    final_paise: int
    message: str


class RemoveCouponRequest(BaseModel):
    code: str
    event_id: Optional[UUID] = None


class RedemptionDetailResponse(BaseModel):
    id: UUID
    booking_id: UUID
    user_id: UUID
    discount_paise: int
    redeemed_at: datetime

    class Config:
        from_attributes = True

