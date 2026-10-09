from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.coupon.interfaces import ICouponRepository
from app.coupon.repository import SQLAlchemyCouponRepository
from app.coupon.services import CouponService


def get_coupon_repository(db: AsyncSession = Depends(get_db)) -> ICouponRepository:
    return SQLAlchemyCouponRepository(db)


def get_coupon_service(
    repo: ICouponRepository = Depends(get_coupon_repository),
    db: AsyncSession = Depends(get_db),
) -> CouponService:
    return CouponService(repo, db)

