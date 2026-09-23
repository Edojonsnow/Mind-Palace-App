from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Thought, User
from app.schemas.remember import (
    RememberCategory,
    RememberItem,
    RememberOverview,
)

CATEGORY_LABELS = (("tags", "Tags"), ("books", "Books"))


def _rank_items(thoughts: list[Thought], field: str) -> list[RememberItem]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}

    for thought in thoughts:
        values = thought.manual_tags if field == "tags" else [thought.book_title or ""]
        for value in {item.strip() for item in values if item.strip()}:
            normalized = value.casefold()
            counts[normalized] += 1
            labels.setdefault(normalized, value)

    ranked = sorted(counts.items(), key=lambda item: (-item[1], labels[item[0]].casefold()))
    return [RememberItem(label=labels[key], count=count) for key, count in ranked[:6]]


def get_remember_overview(db: Session, user: User) -> RememberOverview:
    thoughts = list(
        db.scalars(
            select(Thought)
            .where(Thought.user_id == user.id, Thought.deleted_at.is_(None))
        ).all()
    )

    return RememberOverview(
        thoughts_analyzed=len(thoughts),
        categories=[
            RememberCategory(
                key=field,
                label=label,
                items=_rank_items(thoughts, field),
            )
            for field, label in CATEGORY_LABELS
        ],
    )
