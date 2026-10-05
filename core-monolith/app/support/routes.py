from fastapi import APIRouter, Request, HTTPException
from app.auth.routes import limiter
from app.support.schemas import SupportChatRequest, SupportChatResponse
from app.support.service import generate_support_reply

router = APIRouter(prefix="/support", tags=["Support"])

@router.post("/chat", response_model=SupportChatResponse)
@limiter.limit("20/minute")
async def chat_with_support(request: Request, payload: SupportChatRequest):
    """
    Production-ready support chat endpoint:
    - Protects OPENAI_API_KEY on the backend server.
    - Rate-limited to 20 requests per minute per IP.
    - Seamlessly falls back to Vyhbz knowledge base if key is unconfigured or OpenAI is unreachable.
    """
    try:
        response = await generate_support_reply(
            message=payload.message,
            history=payload.history,
            category=payload.category,
        )
        return response
    except Exception as e:
        # Guarantee 200 response with knowledge base fallback so chat never breaks
        from app.support.service import get_knowledge_base_fallback
        fallback = get_knowledge_base_fallback(payload.message, payload.category)
        return SupportChatResponse(reply=fallback, source="knowledge_base")
