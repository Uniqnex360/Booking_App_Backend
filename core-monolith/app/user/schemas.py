

import uuid
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field



class ProfileUpdateRequest(BaseModel):
    avatar_url: Optional[str] = Field(None, max_length=500)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)
    preferred_language: Optional[str] = Field(None, max_length=10)
    bio: Optional[str] = Field(None, max_length=500)

class ProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    avatar_url: Optional[str]
    date_of_birth: Optional[date]
    gender: Optional[str]
    preferred_language: str
    bio: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    
    model_config = ConfigDict(from_attributes=True)




class AddressCreateRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=50, description="e.g. Home, Work")
    line1: str = Field(..., min_length=1, max_length=255)
    line2: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    pincode: str = Field(..., min_length=1, max_length=10)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_default: bool = False

class AddressUpdateRequest(BaseModel):
    label: Optional[str] = Field(None, max_length=50)
    line1: Optional[str] = Field(None, max_length=255)
    line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_default: Optional[bool] = None

class AddressResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    label: str
    line1: str
    line2: Optional[str]
    city: str
    state: str
    pincode: str
    latitude: Optional[float]
    longitude: Optional[float]
    is_default: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class AddressListResponse(BaseModel):
    addresses: List[AddressResponse]