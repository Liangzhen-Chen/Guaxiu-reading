"""Wiki 知识库服务 —— 概念创建、关联、搜索"""
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload
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
    """分词搜索 Wiki 条目。

    支持中文分词：将查询按空格切分成多个词，各词分别在
    concept_name 和 ai_definition 中查找；同时使用 pg_trgm
    similarity() 做模糊匹配并按相关性降序排列。
    """
    if not query or not query.strip():
        return []

    terms = [t.strip() for t in query.split() if t.strip()]
    if not terms:
        return []

    # 对每个词在 concept_name 和 ai_definition 中做 ILIKE 匹配
    ilike_conditions = []
    for term in terms:
        ilike_conditions.append(WikiEntry.concept_name.ilike(f"%{term}%"))
        ilike_conditions.append(WikiEntry.ai_definition.ilike(f"%{term}%"))

    # 合并 trigram 模糊匹配（覆盖拼写/近似查询）
    result = await db.execute(
        select(WikiEntry)
        .options(selectinload(WikiEntry.book))
        .where(
            WikiEntry.user_id == user_id,
            or_(
                *ilike_conditions,
                func.similarity(WikiEntry.concept_name, query) > 0.2,
                func.similarity(WikiEntry.ai_definition, query) > 0.2,
            )
        )
        .order_by(
            func.greatest(
                func.coalesce(func.similarity(WikiEntry.concept_name, query), 0),
                func.coalesce(func.similarity(WikiEntry.ai_definition, query), 0),
            ).desc(),
            WikiEntry.updated_at.desc()
        )
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
