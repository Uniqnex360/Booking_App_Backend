from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fnb.interfaces import BookingFnbLine, FnbItem, IFnbRepository
from app.fnb.models import BookingFnbModel, FnbItemModel


class SQLAlchemyFnbRepository(IFnbRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_item(self, row: FnbItemModel) -> FnbItem:
        return FnbItem(
            id=row.id,
            venue_id=row.venue_id,
            name=row.name,
            description=row.description,
            category=row.category,
            price_paise=row.price_paise,
            image_url=row.image_url,
            is_veg=row.is_veg,
            is_active=row.is_active,
        )

    async def list_by_venue(self, venue_id: uuid.UUID) -> list[FnbItem]:
        stmt = (
            select(FnbItemModel)
            .where(
                FnbItemModel.venue_id == venue_id,
                FnbItemModel.is_active.is_(True),
            )
            .order_by(FnbItemModel.category, FnbItemModel.name)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_item(r) for r in rows]

    async def get_many_for_venue(
        self, venue_id: uuid.UUID, item_ids: list[uuid.UUID]
    ) -> list[FnbItem]:
        if not item_ids:
            return []
        stmt = select(FnbItemModel).where(
            FnbItemModel.id.in_(item_ids),
            FnbItemModel.venue_id == venue_id,
            FnbItemModel.is_active.is_(True),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_item(r) for r in rows]

    async def list_for_booking(self, booking_id: uuid.UUID) -> list[BookingFnbLine]:
        stmt = (
            select(BookingFnbModel, FnbItemModel.name)
            .join(FnbItemModel, BookingFnbModel.item_id == FnbItemModel.id)
            .where(BookingFnbModel.booking_id == booking_id)
            .order_by(FnbItemModel.name)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            BookingFnbLine(
                item_id=line.item_id,
                name=name,
                quantity=line.quantity,
                unit_price_paise=line.unit_price_paise,
            )
            for line, name in rows
        ]