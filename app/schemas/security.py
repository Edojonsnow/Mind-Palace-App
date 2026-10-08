from typing import Literal

from pydantic import BaseModel, Field

AuthRateLimitAction = Literal["sign_up", "sign_in", "verification", "password_reset"]


class AuthRateLimitRequest(BaseModel):
    client_key: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    action: AuthRateLimitAction
