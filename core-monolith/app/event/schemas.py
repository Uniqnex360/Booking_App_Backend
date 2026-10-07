from pydantic import BaseModel, Field, field_validator, AnyHttpUrl
from datetime import datetime, date, time
from decimal import Decimal
from typing import List, Optional
import uuid
from app.event.interfaces import EventStatus, EventCategory, CancellationPolicy
class ArtistIn(BaseModel):
    name: str
    role: str | None = None
    image_url: str | None = None

class FaqIn(BaseModel):
    question: str
    answer: str

class PromoterIn(BaseModel):
    name: str | None = None
    contact: str | None = None
    details: str | None = None

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
    layout_image_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    artists: Optional[List[ArtistIn]] = None
    faqs: Optional[List[FaqIn]] = None
    terms_and_conditions: Optional[List[str]] = None
    offline_promoter: Optional[PromoterIn] = None
    is_kids_allowed: Optional[bool] = None
    is_masterclass: Optional[bool] = None
    is_new_year_party: Optional[bool] = None
    language: Optional[str] = None
    tags: List[str] = []
    cuisine: Optional[List[str]] = None
    price_range: Optional[int] = None
    what_included: Optional[str] = None


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
    layout_image_url: Optional[str] = None
    gallery_images: List[str] = Field(default_factory=list)
    artists: List[ArtistIn] = Field(default_factory=list)
    faqs: List[FaqIn] = Field(default_factory=list)
    terms_and_conditions: List[str] = Field(default_factory=list)
    offline_promoter: Optional[PromoterIn] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_must_attend: bool = False
    is_unmissable: bool = False
    is_kids_allowed: bool = False
    is_masterclass: bool = False
    is_new_year_party: bool = False
    language: Optional[str] = None
    tags: List[str] = []
    cuisine: Optional[List[str]] = Field(default_factory=list)
    price_range: Optional[int] = Field(None, ge=1, le=4)
    what_included: Optional[str] = None

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
    cuisine: Optional[List[str]] = None
    price_range: Optional[int] = None
    what_included: Optional[str] = None
    min_price_paise: Optional[int] = None

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