import math
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coupon.interfaces import (
    ICouponRepository,
    CouponError,
    CouponNotFoundError,
    CouponInactiveError,
    CouponExpiredError,
    CouponNotApplicableError,
    MinOrderNotMetError,
    UsageLimitReachedError,
    AlreadyUsedError,
)
from app.coupon.models import CouponORM
from app.coupon.schemas import CouponCreateRequest, CouponUpdateRequest
from app.event.models import EventORM
from app.shared.exceptions import EntityNotFoundError, ValidationError, ForbiddenError


class CouponService:
    def __init__(self, repo: ICouponRepository, session: AsyncSession):
        self.repo = repo
        self.session = session

    async def create_coupon(
        self, partner_id: UUID, data: CouponCreateRequest
    ) -> CouponORM:
        code = data.code.strip().upper()
        existing = await self.repo.get_by_code(code)
        if existing:
            raise ValidationError(f"Coupon code '{code}' already exists")

        if data.event_id:
            event_stmt = select(EventORM).where(EventORM.id == data.event_id)
            res = await self.session.execute(event_stmt)
            event = res.scalar_one_or_none()
            if not event:
                raise EntityNotFoundError("Specified event not found")
            if event.partner_id != partner_id:
                raise ForbiddenError("You cannot create coupons for events you do not own")

        coupon_dict = data.model_dump()
        coupon_dict["partner_id"] = partner_id
        coupon_dict["code"] = code
        return await self.repo.create(coupon_dict)

    async def get_coupon(self, partner_id: UUID, coupon_id: UUID) -> CouponORM:
        coupon = await self.repo.get_by_id(coupon_id)
        if not coupon:
            raise EntityNotFoundError("Coupon not found")
        if coupon.partner_id != partner_id:
            raise ForbiddenError("Access denied")
        return coupon

    async def list_partner_coupons(self, partner_id: UUID) -> List[CouponORM]:
        return await self.repo.list_by_partner(partner_id)

    async def update_coupon(
        self, partner_id: UUID, coupon_id: UUID, data: CouponUpdateRequest
    ) -> CouponORM:
        coupon = await self.get_coupon(partner_id, coupon_id)
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        if not update_data:
            return coupon
        updated = await self.repo.update(coupon.id, update_data)
        return updated or coupon

    async def soft_delete_coupon(self, partner_id: UUID, coupon_id: UUID) -> bool:
        await self.get_coupon(partner_id, coupon_id)
        return await self.repo.soft_delete(coupon_id)

    async def list_coupon_redemptions(
        self, partner_id: UUID, coupon_id: UUID
    ) -> List[Any]:
        await self.get_coupon(partner_id, coupon_id)
        return await self.repo.list_redemptions_for_coupon(coupon_id)

    async def validate_and_calculate_discount(
        self,
        code: str,
        event_id: UUID,
        cart_paise: int,
        user_id: Optional[UUID] = None,
        for_update: bool = False,
    ) -> Dict[str, Any]:
        cleaned_code = code.strip().upper()
        coupon = await self.repo.get_by_code(cleaned_code, for_update=for_update)
        if not coupon:
            raise CouponNotFoundError("Invalid coupon code")

        if not coupon.is_active:
            raise CouponInactiveError("Coupon is not active")

        now = datetime.now(timezone.utc)
        valid_from = (
            coupon.valid_from.replace(tzinfo=timezone.utc)
            if coupon.valid_from.tzinfo is None
            else coupon.valid_from
        )
        valid_until = (
            coupon.valid_until.replace(tzinfo=timezone.utc)
            if coupon.valid_until.tzinfo is None
            else coupon.valid_until
        )

        if now < valid_from:
            raise CouponInactiveError("Coupon is not active yet")

        if now > valid_until:
            raise CouponExpiredError("Coupon has expired")

        # Validate event scope
        event_stmt = select(EventORM).where(EventORM.id == event_id)
        res = await self.session.execute(event_stmt)
        event = res.scalar_one_or_none()
        if not event:
            raise CouponNotApplicableError("Event not found")

        if coupon.event_id is not None:
            if coupon.event_id != event.id:
                raise CouponNotApplicableError("Coupon not valid for this event")
        else:
            # Coupon applies to all events of this partner
            if coupon.partner_id != event.partner_id:
                raise CouponNotApplicableError("Coupon not valid for this event")

        # Cart threshold check
        if cart_paise < coupon.min_order_paise:
            min_rs = coupon.min_order_paise // 100
            raise MinOrderNotMetError(
                min_rs, f"Minimum order of ₹{min_rs:,} required"
            )

        # Usage limit checks
        if coupon.total_usage_limit is not None:
            # In addition to coupon.used_count, check redemptions count
            actual_count = await self.repo.count_redemptions(coupon.id)
            if actual_count >= coupon.total_usage_limit or coupon.used_count >= coupon.total_usage_limit:
                raise UsageLimitReachedError("Coupon usage limit reached")

        # Per-user limit check
        if user_id:
            user_count = await self.repo.count_user_redemptions(coupon.id, user_id)
            if user_count >= coupon.per_user_limit:
                raise AlreadyUsedError("You've already used this coupon")

        # Compute discount
        if coupon.discount_type == "PERCENT":
            raw = math.floor(cart_paise * coupon.discount_value / 100)
            discount = (
                min(raw, coupon.max_discount_paise)
                if coupon.max_discount_paise
                else raw
            )
            message = (
                f"{coupon.discount_value}% off"
                + (
                    f" up to ₹{coupon.max_discount_paise // 100}"
                    if coupon.max_discount_paise
                    else ""
                )
                + " applied"
            )
        elif coupon.discount_type == "FLAT":
            discount = min(coupon.discount_value, cart_paise)
            message = f"Flat ₹{coupon.discount_value // 100} off applied"
        else:
            discount = 0
            message = "Discount applied"

        final_paise = cart_paise - discount
        if final_paise < 100:
            raise CouponError("Coupon brings total to less than ₹1 — use a smaller coupon")

        return {
            "coupon": coupon,
            "discount_paise": discount,
            "final_paise": final_paise,
            "message": message,
        }

    async def list_available_coupons_for_event(
        self, event_id: UUID, user_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        event_stmt = select(EventORM).where(EventORM.id == event_id)
        res = await self.session.execute(event_stmt)
        event = res.scalar_one_or_none()
        if not event:
            return []

        now = datetime.now(timezone.utc)
        stmt = (
            select(CouponORM)
            .where(
                CouponORM.is_active.is_(True),
                CouponORM.valid_from <= now,
                CouponORM.valid_until >= now,
                (
                    (CouponORM.event_id == event.id)
                    | (
                        CouponORM.event_id.is_(None)
                        & (CouponORM.partner_id == event.partner_id)
                    )
                ),
            )
            .order_by(CouponORM.created_at.desc())
        )
        coupons_res = await self.session.execute(stmt)
        coupons = coupons_res.scalars().all()

        available = []
        for c in coupons:
            # Check total usage limit
            if c.total_usage_limit is not None and c.used_count >= c.total_usage_limit:
                continue

            # Check per-user limit if user_id is provided
            if user_id:
                u_count = await self.repo.count_user_redemptions(c.id, user_id)
                if u_count >= c.per_user_limit:
                    continue

            # Generate description
            if c.discount_type == "PERCENT":
                cap_text = f" up to ₹{c.max_discount_paise // 100:,}" if c.max_discount_paise else ""
                desc = f"{c.discount_value}% OFF{cap_text}"
            else:
                desc = f"Flat ₹{c.discount_value // 100:,} OFF"

            min_order_text = (
                f"Min order ₹{c.min_order_paise // 100:,}"
                if c.min_order_paise > 0
                else "No min order"
            )

            available.append({
                "id": str(c.id),
                "code": c.code,
                "discount_type": c.discount_type,
                "discount_value": c.discount_value,
                "min_order_paise": c.min_order_paise,
                "max_discount_paise": c.max_discount_paise,
                "valid_until": c.valid_until.isoformat(),
                "discount_label": desc,
                "min_order_label": min_order_text,
                "terms": f"{desc} · {min_order_text}",
            })

        return available

