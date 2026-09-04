import uuid
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, List, Protocol
from app.shared.exceptions import EntityNotFoundError, UnauthorizedError
@dataclass
class UserProfile:
    id: uuid.UUID
    user_id: uuid.UUID
    avatar_url: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    preferred_language: str = "en"
    bio: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
@dataclass
class Address:
    id: uuid.UUID
    user_id: uuid.UUID
    label: str
    line1: str
    city: str
    state: str
    pincode: str
    line2: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
class ProfileNotFoundError(EntityNotFoundError):
    def __init__(self):
        super().__init__("User profile not found")
class AddressNotFoundError(EntityNotFoundError):
    def __init__(self):
        super().__init__("Address not found")
class UnauthorizedAddressAccessError(UnauthorizedError):
    def __init__(self):
        super().__init__("You do not have access to this address")
class IUserProfileRepository(Protocol):
    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[UserProfile]: ...
    async def create(self, profile: UserProfile) -> UserProfile: ...
    async def update(self, profile: UserProfile) -> UserProfile: ...
class IAddressRepository(Protocol):
    async def get_by_id(self, address_id: uuid.UUID) -> Optional[Address]: ...
    async def list_by_user(self, user_id: uuid.UUID) -> List[Address]: ...
    async def create(self, address: Address) -> Address: ...
    async def update(self, address: Address) -> Address: ...
    async def delete(self, address_id: uuid.UUID) -> None: ...
    async def unset_default_for_user(self, user_id: uuid.UUID) -> None: ...