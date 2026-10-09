import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from app.user.exceptions import UserRepositoryHTTP

# Shared logic
from app.shared.response import success_response
from app.shared.exceptions import UnauthorizedError, RepositoryError

# Auth dependencies
from app.auth.dependencies import get_current_user
from app.auth.interfaces import User as AuthUserDomain

# User logic
from app.user.dependencies import get_user_service
from app.user.services import UserProfileService
from app.user.interfaces import ProfileNotFoundError, AddressNotFoundError
from app.user.schemas import (
    ProfileUpdateRequest,
    AddressCreateRequest, 
    AddressUpdateRequest
)
from app.user.exceptions import (
    ProfileNotFoundHTTP, 
    AddressNotFoundHTTP, 
    UnauthorizedAddressHTTP,
)

router = APIRouter(prefix="/users", tags=["User"])

@router.get("/me")
async def get_my_profile(
    current_user: AuthUserDomain = Depends(get_current_user),
    user_service: UserProfileService = Depends(get_user_service)
):
    try:
        profile = await user_service.get_or_create_profile(current_user.id)
        return success_response(
            data=profile, 
            message="Profile fetched successfully."
        )
    except RepositoryError as e:
        raise UserRepositoryHTTP(str(e))

@router.patch("/me")
async def update_my_profile(
    update_data: ProfileUpdateRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    user_service: UserProfileService = Depends(get_user_service)
):
    try:
        data = update_data.model_dump(exclude_unset=True)
        profile = await user_service.update_profile(current_user.id, data)
        return success_response(
            data=profile, 
            message="Profile updated successfully."
        )
    except ProfileNotFoundError:
        raise ProfileNotFoundHTTP()
    except RepositoryError as e:
        raise UserRepositoryHTTP(str(e))

@router.get("/me/addresses")
async def list_my_addresses(
    current_user: AuthUserDomain = Depends(get_current_user),
    user_service: UserProfileService = Depends(get_user_service)
):
    try:
        addresses = await user_service.list_addresses(current_user.id)
        # Wrapping in a dict to match the "addresses": [] requirement in the spec
        return success_response(
            data={"addresses": addresses}, 
            message="Addresses fetched successfully."
        )
    except RepositoryError as e:
        raise UserRepositoryHTTP(str(e))

@router.post("/me/addresses", status_code=201)
async def add_address(
    address_data: AddressCreateRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    user_service: UserProfileService = Depends(get_user_service)
):
    try:
        data = address_data.model_dump()
        address = await user_service.add_address(current_user.id, data)
        return success_response(
            data=address, 
            message="Address added successfully.",
            code=201
        )
    except RepositoryError as e:
        raise UserRepositoryHTTP(str(e))

@router.patch("/me/addresses/{address_id}")
async def update_address(
    address_id: uuid.UUID,
    update_data: AddressUpdateRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    user_service: UserProfileService = Depends(get_user_service)
):
    try:
        data = update_data.model_dump(exclude_unset=True)
        address = await user_service.update_address(current_user.id, address_id, data)
        return success_response(
            data=address, 
            message="Address updated successfully."
        )
    except AddressNotFoundError:
        raise AddressNotFoundHTTP()
    except UnauthorizedError:
        raise UnauthorizedAddressHTTP()
    except RepositoryError as e:
        raise UserRepositoryHTTP(str(e))

@router.delete("/me/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: uuid.UUID,
    current_user: AuthUserDomain = Depends(get_current_user),
    user_service: UserProfileService = Depends(get_user_service)
):
    try:
        await user_service.delete_address(current_user.id, address_id)
        return success_response(
            data=None, 
            message="Address deleted successfully.",
            code=204
        )
    except AddressNotFoundError:
        raise AddressNotFoundHTTP()
    except UnauthorizedError:
        raise UnauthorizedAddressHTTP()
    except RepositoryError as e:
        raise UserRepositoryHTTP(str(e))