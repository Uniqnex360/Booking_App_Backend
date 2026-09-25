from pydantic import BaseModel, Field, field_validator, AnyHttpUrl
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


class _PosterUrlMixin(BaseModel):
    poster_image_url: Optional[AnyHttpUrl] = None


class EventUpdateRequest(_PosterUrlMixin):
    title: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = None
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    city: Optional[str] = None
    is_outdoor: Optional[bool] = None
    is_fast_filling: Optional[bool] = None
    is_must_attend: Optional[bool] = None
    is_unmissable: Optional[bool] = None
    is_kids_allowed: Optional[bool] = None
    is_masterclass: Optional[bool] = None
    is_new_year_party: Optional[bool] = None
    language: Optional[str] = None
    tags: List[str] = []


class EventCreateRequest(_PosterUrlMixin):
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
    is_outdoor: bool = False
    is_fast_filling: bool = False
    is_must_attend: bool = False
    is_unmissable: bool = False
    is_kids_allowed: bool = False
    is_masterclass: bool = False
    is_new_year_party: bool = False
    language: Optional[str] = None
    tags: List[str] = []

class EventStatusUpdateRequest(BaseModel):
    status: EventStatus
    cancellation_reason: Optional[str] = None

    @field_validator("cancellation_reason")
    @classmethod
    def reason_required_for_cancel(cls, v, info):
        if info.data.get("status") == EventStatus.CANCELLED and not v:
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
    is_outdoor: bool = False
    is_fast_filling: bool = False
    is_must_attend: bool = False
    is_unmissable: bool = False
    is_kids_allowed: bool = False
    is_masterclass: bool = False
    language: Optional[str] = None
    tags: List[str] = []
    is_new_year_party: bool = False

    class Config:
        from_attributes = True


class EventDetailResponse(EventResponse):
    description: Optional[str]
    ticket_categories: List[TicketCategoryBase]
    is_outdoor: bool = False
    is_fast_filling: bool = False
    is_must_attend: bool = False
    is_unmissable: bool = False
    is_kids_allowed: bool = False
    is_masterclass: bool = False
    is_new_year_party: bool = False
    language: Optional[str] = None
    tags: List[str] = []