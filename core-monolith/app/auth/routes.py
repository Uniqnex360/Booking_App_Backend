from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import List
import uuid

from app.core.config import settings
from app.shared.response import success_response  
from app.auth.dependencies import (
    get_current_user, 
    require_role, 
    get_auth_service,
    get_firebase_manual_strategy,
    get_otp_service,
    get_user_repo
)
from app.auth.interfaces import (
    User as UserDomain, 
    UserRole, 
    IAuthenticationStrategy,
    IOTPService,
    IUserRepository
)
from app.auth.services import AuthService
from app.auth.schemas import (
    UserRegisterRequest, 
    UserLoginRequest, 
    RefreshTokenRequest,
    VerifyOTPRequest
)
from app.auth.exceptions import DuplicateEmailError, UserNotFoundError

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)

@router.post("/register", status_code=201)
async def register(
    user_data: UserRegisterRequest,
    auth_service: AuthService = Depends(get_auth_service) 
):
    user = await auth_service.register(user_data)
    return success_response(
        data=user, 
        message="Account created. OTP sent to your phone.", 
        code=201
    )
@router.post("/login/firebase")
async def login_firebase(
    payload: dict, 
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    fb_strategy: IAuthenticationStrategy = Depends(get_firebase_manual_strategy)
):
    user = await fb_strategy.authenticate(payload)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    access, refresh = await auth_service.login_user(user, ip, user_agent)
    
    data = {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
    return success_response(data=data, message="Firebase login successful.")

@router.post("/login/phone-email")
async def login_phone_email(
    payload: dict, 
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    user_repo: IUserRepository = Depends(get_user_repo) 
):
    from app.auth.strategies import PhoneEmailStrategy
    strategy = PhoneEmailStrategy(user_repo)
    user = await strategy.authenticate(payload)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    access, refresh = await auth_service.login_user(user, ip, user_agent)
    
    data = {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
    return success_response(data=data, message="Phone/Email login successful.")
@router.post("/register/initiate")
async def register_initiate(
    user_data: UserRegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    otp_service: IOTPService = Depends(get_otp_service),
):
    existing = await auth_service.user_repo.get_by_email(user_data.email)
    if existing:
        if existing.is_verified:
            raise DuplicateEmailError()
        user = existing
    else:
        new_user = UserDomain(
            id=uuid.uuid4(),
            full_name=user_data.full_name,
            email=user_data.email,
            password_hash=auth_service.password_hasher.hash(user_data.password),
            role=UserRole.USER,
            is_active=False,
            is_verified=False
        )
        user = await auth_service.user_repo.create(new_user)
    
    await otp_service.generate_and_send(user, method="EMAIL")
    return success_response(
        data={"user_id": user.id}, 
        message="OTP sent to email"
    )

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    login_data: UserLoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    access, refresh = await auth_service.login(
        email=login_data.email,
        password=login_data.password,
        ip_address=ip,
        user_agent=user_agent
    )
    
    data = {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
    return success_response(data=data, message="Login successful.")

@router.post("/register/verify")
async def register_verify(
    payload: VerifyOTPRequest,
    auth_service: AuthService = Depends(get_auth_service),
    otp_service: IOTPService = Depends(get_otp_service),
):
    await otp_service.verify(payload.user_id, payload.otp_code, method="EMAIL")
    user = await auth_service.user_repo.get_by_id(payload.user_id)
    if not user:
        raise UserNotFoundError()
        
    user.is_active = True
    user.is_verified = True
    updated_user = await auth_service.user_repo.update(user)
    
    return success_response(data=updated_user, message="Phone number verified successfully.")

@router.post("/refresh")
async def refresh(
    refresh_data: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    access, refresh = await auth_service.refresh_token(refresh_data.refresh_token)
    data = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
    return success_response(data=data, message="Token refreshed successfully.")

@router.post("/logout")
async def logout(
    refresh_data: RefreshTokenRequest,
    current_user: UserDomain = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    await auth_service.logout(refresh_data.refresh_token)
    return success_response(data=None, message="Logged out successfully.")

@router.get("/me")
async def get_me(current_user: UserDomain = Depends(get_current_user)):
    return success_response(data=current_user, message="Profile fetched successfully.")

@router.get("/admin/users")
async def list_users(
    admin: UserDomain = Depends(require_role([UserRole.ADMIN.value])),
    auth_service: AuthService = Depends(get_auth_service)
):
    users = await auth_service.user_repo.list_all()
    return success_response(data=users, message="Users list fetched.")