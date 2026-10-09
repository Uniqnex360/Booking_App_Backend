

import uuid
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple, Protocol


from app.shared.exceptions import RepositoryError, EntityNotFoundError, DuplicateEntityError


class PartnerType(str, Enum):
    RESTAURANT = "restaurant"
    CINEMA = "cinema"
    EVENT_ORGANISER = "event_organiser"

class PartnerStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


@dataclass
class Partner:
    id: uuid.UUID
    user_id: uuid.UUID
    business_name: str
    partner_type: PartnerType
    contact_name: str
    contact_phone: str
    city: str
    status: PartnerStatus
    commission_rate: float
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[uuid.UUID] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InvalidStatusTransitionError(Exception):
    def __init__(self, from_status: PartnerStatus, to_status: PartnerStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition from {from_status.value} to {to_status.value}")

class PartnerNotApprovedError(Exception):
    def __init__(self):
        super().__init__("Partner account is not approved.")


class IPartnerRepository(Protocol):
    async def get_by_id(self, partner_id: uuid.UUID) -> Optional[Partner]: ...
    
    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[Partner]: ...
    
    async def list_by_filters(
        self, 
        status: Optional[PartnerStatus], 
        partner_type: Optional[PartnerType], 
        page: int, 
        limit: int
    ) -> Tuple[List[Partner], int]: 
        ...
        
    async def create(self, partner: Partner) -> Partner: ...
    
    async def update(self, partner: Partner) -> Partner: ...