from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ThoughtType(StrEnum):
    THOUGHT = "thought"
    JOURNAL = "journal"
    QUOTE = "quote"
    BOOK_EXCERPT = "book_excerpt"


class SourceType(StrEnum):
    MANUAL = "manual"
    BOOK = "book"
    ARTICLE = "article"
    WEBSITE = "website"
    AUDIO = "audio"
    IMPORT = "import"
    UNKNOWN = "unknown"


class StorageScope(StrEnum):
    CLOUD = "cloud"
    LOCAL_DEVICE = "local_device"


class AIProcessingStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Thought(Base):
    __tablename__ = "thoughts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    thought_type: Mapped[str] = mapped_column(String(32), default=ThoughtType.THOUGHT.value)
    source_type: Mapped[str] = mapped_column(String(32), default=SourceType.MANUAL.value)
    source_title: Mapped[str | None] = mapped_column(String(255))
    source_author: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    book_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("books.id", ondelete="SET NULL"),
        index=True,
    )
    book_title: Mapped[str | None] = mapped_column(String(255))
    book_author: Mapped[str | None] = mapped_column(String(255))
    page_reference: Mapped[str | None] = mapped_column(String(100))
    manual_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    storage_scope: Mapped[str] = mapped_column(String(32), default=StorageScope.CLOUD.value)
    use_with_ask_my_mind: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_processing_status: Mapped[str] = mapped_column(
        String(32),
        default=AIProcessingStatus.NOT_REQUESTED.value,
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    user = relationship("User", back_populates="thoughts")
    book = relationship("Book", back_populates="thoughts")
    chunks = relationship("ThoughtChunk", back_populates="thought", cascade="all, delete-orphan")
    metadata_record = relationship(
        "ThoughtMetadata",
        back_populates="thought",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def ai_metadata(self):
        return self.metadata_record
