import uuid
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Numeric, Integer, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class EventORM(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=False, index=True)

    title = Column(String(150), nullable=False)
    slug = Column(String(180), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)
    event_type = Column(String(20), nullable=False, default="STANDARD")
    seating_mode = Column(String(20), nullable=False, default="TIER")
    venue_name = Column(String(255), nullable=False)
    venue_address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    latitude = Column(Numeric(9, 6), nullable=True)
    longitude = Column(Numeric(9, 6), nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    doors_open_at = Column(DateTime(timezone=True), nullable=True)
    age_restriction = Column(String(20), nullable=True)
    is_online = Column(Boolean, nullable=False, default=False)
    online_link = Column(String(500), nullable=True)
    poster_image_url = Column(String(500), nullable=True)
    cancellation_policy = Column(String(30), nullable=False, default="FLEXIBLE")
    status = Column(String(30), nullable=False, default="DRAFT")
    published_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    ticket_categories = relationship("TicketCategoryORM", back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint('ends_at > starts_at', name='check_ends_after_starts'),
    )

class TicketCategoryORM(Base):
    __tablename__ = "event_ticket_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    price_paise = Column(Integer, nullable=False)
    capacity = Column(Integer, nullable=False)
    max_per_booking = Column(Integer, nullable=False, default=6)
    sales_open_at = Column(DateTime(timezone=True), nullable=True)
    sales_close_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    event = relationship("EventORM", back_populates="ticket_categories")

    __table_args__ = (
        UniqueConstraint('event_id', 'name', name='uq_event_category_name'),
        CheckConstraint('price_paise > 0', name='check_price_positive'),
        CheckConstraint('capacity > 0', name='check_capacity_positive'),
    )