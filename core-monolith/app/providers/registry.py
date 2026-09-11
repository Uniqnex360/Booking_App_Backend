from __future__ import annotations

from app.providers.theatre import PVRProvider


import uuid
from uuid import UUID
import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.database import Base
from app.providers.base import ITheatreProvider


class ProviderRegistryModel(Base):
    __tablename__ = "provider_registry"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    auth_token_ref = Column(String, nullable=True)
    hold_ttl_seconds = Column(Integer, nullable=False, server_default=sa.text("600"))
    enabled = Column(Boolean, nullable=False, server_default=sa.text("true"))
    partner_id = Column(PG_UUID(as_uuid=True), ForeignKey("partners.id"), nullable=True)


def create_provider_client(
    registry: ProviderRegistryModel,
    client: Any = None,
) -> ITheatreProvider:
    name_lower = registry.name.lower()
    if "pvr" in name_lower:
        return PVRProvider(
            base_url=registry.base_url,
            auth_token=registry.auth_token_ref,
            timeout_seconds=float(registry.hold_ttl_seconds if registry.hold_ttl_seconds < 15 else 5.0),
            client=client,
        )
    # Default fallback
    return PVRProvider(
        base_url=registry.base_url,
        auth_token=registry.auth_token_ref,
        client=client,
    )