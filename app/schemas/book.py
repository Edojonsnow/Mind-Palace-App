from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(min_length=1, max_length=255)


class BookRead(BaseModel):
    id: UUID
    title: str
    author: str
    created_at: datetime
    updated_at: datetime
    thought_count: int = 0
