import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.partner.interfaces import PartnerType, PartnerStatus
class PartnerRegisterRequest(BaseModel):
    business_name:str=Field(...,min_length=2,max_length=255)
    partner_type:PartnerType
    contact_name:str=Field(...,min_length=2,max_length=255)
    contact_phone:str=Field(...,min_length=10,max_length=20)
    city:str=Field(...,min_length=2,max_length=100)
    gst_number:Optional[str]=Field(None,max_length=20)
    pan_number:Optional[str]=Field(None,max_length=10)
class PartnerResponse(BaseModel):
    id:uuid.UUID
    business_name:str
    partner_type:PartnerType
    contact_name:str
    contact_phone:str
    city:str
    status:PartnerStatus
    commission_rate:float
    approved_at:Optional[datetime]
    created_at:datetime
    model_config=ConfigDict(from_attributes=True)

class PartnerStatusUpdateRequest(BaseModel):
    status:PartnerStatus
    rejection_reason:Optional[str]=None
    
    
    
    