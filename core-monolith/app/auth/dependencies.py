import uuid
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.services import AuthService
from app.core.database import get_db
from app.core.config import settings  
from app.auth.strategies import PhoneEmailStrategy
from app.auth.otp_service import NotificationService
from app.shared.exceptions import ForbiddenError

from app.auth.interfaces import (
    IUserRepository, 
    IRefreshTokenRepository, 
    IOTPCodesRepository,
    IAuthenticationStrategy, 
    ITokenService, 
    IOTPService, 
    IPasswordHasher,
    User as UserDomain  
)
from app.auth.repositories import (
    SQLAlchemyUserRepository, 
    SQLAlchemyRefreshTokenRepository, 
    SQLAlchemyOTPCodesRepository
)
from app.auth.strategies import (
    PasswordAuthStrategy, 
    OTPAuthStrategy, 
    FirebaseManualPhoneStrategy 
)
from app.auth.otp_service import OTPService
from app.auth.security import BcryptPasswordHasher, JWTTokenService
from app.auth.exceptions import InvalidTokenError

def get_user_repo(db: AsyncSession = Depends(get_db)) -> IUserRepository:
    return SQLAlchemyUserRepository(db)

def get_refresh_token_repo(db: AsyncSession = Depends(get_db)) -> IRefreshTokenRepository:
    return SQLAlchemyRefreshTokenRepository(db)

def get_otp_repo(db: AsyncSession = Depends(get_db)) -> IOTPCodesRepository:
    return SQLAlchemyOTPCodesRepository(db)

def get_password_hasher() -> IPasswordHasher:
    return BcryptPasswordHasher()

def get_notification_service():
    return NotificationService()

def get_otp_service(
    user_repo: IUserRepository = Depends(get_user_repo),
    otp_repo: IOTPCodesRepository = Depends(get_otp_repo),
    notification=Depends(get_notification_service)
) -> IOTPService:
    return OTPService(user_repo, otp_repo, notification)
def get_firebase_manual_strategy(user_repo: IUserRepository=Depends(get_user_repo))->IAuthenticationStrategy:
    return FirebaseManualPhoneStrategy(user_repo,settings.FIREBASE_PROJECT_ID)
def get_phone_email_strategy(
    user_repo: IUserRepository = Depends(get_user_repo)
) -> IAuthenticationStrategy:
    return PhoneEmailStrategy(user_repo)
def get_password_strategy(
    user_repo: IUserRepository = Depends(get_user_repo),
    hasher: IPasswordHasher = Depends(get_password_hasher)
) -> IAuthenticationStrategy:
    return PasswordAuthStrategy(user_repo, hasher)

def get_otp_strategy(
    user_repo: IUserRepository = Depends(get_user_repo),
    otp_service: IOTPService = Depends(get_otp_service)
) -> IAuthenticationStrategy:
    return OTPAuthStrategy(user_repo, otp_service)

def get_token_service() -> ITokenService:
    return JWTTokenService()




oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    token_service: ITokenService = Depends(get_token_service),
    user_repo: IUserRepository = Depends(get_user_repo)
) -> UserDomain:
    try:
        payload = token_service.decode_token(token, token_type="access")
        user_id = uuid.UUID(payload.get("sub"))
    except (InvalidTokenError, ValueError):
        raise InvalidTokenError()
    
    user = await user_repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError()
    
    return user
def get_auth_service(
    user_repo: IUserRepository = Depends(get_user_repo),
    token_repo: IRefreshTokenRepository = Depends(get_refresh_token_repo),
    hasher: IPasswordHasher = Depends(get_password_hasher),
    token_service: ITokenService = Depends(get_token_service),
    strategy: IAuthenticationStrategy = Depends(get_password_strategy) 
) -> AuthService:
   
    return AuthService(
        user_repo=user_repo,
        token_repo=token_repo,
        password_hasher=hasher,
        token_service=token_service,
        auth_strategy=strategy
    )
def require_role(allowed_roles: list[str]):
    async def checker(user: UserDomain = Depends(get_current_user)) -> UserDomain:
        user_role_str=user.role.value if hasattr(user.role,'value')else user.role 
        if user_role_str not in allowed_roles:
            raise ForbiddenError("Insufficient permissions")
        return user
    return checker