import math
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_errors import RequestNotStartedError
from app.models import AIUsageDaily

AIQuotaOperation = Literal["ask", "search", "organization"]


class AIQuotaExceededError(RequestNotStartedError):
    """Raised before an AI provider call when the daily user allowance is spent."""

    def __init__(self, retry_after: int):
        super().__init__(
            status_code=429,
            detail="Daily AI allowance reached. Try again tomorrow.",
            headers={"Retry-After": str(retry_after), "X-AI-Quota": "daily"},
        )


def _next_reset(now: datetime) -> tuple[date, int]:
    usage_date = now.date()
    next_day = datetime.combine(usage_date + timedelta(days=1), datetime.min.time(), UTC)
    retry_after = max(1, math.ceil((next_day - now).total_seconds()))
    return usage_date, retry_after


def reserve_ai_quota(
    db: Session,
    user_id: UUID,
    operation: AIQuotaOperation,
    *,
    units: int,
) -> None:
    """Atomically reserve weighted daily AI units before an external provider call."""
    if not settings.ai_quotas_enabled:
        return
    if units < 1:
        raise ValueError("AI quota units must be positive")
    if units > settings.ai_daily_quota_units:
        raise AIQuotaExceededError(86400)

    now = datetime.now(UTC)
    usage_date, retry_after = _next_reset(now)
    operation_counts = {
        "ask": {"ask_count": 1},
        "search": {"search_count": 1},
        "organization": {"organization_count": 1},
    }
    count_values = operation_counts[operation]
    values = {
        "user_id": user_id,
        "usage_date": usage_date,
        "units_used": units,
        "ask_count": count_values.get("ask_count", 0),
        "search_count": count_values.get("search_count", 0),
        "organization_count": count_values.get("organization_count", 0),
    }
    bind = db.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        insert = postgres_insert(AIUsageDaily)
    elif dialect == "sqlite":
        insert = sqlite_insert(AIUsageDaily)
    else:
        _reserve_generic(db, values, operation, units)
        return

    statement = insert.values(**values).on_conflict_do_update(
        index_elements=[AIUsageDaily.user_id, AIUsageDaily.usage_date],
        set_={
            "units_used": AIUsageDaily.units_used + units,
            "ask_count": AIUsageDaily.ask_count + values["ask_count"],
            "search_count": AIUsageDaily.search_count + values["search_count"],
            "organization_count": AIUsageDaily.organization_count + values["organization_count"],
            "updated_at": now,
        },
        where=AIUsageDaily.units_used + units <= settings.ai_daily_quota_units,
    ).returning(AIUsageDaily.units_used)
    if db.execute(statement).scalar_one_or_none() is None:
        raise AIQuotaExceededError(retry_after)


def _reserve_generic(
    db: Session,
    values: dict[str, object],
    operation: AIQuotaOperation,
    units: int,
) -> None:
    usage = db.get(AIUsageDaily, (values["user_id"], values["usage_date"]))
    if usage is None:
        usage = AIUsageDaily(**values)
        db.add(usage)
        db.flush()
        return
    if usage.units_used + units > settings.ai_daily_quota_units:
        _, retry_after = _next_reset(datetime.now(UTC))
        raise AIQuotaExceededError(retry_after)
    usage.units_used += units
    setattr(usage, f"{operation}_count", getattr(usage, f"{operation}_count") + 1)


def quota_reset_seconds() -> int:
    _, retry_after = _next_reset(datetime.now(UTC))
    return retry_after


def validate_ai_thought_size(body: str) -> None:
    if len(body) > settings.ai_max_thought_chars:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Thoughts used with AI must be {settings.ai_max_thought_chars} "
                "characters or fewer"
            ),
        )
