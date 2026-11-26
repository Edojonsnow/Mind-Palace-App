from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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


class AccountDeletionOptions(BaseModel):
    recovery_window_days: int
    permanent_deletion_available: bool


class PermanentAccountDeletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["DELETE MY ACCOUNT"]
