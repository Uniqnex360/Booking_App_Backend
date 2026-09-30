from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fnb.interfaces import (
    BookingFnbLine,
    FnbItem,
    FnbItemNotFoundError,
    FnbItemWrongVenueError,
    IFnbRepository,
)
from app.fnb.models import BookingFnbModel


class FnbService:
    def __init__(self, session: AsyncSession, repo: IFnbRepository) -> None:
        self._session = session
        self._repo = repo

    async def list_menu_for_showtime(self, showtime_id: uuid.UUID) -> list[FnbItem]:
        """Resolve venue via showtime -> screen -> venue, then list active items."""
        from app.movie.models import Screen, Showtime

        stmt = (
            select(Screen.venue_id)
            .join(Showtime, Showtime.screen_id == Screen.id)
            .where(Showtime.id == showtime_id)
        )
        venue_id = (await self._session.execute(stmt)).scalar_one_or_none()
        if venue_id is None:
            return []
        return await self._repo.list_by_venue(venue_id)

    async def replace_for_booking(
        self,
        booking_id: uuid.UUID,
        venue_id: uuid.UUID,
        items: list[tuple[uuid.UUID, int]],
    ) -> list[BookingFnbLine]:
        """Replace all F&B lines for a booking. Caller must hold the booking row lock
        and be inside a transaction; this method does not commit."""
        if not items:
            await self._session.execute(
                delete(BookingFnbModel).where(BookingFnbModel.booking_id == booking_id)
            )
            return []

        item_ids = [item_id for item_id, _ in items]
        db_items = {it.id: it for it in await self._repo.get_many_for_venue(venue_id, item_ids)}

        missing = [iid for iid in item_ids if iid not in db_items]
        if missing:
            # Any missing means either not found, inactive, or from another venue.
            # Distinguish for a better error, but the venue check is definitive.
            from app.fnb.models import FnbItemModel

            existing_stmt = select(FnbItemModel.id, FnbItemModel.venue_id).where(
                FnbItemModel.id.in_(missing)
            )
            existing = (await self._session.execute(existing_stmt)).all()
            existing_ids = {row.id for row in existing}
            wrong_venue = [
                row.id for row in existing if row.venue_id != venue_id
            ]
            if wrong_venue:
                raise FnbItemWrongVenueError(
                    f"Items from another venue: {[str(i) for i in wrong_venue]}"
                )
            raise FnbItemNotFoundError(
                f"Unknown or inactive items: {[str(i) for i in existing_ids ^ set(missing)] or missing}"
            )

        await self._session.execute(
            delete(BookingFnbModel).where(BookingFnbModel.booking_id == booking_id)
        )
        for item_id, qty in items:
            it = db_items[item_id]
            self._session.add(
                BookingFnbModel(
                    booking_id=booking_id,
                    item_id=item_id,
                    quantity=qty,
                    unit_price_paise=it.price_paise,
                )
            )
        return [
            BookingFnbLine(
                item_id=item_id,
                name=db_items[item_id].name,
                quantity=qty,
                unit_price_paise=db_items[item_id].price_paise,
            )
            for item_id, qty in items
        ]

    @staticmethod
    def fnb_total_paise(lines: list[BookingFnbLine]) -> int:
        return sum(line.quantity * line.unit_price_paise for line in lines)