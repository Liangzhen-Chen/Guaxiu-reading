"""阅读进度表 —— 1:1 关联 Book"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )
    mode: Mapped[str] = mapped_column(String(20), default="quick")  # quick / deep
    language: Mapped[str] = mapped_column(String(10), default="zh")  # zh / en

    # P5-7: current_chapter default 0 -> 1
    current_chapter: Mapped[int] = mapped_column(Integer, default=1)
    total_rounds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(20), default="not_started"
    )  # not_started / assessment / reading / paused / completed

    # P5-4: assessment_result String(2000) -> JSONB (previously JSON string)
    assessment_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # v4.0: Wiki-based reading
    current_wiki_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    completed_wikis: Mapped[list | None] = mapped_column(JSONB, default=list)

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    book: Mapped["Book"] = relationship("Book", back_populates="progress")
