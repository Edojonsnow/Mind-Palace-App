from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _validate_name(value: str) -> str:
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise ValueError("Collection name must not be blank")
    return normalized


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    _name_must_not_be_blank = field_validator("name")(_validate_name)


class CollectionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    _name_must_not_be_blank = field_validator("name")(_validate_name)


class CollectionRead(BaseModel):
    id: UUID
    name: str
    thought_count: int
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime
