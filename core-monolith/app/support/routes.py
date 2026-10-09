import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.auth.dependencies import get_current_user_optional
from app.auth.interfaces import User as AuthUserDomain
from app.auth.routes import limiter
from app.support.schemas import SupportChatRequest, SupportChatResponse
from app.support.service import (
    generate_support_reply,
    get_user_recent_bookings,
    get_knowledge_base_fallback,
)

logger = logging.getLogger("support.routes")

router = APIRouter(prefix="/support", tags=["Support"])

@router.post("/chat", response_model=SupportChatResponse)
@limiter.limit("20/minute")
async def chat_with_support(
    request: Request,
    payload: SupportChatRequest,
    current_user: AuthUserDomain | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Production-ready support chat endpoint:
    - Protects OPENAI_API_KEY on the backend server.
    - Rate-limited to 20 requests per minute per IP.
    - Personalization: Detects logged-in user and loads recent bookings for customized support.
    - Seamlessly falls back to Vyhbz knowledge base if key is unconfigured or OpenAI is unreachable.
    """
    user_bookings = None
    user_name = None
    user_email = None

    if current_user:
        user_name = current_user.full_name
        user_email = current_user.email
        try:
            user_bookings = await get_user_recent_bookings(db, current_user.id, limit=5)
        except Exception as e:
            logger.warning("Failed to fetch user bookings for support chat: %s", e)
            user_bookings = []

    try:
        response = await generate_support_reply(
            message=payload.message,
            history=payload.history,
            category=payload.category,
            user_name=user_name,
            user_email=user_email,
            user_bookings=user_bookings,
        )
        return response
    except Exception as e:
        logger.error("Error in support chat handler: %s", e, exc_info=True)
        # Guarantee 200 response with knowledge base fallback so chat never breaks
        fallback = get_knowledge_base_fallback(
            payload.message,
            payload.category,
            user_name=user_name,
            user_bookings=user_bookings,
        )
        return SupportChatResponse(reply=fallback, source="knowledge_base")

