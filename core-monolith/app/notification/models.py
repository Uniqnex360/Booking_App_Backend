from __future__ import annotations

import uuid
import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.core.database import Base
from app.shared.timeutil import utcnow


class UserNotificationModel(Base):
    __tablename__ = "user_notifications"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    type = Column(String(32), nullable=False, server_default=sa.text("'booking'"))
    link = Column(String(512), nullable=True)
    is_read = Column(Boolean, nullable=False, default=False, server_default=sa.text("false"))
    reference_key = Column(String(128), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.text("now()"),
    )


class UserDeviceTokenModel(Base):
    __tablename__ = "user_device_tokens"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fcm_token = Column(String(512), nullable=False, unique=True)
    platform = Column(String(32), nullable=False, server_default=sa.text("'web'"))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.text("now()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.text("now()"),
    )

