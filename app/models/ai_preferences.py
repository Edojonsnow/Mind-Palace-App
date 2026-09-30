from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIPreferences(Base):
    __tablename__ = "ai_preferences"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    use_profile_context: Mapped[bool] = mapped_column(Boolean, default=False)
    writing_style: Mapped[str] = mapped_column(String(32), default="natural")
    response_detail: Mapped[str] = mapped_column(String(32), default="balanced")
    personal_goals: Mapped[list[str]] = mapped_column(JSON, default=list)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
