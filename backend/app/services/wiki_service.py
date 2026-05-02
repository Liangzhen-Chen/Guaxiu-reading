"""Wiki 知识库服务 —— 概念创建、关联、搜索"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.wiki import WikiEntry


async def create_entry(
    db: AsyncSession, user_id: str, book_id: str, concept_name: str,
    chapter_index: int | None = None, ai_definition: str | None = None,
    source_quote: str | None = None, tags: list[str] | None = None
) -> WikiEntry:
    """创建 Wiki 条目，自动检测同名概念是否已存在"""
    # 检查是否已有同名概念（跨书）
    existing = await db.execute(
        select(WikiEntry).where(
            WikiEntry.user_id == user_id,
            WikiEntry.concept_name == concept_name
        )
    )
    existing_entry = existing.scalar_one_or_none()

    entry = WikiEntry(
        user_id=user_id,
        book_id=book_id,
        concept_name=concept_name,
        chapter_index=chapter_index,
        ai_definition=ai_definition,
        source_quote=source_quote,
        tags=tags,
    )
    if existing_entry:
        entry.parent_concept_id = existing_entry.id  # 关联到已有概念

    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def search_entries(
    db: AsyncSession, user_id: str, query: str, limit: int = 20
) -> list[WikiEntry]:
    """全文搜索 Wiki 条目"""
    result = await db.execute(
        select(WikiEntry)
        .where(
            WikiEntry.user_id == user_id,
            WikiEntry.concept_name.ilike(f"%{query}%")
        )
        .order_by(WikiEntry.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_entries_by_book(
    db: AsyncSession, user_id: str, book_id: str
) -> list[WikiEntry]:
    """获取某本书产生的所有 Wiki 条目"""
    result = await db.execute(
        select(WikiEntry)
        .where(WikiEntry.user_id == user_id, WikiEntry.book_id == book_id)
        .order_by(WikiEntry.chapter_index)
    )
    return list(result.scalars().all())
