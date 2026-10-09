from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.user.services import UserProfileService
from app.user.interfaces import IUserProfileRepository, IAddressRepository
from app.user.repository import SQLAlchemyUserProfileRepository
from app.user.repository import SQLAlchemyAddressRepository
def get_user_repo(db: AsyncSession = Depends(get_db)):
    return SQLAlchemyUserRepository(db)
def get_profile_repo(db: AsyncSession = Depends(get_db)) -> IUserProfileRepository:
    return SQLAlchemyUserProfileRepository(db)

def get_address_repo(db: AsyncSession = Depends(get_db)) -> IAddressRepository:
    return SQLAlchemyAddressRepository(db)

def get_user_service(
    profile_repo: IUserProfileRepository = Depends(get_profile_repo),
    address_repo: IAddressRepository = Depends(get_address_repo)
) -> UserProfileService:
    return UserProfileService(profile_repo, address_repo)