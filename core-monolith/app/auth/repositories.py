from datetime import datetime, timedelta
from typing import Optional, List
import uuid

from sqlalchemy import select, and_, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.models import User as UserORM, RefreshToken as RefreshTokenORM, OTPCode as OTPCodeORM

from app.auth.interfaces import (
    User as UserDomain, 
    RefreshToken as RefreshTokenDomain,
    OTPCodes as OTPCodesDomain,
    IUserRepository, 
    IRefreshTokenRepository, 
    IOTPCodesRepository,
    RepositoryError,
    DuplicateError,
    NotFoundError
)


class SQLAlchemyUserRepository(IUserRepository):
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _to_domain(self, orm_user: Optional[UserORM]) -> Optional[UserDomain]:
        if not orm_user:
            return None
        return UserDomain(
            id=orm_user.id,
            full_name=orm_user.full_name,
            email=orm_user.email,
            role=orm_user.role.value if hasattr(orm_user.role, 'value') else orm_user.role,
            is_active=orm_user.is_active,
            password_hash=orm_user.password_hash,
            phone=orm_user.phone,
            is_verified=orm_user.is_verified,
            last_login_at=orm_user.last_login_at,
            created_at=orm_user.created_at
        )
    
    def _to_orm(self, domain_user: UserDomain) -> UserORM:
        return UserORM(
            id=domain_user.id,
            full_name=domain_user.full_name,
            email=domain_user.email,
            password_hash=domain_user.password_hash,
            phone=domain_user.phone,
            role=domain_user.role,
            is_active=domain_user.is_active,
            is_verified=domain_user.is_verified,
            last_login_at=domain_user.last_login_at
        )
    
    async def get_by_email(self, email: str) -> Optional[UserDomain]:
        try:
            result = await self.db.execute(select(UserORM).where(UserORM.email == email))
            orm_user = result.scalar_one_or_none()
            return self._to_domain(orm_user)
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error fetching user by email: {e}")
    
    async def get_by_phone(self, phone: str) -> Optional[UserDomain]:
        try:
            result = await self.db.execute(select(UserORM).where(UserORM.phone == phone))
            return self._to_domain(result.scalar_one_or_none())
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error: {e}")
    
    async def get_by_id(self, user_id: uuid.UUID) -> Optional[UserDomain]:
        try:
            result = await self.db.execute(select(UserORM).where(UserORM.id == user_id))
            return self._to_domain(result.scalar_one_or_none())
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error: {e}")
    
    async def create(self, user: UserDomain) -> UserDomain:
        
        orm_user = self._to_orm(user)
        self.db.add(orm_user)
        
        try:
            await self.db.commit()
            await self.db.refresh(orm_user)
            return self._to_domain(orm_user)
        except IntegrityError as e:
            await self.db.rollback()
            error_msg = str(e.orig).lower()
            if "unique" in error_msg or "duplicate" in error_msg:
                raise DuplicateError(f"User with email {user.email} already exists")
            raise RepositoryError(f"Integrity error: {e}")
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Database error creating user: {e}")
    
    async def update(self, user: UserDomain) -> UserDomain:
        try:
            result = await self.db.execute(
                select(UserORM).where(UserORM.id == user.id)
            )
            orm_user = result.scalar_one_or_none()
            if not orm_user:
                raise NotFoundError(f"User {user.id} not found")
            
            orm_user.full_name = user.full_name
            orm_user.email = user.email
            orm_user.phone = user.phone
            orm_user.is_active = user.is_active
            orm_user.is_verified = user.is_verified
            
            await self.db.commit()
            await self.db.refresh(orm_user)
            return self._to_domain(orm_user)
        except IntegrityError as e:
            await self.db.rollback()
            if "unique" in str(e.orig).lower():
                raise DuplicateError(f"Email {user.email} already exists")
            raise RepositoryError(f"Update failed: {e}")
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Database error: {e}")
    
    async def update_last_login(self, user_id: uuid.UUID) -> None:
        
        try:
            await self.db.execute(
                update(UserORM)
                .where(UserORM.id == user_id)
                .values(last_login_at=datetime.utcnow())
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            import logging
            logging.warning(f"Failed to update last_login for {user_id}: {e}")


class SQLAlchemyRefreshTokenRepository(IRefreshTokenRepository):
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _to_domain(self, orm: Optional[RefreshTokenORM]) -> Optional[RefreshTokenDomain]:
        if not orm:
            return None
        return RefreshTokenDomain(
            id=orm.id,
            user_id=orm.user_id,
            token_hash=orm.token_hash,
            token_family=orm.token_family,
            expires_at=orm.expires_at,
            is_revoked=orm.is_revoked,
            created_at=orm.created_at,
            ip_address=orm.ip_address,
            user_agent=orm.user_agent
        )
    
    async def get_by_hash(self, token_hash: str, lock: bool = False) -> Optional[RefreshTokenDomain]:
      
        try:
            query = select(RefreshTokenORM).where(RefreshTokenORM.token_hash == token_hash)
            if lock:
                query = query.with_for_update()  
            
            result = await self.db.execute(query)
            return self._to_domain(result.scalar_one_or_none())
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error fetching token: {e}")
    
    async def get_by_family(self, family: uuid.UUID) -> List[RefreshTokenDomain]:
        try:
            result = await self.db.execute(
                select(RefreshTokenORM).where(RefreshTokenORM.token_family == family)
            )
            return [self._to_domain(t) for t in result.scalars().all()]
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error: {e}")
    
    async def create(self, token: RefreshTokenDomain) -> RefreshTokenDomain:
        orm_token = RefreshTokenORM(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            token_family=token.token_family,
            expires_at=token.expires_at,
            is_revoked=token.is_revoked,
            ip_address=token.ip_address,
            user_agent=token.user_agent
        )
        self.db.add(orm_token)
        
        try:
            await self.db.commit()
            await self.db.refresh(orm_token)
            return self._to_domain(orm_token)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to create refresh token: {e}")
    
    async def revoke(self, token_hash: str) -> None:
        try:
            await self.db.execute(
                update(RefreshTokenORM)
                .where(RefreshTokenORM.token_hash == token_hash)
                .values(is_revoked=True)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to revoke token: {e}")
    
    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        try:
            await self.db.execute(
                update(RefreshTokenORM)
                .where(RefreshTokenORM.user_id == user_id)
                .values(is_revoked=True)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to revoke user tokens: {e}")
    
    async def revoke_by_family(self, family: uuid.UUID) -> None:
        try:
            await self.db.execute(
                update(RefreshTokenORM)
                .where(RefreshTokenORM.token_family == family)
                .values(is_revoked=True)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to revoke token family: {e}")


class SQLAlchemyOTPCodesRepository(IOTPCodesRepository):
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _to_domain(self, orm: OTPCodeORM) -> OTPCodesDomain:
        return OTPCodesDomain(
            id=orm.id,
            user_id=orm.user_id,
            code_hash=orm.code_hash,
            method=orm.method,
            expires_at=orm.expires_at,
            is_used=orm.used,
            attempts=orm.attempts,
            created_at=orm.created_at
        )
    
    async def create(self, user_id: uuid.UUID, code_hash: str, method: str, expires_at: datetime) -> None:
        try:
            otp = OTPCodeORM(
                id=uuid.uuid4(),
                user_id=user_id,
                code_hash=code_hash,
                method=method,
                expires_at=expires_at,
                used=False,
                attempts=0
            )
            self.db.add(otp)
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to create OTP: {e}")
    
    async def get_valid_code(self, user_id: uuid.UUID, method: str) -> Optional[dict]:
       
        try:
            result = await self.db.execute(
                select(OTPCodeORM)
                .where(
                    and_(
                        OTPCodeORM.user_id == user_id,
                        OTPCodeORM.method == method,
                        OTPCodeORM.used == False,
                        OTPCodeORM.expires_at > datetime.utcnow()
                    )
                )
                .order_by(OTPCodeORM.created_at.desc())
            )
            otp = result.scalar_one_or_none()
            if otp:
                return {
                    'id': otp.id,
                    'code_hash': otp.code_hash,
                    'attempts': otp.attempts
                }
            return None
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error: {e}")
    
    async def mark_used(self, code_id: uuid.UUID) -> None:
        try:
            await self.db.execute(
                update(OTPCodeORM)
                .where(OTPCodeORM.id == code_id)
                .values(used=True)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to mark OTP used: {e}")
    
    async def increment_attempts(self, code_id: uuid.UUID) -> None:
        try:
            await self.db.execute(
                update(OTPCodeORM)
                .where(OTPCodeORM.id == code_id)
                .values(attempts=OTPCodeORM.attempts + 1)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Failed to increment attempts: {e}")
    
    async def count_recent_requests(self, user_id: uuid.UUID, minutes: int) -> int:
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=minutes)
            result = await self.db.execute(
                select(func.count()).where(
                    and_(
                        OTPCodeORM.user_id == user_id,
                        OTPCodeORM.created_at > cutoff
                    )
                )
            )
            return result.scalar() or 0
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error: {e}")