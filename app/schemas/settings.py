from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserSettingsUpdate(BaseModel):
    default_use_with_ask_my_mind: bool | None = None
    store_chat_history: bool | None = None
    mobile_offline_cache_enabled: bool | None = None


class UserSettingsRead(BaseModel):
    id: UUID
    user_id: UUID
    default_use_with_ask_my_mind: bool
    store_chat_history: bool
    mobile_offline_cache_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

