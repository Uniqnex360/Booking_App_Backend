from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional,Annotated
import unicodedata
from pydantic import BaseModel, EmailStr, BeforeValidator
import re
import uuid
from datetime import datetime
def normalize_email_str(v: str) -> str:
    if isinstance(v, str):
        return unicodedata.normalize('NFKC', v).lower().strip()
    return v
def normalize_phone_str(v: str) -> str:
    if isinstance(v, str):
        return ''.join(c for c in v if c.isdigit() or c == '+')
    return v
NormalizedPhone = Annotated[str, BeforeValidator(normalize_phone_str)]

NormalizedEmail=Annotated[EmailStr,BeforeValidator(normalize_email_str)]
class VerifyOTPRequest(BaseModel):
    user_id: uuid.UUID
    otp_code: str
class UserRegisterRequest(BaseModel):
    full_name:str=Field(...,min_length=2,max_length=255)
    email:NormalizedEmail
    password:str=Field(...,min_length=8,max_length=128)
    phone:Optional[NormalizedPhone] = None
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        if re.search(r'(.)\1{2,}', v):  
            raise ValueError('Password contains too many repeated characters')
        return v
    @field_validator('full_name')
    @classmethod
    def normalize_name(cls,v:str)->str:
        return unicodedata.normalize('NFKC',v).strip()
        
class UserLoginRequest(BaseModel):
    email:NormalizedEmail
    password:str
class TokenResponse(BaseModel):
    access_token:str
    refresh_token:str
    token_type:str='bearer'
    expires_in:int
class UserResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:uuid.UUID
    full_name:str
    email:str
    phone:Optional[str]
    role:str
    is_verified:bool
    created_at:datetime
    
class RefreshTokenRequest(BaseModel):
    refresh_token:str
class MessageResponse(BaseModel):
    message:str

class TokenPayload(BaseModel):
    sub:str
    role:str
    exp:datetime
    iat:datetime
    type:Optional[str]=None
class OTPRequestRequest(BaseModel):
    phone: NormalizedPhone 
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if len(cleaned) < 10:
            raise ValueError('Invalid phone number')
        return cleaned


class OTPVerifyRequest(BaseModel):
    phone: NormalizedPhone
    code: str = Field(..., min_length=6, max_length=6)