from pydantic import BaseModel


class RememberItem(BaseModel):
    label: str
    count: int


class RememberCategory(BaseModel):
    key: str
    label: str
    items: list[RememberItem]


class RememberOverview(BaseModel):
    thoughts_analyzed: int
    categories: list[RememberCategory]
