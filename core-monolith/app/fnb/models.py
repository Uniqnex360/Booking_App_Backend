from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.database import Base
from app.shared.timeutil import TZDateTime, utcnow


FNB_CATEGORIES = ("Popcorn", "Beverages", "Snacks", "Combos", "Desserts")


class FnbItemModel(Base):
    __tablename__ = "fnb_items"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("venues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(20), nullable=False)
    price_paise = Column(Integer, nullable=False)
    image_url = Column(Text, nullable=True)
    is_veg = Column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    is_active = Column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    created_at = Column(TZDateTime, nullable=False, default=utcnow)
    updated_at = Column(TZDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("price_paise >= 0", name="ck_fnb_items_price_paise"),
        CheckConstraint(
            "category IN ('Popcorn','Beverages','Snacks','Combos','Desserts')",
            name="ck_fnb_items_category",
        ),
        sa.Index("ix_fnb_items_venue_active", "venue_id", "is_active"),
    )


class BookingFnbModel(Base):
    __tablename__ = "booking_fnb"

    booking_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    item_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("fnb_items.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    quantity = Column(Integer, nullable=False)
    unit_price_paise = Column(Integer, nullable=False)
    created_at = Column(TZDateTime, nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint("quantity >= 1 AND quantity <= 10", name="ck_booking_fnb_quantity"),
        CheckConstraint("unit_price_paise >= 0", name="ck_booking_fnb_unit_price_paise"),
    )