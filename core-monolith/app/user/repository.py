

import uuid
from typing import Optional, List
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.auth.exceptions import RepositoryError,ProfileNotFoundError
from app.user.interfaces import AddressNotFoundError

from app.user.interfaces import (
    IUserProfileRepository, 
    IAddressRepository, 
    UserProfile, 
    Address, 
    AccountDeletionForbiddenError,
)
from app.user.models import UserProfileORM, AddressORM
from app.auth.models import User, UsedPhoneEmailVerification
from app.booking.models import BookingModel
from app.payment.models import PaymentModel
from app.partner.models import PartnerORM


class SQLAlchemyUserProfileRepository(IUserProfileRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    
    def _to_domain(self, orm: UserProfileORM) -> UserProfile:
        return UserProfile(
            id=orm.id,
            user_id=orm.user_id,
            avatar_url=orm.avatar_url,
            date_of_birth=orm.date_of_birth,
            gender=orm.gender,
            preferred_language=orm.preferred_language,
            bio=orm.bio,
            created_at=orm.created_at,
            updated_at=orm.updated_at
        )

    def _fill_orm_from_domain(self, orm: UserProfileORM, domain: UserProfile):
        orm.avatar_url = domain.avatar_url
        orm.date_of_birth = domain.date_of_birth
        orm.gender = domain.gender
        orm.preferred_language = domain.preferred_language
        orm.bio = domain.bio

    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[UserProfile]:
        try:
            stmt = select(UserProfileORM).where(UserProfileORM.user_id == user_id)
            result = await self.db.execute(stmt)
            orm_profile = result.scalar_one_or_none()
            return self._to_domain(orm_profile) if orm_profile else None
        except SQLAlchemyError as e:
            raise RepositoryError(f"Failed to fetch profile: {str(e)}")

    async def create(self, profile: UserProfile) -> UserProfile:
        try:
            orm_profile = UserProfileORM(
                id=profile.id,
                user_id=profile.user_id
            )
            self._fill_orm_from_domain(orm_profile, profile)
            
            self.db.add(orm_profile)
            await self.db.commit()
            await self.db.refresh(orm_profile)
            return self._to_domain(orm_profile)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to create profile: {str(e)}")

    async def update(self, profile: UserProfile) -> UserProfile:
        try:
            orm_profile = await self.db.get(UserProfileORM, profile.id)
            if not orm_profile:
                raise ProfileNotFoundError()
            
            self._fill_orm_from_domain(orm_profile, profile)
            
            await self.db.commit()
            await self.db.refresh(orm_profile)
            return self._to_domain(orm_profile)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to update profile: {str(e)}")

    async def delete_account(self, user_id: uuid.UUID) -> None:
        # Check if the user is a partner in partners table (e.g. organiser, theater partner, restaurant partner)
        stmt_partner = select(PartnerORM.id).where(PartnerORM.user_id == user_id)
        partner_res = await self.db.execute(stmt_partner)
        if partner_res.scalar_one_or_none() is not None:
            raise AccountDeletionForbiddenError(
                "Partner and Admin accounts cannot be deleted directly from the app. Please contact support at support@vyhbz.com."
            )

        try:
            # 1. Anonymize payments for bookings belonging to this user (strip raw_event)
            stmt_payments = (
                update(PaymentModel)
                .where(
                    PaymentModel.booking_id.in_(
                        select(BookingModel.id).where(BookingModel.user_id == user_id)
                    )
                )
                .values(raw_event=None)
            )
            await self.db.execute(stmt_payments)

            # 2. Anonymize bookings: unlink user and strip contact PII while keeping financial/accounting records
            stmt_bookings = (
                update(BookingModel)
                .where(BookingModel.user_id == user_id)
                .values(user_id=None, contact_email=None, contact_phone=None)
            )
            await self.db.execute(stmt_bookings)

            # 3. Anonymize phone/email verification replay tracking without breaking replay defense
            stmt_verifications = (
                update(UsedPhoneEmailVerification)
                .where(UsedPhoneEmailVerification.user_id == user_id)
                .values(user_id=None)
            )
            await self.db.execute(stmt_verifications)

            # 4. Delete user record.
            # Cascades in DB will automatically delete:
            # - user_profiles, addresses, user_notifications, user_device_tokens,
            # - movie_reviews, coupon_redemptions, refresh_tokens, otp_codes, password_resets
            stmt_user = delete(User).where(User.id == user_id)
            result = await self.db.execute(stmt_user)
            if result.rowcount == 0:
                raise ProfileNotFoundError()

            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to delete account: {str(e)}")


class SQLAlchemyAddressRepository(IAddressRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    
    def _to_domain(self, orm: AddressORM) -> Address:
        return Address(
            id=orm.id,
            user_id=orm.user_id,
            label=orm.label,
            line1=orm.line1,
            line2=orm.line2,
            city=orm.city,
            state=orm.state,
            pincode=orm.pincode,
            latitude=orm.latitude,
            longitude=orm.longitude,
            is_default=orm.is_default,
            created_at=orm.created_at,
            updated_at=orm.updated_at
        )

    
    def _fill_orm_from_domain(self, orm: AddressORM, domain: Address):
        orm.label = domain.label
        orm.line1 = domain.line1
        orm.line2 = domain.line2
        orm.city = domain.city
        orm.state = domain.state
        orm.pincode = domain.pincode
        orm.latitude = domain.latitude
        orm.longitude = domain.longitude
        orm.is_default = domain.is_default

    async def get_by_id(self, address_id: uuid.UUID) -> Optional[Address]:
        try:
            orm = await self.db.get(AddressORM, address_id)
            return self._to_domain(orm) if orm else None
        except SQLAlchemyError as e:
            raise RepositoryError(f"Failed to fetch address: {str(e)}")

    async def list_by_user(self, user_id: uuid.UUID) -> List[Address]:
        try:
            stmt = select(AddressORM).where(AddressORM.user_id == user_id).order_by(AddressORM.created_at.desc())
            result = await self.db.execute(stmt)
            return [self._to_domain(row) for row in result.scalars().all()]
        except SQLAlchemyError as e:
            raise RepositoryError(f"Failed to list addresses: {str(e)}")

    async def create(self, address: Address) -> Address:
        try:
            orm = AddressORM(id=address.id, user_id=address.user_id)
            self._fill_orm_from_domain(orm, address)
            
            self.db.add(orm)
            await self.db.commit()
            await self.db.refresh(orm)
            return self._to_domain(orm)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to create address: {str(e)}")

    async def update(self, address: Address) -> Address:
        try:
            orm = await self.db.get(AddressORM, address.id)
            if not orm:
                raise AddressNotFoundError()
            
            self._fill_orm_from_domain(orm, address)
            
            await self.db.commit()
            await self.db.refresh(orm)
            return self._to_domain(orm)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to update address: {str(e)}")

    async def delete(self, address_id: uuid.UUID) -> None:
        try:
            stmt = delete(AddressORM).where(AddressORM.id == address_id)
            await self.db.execute(stmt)
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to delete address: {str(e)}")

    async def unset_default_for_user(self, user_id: uuid.UUID) -> None:
       
        try:
            stmt = (
                update(AddressORM)
                .where(AddressORM.user_id == user_id, AddressORM.is_default == True)
                .values(is_default=False)
            )
            await self.db.execute(stmt)
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to reset default addresses: {str(e)}")