import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AIProcessingStatus,
    ChatConversation,
    ChatMessage,
    ChatMessageRole,
    Thought,
    ThoughtChunk,
    User,
)
from app.schemas.ask import AskResponse, AskSource, ChatConversationRead, ChatMessageRead
from app.services.openai_ai import (
    GeneratedAskAnswer,
    OpenAIProvider,
)
from app.services.thoughts import get_user_settings

logger = logging.getLogger(__name__)


class ConversationNotFoundError(LookupError):
    """Raised when a conversation does not belong to the authenticated user."""


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


def _has_retrievable_chunks(db: Session, user: User) -> bool:
    statement = (
        select(ThoughtChunk.id)
        .join(Thought, ThoughtChunk.thought_id == Thought.id)
        .where(*_retrieval_filters(user))
        .limit(1)
    )
    return db.scalar(statement) is not None


def _get_conversation(db: Session, user: User, conversation_id: UUID) -> ChatConversation:
    conversation = db.scalar(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise ConversationNotFoundError
    return conversation


def _conversation_history(db: Session, conversation_id: UUID) -> list[dict[str, str]]:
    messages = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(settings.ask_history_messages)
        )
    )
    return [
        {"role": message.role, "content": message.content}
        for message in reversed(messages)
        if message.role in {ChatMessageRole.USER.value, ChatMessageRole.ASSISTANT.value}
    ]


def _source(
    retrieved: RetrievedChunk,
    label: str,
    cited_labels: set[str],
) -> AskSource:
    thought = retrieved.thought
    return AskSource(
        citation_label=label,
        chunk_id=retrieved.chunk.id,
        thought_id=thought.id,
        title=thought.title,
        snippet=retrieved.chunk.chunk_text,
        source_type=thought.source_type,
        source_title=thought.source_title or thought.book_title,
        source_author=thought.source_author or thought.book_author,
        created_at=thought.created_at or datetime.now(UTC),
        similarity_score=retrieved.similarity_score,
        is_cited=label in cited_labels,
    )


def _context(retrieved_chunks: list[RetrievedChunk]) -> str:
    sections: list[str] = []
    remaining = settings.ask_max_context_chars
    for index, retrieved in enumerate(retrieved_chunks, start=1):
        if remaining <= 0:
            break
        label = f"S{index}"
        title = retrieved.thought.title or "Untitled thought"
        text = retrieved.chunk.chunk_text[:remaining]
        sections.append(f"[{label}] {title}\n{text}")
        remaining -= len(text)
    return "\n\n".join(sections)


def _no_source_answer() -> str:
    return "I could not find an AI-enabled thought that answers that question yet."


def _save_message(
    db: Session,
    conversation: ChatConversation,
    user: User,
    role: ChatMessageRole,
    content: str,
    citations: list[dict[str, object]] | None = None,
) -> ChatMessage:
    message = ChatMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        role=role.value,
        content=content,
        citations=citations or [],
        created_at=datetime.now(UTC),
    )
    db.add(message)
    conversation.updated_at = datetime.now(UTC)
    db.flush()
    return message


def ask_my_mind(
    db: Session,
    user: User,
    question: str,
    conversation_id: UUID | None = None,
    *,
    provider_factory: Callable[[], OpenAIProvider] | None = None,
) -> AskResponse:
    user_settings = get_user_settings(db, user)
    should_store_history = user_settings.store_chat_history
    conversation: ChatConversation | None = None
    history: list[dict[str, str]] = []

    if should_store_history:
        conversation = (
            _get_conversation(db, user, conversation_id)
            if conversation_id is not None
            else ChatConversation(user_id=user.id)
        )
        if conversation.id is None:
            db.add(conversation)
            db.flush()
        history = _conversation_history(db, conversation.id)
        _save_message(db, conversation, user, ChatMessageRole.USER, question)
        db.commit()
    else:
        conversation_id = conversation_id or uuid4()

    if not _has_retrievable_chunks(db, user):
        answer = _no_source_answer()
        if should_store_history and conversation is not None:
            assistant_message = _save_message(
                db,
                conversation,
                user,
                ChatMessageRole.ASSISTANT,
                answer,
            )
            db.commit()
            return AskResponse(
                conversation_id=conversation.id,
                answer=answer,
                sources=[],
                created_at=assistant_message.created_at or datetime.now(UTC),
            )
        return AskResponse(
            conversation_id=conversation_id,
            answer=answer,
            sources=[],
            created_at=datetime.now(UTC),
        )

    try:
        provider = (provider_factory or OpenAIProvider)()
        query_embedding = provider.embed([question])[0]
        retrieved_chunks = retrieve_relevant_chunks(db, user, query_embedding)
        if not retrieved_chunks:
            generated = GeneratedAskAnswer(answer=_no_source_answer())
        else:
            generated = provider.answer_question(
                question,
                _context(retrieved_chunks),
                history,
            )
    except Exception as error:
        db.rollback()
        logger.warning("Ask My Mind failed: error_type=%s", type(error).__name__)
        raise

    cited_labels = {
        citation_id
        for citation_id in generated.citation_ids
        if citation_id.startswith("S") and citation_id[1:].isdigit()
    }
    sources = [
        _source(retrieved, f"S{index}", cited_labels)
        for index, retrieved in enumerate(retrieved_chunks, start=1)
    ]
    citation_payload = [source.model_dump(mode="json") for source in sources]

    if should_store_history and conversation is not None:
        assistant_message = _save_message(
            db,
            conversation,
            user,
            ChatMessageRole.ASSISTANT,
            generated.answer,
            citation_payload,
        )
        db.commit()
        response_created_at = assistant_message.created_at or datetime.now(UTC)
        response_conversation_id = conversation.id
    else:
        response_created_at = datetime.now(UTC)
        response_conversation_id = conversation_id

    return AskResponse(
        conversation_id=response_conversation_id,
        answer=generated.answer,
        sources=sources,
        created_at=response_created_at,
    )


def get_conversation_messages(
    db: Session,
    user: User,
    conversation_id: UUID,
) -> ChatConversationRead:
    conversation = _get_conversation(db, user, conversation_id)
    messages = list(
        db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.conversation_id == conversation.id,
                ChatMessage.user_id == user.id,
            )
            .order_by(ChatMessage.created_at.asc())
        )
    )
    return ChatConversationRead(
        conversation_id=conversation.id,
        messages=[
            ChatMessageRead(
                id=message.id,
                role=message.role,
                content=message.content,
                citations=message.citations,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )
