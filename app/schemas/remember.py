from typing import Literal

from pydantic import BaseModel


class RememberItem(BaseModel):
    label: str
    count: int


class RememberCategory(BaseModel):
    key: Literal["tags", "books"]
    label: str
    items: list[RememberItem]


class RememberOverview(BaseModel):
    thoughts_analyzed: int
    categories: list[RememberCategory]
