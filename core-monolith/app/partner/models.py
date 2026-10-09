from app.core.database import Base
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from datetime import datetime

from sqlalchemy import ForeignKey,String,Float,DateTime,func
import uuid
class PartnerORM(Base):
    __tablename__='partners'
    id:Mapped[uuid.UUID]=mapped_column(primary_key=True,default=uuid.uuid4)
    user_id:Mapped[uuid.UUID]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),unique=True,nullable=False,index=True)
    business_name:Mapped[str]=mapped_column(String(255),nullable=False)
    partner_type:Mapped[str]=mapped_column(String(50),nullable=False,index=True)
    contact_name:Mapped[str]=mapped_column(String(255),nullable=False)
    contact_phone:Mapped[str]=mapped_column(String(20),nullable=False)
    city:Mapped[str]=mapped_column(String(100),nullable=False) 
    gst_number:Mapped[Optional[str]]=mapped_column(String(20),nullable=True)
    pan_number:Mapped[Optional[str]]=mapped_column(String(10),nullable=True)
    status:Mapped[str]=mapped_column(String(30),nullable=False,default='PENDING_APPROVAL',index=True)
    commission_rate:Mapped[float]=mapped_column(Float,default=10.0)
    approved_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
    approved_by:Mapped[Optional[uuid.UUID]]=mapped_column(ForeignKey('users.id',ondelete='SET NULL'),nullable=True)
    rejection_reason:Mapped[Optional[str]]=mapped_column(String(500),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),onupdate=func.now())
    
    