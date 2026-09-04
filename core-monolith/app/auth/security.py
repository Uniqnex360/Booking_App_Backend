import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings
from app.auth.exceptions import InvalidTokenError
from app.auth.interfaces import IPasswordHasher, ITokenService, User as UserDomain



class BcryptPasswordHasher(IPasswordHasher):
    
    def __init__(self):
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash(self, password: str) -> str:
        return self.pwd_context.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        return self.pwd_context.verify(password, hashed)




class JWTTokenService(ITokenService):
   
    def create_access_token(self, user: UserDomain, expires_delta: Optional[timedelta] = None) -> str:
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        
        to_encode = {
            "sub": str(user.id),
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        }
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    def create_registration_token(self, data: dict) -> str:
        expire = datetime.utcnow() + timedelta(minutes=10)
        to_encode = data.copy()
        to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "registration"})
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    def create_refresh_token(self, user: UserDomain, family: uuid.UUID, expires_delta: Optional[timedelta] = None) -> str:
        expire = datetime.utcnow() + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
        
        to_encode = {
            "sub": str(user.id),
            "family": str(family),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh"
        }
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def decode_token(self, token: str, token_type: Optional[str] = None) -> Dict[str, Any]:
        try:
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            if token_type and payload.get("type") != token_type:
                raise InvalidTokenError(f"Invalid token type. Expected {token_type}")
                
            return payload
        except JWTError as e:
            print(f"JWT VALIDATION FAILED: {str(e)}")
            raise InvalidTokenError(str(e))

    def hash_token(self, token: str) -> str:
       
        return hashlib.sha256(token.encode()).hexdigest()