from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from app.auth.routes import router as auth_router, limiter
from app.user.routes import router as user_router
from app.partner.routes import router as partner_router
from app.event.routes import router as event_router
from app.admin.routes import router as admin_router


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:5173'
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=['*']
)
app.state.limiter=limiter
app.add_exception_handler(RateLimitExceeded,_rate_limit_exceeded_handler)
@app.exception_handler(DuplicateEmailError)
async def duplicate_email_exception_handler(request: Request, exc: DuplicateEmailError):
    return JSONResponse(status_code=409, content={"detail": str(exc.detail)})

@app.exception_handler(InvalidCredentialsError)
async def invalid_creds_exception_handler(request: Request, exc: InvalidCredentialsError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})

@app.exception_handler(InvalidTokenError)
async def invalid_token_exception_handler(request: Request, exc: InvalidTokenError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})

@app.exception_handler(TokenReuseError)
async def token_reuse_exception_handler(request: Request, exc: TokenReuseError):
    return JSONResponse(status_code=401, content={"detail": str(exc.detail)})
app.include_router(auth_router, prefix="/v1")
app.include_router(user_router, prefix="/v1")
app.include_router(partner_router, prefix="/v1")
app.include_router(event_router, prefix="/v1")
app.include_router(admin_router, prefix="/v1")   
@app.get("/")
async def root():
    return {
        "message": "Welcome to Booking Platform API",
        "docs": "/docs",
        "status": "active"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}