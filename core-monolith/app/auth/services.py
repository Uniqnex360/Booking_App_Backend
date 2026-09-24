
import uuid
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional
from fastapi import HTTPException
from app.shared.hashing import sha256_hex

from app.auth.interfaces import (
    IUserRepository,
    IRefreshTokenRepository,
    IAuthenticationStrategy,
    ITokenService,
    IPasswordHasher,
    IPasswordResetRepository,
    User as UserDomain,
    RefreshToken as RefreshTokenDomain,
    UserRole,
    DuplicateError,
    RepositoryError
)
from app.auth.exceptions import (
    DuplicateEmailError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenReuseError,
    InactiveAccountError
)
from app.auth.schemas import UserRegisterRequest

logger = logging.getLogger(__name__)


class AuthService:
  
    
    def __init__(
        self,
        user_repo: IUserRepository,
        token_repo: IRefreshTokenRepository,
        password_hasher: IPasswordHasher,
        token_service: ITokenService,
        auth_strategy: IAuthenticationStrategy
    ):
        self.user_repo = user_repo
        self.token_repo = token_repo
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.auth_strategy = auth_strategy
    
    async def register(self, user_data: UserRegisterRequest) -> UserDomain:
       
        
        existing = await self.user_repo.get_by_email(user_data.email)
        if existing:
            raise DuplicateEmailError()
        
        
        new_user = UserDomain(
            id=uuid.uuid4(),
            full_name=user_data.full_name,
            email=user_data.email,
            phone=user_data.phone,
            password_hash=self.password_hasher.hash(user_data.password),
            role=UserRole.USER,
            is_active=True,
            is_verified=False
        )
        
        
        try:
            return await self.user_repo.create(new_user)
        except DuplicateError:
            raise DuplicateEmailError()
        except RepositoryError as e:
            logger.error(f"Repository error during registration: {e}")
            raise HTTPException(status_code=503, detail="Service unavailable")
    
    async def authenticate(self, credentials: dict) -> UserDomain:
        
        return await self.auth_strategy.authenticate(credentials)
    
    async def login(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[str, str]:
        
        
        credentials = {"email": email, "password": password}
        user = await self.auth_strategy.authenticate(credentials)
        
        
        await self.user_repo.update_last_login(user.id)
        
        
        access_token = self.token_service.create_access_token(user)
        token_family = uuid.uuid4()
        refresh_token_str = self.token_service.create_refresh_token(user, token_family)
        
        
        refresh_token_domain = RefreshTokenDomain(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=self._hash_refresh_token(refresh_token_str),
            token_family=token_family,
            expires_at=datetime.utcnow() + timedelta(days=7),
            is_revoked=False,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        try:
            await self.token_repo.create(refresh_token_domain)
        except RepositoryError as e:
            logger.error(f"Failed to store refresh token: {e}")
            raise HTTPException(status_code=503, detail="Session creation failed")
        
        return access_token, refresh_token_str
    
    async def refresh_token(self, refresh_token_str: str) -> Tuple[str, str]:
        
        payload = self.token_service.decode_token(refresh_token_str, token_type="refresh")
        token_family = uuid.UUID(payload.get("family"))
        user_id = uuid.UUID(payload.get("sub"))
        
        
        token_hash = self._hash_refresh_token(refresh_token_str)
        
        
        db_token = await self.token_repo.get_by_hash(token_hash, lock=True)
        
        
        if db_token is None:
            
            family_tokens = await self.token_repo.get_by_family(token_family)
            if family_tokens:
                
                await self.token_repo.revoke_by_family(token_family)
                logger.warning(f"Token reuse attack detected for family: {token_family}")
                raise TokenReuseError()
            raise InvalidTokenError("Refresh token not found")
        
        if db_token.is_revoked:
            raise TokenReuseError()
        
        if not db_token.is_valid():
            raise InvalidTokenError("Refresh token expired")
        
        
        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise InvalidTokenError("User not found or inactive")
        
        
        await self.token_repo.revoke(token_hash)
        
        
        new_access = self.token_service.create_access_token(user)
        new_refresh_str = self.token_service.create_refresh_token(user, token_family)
        
        new_token_domain = RefreshTokenDomain(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=self._hash_refresh_token(new_refresh_str),
            token_family=token_family,
            expires_at=datetime.utcnow() + timedelta(days=7),
            is_revoked=False,
            ip_address=db_token.ip_address,  
            user_agent=db_token.user_agent
        )
        
        await self.token_repo.create(new_token_domain)
        
        return new_access, new_refresh_str
    async def login_user(
        self,
        user: UserDomain,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[str, str]:
       
        await self.user_repo.update_last_login(user.id)
        
        access_token = self.token_service.create_access_token(user)
        token_family = uuid.uuid4()
        refresh_token_str = self.token_service.create_refresh_token(user, token_family)
        
        refresh_token_domain = RefreshTokenDomain(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=self.token_service.hash_token(refresh_token_str),
            token_family=token_family,
            expires_at=datetime.utcnow() + timedelta(days=7),
            is_revoked=False,
            ip_address=ip_address,
            user_agent=user_agent
        )
        await self.token_repo.create(refresh_token_domain)
        return access_token, refresh_token_str
    
    async def logout(self, refresh_token_str: str) -> None:
        token_hash = self._hash_refresh_token(refresh_token_str)
        try:
            await self.token_repo.revoke(token_hash)
        except RepositoryError as e:
            logger.warning(f"Logout failed (non-critical): {e}")
    
    async def logout_all(self, user_id: uuid.UUID) -> None:
        try:
            await self.token_repo.revoke_all_for_user(user_id)
        except RepositoryError as e:
            logger.error(f"Failed to revoke all tokens for {user_id}: {e}")
            raise HTTPException(status_code=503, detail="Logout failed")
    
    def _hash_refresh_token(self, token: str) -> str:
        return sha256_hex(token)
    async def request_password_reset(
        self,
        email: str,
        reset_repo: IPasswordResetRepository,
        notification: INotificationService,
    ) -> None:
        """Always succeeds from the caller's perspective. No enumeration."""
        user = await self.user_repo.get_by_email(email)
        if user is None:
            return

        is_password_user = bool(
            user.password_hash and user.password_hash.startswith("$2")
        )

        if is_password_user:
            await reset_repo.delete_for_user(user.id)   # invalidate previous
            raw = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
            await reset_repo.create(user.id, _hash_token(raw), expires_at)

            link = f"{settings.FRONTEND_URL}/reset-password?token={raw}"
            await notification.send_email(
                email=user.email,
                subject="Reset your Vyhbz password",
                body=(
                    f"Click to reset your password:\n\n{link}\n\n"
                    f"This link expires in 30 minutes. "
                    f"If you didn't request this, ignore this email."
                ),
                content_type="text",
            )
            return

        # Google / phone-email user: no password, tell them how to sign in.
        if user.email:
            await notification.send_email(
                email=user.email,
                subject="Reset your Vyhbz password",
                body=(
                    "You signed up with Google or a phone number, "
                    "so there's no password to reset. "
                    "Use the same method to sign in."
                ),
                content_type="text",
            )
        # phone.email users have email=None. Nothing to send. Silent.


    async def validate_reset_token(
        self, reset_repo: IPasswordResetRepository, raw_token: str
    ) -> PasswordResetRow | None:
        return await reset_repo.get_valid(_hash_token(raw_token))


    async def reset_password(
        self,
        reset_repo: IPasswordResetRepository,
        refresh_repo: IRefreshTokenRepository,
        hasher: IPasswordHasher,
        raw_token: str,
        new_password: str,
    ) -> bool:
        row = await reset_repo.get_valid(_hash_token(raw_token))
        if row is None:
            return False

        user = await self.user_repo.get_by_id(row.user_id)
        if user is None:
            return False

        user.password_hash = hasher.hash(new_password)
        await self.user_repo.update(user)

        await reset_repo.mark_used(row.id)

        # Kill every active session for this user.
        try:
            await refresh_repo.revoke_all_for_user(user.id)
        except AttributeError:
            # If your refresh repo doesn't have that method yet, add it.
            pass

        return True