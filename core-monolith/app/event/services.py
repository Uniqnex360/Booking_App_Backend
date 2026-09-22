import uuid
import re
from datetime import datetime, timezone
from app.event.exceptions import EventLockedError
from app.auth.interfaces import ValidationError, NotFoundError
from app.shared.exceptions import ForbiddenError
from app.partner.interfaces import PartnerNotApprovedError, PartnerStatus
from app.partner.interfaces import IPartnerRepository

from typing import Optional, List, Tuple, Callable
from app.event.interfaces import (
    IEventRepository, ITicketCategoryRepository, Event, TicketCategory,
    EventStatus
)

EDIT_LOCK_HOURS = 24


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text


class EventService:
    def __init__(
        self,
        event_repo: IEventRepository,
        partner_repo: IPartnerRepository,
        clock: Callable[[], datetime] = None,
    ):
        self.event_repo = event_repo
        self.partner_repo = partner_repo
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def create_event(self, partner_id: uuid.UUID, data: dict) -> Event:
        partner = await self.partner_repo.get_by_id(partner_id)
        if not partner:
            raise NotFoundError("Partner not found")
        if partner.status != PartnerStatus.APPROVED:
            raise PartnerNotApprovedError("Partner must be approved before hosting events")
        now = self.clock()
        starts_at = data['starts_at']
        ends_at = data['ends_at']
        
        # Ensure tz-aware
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if starts_at <= now:
            raise ValidationError("Event starts_at must be in the future")
        if ends_at <= starts_at:
            raise ValidationError("Event ends_at must be after starts_at")
        
        event_id = uuid.uuid4()
        slug = slugify(data['title'])
        
        if await self.event_repo.get_by_slug(slug):
            slug = f"{slug}-{str(event_id)[:8]}"

        event = Event(
            id=event_id,
            partner_id=partner_id,
            title=data['title'],
            slug=slug,
            category=data['category'],
            venue_name=data['venue_name'],
            venue_address=data.get('venue_address'),
            city=data['city'],
            starts_at=starts_at,
            ends_at=ends_at,
            description=data.get('description'),
            is_online=data.get('is_online', False),
            online_link=data.get('online_link'),
            status=EventStatus.PENDING_APPROVAL
        )

        # Attach ticket categories
        if 'ticket_categories' in data and data['ticket_categories']:
            event.ticket_categories = [
                TicketCategory(
                    id=uuid.uuid4(),
                    event_id=event_id,
                    name=tc['name'],
                    price_paise=tc['price_paise'],
                    capacity=tc['capacity'],
                    description=tc.get('description'),
                    max_per_booking=tc.get('max_per_booking', 6),
                    is_active=True
                )
                for tc in data['ticket_categories']
            ]

        return await self.event_repo.create(event)

    async def list_public(self, **filters) -> Tuple[List[Event], int]:
        return await self.event_repo.list_published(
            city=filters.get('city'),
            category=filters.get('category'),
            date_from=filters.get('date_from'),
            date_to=filters.get('date_to'),
            price_max_paise=filters.get('price_max_paise'),
            page=filters.get('page', 1),
            limit=filters.get('limit', 10)
        )

    async def list_for_partner(self, partner_id: uuid.UUID) -> List[Event]:
        events, _ = await self.event_repo.list_for_partner(partner_id, None, 1, 100)
        return events

    async def get_event_details(self, event_id: uuid.UUID) -> Event:
        event = await self.event_repo.get_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found")
        return event

    async def update_event(self, partner_id: uuid.UUID, event_id: uuid.UUID, patch_data: dict) -> Event:
        event = await self.event_repo.get_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found")
        if event.partner_id != partner_id:
            raise ForbiddenError("Access denied")
        
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        event_start = event.starts_at if event.starts_at.tzinfo else event.starts_at.replace(tzinfo=timezone.utc)

        if event.status == EventStatus.PUBLISHED:
            time_until_start = event_start - now
            if time_until_start.total_seconds() < (EDIT_LOCK_HOURS * 3600):
                raise EventLockedError("Events cannot be edited within 24 hours of the start time.")

        for key, value in patch_data.items():
            if value is not None and hasattr(event, key):
                setattr(event, key, value)

        return await self.event_repo.update(event)

    async def update_status(self, partner_id: uuid.UUID, event_id: uuid.UUID, 
                          new_status: EventStatus, reason: str = None) -> Event:
        event = await self.event_repo.get_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found")
        if event.partner_id != partner_id:
            raise ForbiddenError("Access denied")
        
        valid = {
            EventStatus.DRAFT: [EventStatus.PUBLISHED, EventStatus.CANCELLED, EventStatus.PENDING_APPROVAL],
            EventStatus.PENDING_APPROVAL: [EventStatus.CANCELLED],
            EventStatus.PUBLISHED: [EventStatus.CANCELLED, EventStatus.COMPLETED]
        }
        
        if new_status not in valid.get(event.status, []):
            raise ValidationError(f"Cannot move from {event.status} to {new_status}")
            
        if new_status == EventStatus.PUBLISHED:
            if not event.ticket_categories:
                raise ValidationError("Cannot publish event without ticket categories")
            event.published_at = self.clock()
            
        if new_status == EventStatus.CANCELLED:
            if not reason:
                reason = "Cancelled by organizer"
            event.cancelled_at = self.clock()
            event.cancellation_reason = reason

        event.status = new_status
        return await self.event_repo.update(event)

    async def delete_or_cancel_event(self, partner_id: uuid.UUID, event_id: uuid.UUID, reason: Optional[str] = None) -> Event:
        event = await self.event_repo.get_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found")
        if event.partner_id != partner_id:
            raise ForbiddenError("Access denied")

        if event.status in (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL):
            # Safe to mark cancelled directly
            event.status = EventStatus.CANCELLED
            event.cancelled_at = self.clock()
            event.cancellation_reason = reason or "Deleted by organizer"
            return await self.event_repo.update(event)
        
        return await self.update_status(partner_id, event_id, EventStatus.CANCELLED, reason or "Cancelled by organizer")
