from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ChatConversation,
    ChatMessage,
    Thought,
    ThoughtMetadata,
    User,
    UserSettings,
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _thought_payload(thought: Thought) -> dict[str, object]:
    return {
        "id": str(thought.id),
        "title": thought.title,
        "body": thought.body,
        "thought_type": thought.thought_type,
        "source_type": thought.source_type,
        "source_title": thought.source_title,
        "source_author": thought.source_author,
        "source_url": thought.source_url,
        "book_title": thought.book_title,
        "book_author": thought.book_author,
        "page_reference": thought.page_reference,
        "manual_tags": thought.manual_tags,
        "storage_scope": thought.storage_scope,
        "use_with_ask_my_mind": thought.use_with_ask_my_mind,
        "ai_processing_status": thought.ai_processing_status,
        "is_archived": thought.is_archived,
        "created_at": _iso(thought.created_at),
        "updated_at": _iso(thought.updated_at),
        "deleted_at": _iso(thought.deleted_at),
        "purge_at": _iso(thought.purge_at),
    }


def build_export_payload(db: Session, user: User) -> dict[str, object]:
    settings_record = db.scalar(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    thoughts = list(
        db.scalars(select(Thought).where(Thought.user_id == user.id).order_by(Thought.created_at))
    )
    metadata = list(
        db.scalars(
            select(ThoughtMetadata)
            .where(ThoughtMetadata.user_id == user.id)
            .order_by(ThoughtMetadata.created_at)
        )
    )
    conversations = list(
        db.scalars(
            select(ChatConversation)
            .where(ChatConversation.user_id == user.id)
            .order_by(ChatConversation.created_at)
        )
    )
    messages = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at)
        )
    )

    return {
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {
            "email": user.email,
            "display_name": user.display_name,
            "created_at": _iso(user.created_at),
        },
        "settings": (
            {
                "default_use_with_ask_my_mind": settings_record.default_use_with_ask_my_mind,
                "store_chat_history": settings_record.store_chat_history,
                "mobile_offline_cache_enabled": settings_record.mobile_offline_cache_enabled,
            }
            if settings_record is not None
            else None
        ),
        "thoughts": [_thought_payload(thought) for thought in thoughts],
        "thought_metadata": [
            {
                "thought_id": str(record.thought_id),
                "summary": record.summary,
                "themes": record.themes,
                "emotions": record.emotions,
                "people": record.people,
                "places": record.places,
                "books": record.books,
                "key_questions": record.key_questions,
                "action_items": record.action_items,
                "created_at": _iso(record.created_at),
                "updated_at": _iso(record.updated_at),
            }
            for record in metadata
        ],
        "chat_conversations": [
            {
                "id": str(conversation.id),
                "created_at": _iso(conversation.created_at),
                "updated_at": _iso(conversation.updated_at),
            }
            for conversation in conversations
        ],
        "chat_messages": [
            {
                "id": str(message.id),
                "conversation_id": str(message.conversation_id),
                "role": message.role,
                "content": message.content,
                "citations": message.citations,
                "created_at": _iso(message.created_at),
            }
            for message in messages
        ],
    }
