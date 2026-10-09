import secrets
import logging
import uuid
import httpx
from datetime import datetime, timedelta
from typing import Optional
from email.message import EmailMessage
from app.shared.hashing import sha256_hex

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

    async def send_email(self, email: str, subject: str, body: str, content_type: str = "text") -> bool: 
        resend_key = getattr(settings, "RESEND_API_KEY", None)
        from_email = getattr(settings, "RESEND_FROM_EMAIL", None) or getattr(settings, "EMAILS_FROM", None) or "noreply@datavioai.com"

        
        if resend_key:
            sender = f"Vybh <{from_email}>" if "<" not in from_email else from_email
            payload = {
                "from": sender,
                "to": [email],
                "subject": subject,
                "html" if content_type == "html" else "text": body,

            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        "https://api.resend.com/emails",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {resend_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    if resp.status_code in (200, 201):
                        logger.info(f"Successfully sent email to {email} via Resend")
                        return True
                    else:
                        logger.error(f"Resend error ({resp.status_code}): {resp.text}")
                        return False
            except Exception as e:
                logger.error(f"Failed to connect to Resend API: {e}")
                return False

        
        if getattr(settings, "SMTP_HOST", None) and getattr(settings, "RESEND_FROM_EMAIL", None):
            import aiosmtplib
            msg = EmailMessage()
            msg["From"] = getattr(settings, "EMAILS_FROM", from_email)
            msg["To"] = email
            msg["Subject"] = subject
            msg.add_alternative(body, subtype="html")
            try:
                await aiosmtplib.send(
                    msg,
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT or 587,
                    username=settings.RESEND_FROM_EMAIL,
                    password=settings.SMTP_PASSWORD,
                    use_tls=False,
                    start_tls=True,
                    timeout=10
                )
                logger.info(f"Successfully sent email to {email} via SMTP")
                return True
            except Exception as e:
                logger.error(f"Failed to send email via SMTP: {e}")
                return False

        
        print(f"\n--- [DEV EMAIL] To: {email} | Subject: {subject} | Body: {body} ---\n")
        return True


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
        return sha256_hex(code)


    async def generate_and_send(self, user: UserDomain, method: str = "SMS") -> None:
        recent_count = await self.otp_repo.count_recent_requests(user.id, 60)
        if recent_count >= self.RATE_LIMIT_PER_HOUR:
            raise HTTPException(status_code=429, detail="Too many OTP requests. Try again in an hour.")
        code = self._generate_code()
        code_hash = self._hash_code(code)
        expires_at = datetime.utcnow() + timedelta(minutes=self.EXPIRY_MINUTES)
        await self.otp_repo.create(user.id, code_hash, method, expires_at)
        message_text = f"Your verification code is: {code}. It expires in {self.EXPIRY_MINUTES} minutes."
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
