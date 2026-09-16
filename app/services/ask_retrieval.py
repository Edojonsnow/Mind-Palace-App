import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AIProcessingStatus, Thought, ThoughtChunk, User


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: ThoughtChunk
    thought: Thought
    distance: float

    @property
    def similarity_score(self) -> float:
        return max(-1.0, min(1.0, 1.0 - self.distance))


def _retrieval_filters(user: User):
    return (
        ThoughtChunk.user_id == user.id,
        Thought.user_id == user.id,
        Thought.use_with_ask_my_mind.is_(True),
        Thought.ai_processing_status == AIProcessingStatus.READY.value,
        ThoughtChunk.deleted_at.is_(None),
        Thought.deleted_at.is_(None),
        Thought.is_archived.is_(False),
    )


def _cosine_distance(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 1.0
    cosine_similarity = sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
    return 1.0 - cosine_similarity


def retrieve_relevant_chunks(
    db: Session,
    user: User,
    query_embedding: list[float],
    *,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    """Retrieve the closest eligible chunks, using pgvector in production."""
    result_limit = limit or settings.ask_top_k
    base_statement = (
        select(ThoughtChunk, Thought)
        .join(Thought, ThoughtChunk.thought_id == Thought.id)
        .where(*_retrieval_filters(user))
    )

    if db.get_bind().dialect.name == "sqlite":
        candidates = db.execute(base_statement).all()
        ranked = sorted(
            (
                RetrievedChunk(
                    chunk=chunk,
                    thought=thought,
                    distance=_cosine_distance(chunk.embedding, query_embedding),
                )
                for chunk, thought in candidates
            ),
            key=lambda item: item.distance,
        )
        return ranked[:result_limit]

    distance = ThoughtChunk.embedding.cosine_distance(query_embedding).label("distance")
    statement = (
        select(ThoughtChunk, Thought, distance)
        .join(Thought, ThoughtChunk.thought_id == Thought.id)
        .where(*_retrieval_filters(user))
        .order_by(distance)
        .limit(result_limit)
    )
    return [
        RetrievedChunk(chunk=chunk, thought=thought, distance=float(distance_value))
        for chunk, thought, distance_value in db.execute(statement)
    ]


def has_retrievable_chunks(db: Session, user: User) -> bool:
    statement = (
        select(ThoughtChunk.id)
        .join(Thought, ThoughtChunk.thought_id == Thought.id)
        .where(*_retrieval_filters(user))
        .limit(1)
    )
    return db.scalar(statement) is not None
