from enum import StrEnum


class SearchMode(StrEnum):
    """Retrieval strategy requested by the Recall client."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"
