import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
import os
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

app = FastAPI(
    title="Booking Platform API",
    description="Core Monolith API with SOLID Auth Infrastructure",
    version="1.0.0"
)

cors_origins = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,https://localhost,capacitor://localhost").split(",") if o.strip()
]
# Ensure Capacitor origins and localhost are always explicitly allowed
default_trusted_origins = ["https://localhost", "capacitor://localhost", "http://localhost:5173", "http://localhost:3000"]
for origin in default_trusted_origins:
    if origin not in cors_origins:
        cors_origins.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$|^capacitor://localhost$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Idempotency-Key", "idempotency-key", "Authorization", "Content-Type"]
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(DuplicateEmailError)
async def duplicate_email_exception_handler(request: Request, exc: DuplicateEmailError):
    return JSONResponse(status_code=409, content={"detail": str(exc.detail)})

@app.exception_handler(InvalidCredentialsError)
async def invalid_creds_exception_handler(request: Request, exc: InvalidCredentialsError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})
@app.exception_handler(BookingNotFoundError)
async def booking_not_found_exception_handler(request: Request, exc: BookingNotFoundError):
    return JSONResponse(status_code=404, content={"error": "BOOKING_NOT_FOUND", "message": "Booking not found"})
from app.shared.exceptions import ForbiddenError, UnauthorizedError, EntityNotFoundError

@app.exception_handler(InvalidTokenError)
async def invalid_token_exception_handler(request: Request, exc: InvalidTokenError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})

@app.exception_handler(TokenReuseError)
async def token_reuse_exception_handler(request: Request, exc: TokenReuseError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})

@app.exception_handler(ForbiddenError)
async def forbidden_exception_handler(request: Request, exc: ForbiddenError):
    return JSONResponse(status_code=403, content={"detail": exc.message})

@app.exception_handler(UnauthorizedError)
async def unauthorized_exception_handler(request: Request, exc: UnauthorizedError):
    return JSONResponse(status_code=401, content={"detail": exc.message})

@app.exception_handler(EntityNotFoundError)
async def not_found_exception_handler(request: Request, exc: EntityNotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.message})

from app.auth.interfaces import ValidationError as AuthValidationError
from app.booking.interfaces import ValidationError as BookingValidationError
from app.event.exceptions import EventLockedError
from app.partner.interfaces import PartnerNotApprovedError

@app.exception_handler(AuthValidationError)
async def auth_validation_exception_handler(request: Request, exc: AuthValidationError):
    return JSONResponse(status_code=400, content={"error": "VALIDATION_ERROR", "detail": str(exc), "message": str(exc)})

@app.exception_handler(BookingValidationError)
async def booking_validation_exception_handler(request: Request, exc: BookingValidationError):
    return JSONResponse(status_code=400, content={"error": "VALIDATION_ERROR", "detail": str(exc), "message": str(exc)})

@app.exception_handler(EventLockedError)
async def event_locked_exception_handler(request: Request, exc: EventLockedError):
    return JSONResponse(status_code=400, content={"error": "EVENT_LOCKED", "detail": str(exc), "message": str(exc)})

@app.exception_handler(PartnerNotApprovedError)
async def partner_not_approved_exception_handler(request: Request, exc: PartnerNotApprovedError):
    return JSONResponse(status_code=403, content={"error": "PARTNER_NOT_APPROVED", "detail": str(exc), "message": str(exc)})


app.include_router(auth_router, prefix="/v1")
app.include_router(user_router, prefix="/v1")
app.include_router(partner_router, prefix="/v1")
app.include_router(event_router, prefix="/v1")
app.include_router(booking_router, prefix="/v1")
app.include_router(payment_router, prefix="/v1")
app.include_router(movie_router, prefix="/v1")
app.include_router(admin_router, prefix="/v1")
app.include_router(review_router, prefix="/v1")
app.include_router(support_router, prefix="/v1")
app.include_router(partner_coupon_router)
app.include_router(checkout_coupon_router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to Booking Platform API",
        "docs": "/docs",
        "status": "active"
    }

@app.get("/health")
@app.head("/health")

async def health_check():
    return {"status": "healthy"}
