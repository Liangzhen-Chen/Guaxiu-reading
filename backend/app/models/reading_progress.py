"""阅读进度表 —— 1:1 关联 Book"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
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
    mode: Mapped[str] = mapped_column(String(20), default="quick")  # quick / balanced / deep
    current_chapter: Mapped[int] = mapped_column(Integer, default=0)
    total_rounds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(20), default="not_started"
    )  # not_started / assessment / reading / paused / completed

    # 用户背景评估结果 (json)
    assessment_result: Mapped[dict | None] = mapped_column(
        String(2000), nullable=True
    )  # JSON string

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    book: Mapped["Book"] = relationship("Book", back_populates="progress")
