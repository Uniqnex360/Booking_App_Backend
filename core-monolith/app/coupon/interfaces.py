from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class CouponError(Exception):
    def __init__(self, message: str, code: str = "COUPON_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class CouponNotFoundError(CouponError):
    def __init__(self, message: str = "Invalid coupon code"):
        super().__init__(message, code="INVALID_CODE")


class CouponInactiveError(CouponError):
    def __init__(self, message: str = "Coupon is not active"):
        super().__init__(message, code="COUPON_INACTIVE")


class CouponExpiredError(CouponError):
    def __init__(self, message: str = "Coupon has expired"):
        super().__init__(message, code="COUPON_EXPIRED")


class CouponNotApplicableError(CouponError):
    def __init__(self, message: str = "Coupon not valid for this event"):
        super().__init__(message, code="NOT_APPLICABLE")


class MinOrderNotMetError(CouponError):
    def __init__(self, min_order_rupees: int, message: Optional[str] = None):
        msg = message or f"Minimum order of ₹{min_order_rupees:,} required"
        super().__init__(msg, code="MIN_ORDER_NOT_MET")
        self.min_order_rupees = min_order_rupees


class UsageLimitReachedError(CouponError):
    def __init__(self, message: str = "Coupon usage limit reached"):
        super().__init__(message, code="USAGE_LIMIT_REACHED")


class AlreadyUsedError(CouponError):
    def __init__(self, message: str = "You've already used this coupon"):
        super().__init__(message, code="ALREADY_USED")


class ICouponRepository(ABC):
    @abstractmethod
    async def create(self, coupon_data: Dict[str, Any]) -> Any:
        pass

    @abstractmethod
    async def get_by_id(self, coupon_id: UUID) -> Optional[Any]:
        pass

    @abstractmethod
    async def get_by_code(self, code: str, for_update: bool = False) -> Optional[Any]:
        pass

    @abstractmethod
    async def list_by_partner(self, partner_id: UUID) -> List[Any]:
        pass

    @abstractmethod
    async def update(self, coupon_id: UUID, update_data: Dict[str, Any]) -> Optional[Any]:
        pass

    @abstractmethod
    async def soft_delete(self, coupon_id: UUID) -> bool:
        pass

    @abstractmethod
    async def count_redemptions(self, coupon_id: UUID) -> int:
        pass

    @abstractmethod
    async def count_user_redemptions(self, coupon_id: UUID, user_id: UUID) -> int:
        pass

    @abstractmethod
    async def record_redemption(
        self, coupon_id: UUID, user_id: UUID, booking_id: UUID, discount_paise: int
    ) -> bool:
        pass

    @abstractmethod
    async def list_redemptions_for_coupon(self, coupon_id: UUID) -> List[Dict[str, Any]]:
        pass

