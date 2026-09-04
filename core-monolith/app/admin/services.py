
import uuid
from typing import List
from app.event.interfaces import Event, EventStatus
from app.event.repository import SQLAlchemyEventRepository
from app.partner.services import PartnerService 
from app.auth.interfaces import NotFoundError

class AdminService:
    def __init__(self, event_repo: SQLAlchemyEventRepository):
        self.event_repo = event_repo

    async def list_pending_events(self) -> List[Event]:
        events, _ = await self.event_repo.list_by_status(
            status=EventStatus.PENDING_APPROVAL, page=1, limit=100
        )
        return events

    async def approve_or_reject_event(
        self, 
        event_id: uuid.UUID, 
        new_status: EventStatus, 
        rejection_reason: str = None
    ) -> Event:
        
        event = await self.event_repo.get_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found")

        
        event.status = new_status
        if new_status == EventStatus.REJECTED:
            event.rejection_reason = rejection_reason

        
        return await self.event_repo.update(event)