import uuid
import enum
from dataclasses import dataclass, field
from datetime import datetime, date, time
from typing import Optional, Protocol, List, Tuple
from decimal import Decimal

# class EventStatus(str, enum.Enum):
#     DRAFT = "DRAFT"
#     PENDING_APPROVAL = "PENDING_APPROVAL"
#     PUBLISHED = "PUBLISHED"
#     CANCELLED = "CANCELLED"
#     COMPLETED = "COMPLETED"
#     PENDING_REVIEW = "PENDING_REVIEW"
class EventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL" 
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
class EventCategory(str, enum.Enum):
    CONCERT = "concert"
    COMEDY = "comedy"
    SPORTS = "sports"
    WORKSHOP = "workshop"
    THEATRE = "theatre"
    EXHIBITION = "exhibition"
    OTHER = "other"

class CancellationPolicy(str, enum.Enum):
    NONE = "NONE"
    FLEXIBLE = "FLEXIBLE"
    STRICT = "STRICT"

class SeatingMode(str, enum.Enum):
    TIER = "TIER"

@dataclass
class TicketCategory:
    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    price_paise: int
    capacity: int
    max_per_booking: int = 6
    description: Optional[str] = None
    sales_open_at: Optional[datetime] = None
    sales_close_at: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Event:
    id: uuid.UUID
    partner_id: uuid.UUID
    title: str
    slug: str
    category: EventCategory
    venue_name: str
    city: str
    starts_at: datetime
    ends_at: datetime
    description: Optional[str] = None
    event_type: str = "STANDARD"
    seating_mode: SeatingMode = SeatingMode.TIER
    venue_address: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    doors_open_at: Optional[datetime] = None
    age_restriction: Optional[str] = None
    is_online: bool = False
    online_link: Optional[str] = None
    poster_image_url: Optional[str] = None
    cancellation_policy: CancellationPolicy = CancellationPolicy.FLEXIBLE
    status: EventStatus = EventStatus.DRAFT
    published_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    ticket_categories: List[TicketCategory] = field(default_factory=list)

class IEventRepository(Protocol):
    async def create(self, event: Event) -> Event: ...
    async def get_by_id(self, event_id: uuid.UUID) -> Optional[Event]: ...
    async def get_by_slug(self, slug: str) -> Optional[Event]: ...
    async def list_for_partner(self, partner_id: uuid.UUID, status: Optional[EventStatus], page: int, limit: int) -> Tuple[List[Event], int]: ...
    async def list_published(self, city: Optional[str], category: Optional[EventCategory], date_from: Optional[date], date_to: Optional[date], price_max_paise: Optional[int], page: int, limit: int) -> Tuple[List[Event], int]: ...
    async def update(self, event: Event) -> Event: ...
    async def delete(self, event_id: uuid.UUID) -> None: ...
    async def list_by_status(
        self, 
        status: EventStatus, 
        page: int, 
        limit: int
    ) -> Tuple[List[Event], int]: ...
class ITicketCategoryRepository(Protocol):
    async def create(self, category: TicketCategory) -> TicketCategory: ...
    async def get_by_id(self, category_id: uuid.UUID) -> Optional[TicketCategory]: ...
    async def list_for_event(self, event_id: uuid.UUID) -> List[TicketCategory]: ...
    async def update(self, category: TicketCategory) -> TicketCategory: ...
    async def delete(self, category_id: uuid.UUID) -> None: ...