import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.orm import selectinload, defer
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
        def _u(val):
            if val is None or isinstance(val, uuid.UUID):
                return val
            return uuid.UUID(str(val))

        categories = [
            TicketCategory(
                id=_u(cat.id),
                event_id=_u(cat.event_id),
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

        from sqlalchemy import inspect as sa_inspect
        unloaded = sa_inspect(orm).unloaded

        def _g(name, default):
            return default if name in unloaded else (getattr(orm, name) or default)

        cat_val = orm.category.lower() if orm.category else "other"
        try:
            event_cat = EventCategory(cat_val)
        except Exception:
            event_cat = EventCategory.OTHER

        return Event(
            id=_u(orm.id),
            partner_id=_u(orm.partner_id),
            title=orm.title,
            slug=orm.slug,
            category=event_cat,
            venue_name=orm.venue_name,
            venue_address=orm.venue_address,
            latitude=orm.latitude,
            longitude=orm.longitude,
            layout_image_url=_g("layout_image_url", None),
            gallery_images=_g("gallery_images", []),
            artists=_g("artists", []),
            faqs=_g("faqs", []),
            terms_and_conditions=_g("terms_and_conditions", []),
            offline_promoter=_g("offline_promoter", None),
            city=orm.city,
            starts_at=orm.starts_at,
            ends_at=orm.ends_at,
            description=orm.description,
            poster_image_url=orm.poster_image_url,
            is_online=orm.is_online,
            online_link=orm.online_link,
            is_outdoor=orm.is_outdoor,
            is_fast_filling=orm.is_fast_filling,
            is_must_attend=orm.is_must_attend,
            is_unmissable=orm.is_unmissable,
            is_kids_allowed=orm.is_kids_allowed,
            is_masterclass=orm.is_masterclass,
            is_new_year_party=orm.is_new_year_party,
            language=orm.language,
            age_restriction=getattr(orm, "age_restriction", None),
            tags=list(orm.tags or []),
            cuisine=list(getattr(orm, "cuisine", []) or []),
            price_range=getattr(orm, "price_range", None),
            what_included=getattr(orm, "what_included", None),
            min_price_paise=min([cat.price_paise for cat in categories if cat.price_paise is not None]) if categories else None,
            status=EventStatus(orm.status),
            ticket_categories=categories,
            published_at=orm.published_at,
            created_at=orm.created_at,
            updated_at=orm.updated_at
        )

    async def create(self, event: Event) -> Event:
        try:
            orm = EventORM(
                id=str(event.id),
                partner_id=str(event.partner_id),
                title=event.title,
                slug=event.slug,
                category=event.category.value if hasattr(event.category, "value") else str(event.category),
                venue_name=event.venue_name,
                venue_address=event.venue_address,
                latitude=event.latitude,
                longitude=event.longitude,
                layout_image_url=event.layout_image_url,
                gallery_images=event.gallery_images or [],
                artists=event.artists or [],
                faqs=event.faqs or [],
                terms_and_conditions=event.terms_and_conditions or [],
                offline_promoter=event.offline_promoter,
                city=event.city,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                description=event.description,
                poster_image_url=event.poster_image_url,  
                is_online=event.is_online,
                online_link=event.online_link,
                status=event.status.value if hasattr(event.status, "value") else str(event.status),
                is_outdoor=event.is_outdoor,
                is_fast_filling=event.is_fast_filling,
                is_must_attend=event.is_must_attend,
                is_unmissable=event.is_unmissable,
                is_kids_allowed=event.is_kids_allowed,
                language=event.language,
                age_restriction=getattr(event, "age_restriction", None),
                tags=event.tags or [],
                cuisine=getattr(event, "cuisine", []) or [],
                price_range=getattr(event, "price_range", None),
                what_included=getattr(event, "what_included", None),
                is_masterclass=event.is_masterclass,
                is_new_year_party=event.is_new_year_party,
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
    async def list_venues(self, city: Optional[str] = None):
        stmt = (
            select(
                EventORM.venue_name,
                EventORM.venue_address,
                EventORM.city,
            )
            .where(EventORM.status == EventStatus.PUBLISHED.value)
            .distinct()
        )
        if city:
            stmt = stmt.where(func.lower(EventORM.city) == city.lower())
        stmt = stmt.order_by(EventORM.venue_name)
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "venue_name": r.venue_name,
                "venue_address": r.venue_address,
                "city": r.city,
            }
            for r in rows
        ]
    async def list_published(
        self,
        city: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[str] = None,
        price: Optional[str] = None,
        date_filter: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        price_max_paise: Optional[int] = None,
        page: int = 1,
        limit: int = 10,
        **kwargs,
    ) -> Tuple[List[Event], int]:
        filters = [EventORM.status == EventStatus.PUBLISHED.value]
        if city:
            filters.append(func.lower(EventORM.city) == city.lower().strip())
        if category:
            cat_str = category.value.lower() if hasattr(category, "value") else str(category).lower().strip()
            filters.append(func.lower(EventORM.category) == cat_str)
        if tags:
            tag_list = [t.strip().upper() for t in tags.split(",") if t.strip()]
            if tag_list:
                filters.append(EventORM.tags.overlap(tag_list))

        if date_filter:
            df = date_filter.lower().strip()
            now_dt = datetime.now(timezone.utc)
            today_d = now_dt.date()
            if df == "today":
                filters.append(func.date(EventORM.starts_at) == today_d)
            elif df == "tomorrow":
                filters.append(func.date(EventORM.starts_at) == today_d + timedelta(days=1))
            elif df in ("this-weekend", "weekend"):
                days_until_sat = (5 - today_d.weekday()) % 7
                sat = today_d + timedelta(days=days_until_sat)
                sun = sat + timedelta(days=1)
                filters.append(func.date(EventORM.starts_at).in_([sat, sun]))

        if date_from:
            filters.append(func.date(EventORM.starts_at) >= date_from)
        if date_to:
            filters.append(func.date(EventORM.starts_at) <= date_to)

        stmt = (
            select(EventORM)
            .options(
                selectinload(EventORM.ticket_categories),
                defer(EventORM.layout_image_url),
                defer(EventORM.gallery_images),
                defer(EventORM.artists),
            )
        )

        min_price_subq = (
            select(
                TicketCategoryORM.event_id,
                func.min(TicketCategoryORM.price_paise).label("min_price"),
            )
            .where(TicketCategoryORM.is_active == True)
            .group_by(TicketCategoryORM.event_id)
            .subquery()
        )

        if price:
            stmt = stmt.join(min_price_subq, EventORM.id == min_price_subq.c.event_id)
            pr = price.lower().strip()
            if pr == "free":
                filters.append(min_price_subq.c.min_price == 0)
            elif pr in ("0-500", "under-500"):
                filters.append(min_price_subq.c.min_price <= 50000)
            elif pr in ("500-2000", "501-2000"):
                filters.append(and_(min_price_subq.c.min_price >= 50000, min_price_subq.c.min_price <= 200000))
            elif pr in ("2000+", "above-2000", "2000-above"):
                filters.append(min_price_subq.c.min_price >= 200000)
        elif price_max_paise:
            stmt = stmt.join(min_price_subq, EventORM.id == min_price_subq.c.event_id)
            filters.append(min_price_subq.c.min_price <= price_max_paise)

        stmt = stmt.where(and_(*filters))

        subq = stmt.subquery()
        count_stmt = select(func.count(func.distinct(subq.c.id))).select_from(subq)
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
        eid = event.id if isinstance(event.id, uuid.UUID) else uuid.UUID(str(event.id))
        stmt = select(EventORM).where(EventORM.id == eid)
        res = await self.db.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            raise RepositoryError(f"Event {event.id} not found for update")

        for key, value in event.__dict__.items():
            if key != 'ticket_categories' and hasattr(orm, key):
                if hasattr(value, "value"):
                    setattr(orm, key, value.value)
                else:
                    setattr(orm, key, value)
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

    async def list_all_admin(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[Event], int]:
        filters = []
        if status:
            filters.append(EventORM.status == status)
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    EventORM.title.ilike(term),
                    EventORM.city.ilike(term),
                    EventORM.venue_name.ilike(term),
                    EventORM.category.ilike(term),
                )
            )

        stmt = select(EventORM).options(selectinload(EventORM.ticket_categories))
        if filters:
            stmt = stmt.where(and_(*filters))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(EventORM.created_at.desc())
        result = await self.db.execute(stmt)
        return [self._to_domain(orm) for orm in result.scalars().all()], total

    async def delete(self, event_id: uuid.UUID) -> None:
        orm = await self.db.get(EventORM, str(event_id))
        if orm:
            await self.db.delete(orm)
            await self.db.commit()