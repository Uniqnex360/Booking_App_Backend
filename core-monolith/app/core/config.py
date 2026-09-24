from pydantic_settings import BaseSettings
from pydantic import PostgresDsn, field_validator
from typing import List, Optional
import secrets

class Settings(BaseSettings):
    DATABASE_URL: PostgresDsn
    TEST_DATABASE_URL: Optional[PostgresDsn] = None
    CORS_ORIGINS: str
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUND: int = 12
    MAX_LOGIN_ATTEMPTS: int = 5
    RATE_LIMIT_WINDOW: int = 60
    ALLOWED_HOSTS: List[str] = [""]
    FIREBASE_PROJECT_ID: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    RESEND_API_KEY: Optional[str] = None
    RESEND_FROM_EMAIL: Optional[str] = "noreply@datavioai.com"
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM: Optional[str] = "noreply@datavioai.com"
    GOOGLE_PUBLIC_KEYS_URL: Optional[str] = None

    RAZORPAY_ENV: str = "test"
    RAZORPAY_KEY_ID: str = "rzp_test_VyBhZExTMTk5"
    RAZORPAY_KEY_SECRET: str = "test_secret_placeholder"
    RAZORPAY_WEBHOOK_SECRET: str = "whsec_test_placeholder" 
    FRONTEND_URL:str
    

    class Config:
        env_file = '.env'
        case_sensitive = True
        extra = "ignore" 

settings = Settings()
