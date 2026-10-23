from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CollectionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CollectionRead(BaseModel):
    id: UUID
    name: str
    thought_count: int
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime
