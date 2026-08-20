from collections.abc import Sequence

from openai import OpenAI
from pydantic import BaseModel, Field

from app.core.config import Settings, settings
from app.models.ai import EMBEDDING_DIMENSIONS


class AIProviderError(RuntimeError):
    """Raised when the configured AI provider cannot process a thought."""


class ExtractedThoughtMetadata(BaseModel):
    summary: str = Field(default="", description="A concise summary of the thought.")
    themes: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    books: list[str] = Field(default_factory=list)
    key_questions: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)


class OpenAIProvider:
    """OpenAI adapter kept behind a small interface for testing and replacement."""

    def __init__(self, app_settings: Settings = settings, client: OpenAI | None = None):
        if not app_settings.openai_api_key and client is None:
            raise AIProviderError("OpenAI is not configured")
        if app_settings.openai_embedding_dimensions != EMBEDDING_DIMENSIONS:
            raise AIProviderError("OpenAI embedding dimensions do not match the database schema")

        self.settings = app_settings
        self.client = client or OpenAI(
            api_key=app_settings.openai_api_key,
            timeout=app_settings.openai_timeout_seconds,
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.settings.openai_embedding_model,
            input=list(texts),
            dimensions=self.settings.openai_embedding_dimensions,
            encoding_format="float",
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def extract_metadata(self, thought_body: str) -> ExtractedThoughtMetadata:
        response = self.client.chat.completions.parse(
            model=self.settings.openai_metadata_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract useful, conservative metadata from a personal thought. "
                        "Do not invent people, places, books, emotions, or action items. "
                        "Return empty arrays when the thought does not support a value."
                    ),
                },
                {"role": "user", "content": thought_body},
            ],
            response_format=ExtractedThoughtMetadata,
            temperature=0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise AIProviderError("OpenAI returned no structured metadata")
        return parsed
