import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_errors import RequestNotStartedError
from app.models import ChatMessage, ExportRequest, IdempotencyRequest, Thought, User
from app.schemas import AskResponse, AskSource


def complete_operation(
    operation: IdempotencyRequest | None, resource_kind: str, resource_id: UUID | None
) -> None:
    if operation is not None:
        operation.resource_kind = resource_kind
        operation.resource_id = resource_id
        operation.status = "completed"


def _replay(db: Session, user: User, operation: IdempotencyRequest):
    if operation.resource_kind == "thought":
        from app.services.thoughts import get_thought

        try:
            return get_thought(db, user, operation.resource_id)
        except HTTPException as error:
            if error.status_code != 404:
                raise
    elif operation.resource_kind == "export":
        export = db.get(ExportRequest, operation.resource_id)
        if export is not None and export.user_id == user.id:
            return export
    elif operation.resource_kind == "ask":
        message = db.get(ChatMessage, operation.resource_id)
        if message is not None and message.user_id == user.id:
            sources = [AskSource.model_validate(value) for value in message.citations or []]
            eligible = set(db.scalars(select(Thought.id).where(
                Thought.id.in_([source.thought_id for source in sources]),
                Thought.user_id == user.id,
                Thought.deleted_at.is_(None),
                Thought.use_with_ask_my_mind.is_(True),
            )))
            return AskResponse(
                conversation_id=message.conversation_id,
                answer=message.content,
                sources=[source for source in sources if source.thought_id in eligible],
                created_at=message.created_at,
            )
    elif operation.resource_kind == "unstored_answer":
        raise HTTPException(
            409, "This question was answered, but history is off; replay is unavailable"
        )
    raise HTTPException(410, "The original result is no longer available")


def execute_idempotent[T](
    db: Session,
    user: User,
    scope: str,
    key: str | None,
    payload: dict[str, object],
    response: Response,
    action: Callable[[IdempotencyRequest | None], T],
) -> T:
    if key is None:
        return action(None)
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    now = datetime.now(UTC)
    # Only completed claims expire. Uncertain external side effects are never blindly repeated.
    db.execute(delete(IdempotencyRequest).where(
        IdempotencyRequest.user_id == user.id,
        IdempotencyRequest.status == "completed",
        IdempotencyRequest.expires_at <= now,
    ).execution_options(synchronize_session="fetch"))
    db.commit()
    operation = IdempotencyRequest(
        user_id=user.id, scope=scope, key=key, request_hash=fingerprint,
        expires_at=now + timedelta(hours=settings.idempotency_retention_hours),
    )
    db.add(operation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(IdempotencyRequest).where(
            IdempotencyRequest.user_id == user.id,
            IdempotencyRequest.scope == scope,
            IdempotencyRequest.key == key,
        ))
        if existing is None:
            raise
        if existing.request_hash != fingerprint:
            raise HTTPException(
                409, "Idempotency key was already used with different data"
            ) from None
        if existing.status != "completed":
            raise HTTPException(
                409, "This action is in progress or uncertain; check before resubmitting",
                headers={"Retry-After": "2"} if existing.status == "processing" else None,
            ) from None
        response.headers["Idempotency-Replayed"] = "true"
        return _replay(db, user, existing)

    try:
        result = action(operation)
        if operation.status != "completed":
            raise RuntimeError("Operation did not record its result")
        db.commit()
        response.headers["Idempotency-Replayed"] = "false"
        return result
    except RequestNotStartedError:
        db.rollback()
        persisted = db.get(IdempotencyRequest, operation.id)
        if persisted is not None:
            db.delete(persisted)
        db.commit()
        raise
    except Exception:
        db.rollback()
        persisted = db.get(IdempotencyRequest, operation.id)
        if persisted is not None and persisted.status != "completed":
            persisted.status = "uncertain"
            db.commit()
        raise
