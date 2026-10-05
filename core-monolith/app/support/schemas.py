from pydantic import BaseModel, Field
from typing import List, Optional

class ChatMessageItem(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class SupportChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    category: Optional[str] = None
    history: List[ChatMessageItem] = Field(default_factory=list)

class SupportChatResponse(BaseModel):
    reply: str
    source: str = "ai"  # "ai" or "knowledge_base"
