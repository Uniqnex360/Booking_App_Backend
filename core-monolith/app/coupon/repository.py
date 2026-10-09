from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.coupon.interfaces import ICouponRepository
from app.coupon.models import CouponORM, CouponRedemptionORM


class SQLAlchemyCouponRepository(ICouponRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, coupon_data: Dict[str, Any]) -> CouponORM:
        coupon = CouponORM(**coupon_data)
        self.session.add(coupon)
        await self.session.commit()
        await self.session.refresh(coupon)
        return coupon

    async def get_by_id(self, coupon_id: UUID) -> Optional[CouponORM]:
        stmt = select(CouponORM).where(CouponORM.id == coupon_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str, for_update: bool = False) -> Optional[CouponORM]:
        stmt = select(CouponORM).where(func.upper(CouponORM.code) == func.upper(code.strip()))
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_partner(self, partner_id: UUID) -> List[CouponORM]:
        stmt = (
            select(CouponORM)
            .where(CouponORM.partner_id == partner_id)
            .order_by(CouponORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, coupon_id: UUID, update_data: Dict[str, Any]) -> Optional[CouponORM]:
        stmt = (
            update(CouponORM)
            .where(CouponORM.id == coupon_id)
            .values(**update_data)
            .returning(CouponORM)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def soft_delete(self, coupon_id: UUID) -> bool:
        stmt = (
            update(CouponORM)
            .where(CouponORM.id == coupon_id)
            .values(is_active=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def count_redemptions(self, coupon_id: UUID) -> int:
        stmt = (
            select(func.count(CouponRedemptionORM.id))
            .where(CouponRedemptionORM.coupon_id == coupon_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_user_redemptions(self, coupon_id: UUID, user_id: UUID) -> int:
        stmt = (
            select(func.count(CouponRedemptionORM.id))
            .where(
                CouponRedemptionORM.coupon_id == coupon_id,
                CouponRedemptionORM.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def record_redemption(
        self, coupon_id: UUID, user_id: UUID, booking_id: UUID, discount_paise: int
    ) -> bool:
        insert_stmt = (
            insert(CouponRedemptionORM)
            .values(
                coupon_id=coupon_id,
                user_id=user_id,
                booking_id=booking_id,
                discount_paise=discount_paise,
            )
            .on_conflict_do_nothing(index_elements=["coupon_id", "booking_id"])
        )
        res = await self.session.execute(insert_stmt)
        if res.rowcount and res.rowcount > 0:
            # Increment used_count on coupon
            upd_stmt = (
                update(CouponORM)
                .where(CouponORM.id == coupon_id)
                .values(used_count=CouponORM.used_count + 1)
            )
            await self.session.execute(upd_stmt)
            await self.session.commit()
            return True
        await self.session.commit()
        return False

    async def list_redemptions_for_coupon(self, coupon_id: UUID) -> List[CouponRedemptionORM]:
        stmt = (
            select(CouponRedemptionORM)
            .where(CouponRedemptionORM.coupon_id == coupon_id)
            .order_by(CouponRedemptionORM.redeemed_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

