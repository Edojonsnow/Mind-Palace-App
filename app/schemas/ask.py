from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    conversation_id: UUID | None = None


class AskSource(BaseModel):
    citation_label: str
    chunk_id: UUID
    thought_id: UUID
    title: str | None
    snippet: str
    source_type: str
    source_title: str | None
    source_author: str | None
    created_at: datetime
    similarity_score: float = Field(ge=-1, le=1)
    is_cited: bool


class AskResponse(BaseModel):
    conversation_id: UUID
    answer: str
    sources: list[AskSource]
    created_at: datetime


class ChatMessageRead(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[dict[str, object]]
    created_at: datetime


class ChatConversationRead(BaseModel):
    conversation_id: UUID
    messages: list[ChatMessageRead]
