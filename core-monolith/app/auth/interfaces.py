from abc import ABC, abstractmethod
from typing import Protocol, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
import uuid
import enum




class UserRole(str, enum.Enum):
    USER = "USER"
    PARTNER = "PARTNER"
    ADMIN = "ADMIN"


@dataclass
class User:
    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    password_hash: str
    phone: Optional[str] = None
    is_verified: bool = False
    last_login_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass 
class RefreshToken:
    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    token_family: uuid.UUID
    expires_at: datetime
    is_revoked: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def is_valid(self) -> bool:
        return not self.is_revoked and self.expires_at > datetime.utcnow()


@dataclass
class OTPCodes:
    id: uuid.UUID
    user_id: uuid.UUID
    code_hash: str
    method: str  
    expires_at: datetime
    is_used: bool = False
    attempts: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)




class IUserRepository(Protocol):
    async def get_by_email(self, email: str) -> Optional[User]: ...
    async def get_by_phone(self, phone: str) -> Optional[User]: ...
    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]: ...
    async def create(self, user: User) -> User: ...
    async def update(self, user: User) -> User: ...
    async def update_last_login(self, user_id: uuid.UUID) -> None: ...


class IRefreshTokenRepository(Protocol):
    async def get_by_hash(self, token_hash: str) -> Optional[RefreshToken]: ...
    async def get_by_family(self, family: uuid.UUID) -> List[RefreshToken]: ...
    async def create(self, token: RefreshToken) -> RefreshToken: ...
    async def revoke(self, token_hash: str) -> None: ...
    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None: ...
    async def revoke_by_family(self, family: uuid.UUID) -> None: ...


class IOTPCodesRepository(Protocol):
    async def create(self, otp: OTPCodes) -> OTPCodes: ...
    async def get_valid_code(self, user_id: uuid.UUID, method: str) -> Optional[OTPCodes]: ...
    async def mark_used(self, code_id: uuid.UUID) -> None: ...
    async def increment_attempts(self, code_id: uuid.UUID) -> None: ...
    async def count_recent_requests(self, user_id: uuid.UUID, minutes: int) -> int: ...
    async def verify_registration_otp(self, email: str, code: str) -> bool:
        pass
    async def get_valid_code_by_email(self, email: str, method: str) -> Optional[dict]: ...





class IAuthenticationStrategy(ABC):
    @abstractmethod
    async def authenticate(self, credentials: dict) -> User:
        ...


class IPasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, hashed: str) -> bool: ...


class ITokenService(Protocol):
    def create_access_token(self, user: User) -> str: ...
    def create_refresh_token(self, user: User, family: uuid.UUID) -> str: ...
    def decode_token(self, token: str, token_type: Optional[str] = None) -> dict: ...
    def create_registration_token(self, data: dict) -> str:...


class INotificationService(Protocol):
    async def send_sms(self, phone: str, message: str) -> bool: ...
    async def send_email(self, email: str, subject: str, body: str) -> bool: ...


class IOTPService(Protocol):
    async def generate_and_send(self, user: User, method: str = "SMS") -> None: ...
    async def verify(self, user_id: uuid.UUID, code: str, method: str = "SMS") -> bool: ...




class RepositoryError(Exception):
    pass

class DuplicateError(RepositoryError):
    pass

class NotFoundError(RepositoryError):
    pass

class ValidationError(Exception):
    pass