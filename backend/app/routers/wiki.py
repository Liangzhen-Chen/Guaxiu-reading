"""Wiki 路由 —— 概念浏览、搜索、编辑"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.user import User
from app.models.wiki import WikiEntry
from app.models.book import Book
from app.schemas.wiki import WikiEntryResponse, WikiEntryCreate, WikiEntryUpdate
from app.middleware.auth import get_current_user
from app.services.wiki_service import create_entry, search_entries, get_entries_by_book

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


@router.post("/batch", status_code=201)
async def batch_create(data: list[dict], db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """批量导入 Wiki 条目（章节结束后用户选择导入）"""
    count = 0
    for item in data:
        db.add(WikiEntry(
            user_id=user.id, book_id=item.get("book_id"),
            concept_name=item.get("concept_name") or item.get("name"),
            entry_type=item.get("entry_type", "concept"),
            entry_subtype=item.get("entry_subtype") or item.get("type", "concept"),
            chapter_index=item.get("chapter_index"),
            ai_definition=item.get("ai_definition") or item.get("content", ""),
            evidence=item.get("evidence"),
            source_quote=item.get("source_quote"),
            source_quotes=item.get("source_quotes") or item.get("quotes"),
            tags=item.get("tags", []),
        ))
        count += 1
    await db.commit()
    return {"imported": count}


@router.get("", response_model=list[WikiEntryResponse])
async def list_entries(
    book_id: uuid.UUID | None = None,
    search: str | None = None,
    limit: int = Query(default=50, le=10000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if search:
        entries = await search_entries(db, str(user.id), search, limit)
    elif book_id:
        entries = await get_entries_by_book(db, str(user.id), str(book_id))
    else:
        result = await db.execute(
            select(WikiEntry)
            .options(selectinload(WikiEntry.book))
            .where(WikiEntry.user_id == user.id)
            .order_by(WikiEntry.updated_at.desc())
            .limit(limit)
        )
        entries = list(result.scalars().all())

    # Resolve book titles
    book_ids = list({e.book_id for e in entries if e.book_id})
    titles = {}
    if book_ids:
        r = await db.execute(select(Book.id, Book.title).where(Book.id.in_(book_ids)))
        for bid, btitle in r.all():
            titles[str(bid)] = btitle

    resp = []
    for e in entries:
        d = WikiEntryResponse.model_validate(e).model_dump()
        d["book_title"] = titles.get(str(e.book_id)) if e.book_id else None
        resp.append(WikiEntryResponse(**d))
    return resp


@router.post("", response_model=WikiEntryResponse, status_code=201)
async def add_entry(
    data: WikiEntryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = await create_entry(
        db, str(user.id), book_id=None, concept_name=data.concept_name,
        ai_definition=data.ai_definition, tags=data.tags,
    )
    return WikiEntryResponse.model_validate(entry)


@router.put("/{entry_id}", response_model=WikiEntryResponse)
async def update_entry(
    entry_id: uuid.UUID,
    data: WikiEntryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WikiEntry).where(WikiEntry.id == entry_id, WikiEntry.user_id == user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="条目不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(entry, key, val)
    await db.commit()
    await db.refresh(entry)
    return WikiEntryResponse.model_validate(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WikiEntry).where(WikiEntry.id == entry_id, WikiEntry.user_id == user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="条目不存在")
    await db.delete(entry)
    await db.commit()
