from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.dependencies import CurrentUser, DbSession, IdempotencyKey
from app.schemas import AskRequest, AskResponse, ChatConversationRead
from app.services.ask import (
    ConversationNotFoundError,
    ask_my_mind,
    get_conversation_messages,
)
from app.services.idempotency import execute_idempotent
from app.services.openai_ai import AIProviderError

router = APIRouter(prefix="/ask", tags=["ask-my-mind"])


@router.post("", response_model=AskResponse)
def ask_my_mind_route(
    payload: AskRequest,
    db: DbSession,
    user: CurrentUser,
    response: Response,
    idempotency_key: IdempotencyKey = None,
):
    try:
        return execute_idempotent(
            db, user, "POST /ask", idempotency_key, payload.model_dump(mode="json"), response,
            lambda operation: ask_my_mind(
                db, user, payload.question, payload.conversation_id, operation=operation,
            ),
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from error
    except AIProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ask My Mind is temporarily unavailable",
        ) from error


@router.get("/{conversation_id}", response_model=ChatConversationRead)
def get_conversation_route(
    conversation_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    try:
        return get_conversation_messages(db, user, conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from error
