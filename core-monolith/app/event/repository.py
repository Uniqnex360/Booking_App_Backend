import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import date

from app.event.interfaces import (
    IEventRepository, ITicketCategoryRepository, 
    Event, TicketCategory, EventStatus, EventCategory
)
from app.event.models import EventORM, TicketCategoryORM
from app.shared.exceptions import RepositoryError

class SQLAlchemyEventRepository(IEventRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    def _to_domain(self, orm: EventORM) -> Event:
        categories = [
            TicketCategory(
                id=orm.id if isinstance(orm.id, uuid.UUID) else uuid.UUID(orm.id),
                event_id=uuid.UUID(cat.event_id),
                name=cat.name,
                price_paise=cat.price_paise,
                capacity=cat.capacity,
                max_per_booking=cat.max_per_booking,
                description=cat.description,
                sales_open_at=cat.sales_open_at,
                sales_close_at=cat.sales_close_at,
                is_active=cat.is_active,
                created_at=cat.created_at,
                updated_at=cat.updated_at
            ) for cat in (orm.ticket_categories or [])
        ]
        
        return Event(
            id=orm.id if isinstance(orm.id, uuid.UUID) else uuid.UUID(orm.id),
            partner_id=orm.partner_id if isinstance(orm.partner_id, uuid.UUID) else uuid.UUID(orm.partner_id),
            title=orm.title,
            slug=orm.slug,
            category=EventCategory(orm.category),
            venue_name=orm.venue_name,
            city=orm.city,
            starts_at=orm.starts_at,
            ends_at=orm.ends_at,
            description=orm.description,
            event_type=orm.event_type,
            seating_mode=orm.seating_mode,
            venue_address=orm.venue_address,
            latitude=orm.latitude,
            longitude=orm.longitude,
            doors_open_at=orm.doors_open_at,
            age_restriction=orm.age_restriction,
            is_online=orm.is_online,
            online_link=orm.online_link,
            poster_image_url=orm.poster_image_url,
            cancellation_policy=orm.cancellation_policy,
            status=EventStatus(orm.status),
            published_at=orm.published_at,
            cancelled_at=orm.cancelled_at,
            cancellation_reason=orm.cancellation_reason,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            ticket_categories=categories
        )

    async def create(self, event: Event) -> Event:
        try:
            orm = EventORM(
                id=str(event.id),
                partner_id=str(event.partner_id),
                title=event.title,
                slug=event.slug,
                category=event.category.value,
                venue_name=event.venue_name,
                city=event.city,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                description=event.description,
                is_online=event.is_online,
                online_link=event.online_link,
                status=event.status.value
            )
            for cat in event.ticket_categories:
                orm.ticket_categories.append(TicketCategoryORM(
                    id=cat.id,
                    name=cat.name,
                    price_paise=cat.price_paise,
                    capacity=cat.capacity,
                    max_per_booking=cat.max_per_booking
                ))
            self.db.add(orm)
            await self.db.commit()
            return await self.get_by_id(event.id)
        except Exception as e:
            await self.db.rollback()
            raise RepositoryError(f"Event creation failed: {str(e)}")

    async def get_by_id(self, event_id: uuid.UUID) -> Optional[Event]:
        stmt = select(EventORM).where(EventORM.id == event_id).options(selectinload(EventORM.ticket_categories))
        result = await self.db.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm else None

    async def get_by_slug(self, slug: str) -> Optional[Event]:
        stmt = select(EventORM).where(EventORM.slug == slug).options(selectinload(EventORM.ticket_categories))
        result = await self.db.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm else None

    async def list_published(self, city: Optional[str], category: Optional[EventCategory], 
                             date_from: Optional[date], date_to: Optional[date], 
                             price_max_paise: Optional[int], page: int, limit: int) -> Tuple[List[Event], int]:
        filters = [EventORM.status == EventStatus.PUBLISHED.value]
        if city: filters.append(EventORM.city == city)
        if category: filters.append(EventORM.category == category.value)
        
        stmt = select(EventORM).where(and_(*filters)).options(selectinload(EventORM.ticket_categories))
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        
        stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(EventORM.starts_at.asc())
        result = await self.db.execute(stmt)
        return [self._to_domain(orm) for orm in result.scalars().all()], total
    async def list_for_partner(self, partner_id: uuid.UUID, status: Optional[EventStatus], page: int, limit: int) -> Tuple[List[Event], int]:
        filters = [EventORM.partner_id == partner_id]
        if status is not None:
            filters.append(EventORM.status == status.value)
            
        stmt = select(EventORM).where(and_(*filters)).options(selectinload(EventORM.ticket_categories))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        
        stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(EventORM.created_at.desc())
        result = await self.db.execute(stmt)
        return [self._to_domain(orm) for orm in result.scalars().all()], total
    async def update(self, event: Event) -> Event:
        orm = await self.db.get(EventORM, str(event.id))
        for key, value in event.__dict__.items():
            if key != 'ticket_categories' and hasattr(orm, key):
                setattr(orm, key, value if not isinstance(value, uuid.UUID) else str(value))
        await self.db.commit()
        return await self.get_by_id(event.id)
    async def list_by_status(
        self, 
        status: EventStatus, 
        page: int, 
        limit: int
    ) -> Tuple[List[Event], int]:
        stmt = select(EventORM).where(EventORM.status == status.value)\
            .options(selectinload(EventORM.ticket_categories))
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        
        stmt = stmt.offset((page - 1) * limit).limit(limit)\
            .order_by(EventORM.created_at.desc())
        result = await self.db.execute(stmt)
        return [self._to_domain(orm) for orm in result.scalars().all()], total
    async def delete(self, event_id: uuid.UUID) -> None:
        orm = await self.db.get(EventORM, str(event_id))
        if orm:
            await self.db.delete(orm)
            await self.db.commit()