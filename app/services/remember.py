from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Thought, ThoughtMetadata, User
from app.schemas.remember import (
    RememberCategory,
    RememberItem,
    RememberOverview,
)

CATEGORY_FIELDS = (
    ("themes", "Themes"),
    ("emotions", "Emotions"),
    ("people", "People"),
    ("books", "Books"),
)


def _rank_items(records: list[ThoughtMetadata], field: str) -> list[RememberItem]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}

    for record in records:
        values = getattr(record, field)
        for value in {item.strip() for item in values if item.strip()}:
            normalized = value.casefold()
            counts[normalized] += 1
            labels.setdefault(normalized, value)

    ranked = sorted(counts.items(), key=lambda item: (-item[1], labels[item[0]].casefold()))
    return [RememberItem(label=labels[key], count=count) for key, count in ranked[:6]]


def get_remember_overview(db: Session, user: User) -> RememberOverview:
    records = list(
        db.scalars(
            select(ThoughtMetadata)
            .join(Thought, Thought.id == ThoughtMetadata.thought_id)
            .where(
                ThoughtMetadata.user_id == user.id,
                Thought.deleted_at.is_(None),
            )
        ).all()
    )

    return RememberOverview(
        thoughts_analyzed=len(records),
        categories=[
            RememberCategory(
                key=field,
                label=label,
                items=_rank_items(records, field),
            )
            for field, label in CATEGORY_FIELDS
        ],
    )
