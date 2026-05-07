"""对话记录表 —— 每轮苏格拉底追问存一条。jsonb 灵活存储追问链路。"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # 角色：assistant(苏格拉底追问) / user(用户回答) / system(系统消息)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 追问元数据 (jsonb)
    # 结构: {"depth": 2, "chain": ["事实确认", "概念理解"], "concepts": ["系统1"], "is_correct": null}
    metadata_: Mapped[dict | None] = mapped_column("metadata_jsonb", JSONB, nullable=True)

    # 上下文快照
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compressed_from: Mapped[str | None] = mapped_column(Text, nullable=True)  # 如果被压缩，存摘要

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    book: Mapped["Book"] = relationship("Book", back_populates="conversations")


# P5-9: Composite index for efficient book+chapter+round queries
Index(
    "ix_conv_book_chapter_round",
    Conversation.book_id,
    Conversation.chapter_index,
    Conversation.round_index,
)
