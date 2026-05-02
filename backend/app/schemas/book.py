from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class BookCreate(BaseModel):
    title: str | None = None
    author: str | None = None


class BookResponse(BaseModel):
    id: UUID
    title: str
    author: str | None
    category: str | None
    cover_url: str | None
    file_format: str
    file_size_bytes: int | None
    token_count: int | None
    chapter_count: int | None
    parse_status: str
    created_at: datetime
    # 阅读进度
    progress_status: str | None = None
    progress_percent: int = 0

    model_config = {"from_attributes": True}


class BookListResponse(BaseModel):
    items: list[BookResponse]
    total: int
