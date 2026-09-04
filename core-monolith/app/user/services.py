
import uuid
from typing import List, Optional
from app.shared.exceptions import UnauthorizedError
from app.user.interfaces import AddressNotFoundError

from app.user.interfaces import (
    IUserProfileRepository, IAddressRepository, 
    UserProfile, Address
)


class UserProfileService:
    def __init__(
        self, 
        profile_repo: IUserProfileRepository, 
        address_repo: IAddressRepository
    ):
        self.profile_repo = profile_repo
        self.address_repo = address_repo

    
    async def get_or_create_profile(self, user_id: uuid.UUID) -> UserProfile:
        profile = await self.profile_repo.get_by_user_id(user_id)
        if not profile:
            new_profile = UserProfile(id=uuid.uuid4(), user_id=user_id)
            return await self.profile_repo.create(new_profile)
        return profile

    async def update_profile(self, user_id: uuid.UUID, update_data: dict) -> UserProfile:
        profile = await self.get_or_create_profile(user_id)
        
        
        for key, value in update_data.items():
            if hasattr(profile, key) and value is not None:
                setattr(profile, key, value)
        
        return await self.profile_repo.update(profile)

    async def list_addresses(self, user_id: uuid.UUID) -> List[Address]:
        return await self.address_repo.list_by_user(user_id)

    async def add_address(self, user_id: uuid.UUID, address_data: dict) -> Address:
        
        if address_data.get("is_default"):
            await self.address_repo.unset_default_for_user(user_id)
        
        new_address = Address(
            id=uuid.uuid4(),
            user_id=user_id,
            **address_data 
        )
        return await self.address_repo.create(new_address)

    async def update_address(self, user_id: uuid.UUID, address_id: uuid.UUID, update_data: dict) -> Address:
        address = await self.address_repo.get_by_id(address_id)
        if not address:
            raise AddressNotFoundError()
        
        
        if address.user_id != user_id:
            raise UnauthorizedError("Access Denied")

        if update_data.get("is_default"):
            await self.address_repo.unset_default_for_user(user_id)

        for key, value in update_data.items():
            if hasattr(address, key) and value is not None:
                setattr(address, key, value)
        
        return await self.address_repo.update(address)

    async def delete_address(self, user_id: uuid.UUID, address_id: uuid.UUID) -> None:
        address = await self.address_repo.get_by_id(address_id)
        if not address:
            raise AddressNotFoundError()
        
        if address.user_id != user_id:
            raise UnauthorizedError("Access Denied")
            
        await self.address_repo.delete(address_id)