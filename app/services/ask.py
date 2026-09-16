import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ChatConversation, ChatMessage, ChatMessageRole, User
from app.schemas.ask import AskResponse, ChatConversationRead, ChatMessageRead
from app.services.ask_retrieval import (
    has_retrievable_chunks,
    retrieve_relevant_chunks,
)
from app.services.ask_sources import build_context, build_sources, no_source_answer
from app.services.openai_ai import (
    GeneratedAskAnswer,
    OpenAIProvider,
)
from app.services.settings import get_user_settings

logger = logging.getLogger(__name__)


class ConversationNotFoundError(LookupError):
    """Raised when a conversation does not belong to the authenticated user."""


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

    if not has_retrievable_chunks(db, user):
        answer = no_source_answer()
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
            generated = GeneratedAskAnswer(answer=no_source_answer())
        else:
            generated = provider.answer_question(
                question,
                build_context(retrieved_chunks),
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
    sources = build_sources(retrieved_chunks, cited_labels)
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
