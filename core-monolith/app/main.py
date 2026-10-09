import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
import os
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from app.auth.routes import router as auth_router, limiter
from app.user.routes import router as user_router
from app.partner.routes import router as partner_router
from app.event.routes import router as event_router
from app.admin.routes import router as admin_router
from app.movie.routes import movie_router
from app.booking.routes import router as booking_router
from app.payment.routes import router as payment_router
from app.review.routes import router as review_router
from app.support.routes import router as support_router
from app.coupon.routes import partner_coupon_router, checkout_coupon_router
from app.booking.interfaces import BookingNotFoundError

from slowapi.errors import RateLimitExceeded
from app.auth.exceptions import (
    DuplicateEmailError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenReuseError,
)
from app.shared.exceptions import ForbiddenError, UnauthorizedError, EntityNotFoundError
from app.auth.interfaces import ValidationError as AuthValidationError
from app.booking.interfaces import ValidationError as BookingValidationError
from app.event.exceptions import EventLockedError
from app.partner.interfaces import PartnerNotApprovedError

from app.core.config import settings


async def duplicate_email_exception_handler(request: Request, exc: DuplicateEmailError):
    return JSONResponse(status_code=409, content={"detail": str(exc.detail)})

async def invalid_creds_exception_handler(request: Request, exc: InvalidCredentialsError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})

async def booking_not_found_exception_handler(request: Request, exc: BookingNotFoundError):
    return JSONResponse(status_code=404, content={"error": "BOOKING_NOT_FOUND", "message": "Booking not found"})

async def invalid_token_exception_handler(request: Request, exc: InvalidTokenError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})

async def token_reuse_exception_handler(request: Request, exc: TokenReuseError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})

async def forbidden_exception_handler(request: Request, exc: ForbiddenError):
    return JSONResponse(status_code=403, content={"detail": exc.message})

async def unauthorized_exception_handler(request: Request, exc: UnauthorizedError):
    return JSONResponse(status_code=401, content={"detail": exc.message})

async def not_found_exception_handler(request: Request, exc: EntityNotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.message})

async def auth_validation_exception_handler(request: Request, exc: AuthValidationError):
    return JSONResponse(status_code=400, content={"error": "VALIDATION_ERROR", "detail": str(exc), "message": str(exc)})

async def booking_validation_exception_handler(request: Request, exc: BookingValidationError):
    return JSONResponse(status_code=400, content={"error": "VALIDATION_ERROR", "detail": str(exc), "message": str(exc)})

async def event_locked_exception_handler(request: Request, exc: EventLockedError):
    return JSONResponse(status_code=400, content={"error": "EVENT_LOCKED", "detail": str(exc), "message": str(exc)})

async def partner_not_approved_exception_handler(request: Request, exc: PartnerNotApprovedError):
    return JSONResponse(status_code=403, content={"error": "PARTNER_NOT_APPROVED", "detail": str(exc), "message": str(exc)})


def create_app(environment: Optional[str] = None) -> FastAPI:
    env = (environment or getattr(settings, "ENVIRONMENT", "development") or "development").lower()
    is_production = env == "production"

    application = FastAPI(
        title="Booking Platform API",
        description="Core Monolith API with SOLID Auth Infrastructure",
        version="1.0.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )

    raw_cors = os.getenv("CORS_ORIGINS", "")
    raw_list = [o.strip() for o in raw_cors.split(",") if o.strip()]
    frontend_url = getattr(settings, "FRONTEND_URL", None)
    if frontend_url and frontend_url not in raw_list:
        raw_list.append(frontend_url)

    cors_origins = []
    for o in raw_list:
        if is_production:
            # Gate out insecure http localhost and loopback in production
            if o.startswith("http://localhost") or o.startswith("http://127.0.0.1"):
                continue
        if o not in cors_origins:
            cors_origins.append(o)

    # Always keep Capacitor origins
    always_allowed = ["https://localhost", "capacitor://localhost"]
    for origin in always_allowed:
        if origin not in cors_origins:
            cors_origins.append(origin)

    if not is_production:
        # Development only: allow localhost dev ports and regex
        dev_origins = ["http://localhost:5173", "http://localhost:3000"]
        for origin in dev_origins:
            if origin not in cors_origins:
                cors_origins.append(origin)
        origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$|^capacitor://localhost$"
    else:
        # Production: gate localhost and 127.0.0.1 regex out; keep capacitor and https://localhost
        origin_regex = r"^capacitor://localhost$|^https://localhost$"

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "Idempotency-Key", "idempotency-key", "Authorization", "Content-Type"]
    )

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    application.add_exception_handler(DuplicateEmailError, duplicate_email_exception_handler)
    application.add_exception_handler(InvalidCredentialsError, invalid_creds_exception_handler)
    application.add_exception_handler(BookingNotFoundError, booking_not_found_exception_handler)
    application.add_exception_handler(InvalidTokenError, invalid_token_exception_handler)
    application.add_exception_handler(TokenReuseError, token_reuse_exception_handler)
    application.add_exception_handler(ForbiddenError, forbidden_exception_handler)
    application.add_exception_handler(UnauthorizedError, unauthorized_exception_handler)
    application.add_exception_handler(EntityNotFoundError, not_found_exception_handler)
    application.add_exception_handler(AuthValidationError, auth_validation_exception_handler)
    application.add_exception_handler(BookingValidationError, booking_validation_exception_handler)
    application.add_exception_handler(EventLockedError, event_locked_exception_handler)
    application.add_exception_handler(PartnerNotApprovedError, partner_not_approved_exception_handler)

    application.include_router(auth_router, prefix="/v1")
    application.include_router(user_router, prefix="/v1")
    application.include_router(partner_router, prefix="/v1")
    application.include_router(event_router, prefix="/v1")
    application.include_router(booking_router, prefix="/v1")
    application.include_router(payment_router, prefix="/v1")
    application.include_router(movie_router, prefix="/v1")
    application.include_router(admin_router, prefix="/v1")
    application.include_router(review_router, prefix="/v1")
    application.include_router(support_router, prefix="/v1")
    application.include_router(partner_coupon_router)
    application.include_router(checkout_coupon_router)

    @application.get("/")
    async def root():
        return {
            "message": "Welcome to Booking Platform API",
            "docs": "/docs",
            "status": "active"
        }

    @application.get("/health")
    @application.head("/health")
    async def health_check():
        return {"status": "healthy"}

    return application


app = create_app()
