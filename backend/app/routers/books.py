"""书籍路由 —— 导入、列表、删除"""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, BackgroundTasks
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, async_session
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


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取单本书详情"""
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user.id)
        .options(selectinload(Book.progress))
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    pct = 0
    status_val = "not_started"
    if book.progress:
        pct = (book.progress.current_chapter / max(book.chapter_count or 1, 1)) * 100
        status_val = book.progress.status
    return BookResponse(
        id=book.id, title=book.title, author=book.author, category=book.category,
        cover_url=book.cover_url, file_format=book.file_format,
        file_size_bytes=book.file_size_bytes, token_count=book.token_count,
        chapter_count=book.chapter_count, parse_status=book.parse_status,
        created_at=book.created_at, progress_status=status_val,
        progress_percent=int(pct),
    )


@router.post("/upload", response_model=BookResponse, status_code=201)
async def upload_book(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传新书，立即返回，后台异步解析"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".epub", ".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="支持 ePub / PDF / TXT 格式")

    book_id = uuid.uuid4()
    book_dir = os.path.join(settings.book_storage_path, str(book_id))
    os.makedirs(book_dir, exist_ok=True)
    raw_path = os.path.join(book_dir, f"original{ext}")

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件不能超过 {settings.max_upload_size_mb}MB")
    with open(raw_path, "wb") as f:
        f.write(content)

    book = Book(
        id=book_id, user_id=user.id,
        title=title or os.path.splitext(file.filename or "未命名")[0],
        author=author or None,
        original_filename=file.filename or "",
        file_format=ext.lstrip("."),
        file_path=raw_path,
        file_size_bytes=len(content),
        parse_status="pending",
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    background.add_task(_parse_in_background, str(book_id), raw_path, file.filename or "", book.title)

    return BookResponse(
        id=book.id, title=book.title, author=book.author, category=book.category,
        cover_url=book.cover_url, file_format=book.file_format,
        file_size_bytes=book.file_size_bytes, token_count=book.token_count,
        chapter_count=book.chapter_count, parse_status=book.parse_status,
        created_at=book.created_at, progress_status="not_started", progress_percent=0,
    )


async def _parse_in_background(book_id: str, raw_path: str, filename: str, title: str):
    """后台解析文档 + 生成章节框架。CPU 密集部分在线程池运行，不阻塞事件循环。"""
    import json as _json
    import asyncio

    # Step 1: CPU-heavy parsing in thread pool
    async def _do_parse():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _parse_sync, raw_path, filename)

    try:
        result = await _do_parse()
    except Exception as e:
        async with async_session() as db:
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    parse_status="failed",
                    parse_error=f"文档解析失败: {str(e)[:400]}",
                )
            )
            await db.commit()
        return

    # Step 2: DB operations in main event loop
    async with async_session() as db:
        try:
            text_path = await save_parsed_text(result["text"], book_id)

            parse_error_val = None
            category = None
            try:
                from app.services.socratic_service import generate_chapter_structure
                ch1_text = result["text"][:10000]
                framework = await generate_chapter_structure(
                    book_title=title, chapter_index=1,
                    chapter_text=ch1_text, mode="quick", language="zh",
                )
                if isinstance(framework, dict) and "error" in framework:
                    raise ValueError(framework.get("error", "未返回有效 JSON"))
                category = _json.dumps(framework, ensure_ascii=False)
            except Exception as fe:
                parse_error_val = f"framework: {str(fe)[:200]}"

            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    text_path=text_path,
                    token_count=result["token_count"],
                    chapter_count=result["chapter_count"],
                    category=category,
                    parse_status="done",
                    parse_error=parse_error_val,
                )
            )
            await db.commit()
        except Exception as e:
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    parse_status="failed",
                    parse_error=str(e)[:500],
                )
            )
            await db.commit()


def _parse_sync(raw_path: str, filename: str) -> dict:
    """同步解析文档，在线程池中运行"""
    import asyncio
    return asyncio.run(parse_document(raw_path, filename))


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
