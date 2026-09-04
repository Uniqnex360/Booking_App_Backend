import uuid
import httpx
from jose import jwt, JWTError
from app.core.config import settings
from app.auth.interfaces import (
    IAuthenticationStrategy, 
    IUserRepository, 
    IPasswordHasher, 
    IOTPService,
    User as UserDomain,
    UserRole
)
from app.auth.exceptions import InvalidCredentialsError, InactiveAccountError
class PasswordAuthStrategy(IAuthenticationStrategy):
    DUMMY_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
    def __init__(self, user_repo: IUserRepository, hasher: IPasswordHasher):
        self.user_repo = user_repo
        self.hasher = hasher
    async def authenticate(self, credentials: dict) -> UserDomain:
        email = credentials.get('email')
        password = credentials.get('password')
        user = await self.user_repo.get_by_email(email)
        if user is None:
            self.hasher.verify(password, self.DUMMY_HASH)  
            raise InvalidCredentialsError()
        if not user.password_hash or not user.password_hash.startswith("$"):
            self.hasher.verify(password, self.DUMMY_HASH)
            raise InvalidCredentialsError(
                detail="This account is linked to Google/Phone. Please log in using that method."
            )
        try:
            if not self.hasher.verify(password, user.password_hash):
                raise InvalidCredentialsError()
        except Exception:
            self.hasher.verify(password, self.DUMMY_HASH)
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveAccountError()
        await self.user_repo.update_last_login(user.id)
        return user
class PhoneEmailStrategy(IAuthenticationStrategy):
    
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def authenticate(self, credentials: dict) -> UserDomain:
        user_json_url = credentials.get("url")
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(user_json_url)
            data = resp.json()

        # 1. ✅ CORRECT MAPPING: Phone.email uses these specific keys
        first_name = data.get("user_first_name") or ""
        last_name = data.get("user_last_name") or ""
        
        # Combine them into one string
        full_name = f"{first_name} {last_name}".strip()
        
        # Fallback if both are empty
        if not full_name:
            full_name = "Phone User"

        phone = f"{data.get('user_country_code')}{data.get('user_phone_number')}"

        # 2. Check DB
        user = await self.user_repo.get_by_phone(phone)
        
        if not user:
            # 3. ✅ Pass the correct full_name to registration
            user = await self._handle_auto_registration(phone, full_name)
            
        return user

    async def _handle_auto_registration(self, phone: str, name: str) -> UserDomain:
        import uuid
        from app.auth.interfaces import UserRole
        
        new_user = UserDomain(
            id=uuid.uuid4(),
            full_name=name, # 👈 This now receives the correct string
            email=None,
            phone=phone,
            password_hash="AUTH_TYPE_PHONE_EMAIL",
            role=UserRole.USER,
            is_active=True,
            is_verified=True
        )
        return await self.user_repo.create(new_user)
class FirebaseManualPhoneStrategy(IAuthenticationStrategy):
    def __init__(self, user_repo: IUserRepository, project_id: str):
        self.user_repo = user_repo
        self.project_id = project_id
    async def _get_google_public_keys(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.GOOGLE_PUBLIC_KEYS_URL)
            return response.json()
    async def authenticate(self, credentials: dict) -> UserDomain:
        token = credentials.get('token')
        if not token:
            raise InvalidCredentialsError("No firebase token provided")
        try:
            public_keys = await self._get_google_public_keys()
            decoded_token = jwt.decode(
                token,
                public_keys,
                algorithms=["RS256"],
                audience=self.project_id,
                issuer=f"https://securetoken.google.com/{self.project_id}"
            )
            phone_number = decoded_token.get('phone_number')
            email = decoded_token.get('email')
            if not phone_number and not email:
                raise InvalidCredentialsError("Token contains no identification (email or phone)")
            user = None
            if phone_number:
                user = await self.user_repo.get_by_phone(phone_number)
            elif email:
                user = await self.user_repo.get_by_email(email)
            if not user:
                user = await self._handle_auto_registration(decoded_token, phone_number, email)
            if not user.is_active:  
                raise InactiveAccountError()
            await self.user_repo.update_last_login(user.id)
            return user
        except JWTError as e:
            raise InvalidCredentialsError(f"Firebase verification failed: {str(e)}")
    async def _handle_auto_registration(
        self, 
        decoded_token: dict, 
        phone: str = None, 
        email: str = None
    ) -> UserDomain:
        new_user = UserDomain(
            id=uuid.uuid4(),
            full_name=decoded_token.get("name", "New User"),
            email=email, 
            phone=phone, 
            password_hash="AUTH_TYPE_FIREBASE", 
            role=UserRole.USER,
            is_active=True,
            is_verified=True 
        )
        return await self.user_repo.create(new_user)
class OTPAuthStrategy(IAuthenticationStrategy):
    def __init__(self, user_repo: IUserRepository, otp_service: IOTPService):
        self.user_repo = user_repo
        self.otp_service = otp_service
    async def authenticate(self, credentials: dict) -> UserDomain:
        phone = credentials.get('phone')
        code = credentials.get('code')
        user = await self.user_repo.get_by_phone(phone)
        if not user:
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveAccountError()
        await self.otp_service.verify(user.id, code, method="SMS")
        await self.user_repo.update_last_login(user.id)
        return user