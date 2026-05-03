"""书籍路由 —— 导入、列表、删除"""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.models.book import Book
from app.models.reading_progress import ReadingProgress
from app.schemas.book import BookResponse, BookListResponse
from app.middleware.auth import get_current_user
from app.services.parser_service import parse_document, save_parsed_text
from app.config import settings

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("", response_model=BookListResponse)
async def list_books(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取用户书架"""
    result = await db.execute(
        select(Book).where(Book.user_id == user.id).order_by(Book.created_at.desc())
        .options(selectinload(Book.progress))
    )
    books = result.scalars().all()
    items = []
    for b in books:
        pct = 0
        status_val = "not_started"
        if b.progress:
            pct = (b.progress.current_chapter / max(b.chapter_count or 1, 1)) * 100
            status_val = b.progress.status
        items.append(BookResponse(
            id=b.id, title=b.title, author=b.author, category=b.category,
            cover_url=b.cover_url, file_format=b.file_format,
            file_size_bytes=b.file_size_bytes, token_count=b.token_count,
            chapter_count=b.chapter_count, parse_status=b.parse_status,
            created_at=b.created_at, progress_status=status_val,
            progress_percent=int(pct),
        ))
    return BookListResponse(items=items, total=len(items))


@router.post("/upload", response_model=BookResponse, status_code=201)
async def upload_book(
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传新书并解析"""
    # 校验格式
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".epub", ".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="支持 ePub / PDF / TXT 格式")

    book_id = uuid.uuid4()

    # 保存原始文件
    book_dir = os.path.join(settings.book_storage_path, str(book_id))
    os.makedirs(book_dir, exist_ok=True)
    raw_path = os.path.join(book_dir, f"original{ext}")
    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件不能超过 {settings.max_upload_size_mb}MB")
    with open(raw_path, "wb") as f:
        f.write(content)

    # 先创建记录（解析中），后台异步解析
    book = Book(
        id=book_id, user_id=user.id,
        title=title or os.path.splitext(file.filename or "未命名")[0],
        author=author or None,
        original_filename=file.filename or "",
        file_format=ext.lstrip("."),
        file_path=raw_path,
        file_size_bytes=len(content),
        parse_status="parsing",
    )
    db.add(book)
    await db.commit()

    # 后台解析（不阻塞响应）
    import asyncio
    asyncio.create_task(_parse_background(book_id, raw_path, file.filename or ""))
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return BookResponse(
        id=book.id, title=book.title, author=book.author, category=book.category,
        cover_url=book.cover_url, file_format=book.file_format,
        file_size_bytes=book.file_size_bytes, token_count=book.token_count,
        chapter_count=book.chapter_count, parse_status=book.parse_status,
        created_at=book.created_at, progress_status="not_started", progress_percent=0,
    )


@router.delete("/{book_id}", status_code=204)
async def delete_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user.id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    # 删除文件
    import shutil
    book_dir = os.path.join(settings.book_storage_path, str(book_id))
    if os.path.exists(book_dir):
        shutil.rmtree(book_dir)
    await db.delete(book)
    await db.commit()
