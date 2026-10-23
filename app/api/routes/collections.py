from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas import CollectionCreate, CollectionRead, CollectionUpdate, ThoughtRead
from app.services.collections import (
    add_thought_to_collection,
    create_collection,
    delete_collection,
    get_collection,
    list_collection_thoughts,
    list_collections,
    remove_thought_from_collection,
    update_collection,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionRead])
def list_collections_route(
    db: DbSession,
    user: CurrentUser,
    recent: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    q: Annotated[str | None, Query(max_length=100)] = None,
):
    return list_collections(db, user, recent=recent, limit=limit, query=q)


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection_route(
    payload: CollectionCreate,
    db: DbSession,
    user: CurrentUser,
):
    return create_collection(db, user, payload)


@router.get("/{collection_id}/thoughts", response_model=list[ThoughtRead])
def list_collection_thoughts_route(
    collection_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    return list_collection_thoughts(db, user, collection_id)


@router.post("/{collection_id}/thoughts/{thought_id}", response_model=CollectionRead)
def add_thought_to_collection_route(
    collection_id: UUID,
    thought_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    return add_thought_to_collection(db, user, collection_id, thought_id)


@router.delete("/{collection_id}/thoughts/{thought_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_thought_from_collection_route(
    collection_id: UUID,
    thought_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    remove_thought_from_collection(db, user, collection_id, thought_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{collection_id}", response_model=CollectionRead)
def get_collection_route(
    collection_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    return get_collection(db, user, collection_id, mark_accessed=True)


@router.patch("/{collection_id}", response_model=CollectionRead)
def update_collection_route(
    collection_id: UUID,
    payload: CollectionUpdate,
    db: DbSession,
    user: CurrentUser,
):
    return update_collection(db, user, collection_id, payload)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection_route(
    collection_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    delete_collection(db, user, collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
