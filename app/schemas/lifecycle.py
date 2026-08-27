from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ExportRequestRead(BaseModel):
    id: UUID
    status: str
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime


class AccountDeletionRequestRead(BaseModel):
    id: UUID
    status: str
    requested_at: datetime
    purge_at: datetime
    completed_at: datetime | None
    error_message: str | None
