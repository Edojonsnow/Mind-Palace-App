from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, TypeDecorator, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

EMBEDDING_DIMENSIONS = 1536


class EmbeddingVector(TypeDecorator[Any]):
    """Use pgvector in Neon and JSON in SQLite unit tests."""

    impl = JSON
    cache_ok = True
    comparator_factory = Vector.Comparator

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(EMBEDDING_DIMENSIONS))
        return dialect.type_descriptor(JSON())


class BackgroundJobType(StrEnum):
    CHUNK_THOUGHT = "chunk_thought"
    EMBED_THOUGHT = "embed_thought"
    EXTRACT_METADATA = "extract_metadata"
    PURGE_AI_ARTIFACTS = "purge_ai_artifacts"
    PURGE_DELETED_THOUGHT = "purge_deleted_thought"
    GENERATE_EXPORT = "generate_export"


class BackgroundJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ThoughtChunk(Base):
    __tablename__ = "thought_chunks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    thought_id: Mapped[UUID] = mapped_column(ForeignKey("thoughts.id"), index=True)
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector())
    token_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    thought = relationship("Thought", back_populates="chunks")


class ThoughtMetadata(Base):
    __tablename__ = "thought_metadata"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    thought_id: Mapped[UUID] = mapped_column(ForeignKey("thoughts.id"), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    themes: Mapped[list[str]] = mapped_column(JSON, default=list)
    emotions: Mapped[list[str]] = mapped_column(JSON, default=list)
    people: Mapped[list[str]] = mapped_column(JSON, default=list)
    places: Mapped[list[str]] = mapped_column(JSON, default=list)
    books: Mapped[list[str]] = mapped_column(JSON, default=list)
    key_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    action_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    deterministic_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    thought = relationship("Thought", back_populates="metadata_record")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    thought_id: Mapped[UUID | None] = mapped_column(ForeignKey("thoughts.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default=BackgroundJobStatus.PENDING.value)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
