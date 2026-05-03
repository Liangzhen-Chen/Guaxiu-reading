"""书籍表 —— 元数据 + 文件路径。正文存文件系统，不存数据库。"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(300), nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # 文件信息
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)  # epub / pdf / txt
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)  # 原始文件路径
    text_path: Mapped[str] = mapped_column(String(1000), nullable=True)   # 解析后 Markdown 路径
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 元数据来源
    metadata_source: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # embedded / google_api / open_library / manual

    # 统计
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chapter_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 状态
    parse_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending / parsing / done / failed
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship("User", back_populates="books")
    progress: Mapped["ReadingProgress | None"] = relationship(
        "ReadingProgress", back_populates="book", uselist=False
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="book"
    )
