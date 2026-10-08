from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai_quota import quota_reset_seconds
from app.core.config import settings
from app.models import AIUsageDaily, User
from app.schemas.ai_usage import AIUsageRead


def get_ai_usage(db: Session, user: User) -> AIUsageRead:
    now = datetime.now(UTC)
    usage = db.scalar(
        select(AIUsageDaily).where(
            AIUsageDaily.user_id == user.id,
            AIUsageDaily.usage_date == now.date(),
        )
    )
    units_used = usage.units_used if usage is not None else 0
    return AIUsageRead(
        usage_date=now.date(),
        units_used=units_used,
        daily_limit=settings.ai_daily_quota_units,
        remaining_units=max(0, settings.ai_daily_quota_units - units_used),
        ask_count=usage.ask_count if usage is not None else 0,
        search_count=usage.search_count if usage is not None else 0,
        organization_count=usage.organization_count if usage is not None else 0,
        resets_at=now + timedelta(seconds=quota_reset_seconds()),
    )
