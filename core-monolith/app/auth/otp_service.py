import secrets
import hashlib
import aiosmtplib
import logging
import uuid
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Optional
from app.auth.interfaces import (
    IOTPService, 
    IUserRepository, 
    IOTPCodesRepository, 
    INotificationService,
    User as UserDomain
)
from app.auth.exceptions import InvalidCredentialsError
from fastapi import HTTPException
from app.core.config import settings
logger = logging.getLogger(__name__)
class NotificationService(INotificationService):
   
    async def send_sms(self, phone: str, message: str) -> bool:
        print(f"[SMS MOCK TO {phone}]: {message}")
        return True
    async def send_email(self, email: str, subject: str, body: str) -> bool:
       
        msg = EmailMessage()
        msg["From"] = settings.EMAILS_FROM
        msg["To"] = email
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=False,
                start_tls=True,
                timeout=10 
            )
            logger.info(f"Successfully sent OTP email to {email}")
            return True
        except Exception as e:
            logger.error(f"CRITICAL: Failed to send email to {email}. Error: {str(e)}")
            return False
class OTPService(IOTPService):
 
    MAX_ATTEMPTS = 3
    CODE_LENGTH = 6
    EXPIRY_MINUTES = 10
    RATE_LIMIT_PER_HOUR = 5
    def __init__(
        self,
        user_repo: IUserRepository,
        otp_repo: IOTPCodesRepository,
        notification: INotificationService
    ):
        self.user_repo = user_repo
        self.otp_repo = otp_repo
        self.notification = notification
    def _generate_code(self) -> str:
        return ''.join(secrets.choice('0123456789') for _ in range(self.CODE_LENGTH))
    def _hash_code(self, code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()
    async def generate_and_send(self, user: UserDomain, method: str = "SMS") -> None:
        recent_count = await self.otp_repo.count_recent_requests(user.id, 60)
        if recent_count >= self.RATE_LIMIT_PER_HOUR:
            raise HTTPException(status_code=429, detail="Too many OTP requests. Try again in an hour.")
        code = self._generate_code()
        code_hash = self._hash_code(code)
        expires_at = datetime.utcnow() + timedelta(minutes=self.EXPIRY_MINUTES)
        await self.otp_repo.create(user.id, code_hash, method, expires_at)
        message_text = f"Your Vignette verification code is: {code}. It expires in {self.EXPIRY_MINUTES} minutes."
        success = False
        if method == "EMAIL" and user.email:
            success = await self.notification.send_email(user.email, "Email Verification", message_text)
        elif method == "SMS" and user.phone:
            success = await self.notification.send_sms(user.phone, message_text)
        if not success:
            logger.error(f"OTP Delivery failure for user {user.id}")
            raise HTTPException(
                status_code=500, 
                detail="Account created but we couldn't send the verification code. Please request a resend."
            )
            
    async def verify(self, user_id: uuid.UUID, code: str, method: str = "SMS") -> bool:
        stored = await self.otp_repo.get_valid_code(user_id, method)
        if not stored:
            raise InvalidCredentialsError("Invalid or expired code")
        if stored['attempts'] >= self.MAX_ATTEMPTS:
            raise HTTPException(status_code=403, detail="Too many failed attempts. Request a new code.")
        if self._hash_code(code) != stored['code_hash']:
            await self.otp_repo.increment_attempts(stored['id'])
            raise InvalidCredentialsError("Incorrect verification code")
        await self.otp_repo.mark_used(stored['id'])
        return True