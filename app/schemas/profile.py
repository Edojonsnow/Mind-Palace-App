from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

WritingStyle = Literal["natural", "conversational", "formal"]
ResponseDetail = Literal["concise", "balanced", "detailed"]
PreferenceItem = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=2048)

    @field_validator("display_name", "avatar_url")
    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar(cls, value: str | None) -> str | None:
        if value is not None and HttpUrl(value).scheme != "https":
            raise ValueError("Avatar URL must use HTTPS")
        return value


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: str | None
    email: str | None
    avatar_url: str | None


class AIPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_profile_context: bool = False
    writing_style: WritingStyle = "natural"
    response_detail: ResponseDetail = "balanced"
    personal_goals: list[PreferenceItem] = Field(default_factory=list, max_length=20)
    interests: list[PreferenceItem] = Field(default_factory=list, max_length=20)

    @field_validator("personal_goals", "interests")
    @classmethod
    def unique_items(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class AIPreferencesRead(AIPreferencesUpdate):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime | None = None
