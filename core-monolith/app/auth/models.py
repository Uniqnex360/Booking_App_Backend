from enum import Enum as PyEnum
from app.core.database import Base
from datetime import datetime
from sqlalchemy.orm import relationship, Mapped, mapped_column
import uuid
from typing import Optional,List
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID

class UserRole(str,PyEnum):
    USER="USER"
    PARTNER='PARTNER'
    ADMIN='ADMIN'
class  User(Base):
    __tablename__='users'
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    full_name:Mapped[str]=mapped_column(String(255),nullable=False)
    email:Mapped[str]=mapped_column(String(255),unique=True,nullable=False,index=True)
    phone:Mapped[Optional[str]]=mapped_column(String(20),unique=True,nullable=True)
    password_hash:Mapped[str]=mapped_column(String(255),nullable=False)
    role:Mapped[UserRole]=mapped_column(Enum(UserRole),default=UserRole.USER,nullable=False)
    is_verified:Mapped[bool]=mapped_column(Boolean,default=False)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    last_login_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    refresh_tokens:Mapped[List['RefreshToken']]=relationship('RefreshToken',back_populates='user',cascade='all,delete-orphan')
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
    
    
class RefreshToken(Base):
    __tablename__='refresh_tokens'
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    user_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey('users.id',ondelete='CASCADE'),nullable=False,index=True)
    token_hash:Mapped[str]=mapped_column(String(255),nullable=False,index=True)
    token_family:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),default=uuid.uuid4)
    expires_at:Mapped[datetime]=mapped_column(DateTime,nullable=False,index=True)
    is_revoked:Mapped[bool]=mapped_column(Boolean,default=False)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    ip_address:Mapped[Optional[str]]=mapped_column(String(45),nullable=True) 
    user_agent:Mapped[Optional[str]]=mapped_column(Text,nullable=True)
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
    
    def is_valid(self)->bool:
        return not self.is_revoked and self.expires_at>datetime.utcnow()
    
    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, valid={self.is_valid()})>"


class OTPMethod(str, PyEnum):
    SMS = "SMS"
    EMAIL = "EMAIL"


class OTPCode(Base):
    __tablename__ = "otp_codes"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)  
    method: Mapped[OTPMethod] = mapped_column(Enum(OTPMethod), default=OTPMethod.SMS)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)