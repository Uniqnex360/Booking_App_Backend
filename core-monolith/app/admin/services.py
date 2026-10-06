
import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.event.interfaces import Event, EventStatus
from app.event.repository import SQLAlchemyEventRepository
from app.auth.interfaces import NotFoundError

class AdminService:
    def __init__(self, event_repo: SQLAlchemyEventRepository):
        self.event_repo = event_repo

    async def list_pending_events(self) -> List[Event]:
        events, _ = await self.event_repo.list_by_status(
            status=EventStatus.PENDING_APPROVAL, page=1, limit=100
        )
        return events

    async def list_events(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[Event], int]:
        return await self.event_repo.list_all_admin(
            status=status,
            search=search,
            page=page,
            limit=limit,
        )

    async def approve_or_reject_event(
        self, 
        event_id: uuid.UUID, 
        new_status: str | EventStatus, 
        rejection_reason: str = None
    ) -> Event:
        event = await self.event_repo.get_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found")

        status_enum = EventStatus(new_status) if isinstance(new_status, str) else new_status
        event.status = status_enum
        if status_enum == EventStatus.REJECTED:
            event.rejection_reason = rejection_reason
        elif status_enum == EventStatus.PUBLISHED:
            event.rejection_reason = None

        return await self.event_repo.update(event)

    async def get_platform_stats(self, db: AsyncSession) -> dict:
        from sqlalchemy import select, func
        from app.auth.models import User as UserORM
        from app.movie.models import Movie as MovieORM
        from app.event.models import EventORM
        from app.partner.models import PartnerORM

        total_users = (await db.execute(select(func.count(UserORM.id)))).scalar() or 0
        active_users = (await db.execute(select(func.count(UserORM.id)).where(UserORM.is_active.is_(True)))).scalar() or 0
        blocked_users = total_users - active_users

        total_movies = (await db.execute(select(func.count(MovieORM.id)))).scalar() or 0
        published_movies = (await db.execute(select(func.count(MovieORM.id)).where(MovieORM.status == 'PUBLISHED'))).scalar() or 0
        draft_movies = total_movies - published_movies

        total_events = (await db.execute(select(func.count(EventORM.id)))).scalar() or 0
        published_events = (await db.execute(select(func.count(EventORM.id)).where(EventORM.status == 'PUBLISHED'))).scalar() or 0
        pending_events = (await db.execute(select(func.count(EventORM.id)).where(EventORM.status == 'PENDING_APPROVAL'))).scalar() or 0
        rejected_events = (await db.execute(select(func.count(EventORM.id)).where(EventORM.status == 'REJECTED'))).scalar() or 0

        total_partners = (await db.execute(select(func.count(PartnerORM.id)))).scalar() or 0
        pending_partners = (await db.execute(select(func.count(PartnerORM.id)).where(PartnerORM.status == 'PENDING_APPROVAL'))).scalar() or 0
        approved_partners = (await db.execute(select(func.count(PartnerORM.id)).where(PartnerORM.status == 'APPROVED'))).scalar() or 0

        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "blocked": blocked_users,
            },
            "movies": {
                "total": total_movies,
                "published": published_movies,
                "draft": draft_movies,
            },
            "events": {
                "total": total_events,
                "published": published_events,
                "pending": pending_events,
                "rejected": rejected_events,
            },
            "partners": {
                "total": total_partners,
                "pending": pending_partners,
                "approved": approved_partners,
            },
        }