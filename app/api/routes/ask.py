from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas import AskRequest, AskResponse, ChatConversationRead
from app.services.ask import (
    ConversationNotFoundError,
    ask_my_mind,
    get_conversation_messages,
)
from app.services.openai_ai import AIProviderError
from app.services.users import get_or_create_user

router = APIRouter(prefix="/ask", tags=["ask-my-mind"])


@router.post("", response_model=AskResponse)
def ask_my_mind_route(
    payload: AskRequest,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    try:
        return ask_my_mind(
            db,
            user,
            payload.question,
            payload.conversation_id,
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
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    try:
        return get_conversation_messages(db, user, conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from error
