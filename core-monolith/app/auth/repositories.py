from datetime import datetime, timedelta, timezone
from typing import Optional, List
import uuid

from sqlalchemy import select, and_, or_, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.models import (
    User as UserORM,
    RefreshToken as RefreshTokenORM,
    OTPCode as OTPCodeORM,
    PasswordReset as PasswordResetModel,
    UsedPhoneEmailVerification,
)

from app.auth.interfaces import (
    User as UserDomain,
    RefreshToken as RefreshTokenDomain,
    PasswordResetRow,
    OTPCodes as OTPCodesDomain,
    IUserRepository,
    IRefreshTokenRepository,
    IOTPCodesRepository,
    RepositoryError,
    IPasswordResetRepository,
    DuplicateError,
    NotFoundError,
)
class SQLAlchemyPasswordResetRepository(IPasswordResetRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        row = PasswordResetModel(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(row)
        await self.session.commit()

    async def get_valid(self, token_hash: str) -> PasswordResetRow | None:
        stmt = select(PasswordResetModel).where(
            PasswordResetModel.token_hash == token_hash,
            PasswordResetModel.used_at.is_(None),
            PasswordResetModel.expires_at > datetime.now(timezone.utc),
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return PasswordResetRow(
            id=row.id,
            user_id=row.user_id,
            expires_at=row.expires_at,
            used_at=row.used_at,
        )

    async def mark_used(self, reset_id: uuid.UUID) -> None:
        await self.session.execute(
            update(PasswordResetModel)
            .where(PasswordResetModel.id == reset_id)
            .values(used_at=datetime.now(timezone.utc))
        )
        await self.session.commit()

    async def delete_for_user(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(PasswordResetModel).where(PasswordResetModel.user_id == user_id)
        )
        await self.session.commit()
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

    async def list_users(
        self,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[List[UserDomain], int]:
        try:
            filters = []
            if search:
                term = f"%{search.strip()}%"
                filters.append(
                    or_(
                        UserORM.full_name.ilike(term),
                        UserORM.email.ilike(term),
                        UserORM.phone.ilike(term),
                    )
                )
            if role:
                filters.append(UserORM.role == role)
            if is_active is not None:
                filters.append(UserORM.is_active == is_active)

            base_stmt = select(UserORM)
            if filters:
                base_stmt = base_stmt.where(and_(*filters))

            count_stmt = select(func.count()).select_from(base_stmt.subquery())
            total = (await self.db.execute(count_stmt)).scalar() or 0

            offset = (page - 1) * limit
            query = base_stmt.order_by(UserORM.created_at.desc()).offset(offset).limit(limit)
            result = await self.db.execute(query)
            users = [self._to_domain(u) for u in result.scalars().all()]
            return [u for u in users if u is not None], total
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error listing users: {e}")

    async def set_user_active_status(
        self, user_id: uuid.UUID, is_active: bool
    ) -> UserDomain:
        try:
            result = await self.db.execute(
                select(UserORM).where(UserORM.id == user_id)
            )
            orm_user = result.scalar_one_or_none()
            if not orm_user:
                raise NotFoundError(f"User {user_id} not found")
            orm_user.is_active = is_active
            await self.db.commit()
            await self.db.refresh(orm_user)
            return self._to_domain(orm_user)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Database error setting user active status: {e}")

    async def set_user_role(
        self, user_id: uuid.UUID, role: str
    ) -> UserDomain:
        try:
            result = await self.db.execute(
                select(UserORM).where(UserORM.id == user_id)
            )
            orm_user = result.scalar_one_or_none()
            if not orm_user:
                raise NotFoundError(f"User {user_id} not found")
            orm_user.role = role
            await self.db.commit()
            await self.db.refresh(orm_user)
            return self._to_domain(orm_user)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Database error setting user role: {e}")

    async def is_verification_url_used(self, url_hash: str) -> bool:
        try:
            result = await self.db.execute(
                select(UsedPhoneEmailVerification.id).where(
                    UsedPhoneEmailVerification.url_hash == url_hash
                )
            )
            return result.scalar_one_or_none() is not None
        except SQLAlchemyError as e:
            raise RepositoryError(f"Database error checking verification URL replay: {e}")

    async def mark_verification_url_used(
        self, url_hash: str, user_id: Optional[uuid.UUID] = None
    ) -> None:
        try:
            record = UsedPhoneEmailVerification(
                id=uuid.uuid4(),
                url_hash=url_hash,
                user_id=user_id,
            )
            self.db.add(record)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise DuplicateError("Phone.Email verification URL has already been used")
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Database error saving verification URL: {e}")

    async def cleanup_old_verification_urls(self, max_age_hours: int = 24) -> int:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            result = await self.db.execute(
                delete(UsedPhoneEmailVerification).where(
                    UsedPhoneEmailVerification.created_at < cutoff
                )
            )
            await self.db.commit()
            return result.rowcount or 0
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError(f"Database error cleaning up old verification URLs: {e}")



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