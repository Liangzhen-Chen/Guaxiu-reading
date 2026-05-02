"""Wiki 条目表 —— 导读后自动沉淀的概念知识"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class WikiEntry(Base):
    __tablename__ = "wiki_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="SET NULL"), nullable=True
    )

    concept_name: Mapped[str] = mapped_column(String(300), nullable=False)
    chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 类型：concept（概念） 或 viewpoint（观点）
    entry_type: Mapped[str] = mapped_column(String(20), default="concept", nullable=False)

    # 内容
    ai_definition: Mapped[str] = mapped_column(Text, nullable=True)
    user_understanding: Mapped[str] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    # 证据/论据/例子/数据（JSONB）
    # [{"type": "实验", "content": "Stroop效应——..."}, {"type": "案例", "content": "球拍和球..."}]
    evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # 标签 + 来源引用
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 知识图谱 —— 自引用，支持跨书概念关联
    parent_concept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_entries.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
