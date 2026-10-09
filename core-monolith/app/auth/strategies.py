import uuid
import httpx
import jwt
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
import ipaddress
import socket
import urllib.parse


class PhoneEmailStrategy(IAuthenticationStrategy):
    ALLOWED_HOSTS = {"auth.phone.email"}
    REQUEST_TIMEOUT = 5.0

    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    def _validate_url(self, raw_url: str) -> urllib.parse.ParseResult:
        if not raw_url or not isinstance(raw_url, str):
            raise InvalidCredentialsError("Missing Phone.Email verification URL")

        parsed = urllib.parse.urlparse(raw_url)
        if parsed.scheme != "https":
            raise InvalidCredentialsError("Invalid Phone.Email verification URL: HTTPS required")

        hostname = (parsed.hostname or "").lower().strip()
        if hostname not in self.ALLOWED_HOSTS:
            raise InvalidCredentialsError("Invalid Phone.Email verification URL: untrusted domain")

        if parsed.port and parsed.port != 443:
            raise InvalidCredentialsError("Invalid Phone.Email verification URL: invalid port")

        # SSRF Defense: verify resolved IP addresses are not private/loopback/link-local
        try:
            addr_info = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
            for _, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip_str)
                if (
                    ip_obj.is_private
                    or ip_obj.is_loopback
                    or ip_obj.is_reserved
                    or ip_obj.is_link_local
                    or ip_obj.is_multicast
                ):
                    raise InvalidCredentialsError("Invalid Phone.Email verification URL: restricted IP")
        except socket.gaierror:
            raise InvalidCredentialsError("Invalid Phone.Email verification URL: resolution failed")

        return parsed

    async def authenticate(self, credentials: dict) -> UserDomain:
        user_json_url = credentials.get("url")
        self._validate_url(user_json_url)

        try:
            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT, follow_redirects=False) as client:
                resp = await client.get(user_json_url)
        except httpx.HTTPError:
            raise InvalidCredentialsError("Phone.Email verification failed: network error")

        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            raise InvalidCredentialsError("Phone.Email verification failed: redirects not allowed")

        if resp.status_code != 200:
            raise InvalidCredentialsError(f"Phone.Email verification failed: HTTP {resp.status_code}")

        try:
            data = resp.json()
        except Exception:
            raise InvalidCredentialsError("Phone.Email verification failed: malformed JSON")

        if not isinstance(data, dict):
            raise InvalidCredentialsError("Phone.Email verification failed: invalid payload")

        phone_num = data.get("user_phone_number")
        country_code = data.get("user_country_code")
        if not phone_num or not country_code:
            raise InvalidCredentialsError("Phone.Email verification failed: missing phone details")

        clean_country = str(country_code).strip()
        clean_phone = str(phone_num).strip().replace(" ", "").replace("-", "")
        if not clean_country.startswith("+") or not clean_phone.isdigit():
            raise InvalidCredentialsError("Phone.Email verification failed: invalid phone format")

        first_name = data.get("user_first_name") or ""
        last_name = data.get("user_last_name") or ""
        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = "Phone User"
        phone = f"{clean_country}{clean_phone}"
        user = await self.user_repo.get_by_phone(phone)
        if not user:
            user = await self._handle_auto_registration(phone, full_name)
        return user
    async def _handle_auto_registration(self, phone: str, name: str) -> UserDomain:
        import uuid
        from app.auth.interfaces import UserRole
        new_user = UserDomain(
            id=uuid.uuid4(),
            full_name=name, 
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
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            key = None
            if isinstance(public_keys, dict):
                if "keys" in public_keys and isinstance(public_keys["keys"], list):
                    for jwk in public_keys["keys"]:
                        if jwk.get("kid") == kid:
                            from jwt.algorithms import RSAAlgorithm
                            key = RSAAlgorithm.from_jwk(jwk)
                            break
                elif kid and kid in public_keys:
                    key = public_keys[kid]
            if not key:
                key = public_keys

            decoded_token = jwt.decode(
                token,
                key,
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
        except (jwt.PyJWTError, Exception) as e:
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