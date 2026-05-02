from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class ConversationMessage(BaseModel):
    id: UUID
    role: str
    content: str
    chapter_index: int
    round_index: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    book_id: UUID
    messages: list[ConversationMessage]
    total_rounds: int
