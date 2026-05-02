from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class WikiEntryCreate(BaseModel):
    concept_name: str
    ai_definition: str | None = None
    user_understanding: str | None = None
    tags: list[str] | None = None


class WikiEntryUpdate(BaseModel):
    concept_name: str | None = None
    user_understanding: str | None = None
    notes: str | None = None
    tags: list[str] | None = None


class WikiEntryResponse(BaseModel):
    id: UUID
    concept_name: str
    chapter_index: int | None
    ai_definition: str | None
    user_understanding: str | None
    notes: str | None
    tags: list | None
    source_quote: str | None
    book_id: UUID | None
    parent_concept_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
