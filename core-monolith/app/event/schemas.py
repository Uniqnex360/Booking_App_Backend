from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date, time
from decimal import Decimal
from typing import List, Optional
import uuid
from app.event.interfaces import EventStatus, EventCategory, CancellationPolicy

class TicketCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    price_paise: int = Field(..., gt=0)
    capacity: int = Field(..., gt=0)
    description: Optional[str] = None
    max_per_booking: int = Field(6, gt=0)

class EventCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    category: EventCategory
    description: Optional[str] = None
    venue_name: str
    venue_address: Optional[str] = None
    city: str
    starts_at: datetime
    ends_at: datetime
    is_online: bool = False
    online_link: Optional[str] = None
    cancellation_policy: CancellationPolicy = CancellationPolicy.FLEXIBLE
    ticket_categories: List[TicketCategoryBase]

class EventStatusUpdateRequest(BaseModel):
    status: EventStatus
    cancellation_reason: Optional[str] = None

    @field_validator('cancellation_reason')
    @classmethod
    def reason_required_for_cancel(cls, v, info):
        if info.data.get('status') == EventStatus.CANCELLED and not v:
            raise ValueError("Cancellation reason is required when status is CANCELLED")
        return v

class EventResponse(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    category: EventCategory
    venue_name: str
    city: str
    starts_at: datetime
    ends_at: datetime
    status: EventStatus
    poster_image_url: Optional[str]
    
    class Config:
        from_attributes = True

class EventDetailResponse(EventResponse):
    description: Optional[str]
    ticket_categories: List[TicketCategoryBase]