from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.thought import AIProcessingStatus, SourceType, StorageScope, ThoughtType


class ThoughtCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1)
    thought_type: ThoughtType = ThoughtType.THOUGHT
    source_type: SourceType = SourceType.MANUAL
    source_title: str | None = Field(default=None, max_length=255)
    source_author: str | None = Field(default=None, max_length=255)
    source_url: HttpUrl | None = None
    book_title: str | None = Field(default=None, max_length=255)
    book_author: str | None = Field(default=None, max_length=255)
    page_reference: str | None = Field(default=None, max_length=100)
    manual_tags: list[str] = Field(default_factory=list)
    storage_scope: StorageScope = StorageScope.CLOUD
    use_with_ask_my_mind: bool | None = None
    is_archived: bool = False


class ThoughtUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    thought_type: ThoughtType | None = None
    source_type: SourceType | None = None
    source_title: str | None = Field(default=None, max_length=255)
    source_author: str | None = Field(default=None, max_length=255)
    source_url: HttpUrl | None = None
    book_title: str | None = Field(default=None, max_length=255)
    book_author: str | None = Field(default=None, max_length=255)
    page_reference: str | None = Field(default=None, max_length=100)
    manual_tags: list[str] | None = None
    use_with_ask_my_mind: bool | None = None
    is_archived: bool | None = None


class ThoughtMetadataRead(BaseModel):
    summary: str | None
    themes: list[str]
    emotions: list[str]
    people: list[str]
    places: list[str]
    books: list[str]
    key_questions: list[str]
    action_items: list[str]
    deterministic_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ThoughtRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None
    body: str
    thought_type: ThoughtType
    source_type: SourceType
    source_title: str | None
    source_author: str | None
    source_url: str | None
    book_title: str | None
    book_author: str | None
    page_reference: str | None
    manual_tags: list[str]
    storage_scope: StorageScope
    use_with_ask_my_mind: bool
    ai_processing_status: AIProcessingStatus
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    purge_at: datetime | None
    ai_metadata: ThoughtMetadataRead | None = None

    model_config = ConfigDict(from_attributes=True)
