from typing import Literal
from pydantic import BaseModel, Field
from uuid import UUID


class ModeSelection(BaseModel):
    book_id: UUID
    mode: Literal["quick", "deep"] = Field(
        default="quick",
        description="阅读模式：quick=快速模式, deep=深度模式",
    )
    language: Literal["zh", "en"] = Field(
        default="zh",
        description="语言：zh=中文, en=英文",
    )


class AssessmentRequest(BaseModel):
    book_id: UUID
    message: str  # 用户对 AI 评估问题的回答


class AssessmentResponse(BaseModel):
    ai_message: str
    assessment_complete: bool = False
    next_action: str  # continue / enter_reading


class ReadingRequest(BaseModel):
    book_id: UUID
    message: str  # 用户对追问的回答


class ReadingResponse(BaseModel):
    ai_message: str          # AI 讲解或追问内容
    chapter_index: int
    round_index: int
    concepts_new: list[str]  # 本轮新提取的概念名
    chapter_complete: bool = False
    book_complete: bool = False


class ProgressResponse(BaseModel):
    book_id: UUID
    book_title: str
    mode: str
    current_chapter: int
    total_chapters: int | None
    total_rounds: int
    status: str
    progress_percent: int
    last_messages: list | None = None
    chapter_concepts: list | None = None
    # v4.0 wiki fields
    current_wiki_id: str | None = None
    completed_wikis: list | None = None
    wiki_checklist: list | None = None
    reading_material: str | None = None  # restored from last conversation
