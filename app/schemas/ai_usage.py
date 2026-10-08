from datetime import date, datetime

from pydantic import BaseModel, Field


class AIUsageRead(BaseModel):
    usage_date: date
    units_used: int = Field(ge=0)
    daily_limit: int = Field(ge=1)
    remaining_units: int = Field(ge=0)
    ask_count: int = Field(ge=0)
    search_count: int = Field(ge=0)
    organization_count: int = Field(ge=0)
    resets_at: datetime
