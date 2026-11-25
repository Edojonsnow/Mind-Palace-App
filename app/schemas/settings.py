from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserSettingsUpdate(BaseModel):
    default_use_with_ask_my_mind: bool | None = None
    store_chat_history: bool | None = None
    mobile_offline_cache_enabled: bool | None = None


class OnboardingUpdate(BaseModel):
    action: Literal["continue", "skip"]

    model_config = ConfigDict(extra="forbid")


class UserSettingsRead(BaseModel):
    id: UUID
    user_id: UUID
    default_use_with_ask_my_mind: bool
    store_chat_history: bool
    mobile_offline_cache_enabled: bool
    onboarding_step: Literal["privacy", "first_thought"]
    onboarding_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

